// Brand mark and editorial illustrations, all inline SVG themed through CSS variables.

export function Logo({ className = 'size-9' }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <rect width="40" height="40" rx="12" fill="var(--tt-lime)" />
      <path d="M8 21h3M14 15v12M19.5 10v20M25 14v12M30.5 18v6" stroke="#131312" strokeWidth="3" strokeLinecap="round" />
      <circle cx="33.5" cy="9.5" r="3" fill="var(--tt-signal)" />
    </svg>
  )
}

// "speech + screen -> notes", drawn as the network collage of the editorial reference:
// serif labels in boxes, thin connecting lines with dots, a red square, a dot grid.
export function NetworkIllustration({ className = '' }) {
  const ink = 'var(--tt-ink)'
  const line = 'var(--tt-ink-3)'
  return (
    <svg viewBox="0 0 520 360" className={className} role="img" aria-label="Speech and screen content connected into notes">
      <defs>
        <pattern id="tt-dots" width="10" height="10" patternUnits="userSpaceOnUse">
          <circle cx="1.5" cy="1.5" r="1.2" fill="var(--tt-line-2)" />
        </pattern>
        <pattern id="tt-grid" width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M12 0H0V12" fill="none" stroke="var(--tt-line-2)" strokeWidth="1" />
        </pattern>
      </defs>
      <rect x="18" y="28" width="96" height="78" fill="url(#tt-grid)" />
      <rect x="392" y="246" width="110" height="84" fill="url(#tt-dots)" />
      <rect x="402" y="30" width="44" height="44" fill="var(--tt-signal)" />
      <rect x="60" y="270" width="30" height="30" fill="var(--tt-signal)" />

      {/* connections */}
      <g stroke={line} strokeWidth="1.2" fill="none">
        <path d="M260 180 L120 92" />
        <path d="M260 180 L420 104" />
        <path d="M260 180 L132 270" />
        <path d="M260 180 L400 268" />
        <path d="M120 92 L132 270" strokeDasharray="3 5" />
        <path d="M420 104 L400 268" strokeDasharray="3 5" />
        <circle cx="260" cy="180" r="92" strokeDasharray="2 6" />
      </g>
      {[[190, 136], [338, 143], [196, 225], [330, 224], [126, 181], [410, 186]].map(([x, y]) => (
        <circle key={`${x}-${y}`} cx={x} cy={y} r="4.5" fill={ink} />
      ))}

      {/* centre: a waveform disc */}
      <circle cx="260" cy="180" r="62" fill={ink} />
      <g stroke="var(--tt-lime)" strokeWidth="5" strokeLinecap="round">
        {[-30, -18, -6, 6, 18, 30].map((dx, i) => {
          const h = [14, 30, 44, 36, 22, 12][i]
          return <path key={dx} d={`M${260 + dx} ${180 - h / 2}v${h}`} />
        })}
      </g>

      {/* labels */}
      {[
        ['speech', 120, 92],
        ['screen', 420, 104],
        ['people', 132, 270],
        ['notes', 400, 268],
      ].map(([text, x, y]) => (
        <g key={text}>
          <rect x={x - 46} y={y - 19} width="92" height="38" fill="var(--tt-surface-2)" stroke="var(--tt-line-2)" />
          <text x={x} y={y + 7} textAnchor="middle" fontFamily="var(--font-serif)" fontSize="23" fill={ink}>
            {text}
          </text>
        </g>
      ))}
      <text x="260" y="300" textAnchor="middle" fontFamily="var(--font-serif)" fontStyle="italic" fontSize="17" fill="var(--tt-ink-2)">
        cross-checked
      </text>
      <path d="M210 308 q50 10 100 0" stroke="var(--tt-ink-2)" fill="none" strokeWidth="1" />
    </svg>
  )
}
