import { MessageSquare, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useHotkeys } from '../../hooks/useHotkeys'
import { searchAll } from '../../lib/api'
import { formatBytes, formatDuration } from '../../lib/format'
import { NetworkIllustration } from '../Art'
import { Button, Kbd, Segmented } from '../ui'
import JobCard, { UploadingCard } from './JobCard'
import Onboarding from './Onboarding'
import SearchResults from './SearchResults'
import UploadCard from './UploadCard'

export default function LibraryView({ library, health, offline, selected, onSelect, onClearSelection, onAsk, initialQuery }) {
  const { jobs, uploads, loaded, upload, cancel, remove, rename } = library
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState(initialQuery || '')
  const [results, setResults] = useState({ groups: [], loading: false })
  const searchRef = useRef(null)

  useHotkeys({ '/': () => searchRef.current?.focus() })

  // Debounced full-text search across all transcripts and slides.
  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setResults({ groups: [], loading: false })
      return
    }
    const controller = new AbortController()
    setResults((r) => ({ ...r, loading: true }))
    const timer = setTimeout(() => {
      searchAll(q, controller.signal)
        .then((groups) => setResults({ groups, loading: false }))
        .catch((err) => err.name !== 'AbortError' && setResults({ groups: [], loading: false }))
    }, 220)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const visible = useMemo(
    () => jobs.filter((j) => filter === 'all' || (filter === 'live' ? j.kind === 'live' : j.kind !== 'live')),
    [jobs, filter],
  )
  const totals = useMemo(() => {
    const done = jobs.filter((j) => j.status === 'done')
    return {
      count: done.length,
      hours: done.reduce((sum, j) => sum + (j.media?.duration || 0), 0),
      voices: done.reduce((sum, j) => sum + (j.stats?.speakers || 0), 0),
    }
  }, [jobs])
  const showSetup = offline || !health || health.status !== 'ok' || (loaded && jobs.length === 0) || !health.ffmpeg

  return (
    <div className="space-y-12">
      {/* Hero: editorial headline + upload card */}
      <section className="grid gap-6 lg:grid-cols-[1.05fr_1fr] lg:gap-10">
        <div className="flex flex-col justify-between gap-8">
          <div>
            <p className="eyebrow">№ 01 — The library</p>
            <h1 className="display text-balance mt-4 text-[clamp(48px,6.6vw,104px)]">
              Every word <span className="serif-accent text-[1.08em] tracking-[-0.02em]">heard</span>
              <br />
              &amp; <span className="serif-accent text-[1.08em] tracking-[-0.02em]">seen.</span>
            </h1>
            <p className="mt-5 max-w-md text-[15px] leading-relaxed text-ink-2">
              Upload recordings or join a meeting live. Speech is cross-checked against what was on screen, and voices are told
              apart, so names, numbers and owners come out right.
            </p>
          </div>
          {showSetup ? (
            <Onboarding health={health} offline={offline} />
          ) : (
            <dl className="grid grid-cols-3 gap-3">
              {[
                ['Recordings', totals.count],
                ['Transcribed', formatDuration(totals.hours)],
                ['Stored', formatBytes(health?.storage_bytes)],
              ].map(([label, value], i) => (
                <div key={label} className={`tile p-4 ${i === 0 ? 'bg-lime text-[#131312]' : i === 1 ? 'bg-ink text-on-ink' : 'border border-line bg-surface'}`}>
                  <dt className="font-mono text-[10px] uppercase tracking-[0.14em] opacity-60">{label}</dt>
                  <dd className="display tabular mt-6 text-[clamp(26px,2.6vw,38px)]">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        <UploadCard onUpload={upload} health={health} />
      </section>

      {/* Library */}
      <section>
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <h2 className="text-3xl font-semibold tracking-tight">
            The <span className="serif-accent text-[1.15em]">library</span>
            <span className="ml-2 align-middle font-mono text-sm font-normal text-ink-3">{jobs.length}</span>
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <Segmented
              size="sm"
              label="Filter"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'all', label: 'All' },
                { value: 'files', label: 'Files' },
                { value: 'live', label: 'Live' },
              ]}
            />
            <label className="relative">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-3" />
              <input
                ref={searchRef}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && setQuery('')}
                placeholder="Search every transcript & slide"
                aria-label="Search every transcript and slide"
                className="field h-10 w-[min(320px,80vw)] rounded-full py-0 pl-10 pr-10"
              />
              {query ? (
                <button type="button" aria-label="Clear search" onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-3 hover:text-ink">
                  <X className="size-4" />
                </button>
              ) : (
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2">
                  <Kbd>/</Kbd>
                </span>
              )}
            </label>
          </div>
        </div>

        {selected.length > 0 && (
          <div className="animate-rise mb-5 flex flex-wrap items-center gap-3 rounded-full border border-ink bg-ink py-2 pl-5 pr-2 text-sm text-on-ink">
            <span>
              {selected.length} recording{selected.length > 1 ? 's' : ''} selected for the assistant
            </span>
            <Button size="sm" tone="lime" icon={MessageSquare} onClick={onAsk} className="ml-auto">
              Ask about {selected.length > 1 ? 'them' : 'it'}
            </Button>
            <Button size="sm" tone="ghost" className="border-on-ink/30 text-on-ink hover:bg-white/10" onClick={onClearSelection}>
              Clear
            </Button>
          </div>
        )}

        {query.trim() ? (
          <SearchResults groups={results.groups} loading={results.loading} query={query.trim()} />
        ) : loaded && !visible.length && !uploads.length ? (
          <div className="card grid items-center gap-6 p-8 md:grid-cols-[1fr_1.2fr]">
            <div>
              <p className="text-2xl font-semibold tracking-tight">
                Nothing here <span className="serif-accent">yet</span>
              </p>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">
                {filter === 'live'
                  ? 'Live meetings you record are saved here automatically, then re-transcribed at full accuracy.'
                  : 'Drop a meeting recording, lecture or screen capture above. Videos get their slides read and matched to the speech.'}
              </p>
            </div>
            <NetworkIllustration className="w-full" />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
            {uploads.map((u) => (
              <UploadingCard key={u.localId} upload={u} />
            ))}
            {visible.map((job, i) => (
              <JobCard
                key={job.id}
                job={job}
                index={i}
                selected={selected.includes(job.id)}
                onSelect={onSelect}
                onCancel={cancel}
                onDelete={remove}
                onRename={rename}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
