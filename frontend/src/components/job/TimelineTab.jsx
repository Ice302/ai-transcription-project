import { Check, Eye } from 'lucide-react'
import { memo, useMemo } from 'react'
import { apiUrl } from '../../lib/api'
import { formatTime } from '../../lib/format'
import { pastel } from '../../lib/palette'

// Scenes as stacked pastel cards (calendar reference): a big scene number, the slide
// title, what was on screen, and what was said while it was showing.
export default function TimelineTab({ result, activeScene, activeSegment, onSeek, colors }) {
  const bySceneId = useMemo(() => {
    const map = new Map()
    for (const s of result.segments) {
      if (!map.has(s.scene_id)) map.set(s.scene_id, [])
      map.get(s.scene_id).push(s)
    }
    return map
  }, [result.segments])
  const names = useMemo(() => new Map(result.speakers.map((s) => [s.id, s.name])), [result.speakers])

  return (
    <div className="space-y-4">
      {result.keyframes.map((kf) => (
        <SceneCard
          key={kf.id}
          kf={kf}
          segments={bySceneId.get(kf.id) || []}
          active={kf.id === activeScene}
          activeSegment={kf.id === activeScene ? activeSegment : null}
          onSeek={onSeek}
          names={names}
          colors={colors}
        />
      ))}
    </div>
  )
}

const SceneCard = memo(function SceneCard({ kf, segments, active, activeSegment, onSeek, names, colors }) {
  const p = pastel(kf.id)
  const lines = (kf.ocr_text || '').split('\n').filter((l) => l.trim() && l.trim() !== kf.title)
  return (
    <article
      id={`scene-${kf.id}`}
      className={`scroll-mt-24 rounded-card p-5 transition sm:p-6 ${p.bg} ${p.ink} ${active ? 'ring-[3px] ring-ink ring-offset-2 ring-offset-paper' : ''}`}
    >
      <div className="grid gap-5 md:grid-cols-[minmax(0,1fr)_minmax(180px,260px)]">
        <div className="min-w-0">
          <div className="flex items-start gap-4">
            <button type="button" onClick={() => onSeek(kf.t)} className="display tabular text-[64px] leading-[0.8] hover:opacity-70" aria-label={`Play scene ${kf.id + 1}`}>
              {String(kf.id + 1).padStart(2, '0')}
            </button>
            <div className="min-w-0 pt-0.5">
              <span className="font-mono text-[11px] uppercase tracking-[0.12em] opacity-70">
                {formatTime(kf.t)} – {formatTime(kf.end)}
                {kf.duplicate_of != null && ` · same slide as ${String(kf.duplicate_of + 1).padStart(2, '0')}`}
              </span>
              <h3 className="mt-1 text-[22px] font-semibold leading-tight tracking-tight">{kf.title || 'Untitled scene'}</h3>
            </div>
          </div>
          {lines.length > 0 && (
            <ul className="mt-4 space-y-1 text-sm">
              {lines.slice(0, 8).map((line, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className="mt-[7px] size-2 shrink-0 bg-signal" aria-hidden />
                  <span className="leading-snug">{line}</span>
                </li>
              ))}
              {lines.length > 8 && <li className="pl-4.5 text-xs opacity-70">+ {lines.length - 8} more lines on screen</li>}
            </ul>
          )}
          {kf.caption && <p className="serif-accent mt-3 text-[17px] leading-snug opacity-90">“{kf.caption}”</p>}
          {(kf.terms_confirmed?.length > 0 || kf.terms_unspoken?.length > 0) && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {kf.terms_confirmed?.map((t) => (
                <span key={`c-${t}`} title="On screen and spoken" className="inline-flex items-center gap-1 rounded-full bg-ink px-2.5 py-0.5 text-[11px] font-medium text-on-ink">
                  <Check className="size-3 text-lime" strokeWidth={3} /> {t}
                </span>
              ))}
              {kf.terms_unspoken?.slice(0, 8).map((t) => (
                <span
                  key={`u-${t}`}
                  title="On screen but never spoken - included in AI notes"
                  className="inline-flex items-center gap-1 rounded-full border border-current/30 px-2.5 py-0.5 text-[11px] font-medium"
                >
                  <Eye className="size-3" /> {t}
                </span>
              ))}
            </div>
          )}
        </div>
        <button type="button" onClick={() => onSeek(kf.t)} className="group self-start overflow-hidden rounded-2xl border border-current/20 bg-black/10">
          <img src={apiUrl(kf.image)} alt={kf.title ? `Slide: ${kf.title}` : `Scene ${kf.id + 1}`} loading="lazy" className="aspect-video w-full object-cover transition group-hover:scale-[1.03]" />
        </button>
      </div>

      {segments.length > 0 && (
        <div className="mt-5 space-y-0.5 border-t border-current/20 pt-3">
          {segments.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onSeek(s.start)}
              className={`flex w-full gap-3 rounded-xl px-2 py-1 text-left text-[14.5px] leading-relaxed transition ${s.id === activeSegment ? 'bg-black/12' : 'hover:bg-black/6'}`}
            >
              <span className="w-11 shrink-0 pt-0.5 font-mono text-[11px] opacity-70">{formatTime(s.start)}</span>
              <span className="min-w-0">
                {s.speaker && (
                  <span className="mr-1.5 inline-flex items-center gap-1 font-semibold">
                    <span className="size-2 rounded-full ring-1 ring-current/30" style={{ background: colors.get(s.speaker)?.var }} />
                    {names.get(s.speaker)}:
                  </span>
                )}
                {s.text}
              </span>
            </button>
          ))}
        </div>
      )}
    </article>
  )
})
