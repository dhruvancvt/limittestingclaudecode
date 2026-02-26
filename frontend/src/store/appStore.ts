import { create } from 'zustand'
import type { AppState, PendingApproval, Route, SessionInfo } from '../types'

interface AppActions {
  setRoute: (route: Route) => void
  setToken: (token: string | null) => void
  setApiBase: (base: string) => void
  setSessions: (sessions: SessionInfo[]) => void
  addSession: (session: SessionInfo) => void
  removeSession: (id: string) => void
  setActiveSession: (id: string | null) => void
  setPendingApproval: (a: PendingApproval | null) => void
  setWsStatus: (status: AppState['wsStatus'], error?: string | null) => void
  logout: () => void
}

const stored = {
  token: localStorage.getItem('cc_token'),
  apiBase: localStorage.getItem('cc_api_base') || '',
}

export const useAppStore = create<AppState & AppActions>((set) => ({
  route: stored.token ? 'sessions' : 'login',
  token: stored.token,
  apiBase: stored.apiBase,

  sessions: [],
  activeSessionId: null,

  pendingApproval: null,

  wsStatus: 'disconnected',
  wsError: null,

  setRoute: (route) => set({ route }),

  setToken: (token) => {
    if (token) {
      localStorage.setItem('cc_token', token)
    } else {
      localStorage.removeItem('cc_token')
    }
    set({ token })
  },

  setApiBase: (apiBase) => {
    localStorage.setItem('cc_api_base', apiBase)
    set({ apiBase })
  },

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((s) => ({ sessions: [...s.sessions.filter((x) => x.id !== session.id), session] })),

  removeSession: (id) =>
    set((s) => ({
      sessions: s.sessions.filter((x) => x.id !== id),
      activeSessionId: s.activeSessionId === id ? null : s.activeSessionId,
    })),

  setActiveSession: (id) => set({ activeSessionId: id }),

  setPendingApproval: (pendingApproval) => set({ pendingApproval }),

  setWsStatus: (wsStatus, wsError = null) => set({ wsStatus, wsError }),

  logout: () => {
    localStorage.removeItem('cc_token')
    set({
      token: null,
      route: 'login',
      sessions: [],
      activeSessionId: null,
      pendingApproval: null,
      wsStatus: 'disconnected',
    })
  },
}))
