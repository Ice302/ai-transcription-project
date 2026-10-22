import { AudioLines, Hash, Presentation } from 'lucide-react'
import { formatDate, formatTime, snippetParts } from '../../lib/format'
import { jobPath, navigate } from '../../lib/router'
import { EmptyNote } from '../ui'

const KIND = { speech: AudioLines, screen: Presentation, title: Hash }

// Full-text hits across every transcript and slide, each jumping straight to its moment.
export default function SearchResults({ groups, loading, query }) {
  if (!loading && !groups.length) return <EmptyNote>Nothing matches “{query}” in any transcript or slide.</EmptyNote>
  return (
    <div className="space-y-4">
      {groups.map((group) => (
        <section key={group.job_id} className="card p-5">
          <button type="button" onClick={() => navigate(jobPath(group.job_id))} className="flex w-full items-baseline justify-between gap-3 text-left">
            <h3 className="text-lg font-semibold tracking-tight hover:underline">{group.title}</h3>
            <span className="eyebrow shrink-0">{formatDate(group.created_at, false)}</span>
          </button>
          <ul className="mt-3 divide-y divide-line">
            {group.hits.slice(0, 8).map((hit) => {
              const Icon = KIND[hit.kind] || AudioLines
              return (
                <li key={`${hit.kind}-${hit.ref}`}>
                  <button
                    type="button"
                    onClick={() => navigate(jobPath(group.job_id, hit.kind === 'title' ? null : hit.t))}
                    className="flex w-full items-start gap-3 py-2.5 text-left text-sm hover:bg-paper/60"
                  >
                    <span className="mt-0.5 inline-flex w-16 shrink-0 items-center gap-1.5 font-mono text-[11px] text-ink-3">
                      <Icon className="size-3.5" />
                      {hit.kind === 'title' ? 'title' : formatTime(hit.t)}
                    </span>
                    <span className="min-w-0 flex-1 leading-relaxed text-ink-2">
                      {hit.speaker && <span className="mr-1 font-medium text-ink">{hit.speaker}:</span>}
                      {snippetParts(hit.snippet).map((part, i) =>
                        part.hit ? (
                          <mark key={i} className="rounded bg-lime px-0.5 text-[#131312]">
                            {part.text}
                          </mark>
                        ) : (
                          <span key={i}>{part.text}</span>
                        ),
                      )}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
