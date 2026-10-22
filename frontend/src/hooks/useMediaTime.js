import { useEffect, useState } from 'react'

// Current playback time, refreshed ~15x/s while playing (smooth word highlighting
// without re-rendering on every animation frame).
export function useMediaTime(mediaRef, ready) {
  const [time, setTime] = useState(0)
  useEffect(() => {
    const el = mediaRef.current
    if (!el) return
    let raf = 0
    let last = 0
    const loop = (ts) => {
      if (ts - last > 66) {
        last = ts
        setTime(el.currentTime)
      }
      raf = requestAnimationFrame(loop)
    }
    const onPlay = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(loop)
    }
    const onStop = () => {
      cancelAnimationFrame(raf)
      setTime(el.currentTime)
    }
    el.addEventListener('play', onPlay)
    el.addEventListener('pause', onStop)
    el.addEventListener('ended', onStop)
    el.addEventListener('seeked', onStop)
    return () => {
      cancelAnimationFrame(raf)
      el.removeEventListener('play', onPlay)
      el.removeEventListener('pause', onStop)
      el.removeEventListener('ended', onStop)
      el.removeEventListener('seeked', onStop)
    }
  }, [mediaRef, ready])
  return time
}
