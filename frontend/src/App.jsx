import { Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import AssistantPanel from './components/AssistantPanel'
import JobDetail from './components/job/JobDetail'
import LibraryView from './components/library/LibraryView'
import LiveView from './components/live/LiveView'
import TopBar from './components/TopBar'
import { useHealth } from './hooks/useHealth'
import { useLibrary } from './hooks/useLibrary'
import { useLiveSession } from './hooks/useLiveSession'
import { useTheme } from './hooks/useTheme'
import { buildLiveContext } from './lib/liveContext'
import { navigate, useRoute } from './lib/router'
import { loadUploadOptions, mediaFiles, uploadFields } from './lib/uploads'

export default function App() {
  const route = useRoute()
  const [theme, setTheme] = useTheme()
  const { health, offline } = useHealth()
  const library = useLibrary()
  const live = useLiveSession()
  const [selected, setSelected] = useState([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [dropping, setDropping] = useState(false)

  // Timestamps clicked in the assistant seek whichever recording is open.
  const seekRef = useRef(null)
  const registerSeek = useCallback((fn) => {
    seekRef.current = fn
    return () => {
      if (seekRef.current === fn) seekRef.current = null
    }
  }, [])

  // A finished live meeting lands in the library; refresh so it shows up right away.
  const { refresh, jobs } = library
  useEffect(() => {
    if (live.savedJobId) refresh()
  }, [live.savedJobId, refresh])

  // Drop files anywhere: upload with the saved options and show the library.
  const { upload } = library
  useEffect(() => {
    let depth = 0
    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files')
    const onEnter = (e) => {
      if (!hasFiles(e)) return
      depth += 1
      setDropping(true)
    }
    const onLeave = (e) => {
      if (!hasFiles(e)) return
      depth = Math.max(0, depth - 1)
      if (!depth) setDropping(false)
    }
    const onOver = (e) => hasFiles(e) && e.preventDefault()
    const reset = () => {
      depth = 0
      setDropping(false)
    }
    const onDrop = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      const files = mediaFiles(e.dataTransfer.files)
      if (!files.length) return
      upload(files, uploadFields(loadUploadOptions(), health))
      navigate('/')
    }
    window.addEventListener('dragenter', onEnter)
    window.addEventListener('dragleave', onLeave)
    window.addEventListener('dragover', onOver)
    window.addEventListener('drop', reset, true) // capture: also runs when the upload card handles the drop
    window.addEventListener('drop', onDrop)
    return () => {
      window.removeEventListener('dragenter', onEnter)
      window.removeEventListener('dragleave', onLeave)
      window.removeEventListener('dragover', onOver)
      window.removeEventListener('drop', reset, true)
      window.removeEventListener('drop', onDrop)
    }
  }, [upload, health])

  // Drop selections of recordings that no longer exist.
  useEffect(() => {
    setSelected((ids) => {
      const kept = ids.filter((id) => jobs.some((j) => j.id === id && j.status === 'done'))
      return kept.length === ids.length ? ids : kept
    })
  }, [jobs])

  const liveContext = useMemo(() => (live.events.length ? buildLiveContext(live.events) : ''), [live.events])
  const openJob = route.view === 'job' ? jobs.find((j) => j.id === route.id) : null
  const scope =
    route.view === 'live'
      ? live.events.length
        ? { key: 'live', kind: 'live', label: 'Live meeting', context: liveContext }
        : { key: 'live-empty', kind: 'none', label: 'Live meeting — nothing said yet', reason: 'Start the meeting; you can ask questions as soon as something has been said.' }
      : route.view === 'job'
        ? !openJob || openJob.status === 'done'
          ? { key: `job:${route.id}`, kind: 'job', jobIds: [route.id], label: openJob?.title || 'This recording' }
          : { key: `job-pending:${route.id}`, kind: 'none', label: 'Still processing', reason: 'Available as soon as this recording has finished processing.' }
        : selected.length
          ? {
              key: `jobs:${[...selected].sort().join(',')}`,
              kind: 'jobs',
              jobIds: selected,
              label: `${selected.length} selected recording${selected.length > 1 ? 's' : ''}`,
            }
          : { key: 'none', kind: 'none', label: 'Nothing selected' }
  const onSeek = route.view === 'job' ? (t) => seekRef.current?.(t) : null

  const assistant = (onClose) => <AssistantPanel scope={scope} health={health} onSeek={onSeek} onClose={onClose} />

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        onClick={(e) => {
          e.preventDefault()
          document.getElementById('main')?.focus()
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-ink focus:px-4 focus:py-2 focus:text-on-ink"
      >
        Skip to content
      </a>
      <TopBar
        route={route}
        health={health}
        offline={offline}
        theme={theme}
        setTheme={setTheme}
        liveStatus={live.status}
        onToggleAssistant={() => setDrawerOpen((v) => !v)}
      />
      <div className="mx-auto max-w-[1680px] px-4 py-8 sm:px-6 xl:grid xl:grid-cols-[minmax(0,1fr)_400px] xl:gap-8">
        <main id="main" tabIndex={-1} className="min-w-0 outline-none">
          {route.view === 'live' && <LiveView live={live} health={health} />}
          {route.view === 'job' && (
            <JobDetail
              key={route.id}
              id={route.id}
              initialTime={route.t}
              health={health}
              localUrl={library.localUrl}
              registerSeek={registerSeek}
              onDelete={library.remove}
              onCancel={library.cancel}
            />
          )}
          {route.view === 'library' && (
            <LibraryView
              library={library}
              health={health}
              offline={offline}
              selected={selected}
              onSelect={(id) => setSelected((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))}
              onClearSelection={() => setSelected([])}
              onAsk={() => setDrawerOpen(true)}
              initialQuery={route.q}
            />
          )}
        </main>
        <aside className="no-print hidden xl:block" aria-label="Notes assistant">
          <div className="sticky top-24 h-[calc(100vh-8rem)]">{assistant(null)}</div>
        </aside>
      </div>

      {dropping && (
        <div className="no-print pointer-events-none fixed inset-3 z-50 grid place-items-center rounded-card border-2 border-dashed border-ink bg-lime/90 text-[#131312] backdrop-blur-sm">
          <div className="text-center">
            <Upload className="mx-auto size-10" />
            <p className="display mt-4 text-[clamp(40px,6vw,72px)]">
              Drop to <span className="serif-accent">transcribe</span>
            </p>
            <p className="mt-3 text-sm opacity-75">Uses your saved upload options · audio and video files</p>
          </div>
        </div>
      )}

      {drawerOpen && (
        <div className="no-print fixed inset-0 z-40 xl:hidden" role="dialog" aria-modal="true" aria-label="Notes assistant">
          <button type="button" aria-label="Close assistant" className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setDrawerOpen(false)} />
          <div className="animate-rise absolute inset-y-3 right-3 w-[min(440px,calc(100vw-1.5rem))]">{assistant(() => setDrawerOpen(false))}</div>
        </div>
      )}

      <footer className="no-print mx-auto flex max-w-[1680px] flex-wrap items-center justify-between gap-2 px-4 pb-10 pt-4 font-mono text-[11px] text-ink-3 sm:px-6">
        <span>TurboTranscribe {health?.version ? `v${health.version}` : ''} · speech, screen &amp; voices, cross-checked on your machine</span>
        <span>
          Press <span className="rounded border border-line px-1">?</span> on a recording for shortcuts
        </span>
      </footer>
    </div>
  )
}
