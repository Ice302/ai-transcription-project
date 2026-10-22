import { ArrowRight, Check, Pencil, Search, X } from 'lucide-react'
import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { formatTime } from '../../lib/format'
import { Button, EmptyNote, Kbd } from '../ui'

const norm = (s) => s.toLowerCase().replace(/[^\p{L}\p{N}+#]/gu, '')
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Indices of the consecutive words that spell `heard` (mirrors backend crossref._word_run).
function wordRun(words, heard) {
  const target = norm(heard)
  const norms = words.map((w) => norm(w[2]))
  for (let i = 0; i < words.length; i++) {
    if (!norms[i]) continue
    let acc = ''
    for (let j = i; j < Math.min(i + 5, words.length); j++) {
      acc += norms[j]
      if (acc === target) return [i, j]
      if (acc.length >= target.length) break
    }
  }
  return null
}

function Highlighted({ text, regex }) {
  if (!regex) return text
  return text.split(regex).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="rounded bg-lime px-0.5 text-[#131312]">
        {part}
      </mark>
    ) : (
      part
    ),
  )
}

export default function TranscriptTab({ result, now, activeSegment, onSeek, colors, onEdit, onCorrection, searchRef, speakerFilter, setSpeakerFilter }) {
  const [query, setQuery] = useState('')
  const [follow, setFollow] = useState(true)
  const [showUncertain, setShowUncertain] = useState(true)
  const [editing, setEditing] = useState(false)
  const box = useRef(null)

  const names = useMemo(() => new Map(result.speakers.map((s) => [s.id, s.name])), [result.speakers])
  const pendingBySegment = useMemo(() => {
    const map = new Map()
    for (const c of result.corrections) {
      if (c.status !== 'pending') continue
      if (!map.has(c.segment_id)) map.set(c.segment_id, [])
      map.get(c.segment_id).push(c)
    }
    return map
  }, [result.corrections])

  const q = query.trim()
  const regex = useMemo(() => (q ? new RegExp(`(${escapeRe(q)})`, 'gi') : null), [q])
  const lines = useMemo(
    () =>
      result.segments.filter(
        (s) => (!speakerFilter || s.speaker === speakerFilter) && (!q || s.text.toLowerCase().includes(q.toLowerCase())),
      ),
    [result.segments, speakerFilter, q],
  )
  const uncertainCount = result.stats?.low_confidence_words || 0

  // Keep the playing line in view by scrolling only the transcript box, never the page.
  useEffect(() => {
    if (!follow || editing || activeSegment == null) return
    const el = box.current?.querySelector(`[data-seg="${activeSegment}"]`)
    const container = box.current
    if (!el || !container) return
    const top = el.offsetTop - container.offsetTop
    if (top < container.scrollTop + 40 || top > container.scrollTop + container.clientHeight - 80) {
      container.scrollTo({ top: top - container.clientHeight / 3, behavior: 'smooth' })
    }
  }, [activeSegment, follow, editing])

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3 sm:p-4">
        <label className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-3" />
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && (setQuery(''), e.currentTarget.blur())}
            placeholder="Find in transcript"
            aria-label="Find in transcript"
            className="field h-9 rounded-full py-0 pl-10"
          />
        </label>
        {q && <span className="font-mono text-[11px] text-ink-3">{lines.length} lines</span>}
        <div className="flex flex-wrap items-center gap-1.5">
          <ToggleChip active={follow} onClick={() => setFollow((v) => !v)}>
            Follow
          </ToggleChip>
          <ToggleChip active={showUncertain} onClick={() => setShowUncertain((v) => !v)} title="Words the speech model was unsure about">
            Unsure words{uncertainCount ? ` · ${uncertainCount}` : ''}
          </ToggleChip>
          <Button size="sm" tone={editing ? 'ink' : 'ghost'} icon={editing ? Check : Pencil} onClick={() => setEditing((v) => !v)}>
            {editing ? 'Done' : 'Edit'}
          </Button>
        </div>
      </div>
      {result.speakers.length > 1 && (
        <div className="no-scrollbar flex items-center gap-1.5 overflow-x-auto border-b border-line px-3 py-2 sm:px-4">
          <span className="serif-accent mr-1 text-[15px] text-ink-3">voices</span>
          <ToggleChip active={!speakerFilter} onClick={() => setSpeakerFilter(null)}>
            Everyone
          </ToggleChip>
          {result.speakers.map((s) => (
            <ToggleChip key={s.id} active={speakerFilter === s.id} onClick={() => setSpeakerFilter(speakerFilter === s.id ? null : s.id)}>
              <span className="size-2 rounded-full" style={{ background: colors.get(s.id)?.var }} />
              {s.name}
            </ToggleChip>
          ))}
        </div>
      )}
      {editing && (
        <p className="border-b border-line bg-lime-pale px-4 py-2 text-xs text-ink-2">
          Click a line to edit it; changes save when you leave the line (<Kbd>Ctrl</Kbd> + <Kbd>Enter</Kbd> saves, <Kbd>Esc</Kbd> cancels). Edited lines lose
          word-level timing.
        </p>
      )}
      <div ref={box} className="scroll-thin relative max-h-[68vh] overflow-y-auto p-2 sm:p-3">
        {lines.length === 0 ? (
          <div className="p-4">
            <EmptyNote>{q ? `No line contains “${q}”.` : 'No speech was detected in this recording.'}</EmptyNote>
          </div>
        ) : (
          lines.map((s) => (
            <Line
              key={s.id}
              seg={s}
              name={names.get(s.speaker)}
              color={colors.get(s.speaker)}
              active={s.id === activeSegment}
              now={s.id === activeSegment ? now : null}
              showUncertain={showUncertain}
              corrections={pendingBySegment.get(s.id)}
              regex={regex}
              editing={editing}
              speakers={result.speakers}
              onSeek={onSeek}
              onEdit={onEdit}
              onCorrection={onCorrection}
            />
          ))
        )}
      </div>
    </div>
  )
}

