import { useCallback } from 'react'
import { useAppStore } from '../store/appStore'

export function useAuth() {
  const { token, apiBase, setToken, setApiBase, setRoute, logout } = useAppStore()

  const login = useCallback(
    async (base: string, secret: string): Promise<void> => {
      const url = base.replace(/\/$/, '')
      const res = await fetch(`${url}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ secret }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setApiBase(url)
      setToken(data.token)
      setRoute('sessions')
    },
    [setApiBase, setToken, setRoute],
  )

  const apiFetch = useCallback(
    async (path: string, init: RequestInit = {}): Promise<Response> => {
      const res = await fetch(`${apiBase}${path}`, {
        ...init,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          ...(init.headers ?? {}),
        },
      })
      if (res.status === 401) {
        logout()
        throw new Error('Session expired – please log in again')
      }
      return res
    },
    [apiBase, token, logout],
  )

  return { token, apiBase, login, logout, apiFetch, isLoggedIn: !!token }
}
