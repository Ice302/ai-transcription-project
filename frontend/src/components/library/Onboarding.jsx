import { Check, LoaderCircle, Minus, X } from 'lucide-react'

// First-run checklist on a black card (the dark tiles of the flat reference), built from /api/health.
export default function Onboarding({ health, offline }) {
  const loading = health?.status === 'loading'
  const items = offline
    ? [['bad', 'Backend', 'Not reachable — start it with start_app.bat (or uvicorn main:app in backend/).']]
    : [
        ['ok', 'Backend', `Connected · v${health?.version || '…'}`],
        [health?.ffmpeg ? 'ok' : 'bad', 'ffmpeg', health?.ffmpeg ? 'Found on PATH' : 'Missing — install ffmpeg and restart the backend'],
        [
          loading ? 'wait' : health?.status === 'ok' ? 'ok' : 'bad',
          'Speech model',
          loading ? health?.stage : health?.status === 'ok' ? `${health.model} on ${health.device === 'cuda' ? 'GPU' : 'CPU'}` : health?.error,
        ],
        [health?.ocr === false ? 'off' : loading ? 'wait' : 'ok', 'Screen reading', health?.ocr === false ? 'Off (OCR_ENABLED=false)' : 'Slides and shared screens are read'],
        [
          health?.diarization ? 'ok' : loading ? 'wait' : 'off',
          'Speaker identification',
          health?.diarization ? 'Who-said-what is on' : health?.diarization_error ? `Unavailable: ${health.diarization_error}` : 'Off',
        ],
        [
          health?.llm_configured ? 'ok' : 'off',
          'AI assistant',
          health?.local_only ? 'Local-only mode: nothing leaves this computer' : health?.llm_configured ? health.llm_model : 'Add OPENROUTER_API_KEY to backend/.env',
        ],
      ]
  const Icon = { ok: Check, bad: X, wait: LoaderCircle, off: Minus }
  return (
    <section className="rounded-card bg-ink p-6 text-on-ink">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] opacity-60">Setup check</p>
      <ul className="mt-4 space-y-3">
        {items.map(([state, label, detail]) => {
          const I = Icon[state]
          return (
            <li key={label} className="flex items-start gap-3">
              <span
                className={`grid size-6 shrink-0 place-items-center rounded-full ${
                  state === 'ok' ? 'bg-lime text-[#131312]' : state === 'bad' ? 'bg-signal text-white' : 'border border-on-ink/30 opacity-70'
                }`}
              >
                <I className={`size-3.5 ${state === 'wait' ? 'animate-spin' : ''}`} strokeWidth={3} />
              </span>
              <span className="min-w-0 text-sm">
                <span className="font-medium">{label}</span>
                <span className="block truncate text-xs opacity-60" title={detail || ''}>
                  {detail}
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
