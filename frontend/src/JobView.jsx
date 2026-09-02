import { useEffect, useRef, useState } from 'react'

const POLL_MS = 2000
const TERMINAL = ['ready', 'rendered', 'failed']

export default function JobView({ jobId, onReset }) {
  const [job, setJob] = useState(null)
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
    const v = videoRef.current
    if (!v) return
    const inKeep = segments.some((s) => v.currentTime >= s.start_s && v.currentTime < s.end_s)
    if (!inKeep && segments.length) {
      const next = segments.find((s) => s.start_s > v.currentTime)
      if (next) v.currentTime = next.start_s
      else v.pause()
    }
  }

  async function render() {
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

      {(job.status === 'ready' || job.status === 'rendered' || job.status === 'rendering') && (
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
            {segments.map((s, i) => (
              <div
                key={i}
                className="keep"
                style={{
                  left: `${(s.start_s / duration) * 100}%`,
                  width: `${((s.end_s - s.start_s) / duration) * 100}%`,
                }}
              />
            ))}
          </div>

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

          {job.status === 'ready' && <button onClick={render}>Render final cut</button>}
          {job.status === 'rendering' && <button disabled>Rendering…</button>}
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

      <p><button onClick={onReset} style={{ background: '#3a4150', color: '#e6e8ec', marginTop: 16 }}>
        New video
      </button></p>
    </div>
  )
}

function fmt(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}
