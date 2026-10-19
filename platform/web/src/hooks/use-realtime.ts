import { useEffect, useState } from 'react'

export function useRealtime(topic = 'platform') {
  const [connected, setConnected] = useState(false)
  const [lastEvent, setLastEvent] = useState<string | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const configured = import.meta.env.VITE_WS_URL as string | undefined
    const url = configured ?? `${protocol}//${window.location.host}/ws/${topic}`
    const socket = new WebSocket(url)
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onmessage = (message) => setLastEvent(message.data)
    return () => socket.close()
  }, [topic])

  return { connected, lastEvent }
}
