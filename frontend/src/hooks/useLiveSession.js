import { useCallback, useEffect, useRef, useState } from 'react'
import { liveSocketUrl } from '../lib/api'

const TIMESLICE_MS = 1000 // how often the continuous recording is flushed to the server
const FLUSH_TIMEOUT_MS = 30000 // max wait for the server to finish the last words after "End"
const FRAME_CHECK_MS = 2000 // how often the shared screen is checked for changes
const FRAME_DIFF_THRESHOLD = 0.04 // mean pixel difference (0-1) that counts as "screen changed"
const FRAME_MAX_WIDTH = 1280

const blobToBase64 = (blob) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })

function pickMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  return candidates.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || ''
}

async function getStreams(source) {
  const wantsScreen = source === 'system' || source === 'both'
  const display = wantsScreen ? await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true }) : null
  if (display && display.getAudioTracks().length === 0) {
    display.getTracks().forEach((t) => t.stop())
    throw new Error("No audio was shared. Pick a tab and tick 'Share tab audio' (or 'Share system audio').")
  }
  let mic = null
  if (source === 'mic' || source === 'both') {
    try {
      mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
    } catch (err) {
      display?.getTracks().forEach((t) => t.stop())
      throw err
    }
  }
  return { display, mic }
}

// One audio stream for the recorder. With `separate`, the mic goes to the left channel and
// the shared tab to the right, so the server can transcribe "You" and "Others" apart.
function buildAudio({ display, mic }, separate) {
  const tracks = [display, mic].filter((s) => s?.getAudioTracks().length)
  if (tracks.length === 1 && !separate) return { stream: new MediaStream(tracks[0].getAudioTracks()), ctx: null }
  const ctx = new AudioContext({ sampleRate: 48000 })
  const dest = ctx.createMediaStreamDestination()
  if (separate && mic && display) {
    dest.channelCount = 2
    const merger = ctx.createChannelMerger(2)
    ctx.createMediaStreamSource(new MediaStream(mic.getAudioTracks())).connect(merger, 0, 0)
    ctx.createMediaStreamSource(new MediaStream(display.getAudioTracks())).connect(merger, 0, 1)
    merger.connect(dest)
  } else {
    dest.channelCount = 1
    for (const s of tracks) ctx.createMediaStreamSource(new MediaStream(s.getAudioTracks())).connect(dest)
  }
  return { stream: dest.stream, ctx }
}

