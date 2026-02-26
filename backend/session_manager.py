"""
PTY-based Claude Code session manager.

Each session spawns `claude` in a pseudo-terminal so:
  - xterm.js on the frontend receives raw ANSI output (full fidelity)
  - We simultaneously parse stripped text to detect tool-approval prompts
  - stdin relay lets mobile users type or approve/reject via the modal
"""
from __future__ import annotations

import asyncio
import fcntl
import os
import re
import select
import struct
import termios
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from .config import config

# ---------------------------------------------------------------------------
# ANSI strip helper
# ---------------------------------------------------------------------------
_ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Tool-approval prompt detection
# ---------------------------------------------------------------------------
# Claude Code (v1.x) uses inquirer-style prompts.  The canonical markers are:
#   ›  (U+203A) followed by option text, preceded by a question line.
# We also catch simple y/N prompts emitted in --print mode.
_APPROVAL_PATTERNS = [
    re.compile(r"Allow\s+(?:this\s+)?(?:bash\s+)?(?:command|action|tool)", re.I),
    re.compile(r"\?\s+.*\[y(?:es)?/[nN]", re.I),
    re.compile(r"Do you want to\s+(?:allow|proceed|run)", re.I),
    re.compile(r"›\s+Yes\s*\n", re.M),          # inquirer list prompt
    re.compile(r"❯\s+Yes\s*\n", re.M),          # alternate marker
]

_TOOL_NAME_RE = re.compile(
    r"(?:Tool(?:\s+use)?|bash|write_file|read_file|str_replace_editor|computer)[\s:]+([^\n\r]+)",
    re.I,
)
_COMMAND_RE = re.compile(r"(?:command|cmd|input)[\s:]+([^\n\r]+)", re.I)


def _detect_approval(plain: str) -> bool:
    return any(p.search(plain) for p in _APPROVAL_PATTERNS)


