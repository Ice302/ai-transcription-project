import { LoaderCircle, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

const BUTTON_TONES = {
  ink: 'bg-ink text-on-ink hover:bg-ink-2 border-transparent',
  lime: 'bg-lime text-[#131312] hover:bg-lime-strong border-transparent',
  ghost: 'bg-transparent text-ink border-line hover:border-ink hover:bg-surface-2',
  soft: 'bg-surface-2 text-ink border-line hover:border-ink',
  signal: 'bg-signal text-white hover:brightness-110 border-transparent',
  danger: 'bg-transparent text-signal border-signal/40 hover:bg-signal-pale',
}
const BUTTON_SIZES = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-6 text-[15px] gap-2.5',
}

export function Button({ tone = 'ink', size = 'md', icon: Icon, loading, className = '', children, ...props }) {
  return (
    <button
      type="button"
      className={`inline-flex shrink-0 items-center justify-center rounded-full border font-medium transition disabled:cursor-not-allowed disabled:opacity-45 ${BUTTON_TONES[tone]} ${BUTTON_SIZES[size]} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" /> : Icon ? <Icon className="size-4" strokeWidth={2} /> : null}
      {children}
    </button>
  )
}

// Round icon button (the black circles of the flat reference).
export function IconButton({ icon: Icon, label, tone = 'ghost', size = 'md', className = '', ...props }) {
  const dims = size === 'lg' ? 'size-12' : size === 'sm' ? 'size-8' : 'size-10'
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`inline-flex shrink-0 items-center justify-center rounded-full border transition disabled:cursor-not-allowed disabled:opacity-45 ${BUTTON_TONES[tone]} ${dims} ${className}`}
      {...props}
    >
      <Icon className={size === 'lg' ? 'size-5' : 'size-4'} strokeWidth={2} />
    </button>
  )
}

// Pill tabs: black active pill on an outlined track (Today | Calendar in the references).
export function Segmented({ value, onChange, options, size = 'md', className = '', label }) {
  const pad = size === 'sm' ? 'h-8 px-3 text-xs' : 'h-10 px-4 text-sm'
  return (
    <div role="tablist" aria-label={label} className={`inline-flex items-center gap-1 rounded-full border border-line bg-surface-2/70 p-1 ${className}`}>
      {options.map((o) => {
        const active = o.value === value
        const Icon = o.icon
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            disabled={o.disabled}
            className={`inline-flex items-center gap-1.5 rounded-full font-medium transition ${pad} ${
              active ? 'bg-ink text-on-ink' : 'text-ink-2 hover:text-ink'
            } disabled:opacity-40`}
          >
            {Icon && <Icon className="size-3.5" />}
            {o.label}
            {o.badge != null && o.badge !== 0 && (
              <span className={`rounded-full px-1.5 text-[10px] font-semibold ${active ? 'bg-lime text-[#131312]' : 'bg-line text-ink-2'}`}>{o.badge}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export function Chip({ children, tone = 'line', className = '', title }) {
  const tones = {
    line: 'border border-line text-ink-2 bg-surface-2/60',
    ink: 'bg-ink text-on-ink',
    lime: 'bg-lime text-[#131312]',
    pale: 'bg-lime-pale text-ink',
    signal: 'bg-signal-pale text-signal',
    tint: 'bg-[color-mix(in_oklab,currentColor_14%,transparent)]',
  }
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium leading-5 ${tones[tone]} ${className}`}>
      {children}
    </span>
  )
}

export function Switch({ checked, onChange, label, description, disabled }) {
  const id = useId()
  return (
    <label htmlFor={id} className={`flex items-start gap-3 ${disabled ? 'opacity-45' : 'cursor-pointer'}`}>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-10 shrink-0 rounded-full border transition ${checked ? 'border-ink bg-ink' : 'border-line-2 bg-surface-2'}`}
      >
        <span className={`absolute top-0.5 size-4.5 rounded-full transition-all ${checked ? 'left-[18px] bg-lime' : 'left-0.5 bg-line-2'}`} />
      </button>
      <span className="text-sm">
        <span className="font-medium text-ink">{label}</span>
        {description && <span className="block text-xs text-ink-3">{description}</span>}
      </span>
    </label>
  )
}

// Big-number tile (the "4 Finished / 2 Doing / 7 Abandon" tiles of the flat reference).
export function StatTile({ label, value, unit, tone = 'surface', className = '' }) {
  const tones = {
    surface: 'bg-surface border border-line text-ink',
    lime: 'bg-lime text-[#131312]',
    ink: 'bg-ink text-on-ink',
    signal: 'bg-signal text-white',
  }
  return (
    <div className={`tile flex min-w-0 flex-col justify-between gap-6 p-4 ${tones[tone]} ${className}`}>
      <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${tone === 'surface' ? 'text-ink-3' : 'opacity-70'}`}>{label}</span>
      <span className="display tabular truncate text-[clamp(28px,3.2vw,44px)]">
        {value}
        {unit && <span className="ml-1 text-[0.4em] font-medium tracking-normal opacity-70">{unit}</span>}
      </span>
    </div>
  )
}

export function ProgressBar({ value, tone = 'ink', className = '' }) {
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded-full bg-[color-mix(in_oklab,currentColor_15%,transparent)] ${className}`}>
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${tone === 'lime' ? 'bg-lime' : 'bg-current'}`}
        style={{ width: `${Math.max(2, Math.min(100, (value || 0) * 100))}%` }}
      />
    </div>
  )
}

export function Spinner({ className = '' }) {
  return <LoaderCircle className={`size-4 animate-spin ${className}`} aria-hidden />
}

export function Kbd({ children }) {
  return <kbd className="rounded-md border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-ink-2">{children}</kbd>
}

export function Dialog({ open, onClose, title, children, footer, wide }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`m-auto w-[calc(100%-2rem)] ${wide ? 'max-w-2xl' : 'max-w-lg'} rounded-card border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm`}
    >
      {open && (
        <div className="flex max-h-[85vh] flex-col">
          <div className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
            <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
            <IconButton icon={X} label="Close" size="sm" onClick={onClose} />
          </div>
          <div className="scroll-thin overflow-y-auto px-6 py-5">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-4">{footer}</div>}
        </div>
      )}
    </dialog>
  )
}

// Small dropdown menu; closes on outside click or Escape.
export function Menu({ trigger, items, align = 'right' }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e) => !ref.current?.contains(e.target) && setOpen(false)
    const onKey = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div ref={ref} className="relative">
      {trigger({ open, toggle: () => setOpen((v) => !v) })}
      {open && (
        <div
          role="menu"
          className={`animate-rise absolute top-full z-40 mt-2 min-w-56 overflow-hidden rounded-2xl border border-line bg-surface-2 p-1.5 shadow-xl ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          {items.map((item, i) =>
            item.divider ? (
              <div key={i} className="my-1 h-px bg-line" />
            ) : (
              <button
                key={item.label}
                role="menuitem"
                type="button"
                disabled={item.disabled}
                onClick={() => {
                  setOpen(false)
                  item.onClick()
                }}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition hover:bg-paper disabled:opacity-40 ${item.danger ? 'text-signal' : 'text-ink'}`}
              >
                {item.icon && <item.icon className="size-4 opacity-70" />}
                <span className="flex-1">{item.label}</span>
                {item.hint && <span className="font-mono text-[10px] text-ink-3">{item.hint}</span>}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}

export function EmptyNote({ children }) {
  return <p className="rounded-2xl border border-dashed border-line-2 px-4 py-6 text-center text-sm text-ink-3">{children}</p>
}
