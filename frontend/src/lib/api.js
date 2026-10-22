// All backend calls go through here. In dev, Vite proxies /api to the backend
// (see vite.config.js); set VITE_API_URL to talk to a backend elsewhere.
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export const apiUrl = (path) => (path?.startsWith('/api/') ? `${BASE}${path}` : path)

async function request(path, { method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await fetch(apiUrl(path), {
      method,
      signal,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error('Cannot reach the backend. Is it running?')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join('; ') : data.detail
    const error = new Error(detail || `Request failed (HTTP ${response.status})`)
    error.status = response.status
    throw error
  }
  return data
}

export const getHealth = () => request('/api/health')
export const listJobs = () => request('/api/jobs')
export const getJob = (id, signal) => request(`/api/jobs/${id}`, { signal })
export const deleteJob = (id) => request(`/api/jobs/${id}`, { method: 'DELETE' })
export const cancelJob = (id) => request(`/api/jobs/${id}/cancel`, { method: 'POST' })
export const updateJob = (id, changes) => request(`/api/jobs/${id}`, { method: 'PATCH', body: changes })
export const updateSegment = (id, segmentId, changes) =>
  request(`/api/jobs/${id}/segments/${segmentId}`, { method: 'PATCH', body: changes })
export const actOnCorrection = (id, correctionId, action) =>
  request(`/api/jobs/${id}/corrections/${correctionId}`, { method: 'POST', body: { action } })
export const acceptCorrections = (id, confidence = 'high') =>
  request(`/api/jobs/${id}/corrections`, { method: 'POST', body: { confidence } })
export const reprocessJob = (id, options) => request(`/api/jobs/${id}/reprocess`, { method: 'POST', body: options })
export const searchAll = (q, signal) => request(`/api/search?q=${encodeURIComponent(q)}`, { signal })
export const mediaUrl = (id) => apiUrl(`/api/jobs/${id}/media`)

// XHR instead of fetch: fetch cannot report upload progress, which matters for large videos.
export function uploadJob(file, options, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', apiUrl('/api/jobs'))
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      const detail = xhr.response?.detail
      if (xhr.status < 300) resolve(xhr.response)
      else reject(new Error((Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail) || `Upload failed (HTTP ${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Cannot reach the backend. Is it running?'))
    const form = new FormData()
    form.append('file', file)
    for (const [key, value] of Object.entries(options || {})) {
      if (value !== undefined && value !== null && value !== '') form.append(key, String(value))
    }
    xhr.send(form)
  })
}

// Streams the assistant's answer. Calls onDelta(text) for every chunk; resolves with the full text.
export async function streamChat({ messages, jobIds = [], context = '', signal, onDelta }) {
  let response
  try {
    response = await fetch(apiUrl('/api/chat'), {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, job_ids: jobIds, context, stream: true }),
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new Error('Cannot reach the backend. Is it running?')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `Request failed (HTTP ${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const event = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const line = event.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      const data = JSON.parse(line.slice(5))
      if (data.error) throw new Error(data.error)
      if (data.delta) {
        full += data.delta
        onDelta?.(full)
      }
    }
  }
  return full
}

export function liveSocketUrl() {
  const origin = BASE || window.location.origin
  return `${origin.replace(/^http/, 'ws')}/api/ws/live`
}
