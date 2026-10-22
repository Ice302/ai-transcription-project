import { AudioLines, Captions, FastForward, Rewind } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { apiUrl } from '../../lib/api'
import { formatTime, toVTT } from '../../lib/format'
import { IconButton } from '../ui'

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2]

export default function Player({ mediaRef, src, result, now, initialTime, onReady, captions, onCaptions }) {
  const isVideo = result.media?.has_video
  const [speed, setSpeed] = useState(1)
  const [failed, setFailed] = useState(false)

  // WebVTT captions generated from the (possibly edited) transcript.
  const vttUrl = useMemo(() => URL.createObjectURL(new Blob([toVTT(result)], { type: 'text/vtt' })), [result])
  useEffect(() => () => URL.revokeObjectURL(vttUrl), [vttUrl])

  useEffect(() => {
    const track = mediaRef.current?.textTracks?.[0]
    if (track) track.mode = captions ? 'showing' : 'hidden'
  }, [captions, vttUrl, mediaRef])

  useEffect(() => {
    if (mediaRef.current) mediaRef.current.playbackRate = speed
  }, [speed, mediaRef])

  const onLoaded = (e) => {
    if (initialTime != null) e.currentTarget.currentTime = initialTime
    e.currentTarget.playbackRate = speed
    onReady?.()
  }
  const skip = (delta) => {
    const el = mediaRef.current
    if (el) el.currentTime = Math.max(0, Math.min((el.duration || Infinity) - 0.1, el.currentTime + delta))
  }

  if (!src) {
    return (
      <div className="card flex items-center gap-4 p-5 text-sm text-ink-2">
        <AudioLines className="size-5 shrink-0" />
        The original media wasn’t kept for this recording (KEEP_MEDIA=false), so it can’t be played here. Keyframes and the transcript are
        still available.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {isVideo ? (
        <video
          key={src}
          ref={mediaRef}
          src={src}
          controls
          preload="metadata"
          poster={result.keyframes?.[0]?.image ? apiUrl(result.keyframes[0].image) : undefined}
          playsInline
          onLoadedMetadata={onLoaded}
          onError={() => setFailed(true)}
          className="aspect-video max-h-[480px] w-full rounded-[22px] bg-black object-contain"
        >
          <track kind="captions" src={vttUrl} srcLang={result.language || 'en'} label="Transcript" />
        </video>
      ) : (
        <div className="card relative overflow-hidden p-5">
          <div className="hairline-grid pointer-events-none absolute inset-0 opacity-50" />
          <div className="relative flex items-center gap-4">
            <span className="grid size-14 shrink-0 place-items-center rounded-full bg-ink text-lime">
              <AudioLines className="size-6" />
            </span>
            <audio key={src} ref={mediaRef} src={src} controls preload="metadata" onLoadedMetadata={onLoaded} onError={() => setFailed(true)} className="w-full">
              <track kind="captions" src={vttUrl} srcLang={result.language || 'en'} label="Transcript" />
            </audio>
          </div>
        </div>
      )}
      {failed && (
        <p className="text-xs text-signal">This browser can’t play this file format. Keyframes and the transcript still work; convert to MP4/M4A for playback.</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <IconButton icon={Rewind} label="Back 5 seconds (J)" size="sm" onClick={() => skip(-5)} />
        <IconButton icon={FastForward} label="Forward 5 seconds (L)" size="sm" onClick={() => skip(5)} />
        <span className="font-mono text-xs tabular text-ink-2">
          {formatTime(now)} <span className="text-ink-3">/ {formatTime(result.media?.duration)}</span>
        </span>
        <div className="ml-auto flex items-center gap-2">
          {isVideo && (
            <IconButton
              icon={Captions}
              label={captions ? 'Hide captions (C)' : 'Show captions (C)'}
              size="sm"
              tone={captions ? 'ink' : 'ghost'}
              onClick={() => onCaptions(!captions)}
            />
          )}
          <label className="flex items-center gap-1.5 text-xs text-ink-3">
            Speed
            <select
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
              className="rounded-full border border-line bg-surface-2 px-2 py-1 font-mono text-xs text-ink"
            >
              {SPEEDS.map((s) => (
                <option key={s} value={s}>
                  {s}×
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </div>
  )
}

