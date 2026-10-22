import { describe, expect, it } from 'vitest'
import {
  baseName,
  formatBytes,
  formatClock,
  formatDuration,
  formatTime,
  parseTime,
  snippetParts,
  toMarkdown,
  toSRT,
  toText,
  toVTT,
} from './format'
import { describeDetection, languageName } from './languages'
import { buildLiveContext, liveToPlainText } from './liveContext'
import { colorForLabel, pastel, speakerColors } from './palette'
import { jobPath, parseRoute } from './router'
import { etaSeconds, formatEta, mediaFiles, uploadFields } from './uploads'

const result = {
  filename: 'standup.mp4',
  title: 'Standup',
  created_at: 1792540800,
  language: 'en',
  media: { duration: 75 },
  speakers: [
    { id: 'S1', name: 'Priya' },
    { id: 'S2', name: 'You' },
  ],
  segments: [
    { id: 0, start: 1.5, end: 3.25, text: 'Hello team.', speaker: 'S1', scene_id: 0 },
    { id: 1, start: 61, end: 63, text: 'Ship it.', speaker: 'S2', scene_id: 1 },
  ],
  keyframes: [
    { id: 0, t: 0, end: 60, title: 'Intro', ocr_text: 'Intro\nAgenda' },
    { id: 1, t: 60, end: 75, title: '', ocr_text: '' },
  ],
  corrections: [
    { id: 0, t: 1.5, heard: 'teem', seen: 'team', status: 'pending' },
    { id: 1, t: 61, heard: 'x', seen: 'y', status: 'dismissed' },
  ],
}

describe('time formatting', () => {
  it('formats and parses timestamps', () => {
    expect(formatTime(5)).toBe('00:05')
    expect(formatTime(3725)).toBe('1:02:05')
    expect(formatTime(undefined)).toBe('00:00')
    expect(formatClock(65)).toBe('00:01:05')
    expect(parseTime('1:02:05')).toBe(3725)
    expect(parseTime('12:34')).toBe(754)
  })
  it('formats durations and sizes for humans', () => {
    expect(formatDuration(42)).toBe('42s')
    expect(formatDuration(600)).toBe('10 min')
    expect(formatDuration(5400)).toBe('1h 30m')
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(468_000)).toBe('457 KB')
    expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GB')
  })
  it('makes safe file names', () => {
    expect(baseName('a/b:c?.mp4')).toBe('a_b_c_')
    expect(baseName('meeting.final.mov')).toBe('meeting.final')
  })
})

describe('exports', () => {
  it('writes SRT with speakers', () => {
    expect(toSRT(result)).toBe('1\n00:00:01,500 --> 00:00:03,250\nPriya: Hello team.\n\n2\n00:01:01,000 --> 00:01:03,000\nYou: Ship it.\n')
  })
  it('writes WebVTT with voice tags', () => {
    expect(toVTT(result)).toContain('WEBVTT\n\n00:00:01.500 --> 00:00:03.250\n<v Priya>Hello team.')
  })
  it('writes plain text', () => {
    expect(toText(result)).toBe('[00:01] Priya: Hello team.\n[01:01] You: Ship it.')
  })
  it('writes Markdown notes grouped by scene, with pending fixes only', () => {
    const md = toMarkdown(result)
    expect(md).toContain('# Standup')
    expect(md).toContain('## Intro (00:00 – 01:00)')
    expect(md).toContain('> Agenda')
    expect(md).toContain('## Scene 2 (01:00 – 01:15)')
    expect(md).toContain('- **[00:01]** **Priya:** Hello team.')
    expect(md).toContain('heard "teem" → on screen "team"')
    expect(md).not.toContain('heard "x"')
  })
  it('adds Obsidian front matter on request', () => {
    const md = toMarkdown(result, { frontMatter: true })
    expect(md.startsWith('---\ntitle: "Standup"\ndate: 2026-10-')).toBe(true)
    expect(md).toContain('speakers: ["Priya", "You"]')
  })
})

describe('search snippets', () => {
  it('splits highlight markers without HTML', () => {
    const s = `we ${String.fromCharCode(1)}migrate${String.fromCharCode(2)} the <b>cluster</b>`
    expect(snippetParts(s)).toEqual([
      { text: 'we ', hit: false },
      { text: 'migrate', hit: true },
      { text: ' the <b>cluster</b>', hit: false },
    ])
  })
})

