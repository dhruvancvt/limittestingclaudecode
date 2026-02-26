// ---------------------------------------------------------------------------
// WebSocket message types
// ---------------------------------------------------------------------------

export type ServerMessage =
  | { type: 'output'; data: string }
  | {
      type: 'tool_approval_request'
      requestId: string
      toolName: string
      toolInput: string
    }
  | { type: 'tool_approval_response'; approved: boolean }
  | { type: 'session_started'; sessionId: string; pid: number; workingDir: string }
  | { type: 'session_ended'; exitCode: number | null }
  | { type: 'error'; message: string }
  | { type: 'ping' }

export type ClientMessage =
  | { type: 'input'; data: string }
  | { type: 'approve_tool'; requestId: string }
  | { type: 'reject_tool'; requestId: string; reason?: string }
  | { type: 'resize'; cols: number; rows: number }
  | { type: 'pong' }

// ---------------------------------------------------------------------------
// REST types
// ---------------------------------------------------------------------------

export interface SessionInfo {
  id: string
  workingDir: string
  pid: number | null
  startedAt: number
  ended: boolean
  exitCode: number | null
  clientCount: number
  hasPendingApproval: boolean
}

export interface CreateSessionRequest {
  workingDir: string
  initialPrompt?: string
  cols?: number
  rows?: number
}

export interface PendingApproval {
  requestId: string
  toolName: string
  toolInput: string
}

// ---------------------------------------------------------------------------
// App state
// ---------------------------------------------------------------------------
export type Route = 'login' | 'sessions' | 'terminal'

export interface AppState {
  route: Route
  token: string | null
  apiBase: string

  sessions: SessionInfo[]
  activeSessionId: string | null

  pendingApproval: PendingApproval | null

  // Connection status
  wsStatus: 'disconnected' | 'connecting' | 'connected' | 'error'
  wsError: string | null
}
