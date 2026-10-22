import { ArrowLeft, Copy, Download, FileText, Keyboard, Printer, RefreshCw, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useHotkeys } from '../../hooks/useHotkeys'
import { useJob } from '../../hooks/useJob'
import { useMediaTime } from '../../hooks/useMediaTime'
import { useToast } from '../../hooks/toast'
import { mediaUrl } from '../../lib/api'
import { baseName, download, formatDate, formatTime, toMarkdown, toSRT, toText, toVTT } from '../../lib/format'
import { speakerColors } from '../../lib/palette'
import { etaSeconds, formatEta } from '../../lib/uploads'
import { navigate } from '../../lib/router'
import { NetworkIllustration } from '../Art'
import { Button, Dialog, IconButton, Kbd, Menu, ProgressBar, Segmented, Spinner, StatTile } from '../ui'
import CrossCheckTab from './CrossCheckTab'
import Player from './Player'
import PrintView from './PrintView'
import ReprocessDialog from './ReprocessDialog'
import SceneTrack from './SceneTrack'
import SpeakersTab from './SpeakersTab'
import TimelineTab from './TimelineTab'
import TranscriptTab from './TranscriptTab'

// Last segment that started at or before t, if t is still inside it (binary search).
function segmentAt(segments, t) {
  let lo = 0
  let hi = segments.length - 1
  let found = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (segments[mid].start <= t + 0.05) {
      found = mid
      lo = mid + 1
    } else hi = mid - 1
  }
  return found >= 0 && t <= segments[found].end + 0.4 ? segments[found].id : null
}

