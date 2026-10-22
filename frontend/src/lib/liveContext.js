import { formatTime } from './format'

// Mirrors backend/app/crossref.py:build_notes_context so the assistant sees live
// meetings in the same SPEECH / SCREEN format as uploaded videos.
export function buildLiveContext(events, title = 'Live meeting') {
  const lines = [`=== LIVE MEETING: ${title} ===`]
  const corrections = []
  for (const e of events) {
    if (e.kind === 'speech') lines.push(`SPEECH [${formatTime(e.t)}]${e.speaker ? ` ${e.speaker}:` : ''} ${e.text}`)
    else if (e.kind === 'visual') {
      lines.push(`\n[SCREEN CHANGE | ${formatTime(e.t)}]${e.title ? ` ${e.title}` : ''}`)
      lines.push(`SCREEN: ${e.text.split('\n').map((l) => l.trim()).filter(Boolean).join(' · ')}`)
    } else if (e.kind === 'correction') corrections.push(e)
  }
  if (corrections.length) {
    lines.push('\nPOSSIBLE MIS-TRANSCRIPTIONS (spoken -> spelling on screen):')
    for (const c of corrections) lines.push(`- [${formatTime(c.t)}] "${c.heard}" -> "${c.seen}"`)
  }
  return lines.join('\n')
}

export function liveToPlainText(events) {
  return events
    .filter((e) => e.kind === 'speech' || e.kind === 'visual')
    .map((e) =>
      e.kind === 'speech'
        ? `[${formatTime(e.t)}] ${e.speaker ? `${e.speaker}: ` : ''}${e.text}`
        : `\n[${formatTime(e.t)}] ON SCREEN${e.title ? ` — ${e.title}` : ''}:\n${e.text}\n`,
    )
    .join('\n')
}
