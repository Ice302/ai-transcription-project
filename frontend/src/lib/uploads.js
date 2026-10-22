// Upload options (remembered per browser) and media-file filtering, shared by the
// upload card and the drop-anywhere overlay.
const KEY = 'tt-upload-options'
export const UPLOAD_DEFAULTS = { language: '', num_speakers: '', glossary: '', diarize: true, describe_visuals: false }
const MEDIA_RE = /\.(mp4|mov|mkv|webm|avi|wmv|m4v|mp3|wav|m4a|aac|flac|ogg|opus|wma)$/i

export function loadUploadOptions() {
  try {
    return { ...UPLOAD_DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') }
  } catch {
    return { ...UPLOAD_DEFAULTS }
  }
}

export function saveUploadOptions(options) {
  try {
    localStorage.setItem(KEY, JSON.stringify(options))
  } catch {
    /* per-browser convenience only */
  }
}

export const mediaFiles = (fileList) => Array.from(fileList || []).filter((f) => /^(audio|video)\//.test(f.type) || MEDIA_RE.test(f.name))

// The form fields the backend expects, from the saved options.
export function uploadFields(options, health) {
  return {
    language: options.language,
    glossary: (options.glossary || '').trim(),
    diarize: options.diarize,
    num_speakers: options.num_speakers,
    describe_visuals: Boolean(options.describe_visuals && health?.vision_enabled),
  }
}

// Rough time left from progress so far (stages are weighted, so this is an estimate).
export function etaSeconds(job, nowSeconds = Date.now() / 1000) {
  if (job.status !== 'running' || !job.started_at || !job.progress || job.progress < 0.04) return null
  const elapsed = nowSeconds - job.started_at
  return Math.max(1, (elapsed * (1 - job.progress)) / job.progress)
}

export function formatEta(seconds) {
  if (seconds == null) return ''
  if (seconds < 60) return `≈ ${Math.round(seconds)} s left`
  return `≈ ${Math.round(seconds / 60)} min left`
}
