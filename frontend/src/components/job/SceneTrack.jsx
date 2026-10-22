import { useMemo } from 'react'
import { formatTime } from '../../lib/format'
import { pastel } from '../../lib/palette'

// Speaker turns: consecutive segments of one speaker with short gaps merge into one bar.
function turnsOf(segments) {
  const turns = []
  for (const s of segments) {
    const last = turns[turns.length - 1]
    if (last && last.speaker === s.speaker && s.start - last.end < 1.5) last.end = s.end
    else turns.push({ speaker: s.speaker, start: s.start, end: s.end })
  }
  return turns
}

// The Gantt-style board of the flat reference, as a timeline: what was on screen, who
// was talking, and where the transcript disagrees with the screen.
export default function SceneTrack({ result, now, onSeek, colors }) {
  const duration = Math.max(result.media?.duration || 0, result.segments.at(-1)?.end || 0, 1)
  const turns = useMemo(() => turnsOf(result.segments), [result.segments])
  const pct = (t) => `${(Math.max(0, Math.min(t, duration)) / duration) * 100}%`
  const width = (a, b) => `${Math.max(0.25, ((Math.min(b, duration) - a) / duration) * 100)}%`
  const pending = result.corrections.filter((c) => c.status === 'pending')

  const seekFromEvent = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    onSeek(((e.clientX - rect.left) / rect.width) * duration)
  }

  const rows = [
    result.keyframes.length > 0 && {
      label: 'screen',
      body: result.keyframes.map((kf) => (
        <span
          key={kf.id}
          title={`${kf.title || `Scene ${kf.id + 1}`} · ${formatTime(kf.t)}–${formatTime(kf.end)}`}
          className="absolute inset-y-0 overflow-hidden rounded-md border-r-2 border-surface px-1.5 font-mono text-[10px] leading-7"
          style={{ left: pct(kf.t), width: width(kf.t, kf.end), background: pastel(kf.id).var, color: pastel(kf.id).inkVar }}
        >
          {String(kf.id + 1).padStart(2, '0')}
        </span>
      )),
    },
    {
      label: 'voices',
      body: turns.map((turn, i) => (
        <span
          key={i}
          title={`${result.speakers.find((s) => s.id === turn.speaker)?.name || 'Speech'} · ${formatTime(turn.start)}`}
          className="absolute inset-y-1 rounded-full"
          style={{ left: pct(turn.start), width: width(turn.start, turn.end), background: colors.get(turn.speaker)?.var || 'var(--tt-ink)' }}
        />
      )),
    },
    pending.length > 0 && {
      label: 'fixes',
      body: pending.map((c) => (
        <span
          key={c.id}
          title={`${formatTime(c.t)} heard “${c.heard}”, screen shows “${c.seen}”`}
          className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 bg-signal"
          style={{ left: pct(c.t) }}
        />
      )),
    },
  ].filter(Boolean)

  return (
    <div className="card p-4 sm:p-5">
      <div className="grid grid-cols-[56px_minmax(0,1fr)] items-center gap-x-3 gap-y-2">
        {rows.map((row) => (
          <div key={row.label} className="contents">
            <span className="serif-accent text-right text-[15px] text-ink-2">{row.label}</span>
            <div
              role="slider"
              tabIndex={-1}
              aria-label={`${row.label} timeline`}
              aria-valuemin={0}
              aria-valuemax={Math.round(duration)}
              aria-valuenow={Math.round(now)}
              onClick={seekFromEvent}
              className="relative h-7 cursor-pointer overflow-hidden rounded-lg bg-paper-2"
            >
              {row.body}
              <span className="pointer-events-none absolute inset-y-0 w-0.5 bg-ink" style={{ left: pct(now) }} />
            </div>
          </div>
        ))}
        <span />
        <div className="flex justify-between font-mono text-[10px] text-ink-3">
          {[0, 0.25, 0.5, 0.75, 1].map((f) => (
            <span key={f}>{formatTime(duration * f)}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
