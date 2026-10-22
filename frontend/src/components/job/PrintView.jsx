import { apiUrl } from '../../lib/api'
import { formatDate, formatTime } from '../../lib/format'

// Only visible when printing ("Print / Save as PDF"): a clean notes document.
export default function PrintView({ result }) {
  const names = new Map(result.speakers.map((s) => [s.id, s.name]))
  const bySceneId = new Map()
  for (const s of result.segments) {
    if (!bySceneId.has(s.scene_id)) bySceneId.set(s.scene_id, [])
    bySceneId.get(s.scene_id).push(s)
  }
  const line = (s) => (
    <p key={s.id} style={{ margin: '0 0 6px', fontSize: 12, lineHeight: 1.5 }}>
      <span style={{ fontFamily: 'monospace', color: '#666', marginRight: 8 }}>{formatTime(s.start)}</span>
      {s.speaker && <strong>{names.get(s.speaker)}: </strong>}
      {s.text}
    </p>
  )
  return (
    <article className="print-only" style={{ fontFamily: 'Geist Variable, sans-serif', color: '#111' }}>
      <h1 style={{ fontSize: 28, margin: '0 0 4px' }}>{result.title}</h1>
      <p style={{ color: '#555', fontSize: 12, margin: '0 0 18px' }}>
        {formatDate(result.created_at)} · {formatTime(result.media?.duration)} · {result.language?.toUpperCase()}
        {result.speakers.length > 0 && ` · ${result.speakers.map((s) => s.name).join(', ')}`}
      </p>
      {result.keyframes.length
        ? result.keyframes.map((kf) => (
            <section key={kf.id} style={{ breakInside: 'avoid-page', marginBottom: 18 }}>
              <h2 style={{ fontSize: 16, margin: '0 0 6px' }}>
                {String(kf.id + 1).padStart(2, '0')} · {kf.title || 'Scene'}{' '}
                <span style={{ color: '#777', fontWeight: 400, fontSize: 12 }}>
                  {formatTime(kf.t)}–{formatTime(kf.end)}
                </span>
              </h2>
              <img src={apiUrl(kf.image)} alt="" style={{ width: 260, borderRadius: 6, margin: '0 0 6px' }} />
              {kf.ocr_text && <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, color: '#444', margin: '0 0 8px', fontFamily: 'inherit' }}>{kf.ocr_text}</pre>}
              {(bySceneId.get(kf.id) || []).map(line)}
            </section>
          ))
        : result.segments.map(line)}
    </article>
  )
}
