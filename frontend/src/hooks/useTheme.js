import { useCallback, useEffect, useState } from 'react'

const KEY = 'tt-theme'

function readPreference() {
  try {
    return localStorage.getItem(KEY) || 'system'
  } catch {
    return 'system'
  }
}

// 'system' | 'light' | 'dark'; applied as data-theme on <html>.
export function useTheme() {
  const [preference, setPreference] = useState(readPreference)

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      document.documentElement.dataset.theme = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference
    }
    apply()
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [preference])

  const set = useCallback((value) => {
    setPreference(value)
    try {
      localStorage.setItem(KEY, value)
    } catch {
      /* storage unavailable (private mode): preference lasts for this session */
    }
  }, [])

  return [preference, set]
}
