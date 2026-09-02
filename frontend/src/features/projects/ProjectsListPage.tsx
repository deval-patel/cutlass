import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { fmtSeconds } from '../../lib/status'
import { useProjects, useUploadAsset } from './queries'

export default function ProjectsListPage() {
  const [drag, setDrag] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const upload = useUploadAsset()
  const projects = useProjects()

  async function handleUpload(file: File) {
    setError(null)
    try {
      const asset = await upload.mutateAsync(file)
      navigate(`/p/${asset.project_id}`)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Upload failed')
    }
  }

  return (
    <div className="app">
      <h1>
        cutlass<span>.</span>
      </h1>
      <p className="muted">Upload a video — the AI drafts the first cut for you.</p>
      <div
        className={`dropzone${drag ? ' drag' : ''}`}
        onClick={() => document.getElementById('file')?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          const file = e.dataTransfer.files[0]
          if (file) void handleUpload(file)
        }}
      >
        <p>{upload.isPending ? 'Uploading…' : 'Drop a video here, or click to browse'}</p>
        <p className="muted">MP4 / MOV / MKV / WebM</p>
        <input
          id="file"
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void handleUpload(file)
          }}
        />
      </div>
      {error && <p style={{ color: '#ff8f8f' }}>{error}</p>}

      {projects.data && projects.data.length > 0 && (
        <>
          <h2>Projects</h2>
          <ul className="segments">
            {projects.data.map((p) => (
              <li key={p.id}>
                <Link to={`/p/${p.id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
                  <strong>{p.name}</strong>
                  <div className="muted">
                    {p.assets} asset{p.assets === 1 ? '' : 's'}
                    {p.duration_s ? ` · ${fmtSeconds(p.duration_s)}` : ''}
                    {p.created_at && ` · ${new Date(p.created_at + 'Z').toLocaleString()}`}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
