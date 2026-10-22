// Languages offered in the UI (Whisper codes). Empty = auto-detect.
export const LANGUAGES = [
  ['', 'Auto-detect'],
  ['en', 'English'],
  ['tl', 'Tagalog / Filipino (incl. Taglish)'],
  ['es', 'Spanish'],
  ['fr', 'French'],
  ['de', 'German'],
  ['it', 'Italian'],
  ['pt', 'Portuguese'],
  ['nl', 'Dutch'],
  ['pl', 'Polish'],
  ['sv', 'Swedish'],
  ['ru', 'Russian'],
  ['uk', 'Ukrainian'],
  ['tr', 'Turkish'],
  ['ar', 'Arabic'],
  ['hi', 'Hindi'],
  ['id', 'Indonesian'],
  ['vi', 'Vietnamese'],
  ['ja', 'Japanese'],
  ['ko', 'Korean'],
  ['zh', 'Chinese'],
]

const SHORT = { tl: 'Tagalog' }

/** "en" -> "English"; codes not offered in the UI fall back to the browser's names. */
export function languageName(code) {
  if (!code) return ''
  if (SHORT[code]) return SHORT[code]
  const known = LANGUAGES.find(([c]) => c === code)
  if (known) return known[1]
  try {
    return new Intl.DisplayNames(['en'], { type: 'language' }).of(code) || code
  } catch {
    return code
  }
}

/** One line on how the language was chosen (results from before v3.1 have no detection details). */
export function describeDetection(detection) {
  if (!detection) return ''
  if (detection.method === 'chosen') return 'Chosen for this recording'
  if (detection.method === 'trial' && detection.trial_scores) {
    const [[best, top], [other, low] = []] = Object.entries(detection.trial_scores).sort((a, b) => b[1] - a[1])
    const versus = other ? ` (${Math.round(top)} vs ${Math.round(low)} in ${languageName(other)})` : ''
    return `Mixed languages: a test transcription recognised more words as ${languageName(best)}${versus}`
  }
  return detection.windows > 1 ? `Voted across ${detection.windows} stretches of speech` : 'Detected from the speech'
}
