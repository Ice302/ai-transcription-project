import { ArrowUp, Copy, Download, RotateCcw, Square, X } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useToast } from '../hooks/toast'
import { streamChat } from '../lib/api'
import { download, parseTime } from '../lib/format'

const Markdown = lazy(() => import('./Markdown'))

const PROMPTS = [
  ['Summary', 'Summarize this. Cross-check the speech against the on-screen content and cite timestamps.'],
  ['Meeting notes', 'Write structured notes: overview, key points per topic (with timestamps), decisions, open questions. Include important on-screen details that were not spoken.'],
  ['Action items', 'List every action item as a table: task, owner, due date, timestamp. Use on-screen spellings for names and attribute owners to the speakers who committed.'],
  ['Decisions', 'What was decided, by whom, and when? Quote the deciding line with its timestamp.'],
  ['What was shown', 'List the key visuals (slides, charts, screens) in order, with timestamps and what was said about each.'],
  ['Follow-up email', 'Draft a short follow-up email to the participants: summary, decisions, action items with owners and dates.'],
]

// [12:34] / [1:02:03] become links; clicking one seeks the open recording.
const linkTimestamps = (text) => text.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, '[$1](#t=$1)')

const histories = new Map() // per-scope chat history for this tab, so switching back keeps the conversation