def _extract_tool_info(plain: str) -> tuple[str, str]:
    """Best-effort extraction of tool name and command/input."""
    tool_name = "bash"
    m = _TOOL_NAME_RE.search(plain)
    if m:
        tool_name = m.group(1).strip()[:80]

    tool_input = ""
    m2 = _COMMAND_RE.search(plain)
    if m2:
        tool_input = m2.group(1).strip()[:500]

    return tool_name, tool_input


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class ToolApprovalRequest:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = "unknown"
    tool_input: str = ""
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------
class Session:
    def __init__(self, session_id: str, working_dir: str):
        self.id = session_id
        self.working_dir = working_dir
        self.pid: Optional[int] = None
        self._master_fd: Optional[int] = None
        self.started_at = time.time()
        self.ended = False
        self.exit_code: Optional[int] = None

        # Websocket clients currently watching this session
        self._clients: list[WebSocket] = []
        self._clients_lock = asyncio.Lock()

        # Rolling output buffer for replay on reconnect (~500 KB)
        self._output_buf = bytearray()
        self._buf_lock = threading.Lock()

        # Approval state
        self.pending_approval: Optional[ToolApprovalRequest] = None
        self._approval_event: Optional[asyncio.Event] = None
        self._approval_approved: Optional[bool] = None
        self._approval_lock = asyncio.Lock()

        # Plain-text accumulator for pattern detection (reset after match)
        self._plain_accum = ""
        self._detecting = True   # False once a match fires; reset after response

        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, initial_prompt: Optional[str] = None, cols: int = 220, rows: int = 50):
        self._loop = asyncio.get_event_loop()
        self._approval_event = asyncio.Event()

        master_fd, slave_fd = os.openpty()
        self._master_fd = master_fd

        # Set terminal size
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

        env = os.environ.copy()
        env.update(
            TERM="xterm-256color",
            COLUMNS=str(cols),
            LINES=str(rows),
            COLORTERM="truecolor",
            # Ensure claude uses color
            FORCE_COLOR="1",
            NO_COLOR="",
        )

        cmd = [config.CLAUDE_BINARY]
        if initial_prompt:
            cmd += ["--print", initial_prompt]

        import subprocess

        proc = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self.working_dir,
            env=env,
            close_fds=True,
            start_new_session=True,
        )
        os.close(slave_fd)
        self.pid = proc.pid

        # Background reader thread
        t = threading.Thread(target=self._reader, args=(proc,), daemon=True)
        t.start()

    def _reader(self, proc):
        """Read PTY output, buffer it, broadcast to websocket clients."""
        try:
            while True:
                try:
                    ready, _, _ = select.select([self._master_fd], [], [], 0.1)
                except (ValueError, OSError):
                    break
                if ready:
                    try:
                        data = os.read(self._master_fd, 8192)
                    except OSError:
                        break
                    if not data:
                        break
                    self._handle_output(data)
        finally:
            proc.wait()
            self.exit_code = proc.returncode
            self.ended = True
            if self._master_fd is not None:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = None
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast({"type": "session_ended", "exitCode": self.exit_code}),
                    self._loop,
                )

    def _handle_output(self, data: bytes):
        text = data.decode("utf-8", errors="replace")

        # Buffer management
        with self._buf_lock:
            self._output_buf.extend(data)
            if len(self._output_buf) > config.OUTPUT_BUFFER_MAX:
                # Drop oldest half
                self._output_buf = self._output_buf[len(self._output_buf) // 2 :]

        # Broadcast raw data (xterm.js handles ANSI)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast({"type": "output", "data": text}),
                self._loop,
            )

        # Approval detection
        if self._detecting:
            self._plain_accum += strip_ansi(text)
            # Keep accumulator bounded
            if len(self._plain_accum) > 4000:
                self._plain_accum = self._plain_accum[-4000:]

            if _detect_approval(self._plain_accum):
                tool_name, tool_input = _extract_tool_info(self._plain_accum)
                req = ToolApprovalRequest(tool_name=tool_name, tool_input=tool_input)
                self.pending_approval = req
                self._detecting = False   # stop re-triggering
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self._broadcast(
                            {
                                "type": "tool_approval_request",
                                "requestId": req.id,
                                "toolName": req.tool_name,
                                "toolInput": req.tool_input,
                            }
                        ),
                        self._loop,
                    )

    # ------------------------------------------------------------------
    # Writing to the PTY (stdin relay)
    # ------------------------------------------------------------------
    def write_stdin(self, data: bytes):
        if self._master_fd is None or self.ended:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    def resize(self, cols: int, rows: int):
        if self._master_fd is None:
            return
        try:
            fcntl.ioctl(
                self._master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", rows, cols, 0, 0),
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Approval handling
    # ------------------------------------------------------------------
    async def respond_approval(self, approved: bool, reason: str = ""):
        if self.pending_approval is None:
            return
        self._approval_approved = approved
        self.pending_approval = None
        self._plain_accum = ""
        self._detecting = True   # re-arm for next prompt

        if approved:
            self.write_stdin(b"y\n")
        else:
            # Send 'n' + newline; for inquirer prompts send down-arrow first
            self.write_stdin(b"\x1b[B")   # arrow down (selects "No")
            await asyncio.sleep(0.05)
            self.write_stdin(b"\n")

        await self._broadcast(
            {"type": "tool_approval_response", "approved": approved}
        )

    # ------------------------------------------------------------------
    # WebSocket client management
    # ------------------------------------------------------------------
    async def attach(self, ws: WebSocket):
        async with self._clients_lock:
            self._clients.append(ws)

        # Replay buffered output
        with self._buf_lock:
            snapshot = bytes(self._output_buf)
        if snapshot:
            try:
                await ws.send_json(
                    {"type": "output", "data": snapshot.decode("utf-8", errors="replace")}
                )
            except Exception:
                pass

        # If there's a pending approval, re-send it
        if self.pending_approval:
            try:
                await ws.send_json(
                    {
                        "type": "tool_approval_request",
                        "requestId": self.pending_approval.id,
                        "toolName": self.pending_approval.tool_name,
                        "toolInput": self.pending_approval.tool_input,
                    }
                )
            except Exception:
                pass

        if self.ended:
            try:
                await ws.send_json(
                    {"type": "session_ended", "exitCode": self.exit_code}
                )
            except Exception:
                pass

    async def detach(self, ws: WebSocket):
        async with self._clients_lock:
            self._clients = [c for c in self._clients if c is not ws]

    async def _broadcast(self, message: dict):
        async with self._clients_lock:
            dead = []
            for ws in self._clients:
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_json(message)
                    else:
                        dead.append(ws)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.remove(ws)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workingDir": self.working_dir,
            "pid": self.pid,
            "startedAt": self.started_at,
            "ended": self.ended,
            "exitCode": self.exit_code,
            "clientCount": len(self._clients),
            "hasPendingApproval": self.pending_approval is not None,
        }


# ---------------------------------------------------------------------------
# Session manager (singleton)
# ---------------------------------------------------------------------------
class SessionManager:
    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        working_dir: str,
        initial_prompt: Optional[str] = None,
        cols: int = 220,
        rows: int = 50,
    ) -> Session:
        async with self._lock:
            if len(self._sessions) >= config.MAX_SESSIONS:
                raise RuntimeError(
                    f"Maximum concurrent sessions ({config.MAX_SESSIONS}) reached"
                )
            session_id = str(uuid.uuid4())
            session = Session(session_id, working_dir)
            self._sessions[session_id] = session

        session.start(initial_prompt, cols=cols, rows=rows)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        return [s.to_dict() for s in self._sessions.values()]

    async def kill_session(self, session_id: str):
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session and session.pid:
            try:
                import signal
                os.killpg(os.getpgid(session.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

    async def cleanup_dead_sessions(self):
        """Remove sessions that have ended and have no clients (call periodically)."""
        async with self._lock:
            dead = [
                sid
                for sid, s in self._sessions.items()
                if s.ended and len(s._clients) == 0
            ]
            for sid in dead:
                self._sessions.pop(sid, None)