export function useLiveSession() {
  const [status, setStatus] = useState('idle') // idle | connecting | live | finishing
  const [events, setEvents] = useState([])
  const [partials, setPartials] = useState({})
  const [muted, setMuted] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [lag, setLag] = useState(0)
  const [savedJobId, setSavedJobId] = useState(null)
  const session = useRef(null)
  const nextLocalId = useRef(0)

  const addEvent = useCallback((event) => setEvents((list) => [...list, { key: nextLocalId.current++, ...event }]), [])

  const stop = useCallback(() => {
    const s = session.current
    session.current = null
    if (!s) return
    s.stopped = true
    clearInterval(s.frameTimer)
    clearInterval(s.clock)
    const release = () => {
      s.tracks.forEach((t) => t.stop())
      s.audioCtx?.close().catch(() => {})
      if (s.video) s.video.srcObject = null
    }
    const close = () => {
      clearTimeout(s.flushTimer)
      s.onDone = null
      if (s.socket.readyState <= WebSocket.OPEN) s.socket.close()
      setPartials({})
      setStatus('idle')
    }
    if (s.socket.readyState !== WebSocket.OPEN || !s.recorder) {
      release()
      close()
      return
    }
    // Graceful end: flush the recorder, let the server transcribe the remaining audio and
    // queue the high-accuracy pass, and close once it answers "done" (or after a timeout).
    setStatus('finishing')
    s.onDone = close
    s.flushTimer = setTimeout(close, FLUSH_TIMEOUT_MS)
    s.recorder.onstop = async () => {
      await s.pendingSend
      if (s.socket.readyState === WebSocket.OPEN) s.socket.send(JSON.stringify({ type: 'stop' }))
      release()
    }
    if (s.recorder.state !== 'inactive') s.recorder.stop()
    else s.recorder.onstop()
  }, [])

  const setMute = useCallback((value) => {
    setMuted(value)
    // Disabled tracks record silence, which the server's voice-activity filter drops.
    session.current?.audioTracks.forEach((t) => (t.enabled = !value))
  }, [])

  const start = useCallback(
    async ({ source, captureScreen, separate, glossary, title, language }) => {
      if (session.current) return
      setError('')
      setSavedJobId(null)
      setStatus('connecting')
      let streams
      try {
        streams = await getStreams(source)
      } catch (err) {
        setStatus('idle')
        setError(err.name === 'NotAllowedError' ? 'Permission to capture audio or the screen was denied.' : err.message)
        return
      }
      const { display, mic } = streams
      const twoChannels = Boolean(separate && display && mic)
      const tracks = [display, mic].filter(Boolean).flatMap((st) => st.getTracks())
      const { stream: audioStream, ctx: audioCtx } = buildAudio(streams, twoChannels)
      const s = {
        stopped: false,
        tracks,
        audioCtx,
        audioTracks: [display, mic].filter(Boolean).flatMap((st) => st.getAudioTracks()),
        socket: new WebSocket(liveSocketUrl()),
        t0: 0,
        pendingSend: Promise.resolve(),
      }
      session.current = s
      const send = (msg) => s.socket.readyState === WebSocket.OPEN && s.socket.send(JSON.stringify(msg))
      const now = () => (performance.now() - s.t0) / 1000

      // The browser's own "Stop sharing" button ends the session too.
      tracks.forEach((t) => t.addEventListener('ended', () => session.current === s && stop()))

      // One continuous recording, flushed every second. The server decodes it as a single
      // stream, so words are never cut at chunk boundaries.
      const startRecording = () => {
        const mimeType = pickMimeType()
        const recorder = new MediaRecorder(audioStream, mimeType ? { mimeType, audioBitsPerSecond: twoChannels ? 96000 : 48000 } : undefined)
        recorder.ondataavailable = (e) => {
          if (!e.data.size) return
          // Chain sends so base64 conversion can never reorder the byte stream.
          s.pendingSend = s.pendingSend.then(async () => send({ type: 'audio', data: await blobToBase64(e.data) }))
        }
        recorder.start(TIMESLICE_MS)
        s.recorder = recorder
      }

      // Screen frames: compare a tiny grayscale thumbnail; send a full frame only when it changed.
      const startFrameCapture = async () => {
        const videoTrack = display?.getVideoTracks()[0]
        if (!captureScreen || !videoTrack) return
        const video = Object.assign(document.createElement('video'), { muted: true, playsInline: true })
        video.srcObject = new MediaStream([videoTrack])
        await video.play().catch(() => {})
        s.video = video
        const thumb = Object.assign(document.createElement('canvas'), { width: 64, height: 36 })
        const thumbCtx = thumb.getContext('2d', { willReadFrequently: true })
        const full = document.createElement('canvas')
        let last = null
        const check = async () => {
          if (s.stopped || !video.videoWidth) return
          thumbCtx.drawImage(video, 0, 0, 64, 36)
          const px = thumbCtx.getImageData(0, 0, 64, 36).data
          const gray = new Uint8Array(64 * 36)
          for (let i = 0; i < gray.length; i++) gray[i] = (px[i * 4] + px[i * 4 + 1] + px[i * 4 + 2]) / 3
          let diff = 1
          if (last) {
            diff = 0
            for (let i = 0; i < gray.length; i++) diff += Math.abs(gray[i] - last[i])
            diff /= gray.length * 255
          }
          if (diff < FRAME_DIFF_THRESHOLD) return
          last = gray
          const scale = Math.min(1, FRAME_MAX_WIDTH / video.videoWidth)
          full.width = Math.round(video.videoWidth * scale)
          full.height = Math.round(video.videoHeight * scale)
          full.getContext('2d').drawImage(video, 0, 0, full.width, full.height)
          const t = now()
          const blob = await new Promise((r) => full.toBlob(r, 'image/jpeg', 0.85))
          if (blob) send({ type: 'frame', t, data: await blobToBase64(blob) })
        }
        s.frameTimer = setInterval(check, FRAME_CHECK_MS)
        check()
      }

      s.socket.onopen = () => {
        s.t0 = performance.now()
        setEvents([])
        setPartials({})
        setElapsed(0)
        setLag(0)
        send({
          type: 'start',
          channels: twoChannels ? 2 : 1,
          labels: twoChannels ? ['You', 'Others'] : [],
          glossary: glossary || '',
          title: title || '',
          language: language || null,
          save: true,
        })
        setStatus('live')
        startRecording()
        startFrameCapture()
        s.clock = setInterval(() => setElapsed(now()), 500)
      }
      s.socket.onmessage = (msg) => {
        const data = JSON.parse(msg.data)
        switch (data.type) {
          case 'ready':
            setInfo(data)
            break
          case 'speech':
            addEvent({ kind: 'speech', id: data.id, t: data.t, end: data.end, text: data.text, speaker: data.speaker })
            break
          case 'partial':
            setLag(data.lag || 0)
            setPartials((p) => ({ ...p, [data.speaker || '']: data.text ? { t: data.t, text: data.text, speaker: data.speaker } : null }))
            break
          case 'retract':
            setEvents((list) => list.filter((e) => !(e.kind === 'speech' && e.id === data.id)))
            break
          case 'visual':
            addEvent({ kind: 'visual', t: data.t, text: data.text, title: data.title, terms: data.terms, image: data.image })
            break
          case 'correction':
            addEvent({ kind: 'correction', t: data.t, heard: data.heard, seen: data.seen })
            break
          case 'saved':
            setSavedJobId(data.job_id)
            break
          case 'done':
            s.onDone?.()
            break
          case 'error':
            setError(data.message)
            break
          default:
        }
      }
      s.socket.onerror = () => setError('Connection to the transcription server failed.')
      s.socket.onclose = (e) => {
        if (s.onDone) s.onDone()
        else if (session.current === s) {
          setError(e.code === 1008 ? 'The server refused this page (origin not allowed).' : 'Connection to the transcription server closed.')
          stop()
        }
      }
    },
    [addEvent, stop],
  )

  useEffect(() => () => stop(), [stop])

  return { status, events, partials, muted, error, info, elapsed, lag, savedJobId, start, stop, setMute, clearError: () => setError('') }
}
