import { useEffect, useRef, useState } from 'react'

const POLL_MS = 2000
const TERMINAL = ['ready', 'rendered', 'failed']
const SHOWABLE = ['ready', 'rendered', 'rendering']

export default function JobView({ jobId, onReset }) {
  const [job, setJob] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState([])
  const [saveError, setSaveError] = useState(null)
  const [thumbs, setThumbs] = useState([])
  const [watchingRender, setWatchingRender] = useState(false)
  const videoRef = useRef(null)

  // Poll job status until it reaches a terminal state. Transient fetch
  // failures keep retrying instead of silently freezing the UI; a missing
  // job stops the loop with an explicit error.
  useEffect(() => {
    let cancelled = false
    let timer
    async function poll() {
      try {
        const res = await fetch(`/api/jobs/${jobId}`)
        if (res.status === 404) {
          if (!cancelled) setLoadError('Job not found')
          return
        }
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (cancelled) return
        setLoadError(null)
        setJob(data)
        if (!TERMINAL.includes(data.status)) timer = setTimeout(poll, POLL_MS)
      } catch {
        if (!cancelled) {
          setLoadError('Connection lost — retrying…')
          timer = setTimeout(poll, POLL_MS)
        }
      }
    }
    poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId])

  // Watch an in-flight render (triggered by startRender) until terminal.
  // The interval is owned by this effect, so unmount always cleans it up.
  useEffect(() => {
    if (!watchingRender) return
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`)
        if (!res.ok) return
        const data = await res.json()
        setJob(data)
        if (TERMINAL.includes(data.status)) setWatchingRender(false)
      } catch {
        // keep polling; the main loop surfaces persistent failures
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [watchingRender, jobId])

  // Load the frame manifest once the job has something to show.
  const showable = job?.status && SHOWABLE.includes(job.status)
  useEffect(() => {
    if (!showable) return
    let cancelled = false
    fetch(`/api/jobs/${jobId}/frames`)
      .then((r) => (r.ok ? r.json() : []))
      .then((frames) => {
        if (cancelled) return
        // Cap the strip at 30 evenly-spaced thumbs.
        const step = Math.max(1, Math.ceil(frames.length / 30))
        setThumbs(frames.filter((_, i) => i % step === 0))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [jobId, showable])

  if (loadError && !job) return <div className="app"><p style={{ color: '#ff8f8f' }}>{loadError}</p></div>
  if (!job) return <div className="app"><p>Loading…</p></div>

  const duration = job.meta?.duration_s || 0
  const segments = job.segments || []
  const kept = segments.reduce((a, s) => a + (s.end_s - s.start_s), 0)
  const notes = job.frame_notes || []
  const busy = !TERMINAL.includes(job.status)
  const chunkMatch = job.progress?.match(/(\d+)\/(\d+)/)
  const progressFrac = chunkMatch ? parseInt(chunkMatch[1]) / parseInt(chunkMatch[2]) : null

  // Auto-skip cut ranges during playback.
  function onTimeUpdate() {
    if (editing) return
    const v = videoRef.current
    if (!v) return
    const inKeep = segments.some((s) => v.currentTime >= s.start_s && v.currentTime < s.end_s)
    if (!inKeep && segments.length) {
      const next = segments.find((s) => s.start_s > v.currentTime)
      if (next) v.currentTime = next.start_s
      else v.pause()
    }
  }

  async function startRender() {
    setSaveError(null)
    try {
      const res = await fetch(`/api/jobs/${jobId}/render`, { method: 'POST' })
      if (!res.ok) {
        setSaveError('Render failed to start')
        return
      }
      setWatchingRender(true)
    } catch {
      setSaveError('Render failed to start — network error')
    }
  }

  function startEdit() {
    setDraft(segments.map((s) => ({ ...s })))
    setSaveError(null)
    setEditing(true)
  }

  function updateDraft(i, field, value) {
    const parsed = parseFloat(value)
    if (Number.isNaN(parsed)) return // partial input ("" / "-") — wait for a real number
    const next = draft.map((s, j) => (j === i ? { ...s, [field]: parsed } : s))
    setDraft(next)
  }

  function removeDraft(i) {
    setDraft(draft.filter((_, j) => j !== i))
  }

  function addDraft() {
    // Place a 5s segment in the largest gap; clamp if the video is short.
    const sorted = [...draft].sort((a, b) => a.start_s - b.start_s)
    let best = { start: 0, len: sorted[0] ? sorted[0].start_s : duration }
    for (let i = 0; i < sorted.length; i++) {
      const gapEnd = i + 1 < sorted.length ? sorted[i + 1].start_s : duration
      const gap = gapEnd - sorted[i].end_s
      if (gap > best.len) best = { start: sorted[i].end_s, len: gap }
    }
    const len = Math.min(5, best.len > 0 ? best.len : 5)
    if (best.len <= 0) return
    setDraft([...draft, { start_s: round1(best.start), end_s: round1(best.start + len), reason: 'added manually', confidence: 1 }])
  }

  async function save() {
    setSaveError(null)
    const res = await fetch(`/api/jobs/${jobId}/segments`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draft),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      setSaveError(err.detail || 'Save failed')
      return
    }
    setJob(await res.json())
    setEditing(false)
  }

  const showPlayer = SHOWABLE.includes(job.status)

  return (
    <div className="app">
      <h1>cutlass<span>.</span> <span className="status">{job.status}</span></h1>
      {busy && (
        <p className="muted">
          {job.progress || 'working…'}
          {loadError && <span style={{ color: '#ff8f8f' }}> ({loadError})</span>}
          {progressFrac !== null && (
            <span className="progressbar">
              <span style={{ width: `${Math.round(progressFrac * 100)}%` }} />
            </span>
          )}
        </p>
      )}
      <p className="muted">
        {job.filename}
        {duration > 0 && ` — ${duration.toFixed(0)}s original`}
        {kept > 0 && ` → ${kept.toFixed(0)}s kept (${Math.round((kept / duration) * 100)}%)`}
      </p>

      {job.status === 'failed' && (
        <p style={{ color: '#ff8f8f' }}>Analysis failed: {job.error}</p>
      )}

      {showPlayer && (
        <>
          <video
            ref={videoRef}
            src={`/api/jobs/${jobId}/source`}
            controls
            onTimeUpdate={onTimeUpdate}
          />

          <div
            className="timeline"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const frac = (e.clientX - rect.left) / rect.width
              const t = frac * duration
              const seg = segments.find((s) => t >= s.start_s && t <= s.end_s)
              if (videoRef.current) videoRef.current.currentTime = seg ? t : (segments[0]?.start_s ?? 0)
            }}
          >
            {(editing ? draft : segments).map((s, i) => (
              <div
                key={i}
                className="keep"
                style={{
                  left: `${(Math.min(s.start_s, duration) / duration) * 100}%`,
                  width: `${(Math.max(0, s.end_s - s.start_s) / duration) * 100}%`,
                }}
              />
            ))}
          </div>

          {!editing && thumbs.length > 0 && (
            <div className="filmstrip">
              {thumbs.map((f) => (
                <img
                  key={f.file}
                  src={`/api/jobs/${jobId}/frames/${f.file}`}
                  alt={`${f.t}s`}
                  title={`${f.t}s`}
                  onClick={() => videoRef.current && (videoRef.current.currentTime = f.t)}
                />
              ))}
            </div>
          )}

          {!editing && notes.length > 0 && duration > 0 && (
            <div className="notestrip" title="AI frame labels — hover a tick for details">
              {notes.map((n, i) => (
                <span
                  key={i}
                  className={`note ${n.label}`}
                  style={{ left: `${(Math.min(n.timestamp_s, duration) / duration) * 100}%` }}
                  title={`${n.timestamp_s.toFixed(1)}s [${n.label}] ${n.description}`}
                />
              ))}
            </div>
          )}

          {editing ? (
            <>
              <ul className="segments edit">
                {draft.map((s, i) => (
                  <li key={i} className="edit-row">
                    <label>
                      start <input type="number" step="0.1" min="0" max={duration} value={s.start_s}
                        onChange={(e) => updateDraft(i, 'start_s', e.target.value)} />
                    </label>
                    <label>
                      end <input type="number" step="0.1" min="0" max={duration} value={s.end_s}
                        onChange={(e) => updateDraft(i, 'end_s', e.target.value)} />
                    </label>
                    <span className="muted">{(Math.max(0, s.end_s - s.start_s)).toFixed(1)}s</span>
                    <button className="icon" onClick={() => removeDraft(i)}>✕</button>
                  </li>
                ))}
              </ul>
              <p>
                <button onClick={save}>Save</button>{' '}
                <button className="secondary" onClick={addDraft} disabled={duration <= 0}>+ Add segment</button>{' '}
                <button className="secondary" onClick={() => setEditing(false)}>Cancel</button>
              </p>
              {saveError && <p style={{ color: '#ff8f8f' }}>{saveError}</p>}
            </>
          ) : (
            <>
              <ul className="segments">
                {segments.map((s, i) => (
                  <li
                    key={i}
                    onClick={() => videoRef.current && (videoRef.current.currentTime = s.start_s)}
                  >
                    <strong>{fmt(s.start_s)} – {fmt(s.end_s)}</strong>
                    <span className="muted"> ({(s.end_s - s.start_s).toFixed(1)}s) — {s.reason}</span>
                  </li>
                ))}
              </ul>
              <p>
                {job.status === 'ready' && <button onClick={startRender}>Render final cut</button>}{' '}
                {job.status === 'rendering' && <button disabled>Rendering…</button>}{' '}
                <button className="secondary" onClick={startEdit}>Edit segments</button>
              </p>
              {saveError && <p style={{ color: '#ff8f8f' }}>{saveError}</p>}
              {job.has_render && (
                <p>
                  <a
                    href={`/api/jobs/${jobId}/render`}
                    download="final_cut.mp4"
                    style={{ color: '#4f9cf9' }}
                  >
                    Download final_cut.mp4
                  </a>
                </p>
              )}

              {(job.transcript || []).length > 0 && (
                <div className="transcript">
                  <div className="muted">Transcript — click a line to jump there</div>
                  <ul>
                    {job.transcript.map((line, i) => (
                      <li
                        key={i}
                        onClick={() => videoRef.current && (videoRef.current.currentTime = line.start_s)}
                      >
                        <span className="ts">{fmt(line.start_s)}</span> {line.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </>
      )}

      <p><button onClick={onReset} className="secondary" style={{ marginTop: 16 }}>
        New video
      </button></p>
    </div>
  )
}

function round1(n) {
  return Math.round(n * 10) / 10
}

function fmt(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