function ToggleChip({ active, onClick, children, title }) {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition ${
        active ? 'border-ink bg-ink text-on-ink' : 'border-line text-ink-2 hover:border-ink hover:text-ink'
      }`}
    >
      {children}
    </button>
  )
}

const Line = memo(function Line({ seg, name, color, active, now, showUncertain, corrections, regex, editing, speakers, onSeek, onEdit, onCorrection }) {
  const suspect = useMemo(() => {
    const set = new Set()
    if (seg.words && corrections) {
      for (const c of corrections) {
        const run = wordRun(seg.words, c.heard)
        if (run) for (let i = run[0]; i <= run[1]; i++) set.add(i)
      }
    }
    return set
  }, [seg.words, corrections])

  return (
    <div
      data-seg={seg.id}
      className={`group grid grid-cols-[52px_minmax(0,1fr)] gap-x-3 rounded-2xl px-2 py-2 transition sm:grid-cols-[60px_132px_minmax(0,1fr)] ${
        active ? 'bg-lime-pale' : 'hover:bg-paper/70'
      }`}
    >
      <button type="button" onClick={() => onSeek(seg.start)} className="self-start pt-0.5 text-left font-mono text-[11px] text-ink-3 hover:text-ink">
        {formatTime(seg.start)}
      </button>
      <div className="col-start-2 row-start-1 hidden self-start pt-px sm:col-start-auto sm:row-start-auto sm:block">
        {editing && speakers.length > 0 ? (
          <select
            value={seg.speaker || ''}
            onChange={(e) => onEdit(seg.id, { text: seg.text, speaker: e.target.value })}
            aria-label="Speaker"
            className="w-full truncate rounded-full border border-line bg-surface-2 px-2 py-0.5 text-xs"
          >
            <option value="">—</option>
            {speakers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        ) : (
          name && (
            <span className="inline-flex max-w-full items-center gap-1.5 truncate text-xs font-semibold text-ink-2">
              <span className="size-2.5 shrink-0 rounded-full" style={{ background: color?.var }} />
              <span className="truncate">{name}</span>
            </span>
          )
        )}
      </div>
      <div className="col-start-2 min-w-0 sm:col-start-auto">
        {name && !editing && <span className="mr-1 text-xs font-semibold text-ink-2 sm:hidden">{name}:</span>}
        {editing ? (
          <EditableText seg={seg} onSave={(text) => onEdit(seg.id, { text })} />
        ) : (
          <p className="text-[15px] leading-relaxed text-ink">
            {seg.words && !seg.edited ? (
              seg.words.map(([start, end, text, prob], i) => {
                const lead = text.match(/^\s*/)[0]
                const word = text.slice(lead.length)
                const speaking = now != null && now >= start && now < end + 0.08
                const cls = [
                  'rounded-[4px] cursor-pointer',
                  speaking ? 'bg-lime text-[#131312] box-decoration-clone' : 'hover:bg-line/60',
                  suspect.has(i) ? 'word-suspect' : showUncertain && prob < 0.5 ? 'word-uncertain' : '',
                ].join(' ')
                return (
                  <span key={i}>
                    {lead}
                    <span
                      className={cls}
                      onClick={() => onSeek(start)}
                      title={prob < 0.5 ? `Speech model confidence ${Math.round(prob * 100)}%` : undefined}
                    >
                      <Highlighted text={word} regex={regex} />
                    </span>
                  </span>
                )
              })
            ) : (
              <span onClick={() => onSeek(seg.start)} className="cursor-pointer">
                <Highlighted text={seg.text} regex={regex} />
                {seg.edited && <span className="ml-1.5 align-middle font-mono text-[10px] text-ink-3">edited</span>}
              </span>
            )}
          </p>
        )}
        {corrections?.length > 0 && !editing && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {corrections.map((c) => (
              <span key={c.id} className="inline-flex items-center gap-1.5 rounded-full border border-signal/40 bg-signal-pale py-0.5 pl-2.5 pr-1 text-xs text-ink">
                <span className="text-signal line-through decoration-1">{c.heard}</span>
                <ArrowRight className="size-3 text-ink-3" />
                <span className="font-semibold">{c.seen}</span>
                <span className="text-ink-3">on screen</span>
                <button type="button" onClick={() => onCorrection(c.id, 'accept')} className="rounded-full bg-ink px-2 py-0.5 text-[11px] font-semibold text-on-ink hover:bg-ink-2">
                  Fix
                </button>
                <button type="button" aria-label="Dismiss suggestion" onClick={() => onCorrection(c.id, 'dismiss')} className="rounded-full p-0.5 text-ink-3 hover:text-ink">
                  <X className="size-3.5" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
})

function EditableText({ seg, onSave }) {
  const ref = useRef(null)
  const resize = () => {
    const el = ref.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${el.scrollHeight}px`
    }
  }
  useEffect(resize, [])
  return (
    <textarea
      ref={ref}
      defaultValue={seg.text}
      rows={1}
      onInput={resize}
      onBlur={(e) => {
        const text = e.target.value.trim()
        if (text && text !== seg.text) onSave(text)
        else e.target.value = seg.text
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.currentTarget.value = seg.text
          e.currentTarget.blur()
        } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) e.currentTarget.blur()
      }}
      className="w-full resize-none rounded-xl border border-line bg-surface-2 px-3 py-1.5 text-[15px] leading-relaxed outline-none focus:border-ink"
    />
  )
}
