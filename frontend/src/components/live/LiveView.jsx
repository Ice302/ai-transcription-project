import { ArrowUpRight, Copy, Mic, MicOff, Monitor, MonitorUp, Square, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useToast } from '../../hooks/toast'
import { apiUrl } from '../../lib/api'
import { formatClock, formatTime } from '../../lib/format'
import { LANGUAGES } from '../../lib/languages'
import { liveToPlainText } from '../../lib/liveContext'
import { colorForLabel } from '../../lib/palette'
import { jobPath, navigate } from '../../lib/router'
import { NetworkIllustration } from '../Art'
import { Button, Chip, IconButton, Segmented, Switch } from '../ui'

const KEY = 'tt-live-settings'
const SOURCES = [
  { value: 'system', label: 'Tab / screen', icon: MonitorUp },
  { value: 'both', label: 'Tab + mic', icon: Monitor },
  { value: 'mic', label: 'Microphone', icon: Mic },
]

function loadSettings() {
  try {
    return { source: 'both', captureScreen: true, separate: true, ...JSON.parse(localStorage.getItem(KEY) || '{}') }
  } catch {
    return { source: 'both', captureScreen: true, separate: true }
  }
}

export default function LiveView({ live, health }) {
  const { status, events, partials, muted, error, info, elapsed, lag, savedJobId, start, stop, setMute } = live
  const [settings, setSettings] = useState(loadSettings)
  const [title, setTitle] = useState('')
  const [language, setLanguage] = useState('')
  const [glossary, setGlossary] = useState('')
  const push = useToast()
  const feed = useRef(null)
  const idle = status === 'idle'
  const screenAvailable = settings.source !== 'mic'

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(settings))
    } catch {
      /* per-browser convenience only */
    }
  }, [settings])

  // Auto-scroll only when the reader is already near the bottom.
  useEffect(() => {
    const el = feed.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight
  }, [events, partials])

  const set = (key) => (value) => setSettings((s) => ({ ...s, [key]: value }))
  const begin = () =>
    start({
      source: settings.source,
      captureScreen: settings.captureScreen && screenAvailable,
      separate: settings.separate && settings.source === 'both',
      glossary,
      title,
      language,
    })
  const statusLabel = { idle: 'Ready', connecting: 'Connecting…', live: muted ? 'Paused' : 'Recording', finishing: 'Finishing up…' }[status]
  const pendingPartials = Object.values(partials).filter(Boolean)

  return (
    <div className="space-y-6">
      <section className="card relative overflow-hidden p-6 sm:p-8">
        <div className="dot-grid pointer-events-none absolute -right-10 -top-10 size-72 opacity-60 mask-[radial-gradient(circle,black,transparent_70%)]" />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <Segmented size="sm" label="Audio source" value={settings.source} onChange={(v) => idle && set('source')(v)} options={SOURCES.map((s) => ({ ...s, disabled: !idle && s.value !== settings.source }))} />
          <div className="flex items-center gap-2">
            {status === 'live' && (
              <IconButton icon={muted ? MicOff : Mic} label={muted ? 'Resume transcription' : 'Pause transcription'} tone={muted ? 'lime' : 'ghost'} onClick={() => setMute(!muted)} />
            )}
            {idle ? (
              <Button size="lg" tone="ink" onClick={begin} disabled={health?.status !== 'ok'} className="pl-4">
                <span className="size-3 rounded-full bg-signal" />
                Start listening
              </Button>
            ) : (
              <Button size="lg" tone="signal" icon={Square} onClick={stop} loading={status === 'finishing' || status === 'connecting'}>
                {status === 'finishing' ? 'Saving…' : 'End meeting'}
              </Button>
            )}
          </div>
        </div>

        {/* Big clock + info column, separated by a hairline (calendar reference). */}
        <div className="relative mt-8 flex flex-wrap items-end gap-x-8 gap-y-4">
          <div>
            <p className="eyebrow flex items-center gap-2">
              {status === 'live' && !muted && <span className="size-2 animate-pulse rounded-full bg-signal" />}
              {statusLabel}
            </p>
            <div className="display tabular mt-2 text-[clamp(64px,10.5vw,164px)]">{formatClock(elapsed)}</div>
          </div>
          <dl className="mb-3 space-y-3 border-l border-line-2 pl-6 text-sm">
            {[
              ['Source', SOURCES.find((s) => s.value === settings.source)?.label + (settings.source === 'both' && settings.separate ? ' · you & others apart' : '')],
              ['Model', info ? `${info.model} · live preview` : health?.live_model || '—'],
              ['Delay', status === 'live' ? `${lag.toFixed(1)} s behind` : '—'],
            ].map(([label, value]) => (
              <div key={label}>
                <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">{label}</dt>
                <dd className="font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {idle && (
          <div className="relative mt-8 grid gap-4 border-t border-line pt-6 md:grid-cols-2">
            <label className="text-sm">
              <span className="eyebrow mb-1.5 block">Meeting title</span>
              <input className="field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Weekly product sync" />
            </label>
            <label className="text-sm">
              <span className="eyebrow mb-1.5 block">Language</span>
              <select className="field" value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGUAGES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm md:col-span-2">
              <span className="eyebrow mb-1.5 block">Names & terms (optional)</span>
              <input className="field" value={glossary} onChange={(e) => setGlossary(e.target.value)} placeholder="Attendees, products, jargon — comma separated" />
            </label>
            <Switch
              checked={settings.captureScreen && screenAvailable}
              onChange={set('captureScreen')}
              disabled={!screenAvailable}
              label="Read the shared screen"
              description="Slides and shared windows are read and used to spell names right."
            />
            <Switch
              checked={settings.separate && settings.source === 'both'}
              onChange={set('separate')}
              disabled={settings.source !== 'both'}
              label="Keep you and others apart"
              description="Your mic and the meeting audio are transcribed separately. Use headphones for best results."
            />
            <p className="text-xs text-ink-3 md:col-span-2">
              In the browser’s share dialog pick the meeting tab and tick <b>Share tab audio</b>. Everything is saved to the library as you go and
              re-transcribed at full accuracy, with speakers, when the meeting ends.
            </p>
          </div>
        )}
      </section>

      {error && (
        <p className="flex items-center gap-2 rounded-2xl border border-signal/40 bg-signal-pale px-4 py-3 text-sm text-signal">
          <TriangleAlert className="size-4 shrink-0" /> {error}
        </p>
      )}

      {savedJobId && idle && (
        <section className="animate-rise flex flex-wrap items-center gap-4 rounded-card bg-lime p-5 text-[#131312]">
          <div className="min-w-0 flex-1">
            <p className="font-semibold">Saved to the library.</p>
            <p className="text-sm opacity-75">The full-accuracy transcript with speaker names and slides is being prepared.</p>
          </div>
          <Button tone="ink" icon={ArrowUpRight} onClick={() => navigate(jobPath(savedJobId))}>
            Open
          </Button>
        </section>
      )}

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="text-xl font-semibold tracking-tight">
            The <span className="serif-accent text-[1.15em]">transcript</span>
            <span className="ml-2 font-mono text-xs font-normal text-ink-3">{events.filter((e) => e.kind === 'speech').length} lines</span>
          </h2>
          {events.length > 0 && (
            <Button
              size="sm"
              tone="ghost"
              icon={Copy}
              onClick={() =>
                navigator.clipboard
                  .writeText(liveToPlainText(events))
                  .then(() => push('Meeting notes copied', { tone: 'success' }))
                  .catch(() => push('Clipboard is blocked', { tone: 'error' }))
              }
            >
              Copy
            </Button>
          )}
        </div>
        <div ref={feed} aria-live="polite" className="scroll-thin max-h-[60vh] min-h-72 overflow-y-auto p-4 sm:p-5">
          {events.length === 0 && pendingPartials.length === 0 ? (
            <div className="grid items-center gap-6 py-6 md:grid-cols-[1fr_1.2fr]">
              <p className="text-sm leading-relaxed text-ink-2">
                {status === 'live'
                  ? 'Listening… the first sentences appear within a couple of seconds.'
                  : 'Pick a source and press Start. Speech appears here as it is spoken; screen changes appear as cards.'}
              </p>
              <NetworkIllustration className="w-full" />
            </div>
          ) : (
            <div className="space-y-1">
              {events.map((e) => (
                <FeedItem key={e.key} event={e} />
              ))}
              {pendingPartials.map((p) => (
                <p key={`partial-${p.speaker || ''}`} className="flex gap-3 px-2 py-1 text-[15px] italic leading-relaxed text-ink-3">
                  <span className="w-12 shrink-0 font-mono text-[11px] not-italic">{formatTime(p.t)}</span>
                  <span>
                    {p.speaker && <span className="mr-1 font-semibold not-italic">{p.speaker}:</span>}
                    {p.text}
                  </span>
                </p>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function FeedItem({ event: e }) {
  if (e.kind === 'speech') {
    const color = colorForLabel(e.speaker)
    return (
      <p className="animate-rise flex gap-3 rounded-xl px-2 py-1 text-[15px] leading-relaxed">
        <span className="w-12 shrink-0 pt-0.5 font-mono text-[11px] text-ink-3">{formatTime(e.t)}</span>
        <span className="min-w-0">
          {e.speaker && (
            <span className="mr-1.5 inline-flex items-center gap-1.5 font-semibold">
              <span className="size-2.5 rounded-full" style={{ background: color.var }} />
              {e.speaker}:
            </span>
          )}
          {e.text}
        </span>
      </p>
    )
  }
  if (e.kind === 'visual') {
    return (
      <div className="animate-rise relative my-3 flex flex-col gap-4 rounded-2xl border border-line bg-paper p-3 sm:flex-row">
        <span className="absolute -left-1 -top-1 size-3 bg-signal" aria-hidden />
        {e.image && <img src={apiUrl(e.image)} alt="" className="w-full shrink-0 self-start rounded-xl border border-line sm:w-48" />}
        <div className="min-w-0">
          <p className="flex items-center gap-2">
            <span className="border border-line-2 bg-surface-2 px-2 font-serif text-[17px] leading-7">screen</span>
            <span className="font-mono text-[11px] text-ink-3">{formatTime(e.t)}</span>
          </p>
          {e.title && <p className="mt-2 font-semibold tracking-tight">{e.title}</p>}
          <p className="mt-1 line-clamp-4 whitespace-pre-line text-xs leading-relaxed text-ink-2">{e.text}</p>
          {e.terms?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {e.terms.slice(0, 8).map((t) => (
                <Chip key={t}>{t}</Chip>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }
  return (
    <p className="pl-17 text-xs text-ink-2">
      ↳ heard “<span className="text-signal line-through">{e.heard}</span>” — screen shows <b>{e.seen}</b>
    </p>
  )
}
