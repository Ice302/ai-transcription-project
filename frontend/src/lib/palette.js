// Six muted pastels (calendar reference) used for scenes, library cards and speakers.
// Class names are written out in full so Tailwind can see them.
export const PASTELS = [
  { bg: 'bg-p1', ink: 'text-p1-ink', ring: 'ring-p1', var: 'var(--tt-p1)', inkVar: 'var(--tt-p1-ink)' },
  { bg: 'bg-p3', ink: 'text-p3-ink', ring: 'ring-p3', var: 'var(--tt-p3)', inkVar: 'var(--tt-p3-ink)' },
  { bg: 'bg-p5', ink: 'text-p5-ink', ring: 'ring-p5', var: 'var(--tt-p5)', inkVar: 'var(--tt-p5-ink)' },
  { bg: 'bg-p4', ink: 'text-p4-ink', ring: 'ring-p4', var: 'var(--tt-p4)', inkVar: 'var(--tt-p4-ink)' },
  { bg: 'bg-p6', ink: 'text-p6-ink', ring: 'ring-p6', var: 'var(--tt-p6)', inkVar: 'var(--tt-p6-ink)' },
  { bg: 'bg-p2', ink: 'text-p2-ink', ring: 'ring-p2', var: 'var(--tt-p2)', inkVar: 'var(--tt-p2-ink)' },
]

export const pastel = (i) => PASTELS[((i % PASTELS.length) + PASTELS.length) % PASTELS.length]

const LIME = { bg: 'bg-lime', ink: 'text-ink', ring: 'ring-lime', var: 'var(--tt-lime)', inkVar: '#131312' }

// "You" is always lime; other speakers cycle through the pastels in order of appearance.
export function speakerColors(speakers = []) {
  const map = new Map()
  let n = 0
  for (const s of speakers) map.set(s.id, s.name === 'You' ? LIME : pastel(n++ + 1))
  return map
}

// Stable color for a string (e.g. a live speaker label).
export function colorForLabel(label) {
  if (!label) return pastel(5)
  if (label === 'You') return LIME
  let h = 0
  for (const c of label) h = (h * 31 + c.charCodeAt(0)) | 0
  return pastel(Math.abs(h))
}
