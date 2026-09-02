import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import MediaPlayer from '../../components/MediaPlayer'
import { fmtSeconds, isTerminal } from '../../lib/status'
import type { Asset, FrameManifestItem, ProjectDetail, Segment } from '../../types'
import { queryKeys, useDeleteProject, useProject, useSaveSegments, useStartRender } from './queries'

const SHOWABLE: Asset['status'][] = ['ready', 'rendered', 'rendering']

export default function ProjectPage() {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()
  const project = useProject(projectId)
  const deleteProject = useDeleteProject()
  const videoRef = useRef<HTMLVideoElement>(null)

  const detail = project.data

  // Live status via SSE: patches the query cache between refetches.
  useAssetEvents(projectId, detail)

  // Load the frame manifest once the primary asset has something to show.
  const primary = detail?.assets[0]
  const showable = primary !== undefined && SHOWABLE.includes(primary.status)
  const [thumbs, setThumbs] = useState<FrameManifestItem[]>([])
  useEffect(() => {
    if (!showable || !primary) return
    let cancelled = false
    fetch(`/api/v1/assets/${primary.id}/frames`)
      .then((r) => (r.ok ? r.json() : []))
      .then((frames: FrameManifestItem[]) => {
        if (cancelled) return
        // Cap the strip at 30 evenly-spaced thumbs.
        const step = Math.max(1, Math.ceil(frames.length / 30))
        setThumbs(frames.filter((_, i) => i % step === 0))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [showable, primary])

  if (project.isLoading) {
    return (
      <div className="app">
        <p>Loading…</p>
      </div>
    )
  }
  if (project.isError || !detail) {
    return (
      <div className="app">
        <p style={{ color: '#ff8f8f' }}>
          {project.error instanceof Error ? project.error.message : 'Project not found'}
        </p>
        <button className="secondary" onClick={() => navigate('/')}>
          All projects
        </button>
      </div>
    )
  }

  return (
    <div className="app">
      <h1>
        {detail.project.name}
        <span>.</span> <span className="status">{primary ? primary.status : 'empty'}</span>
      </h1>

      {primary ? (
        <AssetPanel asset={primary} videoRef={videoRef} thumbs={thumbs} projectId={projectId} />
      ) : (
        <p className="muted">This project has no assets yet.</p>
      )}
      {detail.assets.length > 1 && (
        <p className="muted">
          + {detail.assets.length - 1} more asset(s) — multi-asset editing arrives with the timeline
          editor (Plan 3).
        </p>
      )}

      <p>
        <button
          className="secondary"
          style={{ marginTop: 16 }}
          onClick={() => {
            if (window.confirm('Delete this project and all its files?')) {
              deleteProject.mutate(projectId, { onSuccess: () => navigate('/') })
            }
          }}
        >
          Delete project
        </button>{' '}
        <button className="secondary" style={{ marginTop: 16 }} onClick={() => navigate('/')}>
          All projects
        </button>
      </p>
    </div>
  )
}

function AssetPanel(props: {
  asset: Asset
  projectId: string
  videoRef: RefObject<HTMLVideoElement>
  thumbs: FrameManifestItem[]
}) {
  const { asset, projectId, videoRef, thumbs } = props
  const saveSegments = useSaveSegments(projectId)
  const startRender = useStartRender(projectId)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Segment[]>([])
  const [saveError, setSaveError] = useState<string | null>(null)

  const duration = asset.meta?.duration_s ?? 0
  const segments = asset.segments ?? []
  const kept = segments.reduce((a, s) => a + (s.end_s - s.start_s), 0)
  const notes = asset.frame_notes ?? []
  const busy = !isTerminal(asset.status)
  const showPlayer = SHOWABLE.includes(asset.status)
  const chunkMatch = asset.progress?.match(/(\d+)\/(\d+)/)
  const progressFrac = chunkMatch ? parseInt(chunkMatch[1]) / parseInt(chunkMatch[2]) : null

  function startEdit() {
    setDraft(segments.map((s) => ({ ...s })))
    setSaveError(null)
    setEditing(true)
  }

  function updateDraft(i: number, field: 'start_s' | 'end_s', value: string) {
    const parsed = parseFloat(value)
    if (Number.isNaN(parsed)) return // partial input ("" / "-") — wait for a real number
    setDraft(draft.map((s, j) => (j === i ? { ...s, [field]: parsed } : s)))
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
    setDraft([
      ...draft,
      {
        start_s: round1(best.start),
        end_s: round1(best.start + len),
        reason: 'added manually',
        confidence: 1,
      },
    ])
  }

  async function save() {
    setSaveError(null)
    try {
      await saveSegments.mutateAsync({ assetId: asset.id, segments: draft })
      setEditing(false)
    } catch (exc) {
      setSaveError(exc instanceof Error ? exc.message : 'Save failed')
    }
  }

  return (
    <>
      {busy && (
        <p className="muted">
          {asset.progress || 'working…'}
          {progressFrac !== null && (
            <span className="progressbar">
              <span style={{ width: `${Math.round(progressFrac * 100)}%` }} />
            </span>
          )}
        </p>
      )}
      <p className="muted">
        {asset.filename}
        {duration > 0 && ` — ${duration.toFixed(0)}s original`}
        {kept > 0 && ` → ${kept.toFixed(0)}s kept (${Math.round((kept / duration) * 100)}%)`}
      </p>

      {asset.status === 'failed' && (
        <p style={{ color: '#ff8f8f' }}>Analysis failed: {asset.error}</p>
      )}

      {showPlayer && (
        <>
          <MediaPlayer
            src={`/api/v1/assets/${asset.id}/source`}
            segments={editing ? [] : segments}
            videoRef={videoRef}
            skipDisabled={editing}
          />

          <div
            className="timeline"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const frac = (e.clientX - rect.left) / rect.width
              const t = frac * duration
              const seg = segments.find((s) => t >= s.start_s && t <= s.end_s)
              if (videoRef.current)
                videoRef.current.currentTime = seg ? t : (segments[0]?.start_s ?? 0)
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
                  src={`/api/v1/assets/${asset.id}/frames/${f.file}`}
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
                      start{' '}
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max={duration}
                        value={s.start_s}
                        onChange={(e) => updateDraft(i, 'start_s', e.target.value)}
                      />
                    </label>
                    <label>
                      end{' '}
                      <input
                        type="number"
                        step="0.1"
                        min="0"
                        max={duration}
                        value={s.end_s}
                        onChange={(e) => updateDraft(i, 'end_s', e.target.value)}
                      />
                    </label>
                    <span className="muted">{Math.max(0, s.end_s - s.start_s).toFixed(1)}s</span>
                    <button
                      className="icon"
                      onClick={() => setDraft(draft.filter((_, j) => j !== i))}
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
              <p>
                <button onClick={save}>Save</button>{' '}
                <button className="secondary" onClick={addDraft} disabled={duration <= 0}>
                  + Add segment
                </button>{' '}
                <button className="secondary" onClick={() => setEditing(false)}>
                  Cancel
                </button>
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
                    <strong>
                      {fmtSeconds(s.start_s)} – {fmtSeconds(s.end_s)}
                    </strong>
                    <span className="muted">
                      {' '}
                      ({(s.end_s - s.start_s).toFixed(1)}s) — {s.reason}
                    </span>
                  </li>
                ))}
              </ul>
              <p>
                {asset.status === 'ready' && (
                  <button onClick={() => startRender.mutate(asset.id)}>Render final cut</button>
                )}{' '}
                {asset.status === 'rendering' && <button disabled>Rendering…</button>}{' '}
                <button className="secondary" onClick={startEdit}>
                  Edit segments
                </button>
              </p>
              {saveError && <p style={{ color: '#ff8f8f' }}>{saveError}</p>}
              {asset.has_render && (
                <p>
                  <a
                    href={`/api/v1/assets/${asset.id}/render`}
                    download="final_cut.mp4"
                    style={{ color: '#4f9cf9' }}
                  >
                    Download final_cut.mp4
                  </a>
                </p>
              )}

              {(asset.transcript ?? []).length > 0 && (
                <div className="transcript">
                  <div className="muted">Transcript — click a line to jump there</div>
                  <ul>
                    {(asset.transcript ?? []).map((line, i) => (
                      <li
                        key={i}
                        onClick={() =>
                          videoRef.current && (videoRef.current.currentTime = line.start_s)
                        }
                      >
                        <span className="ts">{fmtSeconds(line.start_s)}</span> {line.text}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </>
      )}
    </>
  )
}

/** Subscribe to SSE for the busy asset; live events patch the query cache. */
function useAssetEvents(projectId: string, detail: ProjectDetail | undefined) {
  const queryClient = useQueryClient()
  const busyAsset = detail?.assets.find((a) => !isTerminal(a.status))
  const targetId = busyAsset?.id
  const targetStatus = busyAsset?.status
  useEffect(() => {
    if (!targetId || typeof EventSource === 'undefined') return
    const source = new EventSource(`/api/v1/assets/${targetId}/events`)
    source.onmessage = (ev) => {
      let data: { status?: Asset['status']; progress?: string | null; error?: string | null }
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      queryClient.setQueryData<ProjectDetail>(queryKeys.project(projectId), (prev) =>
        prev
          ? {
              ...prev,
              assets: prev.assets.map((a) =>
                a.id === targetId
                  ? {
                      ...a,
                      status: data.status ?? a.status,
                      progress: data.progress,
                      error: data.error,
                    }
                  : a,
              ),
            }
          : prev,
      )
      if (data.status && isTerminal(data.status)) source.close()
    }
    source.onerror = () => source.close() // refetchInterval polling is the fallback
    return () => source.close()
  }, [projectId, targetId, targetStatus, queryClient])
}

function round1(n: number) {
  return Math.round(n * 10) / 10
}
