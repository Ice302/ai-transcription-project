import { useEffect, useState } from 'react'

// Tiny hash router: #/ (library), #/live, #/job/<id>?t=<seconds>. Hash URLs survive
// reloads and work when the build is served by the backend from any path.
export function parseRoute(hash) {
  const [path, query = ''] = hash.replace(/^#/, '').split('?')
  const params = new URLSearchParams(query)
  const parts = path.split('/').filter(Boolean)
  if (parts[0] === 'live') return { view: 'live' }
  if (parts[0] === 'job' && /^[0-9a-f]{12}$/.test(parts[1] || '')) {
    const t = Number(params.get('t'))
    return { view: 'job', id: parts[1], t: Number.isFinite(t) && params.has('t') ? t : null }
  }
  return { view: 'library', q: params.get('q') || '' }
}

export function useRoute() {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return parseRoute(hash)
}

export function navigate(path) {
  if (window.location.hash !== `#${path}`) window.location.hash = path
}

export const jobPath = (id, t) => `/job/${id}${t != null ? `?t=${Math.max(0, Math.floor(t * 10) / 10)}` : ''}`
