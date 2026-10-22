import { ChevronDown, Plus, SlidersHorizontal } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { LANGUAGES } from '../../lib/languages'
import { loadUploadOptions, mediaFiles, saveUploadOptions, uploadFields } from '../../lib/uploads'
import { Switch } from '../ui'

const ACCEPT = 'audio/*,video/*,.mkv,.m4a,.flac,.ogg,.opus,.webm,.mov,.avi,.wmv'

export default function UploadCard({ onUpload, health }) {
  const [dragging, setDragging] = useState(false)
  const [showOptions, setShowOptions] = useState(false)
  const [options, setOptions] = useState(loadUploadOptions)
  const input = useRef(null)

  useEffect(() => saveUploadOptions(options), [options])

  const set = (key) => (value) => setOptions((o) => ({ ...o, [key]: value }))
  const submit = (fileList) => {
    const files = mediaFiles(fileList)
    if (files.length) onUpload(files, uploadFields(options, health))
  }

  return (
    <section className="card relative flex flex-col overflow-hidden">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          e.stopPropagation() // handled here; keep the drop-anywhere overlay from uploading it again
          setDragging(false)
          submit(e.dataTransfer.files)
        }}
        className={`relative flex min-h-60 flex-1 flex-col items-center justify-center gap-4 p-6 text-center transition ${dragging ? 'bg-lime-pale' : ''}`}
      >
        <div className="dot-grid pointer-events-none absolute inset-0 opacity-70 mask-[radial-gradient(ellipse_at_center,black,transparent_75%)]" />
        <button
          type="button"
          onClick={() => input.current?.click()}
          aria-label="Choose files to transcribe"
          className={`relative grid size-20 place-items-center rounded-full transition ${dragging ? 'scale-110 bg-lime text-[#131312]' : 'bg-ink text-on-ink hover:scale-105'}`}
        >
          <Plus className="size-8" strokeWidth={2.2} />
        </button>
        <div className="relative">
          <p className="text-xl font-semibold tracking-tight">
            Drop recordings <span className="serif-accent text-2xl">here</span>
          </p>
          <p className="mt-1 text-sm text-ink-3">Audio or video — MP4, MOV, MKV, MP3, WAV, M4A… Several at once is fine.</p>
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            submit(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      <div className="relative border-t border-line">
        <button
          type="button"
          onClick={() => setShowOptions((v) => !v)}
          aria-expanded={showOptions}
          className="flex w-full items-center gap-2 px-6 py-3 text-sm font-medium text-ink-2 hover:text-ink"
        >
          <SlidersHorizontal className="size-4" />
          Options
          <span className="truncate font-mono text-[11px] text-ink-3">
            {[
              options.language ? LANGUAGES.find(([c]) => c === options.language)?.[1] : 'auto language',
              options.diarize ? (options.num_speakers ? `${options.num_speakers} speakers` : 'speakers on') : 'speakers off',
              options.glossary.trim() ? `${options.glossary.split(/[,\n]/).filter((t) => t.trim()).length} terms` : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </span>
          <ChevronDown className={`ml-auto size-4 transition ${showOptions ? 'rotate-180' : ''}`} />
        </button>
        {showOptions && (
          <div className="animate-rise grid gap-4 px-6 pb-6 sm:grid-cols-2">
            <label className="text-sm">
              <span className="eyebrow mb-1.5 block">Language</span>
              <select className="field" value={options.language} onChange={(e) => set('language')(e.target.value)}>
                {LANGUAGES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              <span className="eyebrow mb-1.5 block">Number of speakers</span>
              <select className="field" value={options.num_speakers} disabled={!options.diarize} onChange={(e) => set('num_speakers')(e.target.value)}>
                <option value="">Detect automatically</option>
                {[1, 2, 3, 4, 5, 6, 7, 8, 10, 12].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm sm:col-span-2">
              <span className="eyebrow mb-1.5 block">Names & terms (optional)</span>
              <textarea
                className="field min-h-20 resize-y"
                placeholder="Priya Raghunathan, Kubernetes, Q3 OKRs… — spelled the way they should appear"
                value={options.glossary}
                onChange={(e) => set('glossary')(e.target.value)}
              />
            </label>
            <Switch
              checked={options.diarize}
              onChange={set('diarize')}
              label="Identify speakers"
              description={
                health?.status === 'ok' && !health.diarization
                  ? 'Unavailable on this server — transcripts will have no speaker labels.'
                  : 'Who said what, from voice differences.'
              }
            />
            <Switch
              checked={options.describe_visuals && Boolean(health?.vision_enabled)}
              onChange={set('describe_visuals')}
              disabled={!health?.vision_enabled}
              label="Describe charts & images"
              description={health?.vision_enabled ? 'Uses the AI vision model (paid, capped).' : 'Set VISION_MODEL in backend/.env to enable.'}
            />
          </div>
        )}
      </div>
    </section>
  )
}
