import { useEffect, useState } from 'react'
import { getHealth } from '../lib/api'

// Polls /api/health: fast while models load, slowly once ready, and keeps retrying if offline.
export function useHealth() {
  const [health, setHealth] = useState(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let timer
    let cancelled = false
    const tick = async () => {
      try {
        const h = await getHealth()
        if (cancelled) return
        setHealth(h)
        setOffline(false)
        timer = setTimeout(tick, h.status === 'loading' ? 1500 : 20000)
      } catch {
        if (cancelled) return
        setOffline(true)
        timer = setTimeout(tick, 3000)
      }
    }
    tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [])

  return { health, offline }
}
