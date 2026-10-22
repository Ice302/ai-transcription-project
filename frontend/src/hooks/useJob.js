import { useCallback, useEffect, useRef, useState } from 'react'
import { acceptCorrections, actOnCorrection, getJob, reprocessJob, updateJob, updateSegment } from '../lib/api'
import { useToast } from './toast'

const ACTIVE = new Set(['queued', 'running', 'recording'])

// One recording: loads it, polls while it is still processing, and applies edits.
// Every edit endpoint returns the updated result, so the view never goes stale.
export function useJob(id) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const push = useToast()
  const status = data?.status

  const load = useCallback(
    async (signal) => {
      try {
        const next = await getJob(id, signal)
        setData(next)
        setError('')
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.status === 404 ? 'not-found' : err.message)
      }
    },
    [id],
  )

  useEffect(() => {
    const controller = new AbortController()
    setData(null)
    setError('')
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  useEffect(() => {
    if (!ACTIVE.has(status)) return
    const timer = setTimeout(() => load(), 1500)
    return () => clearTimeout(timer)
  }, [status, data, load])

  const busy = useRef(false)
  const apply = useCallback(
    async (call, success) => {
      if (busy.current) return null
      busy.current = true
      try {
        const result = await call()
        setData((d) => (d ? { ...d, title: result.title ?? d.title, result } : d))
        if (success) push(success, { tone: 'success' })
        return result
      } catch (err) {
        push(err.message, { tone: 'error' })
        return null
      } finally {
        busy.current = false
      }
    },
    [push],
  )

  return {
    data,
    error,
    reload: load,
    rename: (title) => apply(() => updateJob(id, { title })),
    renameSpeaker: (speakerId, name) => apply(() => updateJob(id, { speakers: { [speakerId]: name } })),
    editSegment: (segmentId, changes) => apply(() => updateSegment(id, segmentId, changes)),
    correction: (correctionId, action) => apply(() => actOnCorrection(id, correctionId, action)),
    acceptAll: (confidence = 'high') => apply(() => acceptCorrections(id, confidence), 'Suggested fixes applied'),
    reprocess: async (options) => {
      try {
        const job = await reprocessJob(id, options)
        setData(job)
        push('Processing again with the new settings…')
      } catch (err) {
        push(err.message, { tone: 'error' })
      }
    },
  }
}
