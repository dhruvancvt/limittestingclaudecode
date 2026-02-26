/**
 * Robust WebSocket hook with:
 *  - Automatic reconnection with exponential back-off (up to 30 s)
 *  - Ping/pong keepalive
 *  - Queued messages during reconnect
 *  - onMessage callback receives typed ServerMessage events
 */
import { useCallback, useEffect, useRef } from 'react'
import type { ClientMessage, ServerMessage } from '../types'
import { useAppStore } from '../store/appStore'

interface Options {
  sessionId: string | null
  onMessage: (msg: ServerMessage) => void
  enabled?: boolean
}

const MAX_BACKOFF_MS = 30_000
const INITIAL_BACKOFF_MS = 1_000
const PING_INTERVAL_MS = 25_000

export function useWebSocket({ sessionId, onMessage, enabled = true }: Options) {
  const { token, apiBase, setWsStatus } = useAppStore()
  const wsRef = useRef<WebSocket | null>(null)
  const backoffRef = useRef(INITIAL_BACKOFF_MS)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const queueRef = useRef<string[]>([])
  const mountedRef = useRef(true)

  const clearPing = () => {
    if (pingTimer.current) {
      clearInterval(pingTimer.current)
      pingTimer.current = null
    }
  }

  const startPing = (ws: WebSocket) => {
    clearPing()
    pingTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'pong' }))
      }
    }, PING_INTERVAL_MS)
  }

  const connect = useCallback(() => {
    if (!sessionId || !token || !apiBase || !enabled) return

    setWsStatus('connecting')

    // Build WebSocket URL from API base (http→ws, https→wss)
    const wsBase = apiBase.replace(/^http/, 'ws')
    const url = `${wsBase}/ws/${sessionId}?token=${encodeURIComponent(token)}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      backoffRef.current = INITIAL_BACKOFF_MS
      setWsStatus('connected')
      startPing(ws)

      // Flush queued messages
      const queued = queueRef.current.splice(0)
      for (const m of queued) ws.send(m)
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data) as ServerMessage
        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
          return
        }
        onMessage(msg)
      } catch {
        /* ignore malformed frames */
      }
    }

    ws.onerror = () => {
      setWsStatus('error', 'WebSocket error')
    }

    ws.onclose = (evt) => {
      clearPing()
      wsRef.current = null
      if (!mountedRef.current || !enabled) return

      const clean = evt.code === 1000 || evt.code === 4404
      if (clean) {
        setWsStatus('disconnected')
        return
      }

      setWsStatus('error', `Disconnected (${evt.code}) – reconnecting…`)

      // Exponential back-off
      const delay = Math.min(backoffRef.current, MAX_BACKOFF_MS)
      backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
      reconnectTimer.current = setTimeout(connect, delay)
    }
  }, [sessionId, token, apiBase, enabled, onMessage, setWsStatus])

  // Send helper (queues if not connected)
  const send = useCallback((msg: ClientMessage) => {
    const json = JSON.stringify(msg)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(json)
    } else {
      queueRef.current.push(json)
    }
  }, [])

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    clearPing()
    wsRef.current?.close(1000)
    wsRef.current = null
    setWsStatus('disconnected')
  }, [setWsStatus])

  useEffect(() => {
    mountedRef.current = true
    if (enabled && sessionId) connect()
    return () => {
      mountedRef.current = false
      disconnect()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, enabled])

  return { send, disconnect, reconnect: connect }
}