export default function JobDetail({ id, initialTime, health, localUrl, registerSeek, onDelete, onCancel }) {
  const job = useJob(id)
  const { data, error } = job
  const result = data?.result
  const push = useToast()
  const mediaRef = useRef(null)
  const transcriptSearch = useRef(null)
  const [mediaReady, setMediaReady] = useState(0)
  const now = useMediaTime(mediaRef, mediaReady)
  const [tab, setTab] = useState(null)
  const [captions, setCaptions] = useState(false)
  const [speakerFilter, setSpeakerFilter] = useState(null)
  const [reprocessOpen, setReprocessOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  const seek = useCallback((t, play = true) => {
    const el = mediaRef.current
    if (!el) return
    el.currentTime = Math.max(0, t)
    if (play) el.play().catch(() => {})
  }, [])
  useEffect(() => registerSeek(seek), [registerSeek, seek])

  // A search hit for the recording that is already open only changes ?t= - seek to it.
  useEffect(() => {
    if (initialTime != null && mediaRef.current?.readyState >= 1) seek(initialTime, false)
  }, [initialTime, seek])

  const colors = useMemo(() => speakerColors(result?.speakers), [result?.speakers])
  const activeSegment = useMemo(() => (result ? segmentAt(result.segments, now) : null), [result, now])
  const activeScene = useMemo(() => result?.keyframes.findLast((k) => k.t <= now + 0.05)?.id ?? null, [result, now])
  const activeTab = tab || (result?.keyframes?.length ? 'timeline' : 'transcript')

  useHotkeys(
    {
      k: () => (mediaRef.current?.paused ? mediaRef.current.play() : mediaRef.current?.pause()),
      ' ': () => (mediaRef.current?.paused ? mediaRef.current.play() : mediaRef.current?.pause()),
      j: () => mediaRef.current && seek(mediaRef.current.currentTime - 5, false),
      l: () => mediaRef.current && seek(mediaRef.current.currentTime + 5, false),
      c: () => setCaptions((v) => !v),
      '/': () => {
        setTab('transcript')
        setTimeout(() => transcriptSearch.current?.focus(), 0)
      },
      '?': () => setHelpOpen(true),
    },
    Boolean(result),
  )

  if (error === 'not-found') {
    return (
      <div className="card mx-auto max-w-xl p-8 text-center">
        <p className="text-2xl font-semibold tracking-tight">
          This recording is <span className="serif-accent">gone</span>
        </p>
        <p className="mt-2 text-sm text-ink-2">It may have been deleted.</p>
        <Button className="mt-6" icon={ArrowLeft} onClick={() => navigate('/')}>
          Back to the library
        </Button>
      </div>
    )
  }
  if (error) return <p className="card p-6 text-signal">{error}</p>
  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center gap-3 text-ink-3">
        <Spinner /> Loading…
      </div>
    )
  }
  if (!result) return <ProcessingView data={data} onCancel={onCancel} onDelete={onDelete} onRetry={() => job.reprocess(data.options || {})} />

  const name = baseName(result.title)
  const stats = result.stats || {}
  const src = localUrl(id) || (result.has_media ? mediaUrl(id) : null)
  const copyTranscript = async () => {
    try {
      await navigator.clipboard.writeText(toText(result))
      push('Transcript copied', { tone: 'success' })
    } catch {
      push('Clipboard is blocked in this browser', { tone: 'error' })
    }
  }

  return (
    <div className="space-y-6">
      <header className="no-print flex flex-wrap items-start gap-4">
        <IconButton icon={ArrowLeft} tone="ink" size="lg" label="Back to the library" onClick={() => navigate('/')} />
        <div className="min-w-0 flex-1 basis-[calc(100%-4.5rem)] sm:basis-0">
          <p className="eyebrow">
            {data.kind === 'live' ? 'Live meeting' : result.media?.has_video ? 'Video' : 'Audio'} · {formatDate(data.created_at)}
            {result.language ? ` · ${result.language.toUpperCase()}` : ''}
          </p>
          <EditableTitle value={result.title} onSave={job.rename} />
        </div>
        <div className="flex w-full items-center gap-2 sm:w-auto">
          <Menu
            trigger={({ toggle }) => (
              <Button tone="ink" icon={Download} onClick={toggle}>
                Export
              </Button>
            )}
            items={[
              { label: 'Notes (Markdown)', icon: FileText, hint: '.md', onClick: () => download(`${name}.md`, toMarkdown(result), 'text/markdown') },
              {
                label: 'Obsidian note',
                icon: FileText,
                hint: '.md',
                onClick: () => download(`${name}.md`, toMarkdown(result, { frontMatter: true }), 'text/markdown'),
              },
              { label: 'Plain text', icon: FileText, hint: '.txt', onClick: () => download(`${name}.txt`, toText(result)) },
              { label: 'Subtitles', icon: FileText, hint: '.srt', onClick: () => download(`${name}.srt`, toSRT(result)) },
              { label: 'Web captions', icon: FileText, hint: '.vtt', onClick: () => download(`${name}.vtt`, toVTT(result), 'text/vtt') },
              { label: 'Full data', icon: FileText, hint: '.json', onClick: () => download(`${name}.json`, JSON.stringify(result, null, 2), 'application/json') },
              { divider: true },
              { label: 'Copy transcript', icon: Copy, onClick: copyTranscript },
              { label: 'Print / save as PDF', icon: Printer, onClick: () => window.print() },
            ]}
          />
          {result.has_media && <IconButton icon={RefreshCw} label="Reprocess with new settings" onClick={() => setReprocessOpen(true)} />}
          <IconButton icon={Keyboard} label="Keyboard shortcuts (?)" onClick={() => setHelpOpen(true)} className="hidden sm:inline-flex" />
          <IconButton
            icon={Trash2}
            label="Delete recording"
            tone="danger"
            onClick={async () => {
              if (window.confirm(`Delete “${result.title}” and its transcript?`) && (await onDelete(id))) navigate('/')
            }}
          />
        </div>
      </header>

      <div className="no-print grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile label="Duration" value={formatTime(result.media?.duration)} tone="lime" />
        <StatTile label="Scenes" value={stats.scenes ?? 0} tone="ink" />
        <StatTile label="Voices" value={stats.speakers || '—'} />
        <StatTile label="Words" value={(stats.words || 0).toLocaleString()} />
        <StatTile label="To review" value={stats.corrections_pending ?? 0} tone={stats.corrections_pending ? 'signal' : 'surface'} className="col-span-2 sm:col-span-1" />
      </div>

      <div className="no-print space-y-4">
        <Player
          mediaRef={mediaRef}
          src={src}
          result={result}
          now={now}
          initialTime={initialTime}
          onReady={() => setMediaReady((n) => n + 1)}
          captions={captions}
          onCaptions={setCaptions}
        />
        <SceneTrack result={result} now={now} onSeek={seek} colors={colors} />
      </div>

      <div className="no-print">
        <Segmented
          label="Views"
          value={activeTab}
          onChange={setTab}
          className="mb-4 max-w-full overflow-x-auto"
          options={[
            ...(result.keyframes.length ? [{ value: 'timeline', label: 'Timeline' }] : []),
            { value: 'transcript', label: 'Transcript' },
            { value: 'check', label: 'Cross-check', badge: stats.corrections_pending },
            { value: 'speakers', label: 'Speakers', badge: result.speakers.length || null },
          ]}
        />
        {activeTab === 'timeline' && (
          <TimelineTab result={result} activeScene={activeScene} activeSegment={activeSegment} onSeek={seek} colors={colors} />
        )}
        {activeTab === 'transcript' && (
          <TranscriptTab
            result={result}
            now={now}
            activeSegment={activeSegment}
            onSeek={seek}
            colors={colors}
            onEdit={job.editSegment}
            onCorrection={job.correction}
            searchRef={transcriptSearch}
            speakerFilter={speakerFilter}
            setSpeakerFilter={setSpeakerFilter}
          />
        )}
        {activeTab === 'check' && <CrossCheckTab result={result} onSeek={seek} onCorrection={job.correction} onAcceptAll={job.acceptAll} />}
        {activeTab === 'speakers' && (
          <SpeakersTab
            result={result}
            colors={colors}
            onRename={job.renameSpeaker}
            onSeek={seek}
            onShowLines={(speakerId) => {
              setSpeakerFilter(speakerId)
              setTab('transcript')
            }}
            onReprocess={() => setReprocessOpen(true)}
          />
        )}
      </div>

      <PrintView result={result} />
      {reprocessOpen && (
        <ReprocessDialog open={reprocessOpen} onClose={() => setReprocessOpen(false)} job={data} health={health} onSubmit={job.reprocess} />
      )}
      <ShortcutsDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  )
}

