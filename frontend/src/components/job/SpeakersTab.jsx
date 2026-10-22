import { Play, Users } from 'lucide-react'
import { useMemo } from 'react'
import { formatDuration } from '../../lib/format'
import { Button, EmptyNote } from '../ui'

// Who spoke, for how long; rename voices ("Speaker 2" -> "Priya") everywhere at once.
export default function SpeakersTab({ result, colors, onRename, onSeek, onShowLines, onReprocess }) {
  const stats = useMemo(() => {
    const lines = new Map()
    const first = new Map()
    for (const s of result.segments) {
      if (!s.speaker) continue
      lines.set(s.speaker, (lines.get(s.speaker) || 0) + 1)
      if (!first.has(s.speaker)) first.set(s.speaker, s.start)
    }
    return { lines, first }
  }, [result.segments])
  const total = result.speakers.reduce((sum, s) => sum + (s.talk_time || 0), 0) || 1

  if (!result.speakers.length) {
    return (
      <div className="card space-y-4 p-6">
        <EmptyNote>
          No speakers were identified — speaker identification was off, unavailable, or heard a single voice.
        </EmptyNote>
        <div className="flex justify-center">
          <Button tone="ghost" icon={Users} onClick={onReprocess}>
            Reprocess with speaker identification
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {result.speakers.map((s) => {
        const share = (s.talk_time || 0) / total
        const color = colors.get(s.id)
        return (
          <article key={s.id} className="card p-5">
            <div className="flex items-center gap-3">
              <span className="grid size-11 shrink-0 place-items-center rounded-full text-sm font-semibold" style={{ background: color?.var, color: color?.inkVar }}>
                {s.name.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 2).toUpperCase() || s.id}
              </span>
              <input
                key={s.name}
                defaultValue={s.name}
                aria-label={`Name for ${s.id}`}
                onBlur={(e) => {
                  const name = e.target.value.trim()
                  if (name && name !== s.name) onRename(s.id, name)
                  else e.target.value = s.name
                }}
                onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
                className="min-w-0 flex-1 rounded-xl border border-transparent bg-transparent px-2 py-1 text-lg font-semibold tracking-tight outline-none hover:border-line focus:border-ink focus:bg-surface-2"
              />
            </div>
            <div className="mt-5 flex items-end justify-between gap-4">
              <span className="display tabular text-[44px]">
                {Math.round(share * 100)}
                <span className="text-[0.4em] tracking-normal">%</span>
              </span>
              <span className="pb-1 text-right font-mono text-[11px] text-ink-3">
                {formatDuration(s.talk_time)} · {stats.lines.get(s.id) || 0} lines
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-paper-2">
              <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: color?.var }} />
            </div>
            <div className="mt-4 flex gap-2">
              <Button size="sm" tone="ghost" icon={Play} onClick={() => onSeek(stats.first.get(s.id) || 0)}>
                First words
              </Button>
              <Button size="sm" tone="ghost" onClick={() => onShowLines(s.id)}>
                Show lines
              </Button>
            </div>
          </article>
        )
      })}
      <p className="text-xs text-ink-3 md:col-span-2">
        Voices are told apart automatically; names you type here are used in the transcript, exports and AI notes.
      </p>
    </div>
  )
}