export default function AssistantPanel({ scope, health, onSeek, onClose }) {
  const [history, setHistory] = useState(() => histories.get(scope.key) || [])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const push = useToast()
  const abort = useRef(null)
  const scroller = useRef(null)
  const textarea = useRef(null)

  useEffect(() => {
    abort.current?.abort()
    setHistory(histories.get(scope.key) || [])
    setStreaming(false)
  }, [scope.key])

  useEffect(() => {
    histories.set(scope.key, history.filter((m) => !m.pending))
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
  }, [history, scope.key])

  const ready = scope.kind !== 'none' && health?.llm_configured
  const disabledReason =
    scope.kind === 'none'
      ? scope.reason || 'Open a recording, start a meeting, or tick recordings in the library to ask about them.'
      : !health
        ? 'Connecting to the backend…'
        : health.local_only
          ? 'Local-only mode is on, so the assistant (an online AI model) is disabled.'
          : !health.llm_configured
            ? 'Add OPENROUTER_API_KEY to backend/.env and restart the backend to enable the assistant.'
            : ''

  const ask = async (prompt, base = history) => {
    const text = prompt.trim()
    if (!text || streaming || !ready) return
    const conversation = [...base.filter((m) => !m.error), { role: 'user', content: text }]
    setHistory([...conversation, { role: 'assistant', content: '', pending: true }])
    setInput('')
    setStreaming(true)
    const controller = new AbortController()
    abort.current = controller
    try {
      const answer = await streamChat({
        messages: conversation.slice(-20).map(({ role, content }) => ({ role, content })),
        jobIds: scope.jobIds || [],
        context: scope.kind === 'live' ? scope.context : '',
        signal: controller.signal,
        onDelta: (partial) => setHistory((h) => [...h.slice(0, -1), { role: 'assistant', content: partial, pending: true }]),
      })
      setHistory((h) => [...h.slice(0, -1), { role: 'assistant', content: answer || '_No answer was generated._' }])
    } catch (err) {
      setHistory((h) => {
        const last = h[h.length - 1]
        if (err.name === 'AbortError') return [...h.slice(0, -1), { role: 'assistant', content: `${last?.content || ''}\n\n_Stopped._` }]
        return [...h.slice(0, -1), { role: 'assistant', content: `⚠️ ${err.message}`, error: true }]
      })
    } finally {
      setStreaming(false)
      abort.current = null
    }
  }

  const regenerate = () => {
    const lastUser = [...history].reverse().findIndex((m) => m.role === 'user')
    if (lastUser < 0) return
    const idx = history.length - 1 - lastUser
    ask(history[idx].content, history.slice(0, idx))
  }

  const markdown = {
    a: ({ href, children }) =>
      href?.startsWith('#t=') ? (
        <button
          type="button"
          disabled={!onSeek}
          onClick={() => onSeek?.(parseTime(href.slice(3)))}
          className="rounded-md bg-lime/15 px-1 font-mono text-[0.85em] text-lime no-underline hover:bg-lime hover:text-[#131312] disabled:cursor-default disabled:hover:bg-lime/15 disabled:hover:text-lime"
        >
          {children}
        </button>
      ) : (
        <a href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      ),
  }

  return (
    <aside className="flex h-full flex-col overflow-hidden rounded-card bg-ink text-on-ink dark:border dark:border-line dark:bg-surface-2 dark:text-ink">
      <div className="flex items-start gap-3 px-5 pb-3 pt-5">
        <div className="min-w-0 flex-1">
          <h2 className="text-[22px] font-semibold leading-none tracking-tight">
            Notes <span className="serif-accent text-[1.18em]">assistant</span>
          </h2>
          <p className="mt-2 flex items-center gap-2 truncate font-mono text-[11px] opacity-60">
            <span className={`size-1.5 shrink-0 rounded-full ${scope.kind === 'none' ? 'bg-current' : 'bg-lime'}`} />
            <span className="truncate">{scope.label}</span>
          </p>
        </div>
        {onClose && (
          <button type="button" aria-label="Close assistant" onClick={onClose} className="rounded-full p-1.5 opacity-60 hover:bg-white/10 hover:opacity-100">
            <X className="size-4" />
          </button>
        )}
      </div>

      <div className="no-scrollbar flex gap-1.5 overflow-x-auto px-5 pb-4 mask-[linear-gradient(to_right,black_85%,transparent)]">
        {PROMPTS.map(([label, prompt]) => (
          <button
            key={label}
            type="button"
            disabled={!ready || streaming}
            onClick={() => ask(prompt)}
            className="shrink-0 rounded-full border border-lime/50 px-3 py-1.5 text-xs font-medium text-lime transition hover:bg-lime hover:text-[#131312] disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-lime"
          >
            {label}
          </button>
        ))}
      </div>

      <div ref={scroller} className="scroll-thin flex-1 space-y-5 overflow-y-auto border-t border-white/10 px-5 py-5 dark:border-line">
        {disabledReason ? (
          <p className="text-sm leading-relaxed opacity-60">{disabledReason}</p>
        ) : history.length === 0 ? (
          <div className="space-y-3 text-sm leading-relaxed opacity-70">
            <p>
              Ask for a summary, notes or action items. Answers combine what was <span className="serif-accent text-[1.1em]">said</span> with what was{' '}
              <span className="serif-accent text-[1.1em]">shown</span>, and timestamps are clickable.
            </p>
          </div>
        ) : (
          history.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <p className="max-w-[88%] whitespace-pre-wrap rounded-3xl rounded-br-md bg-lime px-4 py-2.5 text-sm text-[#131312]">{m.content}</p>
              </div>
            ) : (
              <div key={i} className="group">
                <div
                  className={`prose prose-sm prose-invert max-w-none prose-headings:tracking-tight prose-a:text-lime prose-table:block prose-table:overflow-x-auto prose-table:text-xs prose-th:text-left prose-td:align-top dark:prose-invert ${
                    m.pending ? 'stream-caret' : ''
                  } ${m.error ? 'text-signal' : ''}`}
                >
                  <Suspense fallback={<p className="whitespace-pre-wrap">{m.content}</p>}>
                    <Markdown components={markdown}>{linkTimestamps(m.content)}</Markdown>
                  </Suspense>
                </div>
                {m.error && i === history.length - 1 && !streaming && (
                  <div className="mt-2 flex gap-1">
                    <MiniButton icon={RotateCcw} label="Try again" onClick={regenerate} />
                  </div>
                )}
                {!m.pending && !m.error && (
                  <div className="mt-2 flex gap-1 opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
                    <MiniButton
                      icon={Copy}
                      label="Copy"
                      onClick={() =>
                        navigator.clipboard
                          .writeText(m.content)
                          .then(() => push('Copied', { tone: 'success' }))
                          .catch(() => push('Clipboard is blocked', { tone: 'error' }))
                      }
                    />
                    <MiniButton icon={Download} label="Save as note" onClick={() => download('notes.md', m.content, 'text/markdown')} />
                    {i === history.length - 1 && <MiniButton icon={RotateCcw} label="Regenerate" onClick={regenerate} />}
                  </div>
                )}
              </div>
            ),
          )
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(input)
        }}
        className="flex items-end gap-2 border-t border-white/10 p-3 dark:border-line"
      >
        <textarea
          ref={textarea}
          rows={1}
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            e.target.style.height = 'auto'
            e.target.style.height = `${Math.min(160, e.target.scrollHeight)}px`
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              ask(input)
            }
          }}
          disabled={!ready}
          placeholder={ready ? 'Ask anything about it…' : scope.kind === 'none' ? 'Pick something to ask about first' : 'Assistant unavailable'}
          aria-label="Message the notes assistant"
          className="max-h-40 min-h-11 flex-1 resize-none rounded-3xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm text-inherit outline-none placeholder:opacity-50 focus:border-lime dark:border-line dark:bg-surface"
        />
        {streaming ? (
          <button type="button" aria-label="Stop" onClick={() => abort.current?.abort()} className="grid size-11 shrink-0 place-items-center rounded-full bg-signal text-white">
            <Square className="size-4" />
          </button>
        ) : (
          <button
            type="submit"
            aria-label="Send"
            disabled={!ready || !input.trim()}
            className="grid size-11 shrink-0 place-items-center rounded-full bg-lime text-[#131312] transition disabled:opacity-35"
          >
            <ArrowUp className="size-5" strokeWidth={2.5} />
          </button>
        )}
      </form>
    </aside>
  )
}

function MiniButton({ icon: Icon, label, onClick }) {
  return (
    <button type="button" onClick={onClick} className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] opacity-70 hover:bg-white/10 hover:opacity-100 dark:hover:bg-paper">
      <Icon className="size-3.5" />
      {label}
    </button>
  )
}
