export function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${String(m).padStart(2, '0')}:${ss}`
}

// Always h:mm:ss style with hours, for the big live clock.
export function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0))
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`
}

export function parseTime(text) {
  return String(text)
    .split(':')
    .reduce((acc, part) => acc * 60 + Number(part), 0)
}

export function formatDuration(seconds) {
  const s = Math.round(seconds || 0)
  if (s < 60) return `${s}s`
  const h = Math.floor(s / 3600)
  const m = Math.round((s % 3600) / 60)
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m} min`
}

export function formatBytes(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${(bytes / 1024 ** i).toFixed(i >= 2 ? 1 : 0)} ${units[i]}`
}

export function formatDate(epochSeconds, withTime = true) {
  if (!epochSeconds) return ''
  const d = new Date(epochSeconds * 1000)
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const yesterday = new Date(today.getTime() - 86400000).toDateString() === d.toDateString()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return withTime ? `Today, ${time}` : 'Today'
  if (yesterday) return withTime ? `Yesterday, ${time}` : 'Yesterday'
  const date = d.toLocaleDateString([], { day: 'numeric', month: 'short', year: d.getFullYear() === today.getFullYear() ? undefined : 'numeric' })
  return withTime ? `${date}, ${time}` : date
}

function subtitleTime(seconds, sep) {
  const ms = Math.round((seconds || 0) * 1000)
  const pad = (n, w = 2) => String(n).padStart(w, '0')
  return `${pad(Math.floor(ms / 3600000))}:${pad(Math.floor(ms / 60000) % 60)}:${pad(Math.floor(ms / 1000) % 60)}${sep}${pad(ms % 1000, 3)}`
}

const speakerName = (result, id) => result.speakers?.find((s) => s.id === id)?.name || ''

export function toSRT(result) {
  return result.segments
    .map((s, i) => {
      const who = speakerName(result, s.speaker)
      return `${i + 1}\n${subtitleTime(s.start, ',')} --> ${subtitleTime(s.end, ',')}\n${who ? `${who}: ` : ''}${s.text}\n`
    })
    .join('\n')
}

export function toVTT(result) {
  const cues = result.segments.map((s) => {
    const who = speakerName(result, s.speaker)
    return `${subtitleTime(s.start, '.')} --> ${subtitleTime(s.end, '.')}\n${who ? `<v ${who}>` : ''}${s.text}\n`
  })
  return `WEBVTT\n\n${cues.join('\n')}`
}

export function toText(result) {
  return result.segments
    .map((s) => {
      const who = speakerName(result, s.speaker)
      return `[${formatTime(s.start)}] ${who ? `${who}: ` : ''}${s.text}`
    })
    .join('\n')
}

export function toMarkdown(result, { frontMatter = false } = {}) {
  const lines = []
  if (frontMatter) {
    const created = result.created_at ? new Date(result.created_at * 1000).toISOString().slice(0, 10) : ''
    lines.push(
      '---',
      `title: "${(result.title || result.filename).replace(/"/g, "'")}"`,
      `date: ${created}`,
      `duration: "${formatTime(result.media?.duration)}"`,
      `source: "${result.filename}"`,
      `speakers: [${(result.speakers || []).map((s) => `"${s.name}"`).join(', ')}]`,
      'tags: [meeting, transcript]',
      '---',
      '',
    )
  }
  lines.push(`# ${result.title || result.filename}`, '')
  const meta = [formatTime(result.media?.duration), result.language?.toUpperCase(), result.speakers?.length ? `${result.speakers.length} speakers` : '']
  lines.push(`*${meta.filter(Boolean).join(' · ')}*`, '')
  const line = (s) => {
    const who = speakerName(result, s.speaker)
    return `- **[${formatTime(s.start)}]** ${who ? `**${who}:** ` : ''}${s.text}`
  }
  if (result.keyframes?.length) {
    const byScene = new Map()
    for (const seg of result.segments) {
      if (!byScene.has(seg.scene_id)) byScene.set(seg.scene_id, [])
      byScene.get(seg.scene_id).push(seg)
    }
    for (const kf of result.keyframes) {
      lines.push(`## ${kf.title || `Scene ${kf.id + 1}`} (${formatTime(kf.t)} – ${formatTime(kf.end)})`, '')
      if (kf.ocr_text) lines.push('**On screen:**', '', ...kf.ocr_text.split('\n').map((l) => `> ${l}`), '')
      if (kf.caption) lines.push(`*${kf.caption}*`, '')
      for (const seg of byScene.get(kf.id) || []) lines.push(line(seg))
      lines.push('')
    }
  } else {
    lines.push(...result.segments.map(line), '')
  }
  const pending = (result.corrections || []).filter((c) => c.status === 'pending')
  if (pending.length) {
    lines.push('## Possible mis-transcriptions', '')
    for (const c of pending) lines.push(`- [${formatTime(c.t)}] heard "${c.heard}" → on screen "${c.seen}"`)
  }
  return lines.join('\n')
}

export function download(filename, text, type = 'text/plain') {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const baseName = (name) => (name || 'transcript').replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]+/g, '_')

const HIT_START = String.fromCharCode(1)
const HIT_END = String.fromCharCode(2)

// Split a search snippet with \u0001…\u0002 markers (backend/app/search.py) into
// [{text, hit}] parts, so matches are highlighted without rendering any HTML.
export function snippetParts(snippet) {
  const parts = []
  let text = ''
  let hit = false
  for (const ch of String(snippet)) {
    if (ch === HIT_START || ch === HIT_END) {
      if (text) parts.push({ text, hit })
      text = ''
      hit = ch === HIT_START
    } else text += ch
  }
  if (text) parts.push({ text, hit })
  return parts
}
