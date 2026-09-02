import { useEffect, useRef, useState } from 'react'

const POLL_MS = 2000
const TERMINAL = ['ready', 'rendered', 'failed']

export default function JobView({ jobId, onReset }) {
  const [job, setJob] = useState(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState([])
  const [saveError, setSaveError] = useState(null)
  const videoRef = useRef(null)

  useEffect(() => {
    let timer
    async function poll() {
      const res = await fetch(`/api/jobs/${jobId}`)
      if (res.ok) {
        const data = await res.json()
        setJob(data)
        if (!TERMINAL.includes(data.status)) timer = setTimeout(poll, POLL_MS)
      }
    }
    poll()
    return () => clearTimeout(timer)
  }, [jobId])

  if (!job) return <div className="app"><p>Loading…</p></div>

  const duration = job.meta?.duration_s || 0
  const segments = job.segments || []
  const kept = segments.reduce((a, s) => a + (s.end_s - s.start_s), 0)

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
    await fetch(`/api/jobs/${jobId}/render`, { method: 'POST' })
    const timer = setInterval(async () => {
      const res = await fetch(`/api/jobs/${jobId}`)
      if (res.ok) {
        const data = await res.json()
        setJob(data)
        if (TERMINAL.includes(data.status)) clearInterval(timer)
      }
    }, POLL_MS)
  }

  function startEdit() {
    setDraft(segments.map((s) => ({ ...s })))
    setSaveError(null)
    setEditing(true)
  }

  function updateDraft(i, field, value) {
    const next = draft.map((s, j) => (j === i ? { ...s, [field]: value } : s))
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

  const showPlayer = ['ready', 'rendered', 'rendering'].includes(job.status)

  return (
    <div className="app">
      <h1>cutlass<span>.</span> <span className="status">{job.status}</span></h1>
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

          {editing ? (
            <>
              <ul className="segments edit">
                {draft.map((s, i) => (
                  <li key={i} className="edit-row">
                    <label>
                      start <input type="number" step="0.1" min="0" max={duration} value={s.start_s}
                        onChange={(e) => updateDraft(i, 'start_s', parseFloat(e.target.value))} />
                    </label>
                    <label>
                      end <input type="number" step="0.1" min="0" max={duration} value={s.end_s}
                        onChange={(e) => updateDraft(i, 'end_s', parseFloat(e.target.value))} />
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
