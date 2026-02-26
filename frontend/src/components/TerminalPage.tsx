import { useCallback, useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { WebLinksAddon } from '@xterm/addon-web-links'
import '@xterm/xterm/css/xterm.css'
import { useAppStore } from '../store/appStore'
import { useWebSocket } from '../hooks/useWebSocket'
import type { ServerMessage } from '../types'
import ApprovalModal from './ApprovalModal'
import DiffViewer from './DiffViewer'

// Unified diff detection – look for a block starting with "diff --git" or "--- a/"
const DIFF_RE = /(?:diff --git|^--- a\/)/m

// Accumulate output to detect diffs
function extractDiff(text: string): string | null {
  const idx = text.search(DIFF_RE)
  if (idx === -1) return null
  return text.slice(idx)
}

export default function TerminalPage() {
  const { activeSessionId, pendingApproval, setPendingApproval, setRoute, wsStatus } =
    useAppStore()

  const termRef = useRef<HTMLDivElement>(null)
  const xtermRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const outputAccRef = useRef('')   // rolling accumulator for diff detection

  const [diff, setDiff] = useState<string | null>(null)
  const [sessionEnded, setSessionEnded] = useState(false)
  const [exitCode, setExitCode] = useState<number | null>(null)

  // -----------------------------------------------------------------------
  // xterm setup
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!termRef.current) return

    const term = new Terminal({
      theme: {
        background: '#0f0f0f',
        foreground: '#e0e0e0',
        cursor: '#a78bfa',
        cursorAccent: '#0f0f0f',
        selectionBackground: '#7c3aed44',
        black: '#1e1e2e',
        red: '#f38ba8',
        green: '#a6e3a1',
        yellow: '#f9e2af',
        blue: '#89b4fa',
        magenta: '#cba6f7',
        cyan: '#89dceb',
        white: '#cdd6f4',
      },
      fontFamily: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
      fontSize: 13,
      lineHeight: 1.3,
      cursorBlink: true,
      scrollback: 5000,
      allowProposedApi: true,
    })

    const fit = new FitAddon()
    const links = new WebLinksAddon()
    term.loadAddon(fit)
    term.loadAddon(links)
    term.open(termRef.current)
    fit.fit()

    xtermRef.current = term
    fitRef.current = fit

    const ro = new ResizeObserver(() => fit.fit())
    ro.observe(termRef.current)

    return () => {
      ro.disconnect()
      term.dispose()
      xtermRef.current = null
      fitRef.current = null
    }
  }, [])

  // -----------------------------------------------------------------------
  // WebSocket message handler
  // -----------------------------------------------------------------------
  const handleMessage = useCallback(
    (msg: ServerMessage) => {
      switch (msg.type) {
        case 'output': {
          xtermRef.current?.write(msg.data)
          // Accumulate for diff detection (keep last 20 KB)
          outputAccRef.current += msg.data
          if (outputAccRef.current.length > 20_000) {
            outputAccRef.current = outputAccRef.current.slice(-20_000)
          }
          const found = extractDiff(outputAccRef.current)
          if (found && found.length > 100) {
            setDiff(found)
            outputAccRef.current = ''
          }
          break
        }
        case 'tool_approval_request':
          setPendingApproval({
            requestId: msg.requestId,
            toolName: msg.toolName,
            toolInput: msg.toolInput,
          })
          break
        case 'tool_approval_response':
          setPendingApproval(null)
          break
        case 'session_ended':
          setSessionEnded(true)
          setExitCode(msg.exitCode)
          break
        default:
          break
      }
    },
    [setPendingApproval],
  )

  const { send, reconnect } = useWebSocket({
    sessionId: activeSessionId,
    onMessage: handleMessage,
    enabled: !!activeSessionId,
  })

  // -----------------------------------------------------------------------
  // xterm → stdin relay
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!xtermRef.current) return
    const term = xtermRef.current
    const dispose = term.onData((data) => {
      send({ type: 'input', data })
    })
    return () => dispose.dispose()
  }, [send])

  // -----------------------------------------------------------------------
  // Terminal resize → server
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (!xtermRef.current || !fitRef.current) return
    const term = xtermRef.current
    const dispose = term.onResize(({ cols, rows }) => {
      send({ type: 'resize', cols, rows })
    })
    return () => dispose.dispose()
  }, [send])

  // -----------------------------------------------------------------------
  // Approval handlers
  // -----------------------------------------------------------------------
  const handleApprove = () => {
    if (!pendingApproval) return
    send({ type: 'approve_tool', requestId: pendingApproval.requestId })
    setPendingApproval(null)
  }

  const handleReject = () => {
    if (!pendingApproval) return
    send({ type: 'reject_tool', requestId: pendingApproval.requestId })
    setPendingApproval(null)
  }

  const statusColor =
    wsStatus === 'connected' ? '#a6e3a1' : wsStatus === 'error' ? '#f38ba8' : '#f9e2af'

  return (
    <div className="terminal-page">
      <div className="terminal-topbar">
        <button className="btn-back" onClick={() => setRoute('sessions')}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        <span className="terminal-session-id" title={activeSessionId ?? ''}>
          {activeSessionId?.slice(0, 8) ?? '—'}
        </span>

        <div className="terminal-status">
          <span className="status-led" style={{ backgroundColor: statusColor }} />
          <span className="status-text">
            {wsStatus === 'connected' && !sessionEnded && 'Live'}
            {wsStatus === 'connected' && sessionEnded && `Exited (${exitCode ?? '?'})`}
            {wsStatus === 'connecting' && 'Connecting…'}
            {wsStatus === 'error' && 'Reconnecting…'}
            {wsStatus === 'disconnected' && 'Disconnected'}
          </span>
        </div>

        <div className="terminal-toolbar">
          {(wsStatus === 'error' || wsStatus === 'disconnected') && (
            <button className="btn-icon" onClick={reconnect} title="Reconnect">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M23 4v6h-6M1 20v-6h6" />
                <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
              </svg>
            </button>
          )}
          {diff && (
            <button className="btn-icon btn-diff" onClick={() => setDiff(diff)} title="View diff">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className="terminal-container" ref={termRef} />

      {sessionEnded && (
        <div className="session-ended-banner">
          Session ended with exit code {exitCode ?? '?'}
        </div>
      )}

      {pendingApproval && (
        <ApprovalModal
          approval={pendingApproval}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}

      {diff && (
        <DiffViewer diff={diff} onClose={() => setDiff(null)} />
      )}
    </div>
  )
}
