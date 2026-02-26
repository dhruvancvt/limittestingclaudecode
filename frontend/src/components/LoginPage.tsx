import { FormEvent, useState } from 'react'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { login } = useAuth()
  const [apiBase, setApiBase] = useState(localStorage.getItem('cc_api_base') || '')
  const [secret, setSecret] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(apiBase.trim(), secret)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect width="48" height="48" rx="12" fill="#1a1a2e" />
            <path d="M12 24 L24 12 L36 24 L24 36 Z" fill="#7c3aed" opacity="0.8" />
            <circle cx="24" cy="24" r="6" fill="#a78bfa" />
          </svg>
          <h1>Claude Code Remote</h1>
          <p>Control Claude Code from your phone</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="field">
            <label htmlFor="api-base">Server URL</label>
            <input
              id="api-base"
              type="url"
              placeholder="http://100.x.x.x:8000"
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              required
              autoComplete="url"
              inputMode="url"
            />
            <span className="field-hint">Your Tailscale IP and port</span>
          </div>

          <div className="field">
            <label htmlFor="secret">Auth Secret</label>
            <input
              id="secret"
              type="password"
              placeholder="your-auth-secret"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              required
              autoComplete="current-password"
            />
          </div>

          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" />
                Connecting…
              </>
            ) : (
              'Connect'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
