import { AudioLines, Check, Film, MoreHorizontal, Pencil, Radio, Trash2, Upload, X } from 'lucide-react'
import { formatDate, formatTime } from '../../lib/format'
import { pastel } from '../../lib/palette'
import { etaSeconds, formatEta } from '../../lib/uploads'
import { jobPath, navigate } from '../../lib/router'
import { Menu, ProgressBar } from '../ui'

const KIND_ICON = { live: Radio, video: Film, audio: AudioLines }

// A recording in the library: pastel card with a big duration numeral (calendar reference)
// and a round select circle (the check circles of the flat reference) for the assistant.
export default function JobCard({ job, index, selected, onSelect, onCancel, onDelete, onRename }) {
  const p = pastel(index)
  const kind = job.kind === 'live' ? 'live' : job.media?.has_video ? 'video' : 'audio'
  const KindIcon = KIND_ICON[kind]
  const busy = ['queued', 'running', 'recording'].includes(job.status)
  const stats = job.stats || {}
  const open = () => navigate(jobPath(job.id))

  return (
    <article
      className={`group relative flex min-h-[236px] flex-col rounded-card p-5 transition ${p.bg} ${p.ink} ${
        selected ? 'ring-[3px] ring-ink ring-offset-2 ring-offset-paper' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] opacity-75">
          <KindIcon className="size-3.5" />
          {kind} · {formatDate(job.created_at)}
        </span>
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          {job.status === 'done' && (
            <button
              type="button"
              aria-pressed={selected}
              aria-label={selected ? 'Remove from assistant' : 'Ask the assistant about this recording'}
              title={selected ? 'Selected for the assistant' : 'Select for the assistant'}
              onClick={() => onSelect(job.id)}
              className={`grid size-7 place-items-center rounded-full border-2 transition ${
                selected ? 'border-ink bg-ink text-lime' : 'border-current/40 opacity-60 hover:opacity-100'
              }`}
            >
              {selected && <Check className="size-4" strokeWidth={3} />}
            </button>
          )}
          <Menu
            trigger={({ toggle }) => (
              <button type="button" aria-label="More actions" onClick={toggle} className="grid size-7 place-items-center rounded-full opacity-60 hover:bg-black/10 hover:opacity-100">
                <MoreHorizontal className="size-4" />
              </button>
            )}
            items={[
              {
                label: 'Rename',
                icon: Pencil,
                onClick: () => {
                  const title = window.prompt('Rename recording', job.title)
                  if (title?.trim()) onRename(job.id, title.trim())
                },
              },
              busy && job.status !== 'recording' ? { label: 'Cancel processing', icon: X, onClick: () => onCancel(job.id) } : null,
              { divider: true },
              {
                label: 'Delete',
                icon: Trash2,
                danger: true,
                disabled: job.status === 'recording',
                onClick: () => window.confirm(`Delete “${job.title}” and its transcript?`) && onDelete(job.id),
              },
            ].filter(Boolean)}
          />
        </div>
      </div>

      <button type="button" onClick={open} className="mt-3 flex flex-1 flex-col text-left focus-visible:outline-current">
        <h3 className="line-clamp-2 text-[21px] font-semibold leading-[1.08] tracking-tight">{job.title}</h3>

        {busy ? (
          <div className="mt-auto pt-4">
            <div className="flex items-end justify-between gap-3">
              <span className="display tabular text-[52px]">
                {job.status === 'recording' ? '●' : `${Math.round((job.progress || 0) * 100)}`}
                {job.status !== 'recording' && <span className="text-[0.4em] tracking-normal">%</span>}
              </span>
              <span className="pb-2 text-right font-mono text-[11px] leading-tight opacity-80">
                {/* "Transcribing speech · Reading on-screen text (40/136)": the card shows the main step */}
                {job.stage?.split(' · ')[0]}
                {etaSeconds(job) != null && <span className="block opacity-70">{formatEta(etaSeconds(job))}</span>}
              </span>
            </div>
            {job.status !== 'recording' && <ProgressBar value={job.progress} className="mt-2" />}
          </div>
        ) : job.status === 'error' || job.status === 'cancelled' ? (
          <div className="mt-auto pt-4">
            <span className="display text-[40px]">{job.status === 'cancelled' ? 'Cancelled' : 'Failed'}</span>
            {job.error && <p className="mt-1 line-clamp-2 text-xs opacity-80">{job.error}</p>}
          </div>
        ) : (
          <div className="mt-auto flex items-end justify-between gap-3 pt-4">
            <span className="display tabular text-[clamp(44px,4.4vw,60px)]">{formatTime(job.media?.duration)}</span>
            <dl className="mb-1 flex gap-3 border-l border-current/25 pl-3 font-mono text-[10px] uppercase leading-tight tracking-wider">
              {[
                ['Scenes', stats.scenes],
                ['Voices', stats.speakers],
                ['Review', stats.corrections_pending],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="opacity-60">{label}</dt>
                  <dd className="text-[15px] font-semibold tracking-normal">{value ?? '–'}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </button>
    </article>
  )
}

export function UploadingCard({ upload }) {
  return (
    <article className="flex min-h-[236px] flex-col rounded-card border border-dashed border-line-2 bg-surface p-5">
      <span className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
        <Upload className="size-3.5" /> Uploading
      </span>
      <h3 className="mt-3 line-clamp-2 text-[21px] font-semibold leading-tight tracking-tight">{upload.filename}</h3>
      <div className="mt-auto">
        <span className="display tabular text-[52px]">
          {Math.round(upload.progress * 100)}
          <span className="text-[0.4em] tracking-normal">%</span>
        </span>
        <ProgressBar value={upload.progress} />
      </div>
    </article>
  )
}
