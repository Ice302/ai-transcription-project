import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelJob, deleteJob, listJobs, updateJob, uploadJob } from '../lib/api'
import { jobPath, navigate } from '../lib/router'
import { useToast } from './toast'

const ACTIVE = new Set(['queued', 'running', 'recording'])
let localCounter = 0

function notifyDesktop(title, body) {
  if (!('Notification' in window) || Notification.permission !== 'granted' || !document.hidden) return
  try {
    new Notification(title, { body, icon: '/favicon.svg' })
  } catch {
    /* some browsers only allow notifications from a service worker */
  }
}

// The library: every recording on the server, plus uploads still in flight from this tab.
export function useLibrary() {
  const [jobs, setJobs] = useState([])
  const [uploads, setUploads] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const push = useToast()
  const localUrls = useRef(new Map()) // job id -> object URL of a file uploaded in this session
  const lastStatus = useRef(new Map())

  const refresh = useCallback(async () => {
    try {
      const list = await listJobs()
      for (const job of list) {
        const before = lastStatus.current.get(job.id)
        if (before && ACTIVE.has(before) && (job.status === 'done' || job.status === 'error')) {
          const ok = job.status === 'done'
          const viewing = window.location.hash.startsWith(`#${jobPath(job.id)}`)
          push(ok ? `“${job.title}” is ready` : `“${job.title}” failed: ${job.error}`, {
            tone: ok ? 'success' : 'error',
            action: ok && !viewing ? { label: 'Open', onClick: () => navigate(jobPath(job.id)) } : undefined,
          })
          notifyDesktop(ok ? 'Transcript ready' : 'Processing failed', job.title)
        }
        lastStatus.current.set(job.id, job.status)
      }
      setJobs(list)
      setLoaded(true)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [push])

  const busy = uploads.length > 0 || jobs.some((j) => ACTIVE.has(j.status))
  useEffect(() => {
    refresh()
  }, [refresh])
  useEffect(() => {
    const timer = setInterval(refresh, busy ? 1500 : 15000)
    return () => clearInterval(timer)
  }, [busy, refresh])

  useEffect(() => () => localUrls.current.forEach((url) => URL.revokeObjectURL(url)), [])

  const upload = useCallback(
    (files, options) => {
      if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {})
      for (const file of files) {
        const localId = `u${++localCounter}`
        setUploads((u) => [...u, { localId, filename: file.name, size: file.size, progress: 0 }])
        uploadJob(file, options, (p) => setUploads((u) => u.map((x) => (x.localId === localId ? { ...x, progress: p } : x))))
          .then((job) => {
            localUrls.current.set(job.id, URL.createObjectURL(file))
            lastStatus.current.set(job.id, job.status)
            setJobs((list) => [job, ...list.filter((j) => j.id !== job.id)])
          })
          .catch((err) => push(`${file.name}: ${err.message}`, { tone: 'error', timeout: 8000 }))
          .finally(() => setUploads((u) => u.filter((x) => x.localId !== localId)))
      }
    },
    [push],
  )

  const cancel = useCallback(
    async (id) => {
      try {
        await cancelJob(id)
        refresh()
      } catch (err) {
        push(err.message, { tone: 'error' })
      }
    },
    [push, refresh],
  )

  const remove = useCallback(
    async (id) => {
      try {
        await deleteJob(id)
        const url = localUrls.current.get(id)
        if (url) URL.revokeObjectURL(url)
        localUrls.current.delete(id)
        setJobs((list) => list.filter((j) => j.id !== id))
        return true
      } catch (err) {
        push(err.message, { tone: 'error' })
        return false
      }
    },
    [push],
  )

  const rename = useCallback(
    async (id, title) => {
      try {
        await updateJob(id, { title })
        setJobs((list) => list.map((j) => (j.id === id ? { ...j, title } : j)))
      } catch (err) {
        push(err.message, { tone: 'error' })
      }
    },
    [push],
  )

  const localUrl = useCallback((id) => localUrls.current.get(id), [])

  return { jobs, uploads, loaded, error, refresh, upload, cancel, remove, rename, localUrl }
}
