import { Library, Monitor, Moon, PanelRight, Radio, Sun } from 'lucide-react'
import { navigate } from '../lib/router'
import { Logo } from './Art'
import { IconButton, Segmented } from './ui'

const THEMES = { system: Monitor, light: Sun, dark: Moon }
const NEXT_THEME = { system: 'light', light: 'dark', dark: 'system' }

export default function TopBar({ route, health, offline, theme, setTheme, liveStatus, onToggleAssistant }) {
  const ThemeIcon = THEMES[theme]
  const view = route.view === 'live' ? 'live' : 'library'
  return (
    <header className="no-print sticky top-0 z-30 border-b border-line bg-paper/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1680px] items-center gap-3 px-4 sm:px-6">
        <a href="#/" className="flex items-center gap-2.5" aria-label="TurboTranscribe home">
          <Logo />
          <span className="hidden text-[17px] font-semibold tracking-tight sm:inline">
            Turbo<span className="serif-accent text-[21px]">transcribe</span>
          </span>
        </a>
        <Segmented
          className="ml-1 sm:ml-4"
          label="Sections"
          value={view}
          onChange={(v) => navigate(v === 'live' ? '/live' : '/')}
          options={[
            { value: 'library', label: 'Library', icon: Library },
            {
              value: 'live',
              label: liveStatus === 'live' ? 'Live ●' : 'Live',
              icon: Radio,
            },
          ]}
        />
        <div className="ml-auto flex items-center gap-2">
          <StatusPill health={health} offline={offline} />
          <IconButton icon={ThemeIcon} label={`Theme: ${theme} (click to change)`} size="sm" onClick={() => setTheme(NEXT_THEME[theme])} />
          <IconButton icon={PanelRight} label="Notes assistant" size="sm" className="xl:hidden" onClick={onToggleAssistant} />
        </div>
      </div>
    </header>
  )
}

function StatusPill({ health, offline }) {
  let dot = 'bg-ink-3'
  let text = 'Connecting…'
  if (offline) [dot, text] = ['bg-signal', 'Backend offline']
  else if (health?.status === 'loading') [dot, text] = ['bg-lime animate-pulse', health.stage || 'Loading models…']
  else if (health?.status === 'error') [dot, text] = ['bg-signal', 'Model failed to load']
  else if (health) [dot, text] = ['bg-lime', `${health.model} · ${health.device === 'cuda' ? 'GPU' : 'CPU'}`]
  const details = health
    ? [
        `Speech: ${health.engine || '…'} ${health.model} on ${health.device || '…'} (live: ${health.live_model})`,
        `Speakers: ${health.diarization ? 'on' : health.diarization_error ? `unavailable (${health.diarization_error})` : 'off'}`,
        `Screen reading (OCR): ${health.ocr === false ? 'off' : 'on'}`,
        `Assistant: ${health.local_only ? 'local-only mode' : health.llm_configured ? health.llm_model : 'no API key'}`,
        `ffmpeg: ${health.ffmpeg ? 'ok' : 'missing'}`,
        health.error ? `Error: ${health.error}` : '',
      ]
        .filter(Boolean)
        .join('\n')
    : ''
  return (
    <span
      title={details}
      className="hidden max-w-[260px] items-center gap-2 truncate rounded-full border border-line bg-surface-2/70 px-3 py-1.5 font-mono text-[11px] text-ink-2 md:inline-flex"
    >
      <span className={`size-2 shrink-0 rounded-full ${dot}`} />
      <span className="truncate">{text}</span>
    </span>
  )
}
