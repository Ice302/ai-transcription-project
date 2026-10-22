import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { LANGUAGES } from '../../lib/languages'
import { Button, Dialog, Switch } from '../ui'

// Run the pipeline again on the stored media with better hints (language, names, speaker count).
export default function ReprocessDialog({ open, onClose, job, health, onSubmit }) {
  const opts = job?.options || {}
  const [language, setLanguage] = useState(opts.language || '')
  const [glossary, setGlossary] = useState(opts.glossary || '')
  const [diarize, setDiarize] = useState(opts.diarize !== false)
  const [speakers, setSpeakers] = useState(opts.num_speakers ? String(opts.num_speakers) : '')
  const [visuals, setVisuals] = useState(Boolean(opts.describe_visuals))

  const submit = () => {
    onSubmit({
      language,
      glossary,
      diarize,
      num_speakers: speakers ? Number(speakers) : null,
      describe_visuals: visuals && Boolean(health?.vision_enabled),
    })
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Reprocess recording"
      footer={
        <>
          <Button tone="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button tone="ink" icon={RefreshCw} onClick={submit}>
            Reprocess
          </Button>
        </>
      }
    >
      <p className="mb-5 text-sm text-ink-2">
        Transcribes the stored recording again. Your edits and accepted fixes are replaced by the new transcript; speaker names are reset.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
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
        <label className="text-sm">
          <span className="eyebrow mb-1.5 block">Number of speakers</span>
          <select className="field" value={speakers} disabled={!diarize} onChange={(e) => setSpeakers(e.target.value)}>
            <option value="">Detect automatically</option>
            {[1, 2, 3, 4, 5, 6, 7, 8, 10, 12].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm sm:col-span-2">
          <span className="eyebrow mb-1.5 block">Names & terms</span>
          <textarea
            className="field min-h-24 resize-y"
            value={glossary}
            onChange={(e) => setGlossary(e.target.value)}
            placeholder="People, products and jargon, spelled the way they should appear"
          />
        </label>
        <Switch checked={diarize} onChange={setDiarize} label="Identify speakers" />
        <Switch
          checked={visuals && Boolean(health?.vision_enabled)}
          onChange={setVisuals}
          disabled={!health?.vision_enabled}
          label="Describe charts & images"
        />
      </div>
    </Dialog>
  )
}
