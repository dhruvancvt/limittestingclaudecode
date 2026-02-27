"""
Claude Code Mobile – FastAPI backend
=====================================
Endpoints
---------
POST /auth/token          Exchange AUTH_SECRET for a JWT
GET  /sessions            List active sessions
POST /sessions            Create a new session
DELETE /sessions/{id}     Kill a session
GET  /sessions/{id}       Session detail
WS   /ws/{id}?token=...   Attach to a session (real-time I/O)

WebSocket message protocol
--------------------------
Client → Server
  { "type": "input",         "data": "<string>" }       # raw stdin
  { "type": "approve_tool",  "requestId": "..." }        # approve pending tool call
  { "type": "reject_tool",   "requestId": "...", "reason?": "..." }
  { "type": "resize",        "cols": N, "rows": N }      # terminal resize
  { "type": "ping" }

Server → Client
  { "type": "output",                "data": "<string>" }      # raw ANSI output
  { "type": "tool_approval_request", "requestId", "toolName", "toolInput" }
  { "type": "tool_approval_response","approved": bool }
  { "type": "session_started",       "sessionId", "pid" }
  { "type": "session_ended",         "exitCode": int|null }
  { "type": "error",                 "message": "..." }
  { "type": "pong" }
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .auth import create_token, require_auth, ws_auth
from .config import config
from .session_manager import SessionManager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("claude-mobile")

session_manager = SessionManager()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Periodic cleanup task
    async def _cleanup():
        while True:
            await asyncio.sleep(300)
            await session_manager.cleanup_dead_sessions()

    task = asyncio.create_task(_cleanup())
    yield
    task.cancel()


app = FastAPI(title="Claude Code Mobile", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class TokenRequest(BaseModel):
    secret: str


class CreateSessionRequest(BaseModel):
    workingDir: str = config.DEFAULT_WORKING_DIR
    initialPrompt: Optional[str] = None
    cols: int = 220
    rows: int = 50


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post("/auth/token")
async def get_token(req: TokenRequest):
    if not config.AUTH_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AUTH_SECRET not configured on server",
        )
    if req.secret != config.AUTH_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid secret",
        )
    return {"token": create_token(), "expiresIn": config.JWT_EXPIRE_HOURS * 3600}


# ---------------------------------------------------------------------------
# Sessions REST
# ---------------------------------------------------------------------------
@app.get("/sessions")
async def list_sessions(_auth=Depends(require_auth)):
    return session_manager.list_sessions()


@app.get("/sessions/{session_id}")
async def get_session(session_id: str, _auth=Depends(require_auth)):
    s = session_manager.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s.to_dict()


@app.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(req: CreateSessionRequest, _auth=Depends(require_auth)):
    # Validate working dir exists
    if not Path(req.workingDir).is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Working directory does not exist: {req.workingDir}",
        )
    try:
        session = await session_manager.create_session(
            req.workingDir,
            req.initialPrompt,
            cols=req.cols,
            rows=req.rows,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    log.info("Session created: %s in %s (pid %s)", session.id, req.workingDir, session.pid)
    return {"sessionId": session.id, "pid": session.pid}


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, _auth=Depends(require_auth)):
    s = session_manager.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_manager.kill_session(session_id)
    log.info("Session killed: %s", session_id)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/ws/{session_id}")
async def ws_endpoint(
    websocket: WebSocket,
    session_id: str,
    _auth: dict = Depends(ws_auth),
):
    session = session_manager.get_session(session_id)
    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return

    await websocket.accept()
    await session.attach(websocket)
    log.info("WS client attached to session %s", session_id)

    # Notify client of current session state
    await websocket.send_json(
        {
            "type": "session_started",
            "sessionId": session.id,
            "pid": session.pid,
            "workingDir": session.working_dir,
        }
    )

    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive ping
                await websocket.send_json({"type": "ping"})
                continue

            mtype = msg.get("type")

            if mtype == "input":
                data = msg.get("data", "")
                if isinstance(data, str):
                    session.write_stdin(data.encode("utf-8", errors="replace"))

            elif mtype == "approve_tool":
                req_id = msg.get("requestId", "")
                if session.pending_approval and session.pending_approval.id == req_id:
                    await session.respond_approval(True)
                else:
                    log.warning("approve_tool: no matching pending request %s", req_id)

            elif mtype == "reject_tool":
                req_id = msg.get("requestId", "")
                if session.pending_approval and session.pending_approval.id == req_id:
                    await session.respond_approval(False, msg.get("reason", ""))
                else:
                    log.warning("reject_tool: no matching pending request %s", req_id)

            elif mtype == "resize":
                cols = int(msg.get("cols", 220))
                rows = int(msg.get("rows", 50))
                session.resize(cols, rows)

            elif mtype == "pong":
                pass  # keepalive response

            else:
                log.debug("Unknown WS message type: %s", mtype)

    except WebSocketDisconnect:
        log.info("WS client disconnected from session %s", session_id)
    except Exception as e:
        log.exception("WS error for session %s: %s", session_id, e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        await session.detach(websocket)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "sessions": len(session_manager._sessions),
        "maxSessions": config.MAX_SESSIONS,
    }
