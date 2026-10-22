import { ArrowRight, CheckCheck, Eye, Play, RotateCcw, X } from 'lucide-react'
import { useMemo } from 'react'
import { formatTime } from '../../lib/format'
import { describeDetection, languageName } from '../../lib/languages'
import { pastel } from '../../lib/palette'
import { Button, Chip, EmptyNote } from '../ui'

// Where speech and screen disagree, what was shown but never said, and the vocabulary
// that steered the speech model.
export default function CrossCheckTab({ result, onSeek, onCorrection, onAcceptAll }) {
  const groups = useMemo(() => {
    const by = { pending: [], accepted: [], dismissed: [], stale: [] }
    for (const c of result.corrections) (by[c.status] || by.pending).push(c)
    return by
  }, [result.corrections])
  const segText = useMemo(() => new Map(result.segments.map((s) => [s.id, s.text])), [result.segments])
  const highCount = groups.pending.filter((c) => c.confidence === 'high').length
  const unspoken = result.keyframes.filter((k) => k.terms_unspoken?.length && k.duplicate_of == null)

  return (
    <div className="space-y-6">
      <section className="card p-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow">Speech vs. screen</p>
            <h3 className="mt-1 text-2xl font-semibold tracking-tight">
              Suggested <span className="serif-accent text-[1.15em]">fixes</span>
            </h3>
            <p className="mt-1 max-w-xl text-sm text-ink-2">
              Spoken words that closely match a term visible on screen at the same moment. Accepting one rewrites that line; the AI notes pick
              up the change.
            </p>
          </div>
          {highCount > 0 && (
            <Button tone="lime" icon={CheckCheck} onClick={() => onAcceptAll('high')}>
              Accept {highCount} high-confidence
            </Button>
          )}
        </div>
        <div className="mt-5 space-y-2">
          {groups.pending.length === 0 && groups.accepted.length === 0 && groups.dismissed.length === 0 ? (
            <EmptyNote>
              {result.keyframes.length
                ? 'Speech and screen agree — nothing to fix.'
                : 'No on-screen text to compare with. Add names & terms and reprocess to check spellings.'}
            </EmptyNote>
          ) : (
            [...groups.pending, ...groups.accepted, ...groups.dismissed, ...groups.stale].map((c) => (
              <CorrectionRow key={c.id} c={c} context={segText.get(c.segment_id)} onSeek={onSeek} onCorrection={onCorrection} />
            ))
          )}
        </div>
      </section>

      {unspoken.length > 0 && (
        <section className="card p-5 sm:p-6">
          <p className="eyebrow">Content the audio misses</p>
          <h3 className="mt-1 text-2xl font-semibold tracking-tight">
            Shown, <span className="serif-accent text-[1.15em]">never said</span>
          </h3>
          <ul className="mt-4 space-y-2">
            {unspoken.map((k) => (
              <li key={k.id}>
                <button type="button" onClick={() => onSeek(k.t)} className="flex w-full flex-wrap items-center gap-2 rounded-2xl px-2 py-1.5 text-left hover:bg-paper">
                  <span className={`rounded-full px-2 py-0.5 font-mono text-[11px] ${pastel(k.id).bg} ${pastel(k.id).ink}`}>{String(k.id + 1).padStart(2, '0')}</span>
                  <span className="text-sm font-medium">{k.title || `Scene ${k.id + 1}`}</span>
                  <span className="ml-auto flex flex-wrap gap-1">
                    {k.terms_unspoken.slice(0, 10).map((t) => (
                      <Chip key={t}>
                        <Eye className="size-3" /> {t}
                      </Chip>
                    ))}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="grid gap-4 md:grid-cols-2">
        <div className="card p-5 sm:p-6">
          <p className="eyebrow">Spelling hints given to the speech model</p>
          {result.glossary ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {result.glossary.split(', ').map((t) => (
                <Chip key={t} tone="pale">
                  {t}
                </Chip>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-3">None — no on-screen text and no names & terms were given.</p>
          )}
        </div>
        <div className="card p-5 sm:p-6">
          <p className="eyebrow">How this was made</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-ink-3">Speech model</dt>
            <dd className="font-medium">
              {result.model} <span className="text-ink-3">({result.device === 'cuda' ? 'GPU' : 'CPU'})</span>
            </dd>
            <dt className="text-ink-3">Language</dt>
            <dd className="font-medium">
              {languageName(result.language) || '—'}
              {result.language_probability && result.language_detection?.method !== 'chosen' ? (
                <span className="text-ink-3"> · {Math.round(result.language_probability * 100)}%</span>
              ) : null}
              {describeDetection(result.language_detection) && (
                <span className="mt-0.5 block text-xs font-normal text-ink-3">
                  {describeDetection(result.language_detection)}. Wrong? Reprocess and pick the language.
                </span>
              )}
            </dd>
            {Object.entries(result.timings || {}).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-ink-3">{k.replace(/_/g, ' ')}</dt>
                <dd className="font-mono text-xs tabular">{v}s</dd>
              </div>
            ))}
          </dl>
        </div>
        {result.screen_chrome?.length > 0 && (
          <div className="card p-5 sm:p-6 md:col-span-2">
            <p className="eyebrow">Interface text left out</p>
            <p className="mt-1 max-w-2xl text-sm text-ink-2">
              On screen nearly all the time (video-call buttons, participant names, toolbars), so it was kept out of scene text, spelling hints and
              the assistant’s context.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {result.screen_chrome.map((t) => (
                <Chip key={t}>{t}</Chip>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

function CorrectionRow({ c, context, onSeek, onCorrection }) {
  const done = c.status !== 'pending'
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border p-3 sm:p-4 ${done ? 'border-line opacity-70' : 'border-line-2 bg-surface-2'}`}>
      <button type="button" onClick={() => onSeek(c.t)} className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-3 hover:text-ink">
        <Play className="size-3" /> {formatTime(c.t)}
      </button>
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <span className={`text-[17px] ${c.status === 'accepted' ? 'text-ink-3 line-through' : 'text-signal line-through decoration-2'}`}>{c.heard}</span>
        <ArrowRight className="size-4 text-ink-3" />
        <span className="rounded-full bg-lime px-2.5 py-0.5 text-[15px] font-semibold text-[#131312]">{c.seen}</span>
        <Chip tone={c.confidence === 'high' ? 'ink' : 'line'}>{c.confidence} confidence</Chip>
        <span className="font-mono text-[11px] text-ink-3">
          {Math.round(c.similarity * 100)}% alike{c.probability != null ? ` · heard with ${Math.round(c.probability * 100)}% certainty` : ''}
        </span>
        {context && <p className="w-full truncate text-xs text-ink-3">“{context}”</p>}
      </div>
      <div className="flex items-center gap-2">
        {c.status === 'pending' && (
          <>
            <Button size="sm" tone="ink" onClick={() => onCorrection(c.id, 'accept')}>
              Fix
            </Button>
            <Button size="sm" tone="ghost" icon={X} onClick={() => onCorrection(c.id, 'dismiss')}>
              Dismiss
            </Button>
          </>
        )}
        {c.status === 'accepted' && <Chip tone="lime">Applied</Chip>}
        {c.status === 'stale' && <Chip tone="signal">Text changed</Chip>}
        {c.status === 'dismissed' && (
          <Button size="sm" tone="ghost" icon={RotateCcw} onClick={() => onCorrection(c.id, 'reset')}>
            Undo
          </Button>
        )}
      </div>
    </div>
  )
}
