import { FormEvent, useCallback, useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { useAppStore } from '../store/appStore'
import type { SessionInfo } from '../types'

export default function SessionsPage() {
  const { apiFetch, logout } = useAuth()
  const { sessions, setSessions, addSession, removeSession, setActiveSession, setRoute } =
    useAppStore()

  const [workingDir, setWorkingDir] = useState('')
  const [initialPrompt, setInitialPrompt] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [showNewForm, setShowNewForm] = useState(false)

  const loadSessions = useCallback(async () => {
    try {
      const res = await apiFetch('/sessions')
      if (res.ok) {
        const data: SessionInfo[] = await res.json()
        setSessions(data)
      }
    } catch {
      // silently ignore – will retry
    }
  }, [apiFetch, setSessions])

  useEffect(() => {
    loadSessions()
    const interval = setInterval(loadSessions, 5000)
    return () => clearInterval(interval)
  }, [loadSessions])

  const createSession = async (e: FormEvent) => {
    e.preventDefault()
    if (!workingDir.trim()) return
    setCreating(true)
    setError('')
    try {
      const res = await apiFetch('/sessions', {
        method: 'POST',
        body: JSON.stringify({
          workingDir: workingDir.trim(),
          initialPrompt: initialPrompt.trim() || undefined,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      const newSession: SessionInfo = {
        id: data.sessionId,
        workingDir: workingDir.trim(),
        pid: data.pid,
        startedAt: Date.now() / 1000,
        ended: false,
        exitCode: null,
        clientCount: 0,
        hasPendingApproval: false,
      }
      addSession(newSession)
      setWorkingDir('')
      setInitialPrompt('')
      setShowNewForm(false)
      // Navigate to the new session
      setActiveSession(newSession.id)
      setRoute('terminal')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setCreating(false)
    }
  }

  const killSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await apiFetch(`/sessions/${id}`, { method: 'DELETE' })
      removeSession(id)
    } catch {
      // ignore
    }
  }

  const openSession = (id: string) => {
    setActiveSession(id)
    setRoute('terminal')
  }

  const formatAge = (ts: number) => {
    const secs = Math.floor(Date.now() / 1000 - ts)
    if (secs < 60) return `${secs}s ago`
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
    return `${Math.floor(secs / 3600)}h ago`
  }

  return (
    <div className="page">
      <header className="page-header">
        <h2>Sessions</h2>
        <div className="header-actions">
          <button className="btn-icon" onClick={loadSessions} title="Refresh">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
          </button>
          <button className="btn-icon" onClick={logout} title="Logout">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
            </svg>
          </button>
        </div>
      </header>

      <div className="page-content">
        {sessions.length === 0 && !showNewForm && (
          <div className="empty-state">
            <p>No active sessions</p>
            <p className="empty-hint">Start a new session to begin</p>
          </div>
        )}

        <div className="session-list">
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-card ${s.ended ? 'ended' : ''} ${s.hasPendingApproval ? 'needs-approval' : ''}`}
              onClick={() => !s.ended && openSession(s.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && !s.ended && openSession(s.id)}
            >
              <div className="session-info">
                <div className="session-dir" title={s.workingDir}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
                    <polyline points="9 22 9 12 15 12 15 22" />
                  </svg>
                  {s.workingDir.split('/').pop() || s.workingDir}
                </div>
                <div className="session-meta">
                  <span className={`status-dot ${s.ended ? 'dead' : 'alive'}`} />
                  {s.ended ? `Exited (${s.exitCode ?? '?'})` : 'Running'} · {formatAge(s.startedAt)}
                  {s.clientCount > 0 && ` · ${s.clientCount} viewer${s.clientCount > 1 ? 's' : ''}`}
                </div>
              </div>
              <div className="session-actions">
                {s.hasPendingApproval && (
                  <span className="badge-approval">⚠ Approval</span>
                )}
                {!s.ended && (
                  <button
                    className="btn-danger-sm"
                    onClick={(e) => killSession(s.id, e)}
                    title="Kill session"
                  >
                    Kill
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {showNewForm ? (
          <form className="new-session-form" onSubmit={createSession}>
            <h3>New Session</h3>
            <div className="field">
              <label>Working Directory</label>
              <input
                type="text"
                placeholder="/home/user/my-project"
                value={workingDir}
                onChange={(e) => setWorkingDir(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="field">
              <label>Initial Prompt (optional)</label>
              <input
                type="text"
                placeholder="Describe your task…"
                value={initialPrompt}
                onChange={(e) => setInitialPrompt(e.target.value)}
              />
            </div>
            {error && <div className="error-banner">{error}</div>}
            <div className="form-actions">
              <button type="button" className="btn-secondary" onClick={() => setShowNewForm(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={creating}>
                {creating ? <><span className="spinner" /> Creating…</> : 'Start Session'}
              </button>
            </div>
          </form>
        ) : (
          <button className="btn-fab" onClick={() => setShowNewForm(true)} title="New session">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
