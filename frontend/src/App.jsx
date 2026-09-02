import { useEffect, useState } from 'react'
import JobView from './JobView.jsx'

export default function App() {
  const [jobId, setJobId] = useState(null)
  const [jobs, setJobs] = useState([])
  const [drag, setDrag] = useState(false)
  const [error, setError] = useState(null)

  async function refreshJobs() {
    const res = await fetch('/api/jobs')
    if (res.ok) setJobs(await res.json())
  }

  useEffect(() => { refreshJobs() }, [])

  async function upload(file) {
    setError(null)
    const body = new FormData()
    body.append('video', file)
    const res = await fetch('/api/upload', { method: 'POST', body })
    if (!res.ok) {
      setError('Upload failed')
      return
    }
    const data = await res.json()
    setJobId(data.id)
  }

  if (jobId) return <JobView jobId={jobId} onReset={() => { setJobId(null); refreshJobs() }} />

  return (
    <div className="app">
      <h1>cutlass<span>.</span></h1>
      <p className="muted">Upload a video — the AI drafts the first cut for you.</p>
      <div
        className={`dropzone${drag ? ' drag' : ''}`}
        onClick={() => document.getElementById('file').click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0])
        }}
      >
        <p>Drop a video here, or click to browse</p>
        <p className="muted">MP4 / MOV / MKV / WebM</p>
        <input
          id="file"
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => e.target.files[0] && upload(e.target.files[0])}
        />
      </div>
      {error && <p style={{ color: '#ff8f8f' }}>{error}</p>}

      {jobs.length > 0 && (
        <>
          <h2>Recent videos</h2>
          <ul className="segments">
            {jobs.map((j) => (
              <li key={j.id} onClick={() => setJobId(j.id)}>
                <strong>{j.filename}</strong>{' '}
                <span className={`status ${j.status}`}>{j.status}</span>
                <div className="muted">
                  {j.duration_s ? `${j.duration_s.toFixed(0)}s` : ''}
                  {j.segments > 0 && ` · ${j.segments} segment${j.segments > 1 ? 's' : ''}`}
                  {j.has_render && ' · rendered'}
                  {j.created_at && ` · ${new Date(j.created_at + 'Z').toLocaleString()}`}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