function EditableTitle({ value, onSave }) {
  const [editing, setEditing] = useState(false)
  const cls = 'display mt-2 w-full text-[clamp(34px,4.2vw,60px)]'
  if (!editing) {
    return (
      <h1 className={`${cls} cursor-text text-balance`} title="Click to rename" onClick={() => setEditing(true)}>
        {value}
      </h1>
    )
  }
  return (
    <input
      autoFocus
      defaultValue={value}
      aria-label="Recording title"
      onBlur={(e) => {
        const next = e.target.value.trim()
        setEditing(false)
        if (next && next !== value) onSave(next)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') e.currentTarget.blur()
        if (e.key === 'Escape') {
          e.currentTarget.value = value
          e.currentTarget.blur()
        }
      }}
      className={`${cls} rounded-2xl border border-line bg-surface-2 px-3 py-1 outline-none focus:border-ink`}
    />
  )
}

function ProcessingView({ data, onCancel, onDelete, onRetry }) {
  const failed = data.status === 'error' || data.status === 'cancelled'
  const recording = data.status === 'recording'
  return (
    <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
      <div>
        <IconButton icon={ArrowLeft} tone="ink" size="lg" label="Back to the library" onClick={() => navigate('/')} />
        <p className="eyebrow mt-8">
          {recording ? 'Live meeting in progress' : failed ? (data.status === 'cancelled' ? 'Cancelled' : 'Processing failed') : 'Processing'}
        </p>
        <h1 className="display mt-3 text-[clamp(34px,4vw,56px)]">{data.title}</h1>
        {failed ? (
          <>
            {data.error && <p className="mt-6 max-w-lg rounded-2xl bg-signal-pale p-4 text-sm text-signal">{data.error}</p>}
            <div className="mt-6 flex gap-2">
              {data.has_media && (
                <Button icon={RefreshCw} onClick={onRetry}>
                  Try again
                </Button>
              )}
              <Button tone="danger" icon={Trash2} onClick={async () => (await onDelete(data.id)) && navigate('/')}>
                Delete
              </Button>
            </div>
          </>
        ) : recording ? (
          <div className="mt-6">
            <p className="text-sm text-ink-2">This meeting is still being recorded. It is processed at full accuracy as soon as it ends.</p>
            <Button className="mt-5" tone="signal" onClick={() => navigate('/live')}>
              Go to the live meeting
            </Button>
          </div>
        ) : (
          <>
            <div className="display tabular mt-6 text-[clamp(96px,13vw,190px)]">
              {Math.round((data.progress || 0) * 100)}
              <span className="text-[0.35em] tracking-normal">%</span>
            </div>
            <p className="mt-2 font-mono text-sm text-ink-2">
              {data.stage}
              {etaSeconds(data) != null && <span className="text-ink-3"> · {formatEta(etaSeconds(data))}</span>}
            </p>
            <ProgressBar value={data.progress} className="mt-4 max-w-lg text-ink" />
            <Button className="mt-6" tone="ghost" icon={X} onClick={() => onCancel(data.id)}>
              Cancel
            </Button>
          </>
        )}
      </div>
      <NetworkIllustration className="w-full max-w-xl justify-self-center" />
    </div>
  )
}

function ShortcutsDialog({ open, onClose }) {
  const rows = [
    ['K or Space', 'Play / pause'],
    ['J / L', 'Back / forward 5 seconds'],
    ['C', 'Captions on / off'],
    ['/', 'Find in transcript'],
    ['?', 'This list'],
  ]
  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts">
      <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-3 text-sm">
        {rows.map(([keys, what]) => (
          <div key={keys} className="contents">
            <dt>
              <Kbd>{keys}</Kbd>
            </dt>
            <dd className="text-ink-2">{what}</dd>
          </div>
        ))}
      </dl>
    </Dialog>
  )
}