describe('routing', () => {
  it('parses hash routes', () => {
    expect(parseRoute('')).toEqual({ view: 'library', q: '' })
    expect(parseRoute('#/?q=postgres')).toEqual({ view: 'library', q: 'postgres' })
    expect(parseRoute('#/live')).toEqual({ view: 'live' })
    expect(parseRoute('#/job/0123456789ab?t=12.5')).toEqual({ view: 'job', id: '0123456789ab', t: 12.5 })
    expect(parseRoute('#/job/0123456789ab')).toEqual({ view: 'job', id: '0123456789ab', t: null })
    expect(parseRoute('#/job/../../etc')).toEqual({ view: 'library', q: '' })
  })
  it('builds job paths', () => {
    expect(jobPath('0123456789ab')).toBe('/job/0123456789ab')
    expect(jobPath('0123456789ab', 12.34)).toBe('/job/0123456789ab?t=12.3')
  })
})

describe('live context', () => {
  const events = [
    { kind: 'speech', t: 2, text: 'Kick-off.', speaker: 'You' },
    { kind: 'visual', t: 5, title: 'Q3', text: 'Q3\nRevenue 4.2M' },
    { kind: 'correction', t: 7, heard: 'cubernetes', seen: 'Kubernetes' },
  ]
  it('mirrors the backend notes format', () => {
    const ctx = buildLiveContext(events, 'Sync')
    expect(ctx).toContain('=== LIVE MEETING: Sync ===')
    expect(ctx).toContain('SPEECH [00:02] You: Kick-off.')
    expect(ctx).toContain('[SCREEN CHANGE | 00:05] Q3\nSCREEN: Q3 · Revenue 4.2M')
    expect(ctx).toContain('- [00:07] "cubernetes" -> "Kubernetes"')
  })
  it('copies as plain text', () => {
    expect(liveToPlainText(events)).toBe('[00:02] You: Kick-off.\n\n[00:05] ON SCREEN — Q3:\nQ3\nRevenue 4.2M\n')
  })
})

describe('palette', () => {
  it('cycles pastels and keeps "You" lime', () => {
    expect(pastel(0)).toBe(pastel(6))
    expect(pastel(-1)).toBe(pastel(5))
    const colors = speakerColors(result.speakers)
    expect(colors.get('S2').bg).toBe('bg-lime')
    expect(colors.get('S1').bg).not.toBe('bg-lime')
    expect(colorForLabel('You').bg).toBe('bg-lime')
    expect(colorForLabel('Others')).toBe(colorForLabel('Others'))
  })
})

describe('uploads', () => {
  it('keeps only media files', () => {
    const files = [
      { name: 'a.mp4', type: 'video/mp4' },
      { name: 'notes.txt', type: 'text/plain' },
      { name: 'call.MKV', type: '' },
      { name: 'voice.m4a', type: 'audio/x-m4a' },
    ]
    expect(mediaFiles(files).map((f) => f.name)).toEqual(['a.mp4', 'call.MKV', 'voice.m4a'])
  })
  it('only asks for captions when the server can make them', () => {
    const opts = { language: 'en', glossary: ' Okafor ', diarize: true, num_speakers: '2', describe_visuals: true }
    expect(uploadFields(opts, { vision_enabled: false })).toEqual({ language: 'en', glossary: 'Okafor', diarize: true, num_speakers: '2', describe_visuals: false })
    expect(uploadFields(opts, { vision_enabled: true }).describe_visuals).toBe(true)
  })
  it('estimates time left while running', () => {
    expect(etaSeconds({ status: 'running', started_at: 100, progress: 0.25 }, 130)).toBe(90)
    expect(etaSeconds({ status: 'running', started_at: 100, progress: 0.01 }, 130)).toBe(null)
    expect(etaSeconds({ status: 'queued', started_at: null, progress: 0 }, 130)).toBe(null)
    expect(formatEta(42.4)).toBe('≈ 42 s left')
    expect(formatEta(185)).toBe('≈ 3 min left')
  })
})

describe('language details', () => {
  it('names languages', () => {
    expect(languageName('en')).toBe('English')
    expect(languageName('tl')).toBe('Tagalog')
    expect(languageName('')).toBe('')
    expect(languageName('ms')).toMatch(/Malay|ms/)
  })

  it('explains how the language was chosen', () => {
    expect(describeDetection(null)).toBe('')
    expect(describeDetection({ method: 'chosen', language: 'en' })).toBe('Chosen for this recording')
    expect(describeDetection({ method: 'vote', windows: 8 })).toBe('Voted across 8 stretches of speech')
    expect(describeDetection({ method: 'trial', trial_scores: { en: 40.2, tl: 180.6 } })).toBe(
      'Mixed languages: a test transcription recognised more words as Tagalog (181 vs 40 in English)',
    )
  })
})
