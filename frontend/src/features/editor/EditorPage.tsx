import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import ProgramMonitor, { type MonitorHandle } from './ProgramMonitor'
import Timeline from './Timeline'
import * as ops from './operations'
import { useEditorStore } from './store'
import { usePeaks, useProject, useProjectRedraft } from '../projects/queries'
import { jsonFetch } from '../../lib/api'
import { useQuery } from '@tanstack/react-query'
import { fmtSeconds } from '../../lib/status'

const AUTOSAVE_DEBOUNCE_MS = 1200

/** The editor: program monitor + timeline + autosave + exports. */
export default function EditorPage() {
  const { projectId = '' } = useParams()
  const project = useProject(projectId)
  const detail = project.data
  const timeline = detail?.timeline
  const primary = detail?.assets[0]

  const storeTimeline = useEditorStore((s) => s.timeline)
  const dirty = useEditorStore((s) => s.dirty)
  const load = useEditorStore((s) => s.load)
  const markSaved = useEditorStore((s) => s.markSaved)
  const undo = useEditorStore((s) => s.undo)
  const redo = useEditorStore((s) => s.redo)
  const select = useEditorStore((s) => s.select)
  const split = useEditorStore((s) => s.split)
  const remove = useEditorStore((s) => s.remove)
  const setPlayhead = useEditorStore((s) => s.setPlayhead)
  const setZoom = useEditorStore((s) => s.setZoom)
  const playhead = useEditorStore((s) => s.playhead)
  const selection = useEditorStore((s) => s.selection)
  const pps = useEditorStore((s) => s.pixelsPerSecond)
  const append = useEditorStore((s) => s.append)

  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const monitor = useRef<MonitorHandle | null>(null)
  const monitorRef = useCallback((handle: MonitorHandle) => (monitor.current = handle), [])

  const fps = timeline?.document.frame_rate ?? primary?.meta?.fps ?? 30
  const loaded = useRef(false)
  const loadedVersion = useRef<number | null>(null)
  useEffect(() => {
    if (!timeline) return
    // First load, or a server-side version change (e.g. a project redraft
    // landed): replace the editor document. Redrafts are explicit user
    // actions, so local unsaved edits yield to the new draft.
    if (!loaded.current || loadedVersion.current !== timeline.version) {
      load(timeline.document as never)
      loaded.current = true
      loadedVersion.current = timeline.version
    }
  }, [timeline, load])

  // Autosave: debounce pushes of the edited document to the versioned API.
  const saveTimer = useRef<number | undefined>(undefined)
  useEffect(() => {
    if (!dirty || !projectId) return
    setSaveState('saving')
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(async () => {
      try {
        await jsonFetch(`/api/v1/projects/${projectId}/timeline`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(useEditorStore.getState().timeline),
        })
        markSaved()
        setSaveState('saved')
      } catch {
        setSaveState('error') // local edits are kept; retry on next change
      }
    }, AUTOSAVE_DEBOUNCE_MS)
    return () => window.clearTimeout(saveTimer.current)
  }, [storeTimeline, dirty, projectId, markSaved])

  // Keyboard map: space/step in the monitor; edit commands in the store.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return
      const state = useEditorStore.getState()
      const selected = state.selection[0]
      if (e.key === ' ') {
        e.preventDefault()
        monitor.current?.playPause()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        monitor.current?.stepFrames(e.shiftKey ? -30 : -1)
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        monitor.current?.stepFrames(e.shiftKey ? 30 : 1)
      } else if (e.key.toLowerCase() === 's' && selected) {
        split(selected, state.playhead)
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && state.selection.length) {
        remove(state.selection, e.shiftKey)
      } else if (e.key.toLowerCase() === 'z' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        if (e.shiftKey) redo()
        else undo()
      } else if (e.key.toLowerCase() === 'y' && (e.ctrlKey || e.metaKey)) {
        redo()
      } else if (e.key === 'Home') {
        setPlayhead(0)
      } else if (e.key === 'End') {
        setPlayhead(ops.duration(state.timeline))
      } else if (e.key === 'Escape') {
        select([])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [split, remove, undo, redo, setPlayhead, select])

  const peaks = usePeaks(primary?.id)

  if (project.isLoading)
    return (
      <div className="app">
        <p>Loading…</p>
      </div>
    )
  if (project.isError || !detail || !timeline) {
    return (
      <div className="app">
        <p style={{ color: '#ff8f8f' }}>
          {project.error instanceof Error ? project.error.message : 'Nothing to edit yet'}
        </p>
        <Link to={`/p/${projectId}`} className="secondary">
          Back to project
        </Link>
      </div>
    )
  }

  const selected = selection[0]
  const total = ops.duration(storeTimeline)

  return (
    <div className="app editor-page">
      <h1>
        {detail.project.name}
        <span>.</span> <span className="status">editor</span>
      </h1>
      <p className="muted">
        <Link to={`/p/${projectId}`}>← Project</Link> · space play · ←/→ step · S split · Del remove
        (Shift = ripple) · Ctrl+Z undo · ctrl+wheel zoom
        {' · '}
        <span className={saveState === 'error' ? 'save-error' : undefined}>
          {saveState === 'saving'
            ? 'saving…'
            : saveState === 'saved'
              ? 'saved'
              : saveState === 'error'
                ? 'save failed — retrying on next edit'
                : ''}
        </span>
      </p>

      <ProgramMonitor timeline={storeTimeline} fps={fps} onReady={monitorRef} />
      <p className="muted monitor-readout">
        {fmtSeconds(playhead)} / {fmtSeconds(total)}
        {' · '}
        <button className="secondary" onClick={() => monitor.current?.playPause()}>
          play/pause
        </button>{' '}
        <button className="secondary" onClick={() => monitor.current?.stepFrames(-1)}>
          ◀|
        </button>{' '}
        <button className="secondary" onClick={() => monitor.current?.stepFrames(1)}>
          |▶
        </button>
        {' · '}
        <button className="secondary" onClick={() => undo()}>
          undo
        </button>{' '}
        <button className="secondary" onClick={() => redo()}>
          redo
        </button>{' '}
        <button
          className="secondary"
          disabled={!selected}
          onClick={() => selected && split(selected, playhead)}
        >
          split at playhead
        </button>{' '}
        <button
          className="secondary"
          disabled={!selection.length}
          onClick={() => remove(selection, false)}
        >
          remove
        </button>{' '}
        <button className="secondary" onClick={() => setZoom(pps * 1.3)}>
          +
        </button>{' '}
        <button className="secondary" onClick={() => setZoom(pps / 1.3)}>
          −
        </button>
      </p>

      <div className="editor-grid">
        <div className="asset-browser">
          <div className="muted">Assets in this project</div>
          <ul className="asset-list">
            {(detail.assets ?? []).map((a) => (
              <li key={a.id} className={a.status !== 'ready' ? 'unavailable' : undefined}>
                <div>
                  <strong>{a.filename}</strong>
                  <div className="muted">
                    {a.status !== 'ready' ? a.status : `${(a.meta?.duration_s ?? 0).toFixed(0)}s`}
                    {a.style_preset !== 'default' && ` · ${a.style_preset}`}
                  </div>
                </div>
                <button
                  className="secondary"
                  disabled={a.status !== 'ready'}
                  onClick={() =>
                    append({ asset_id: a.id, in_s: 0, out_s: a.meta?.duration_s ?? 0 }, a.filename)
                  }
                >
                  + timeline
                </button>
              </li>
            ))}
          </ul>
          <ProjectRedraftControl projectId={projectId} />
        </div>
        <Timeline timeline={storeTimeline} peaks={peaks.data ?? null} />
      </div>

      <p className="muted">
        Exports: <a href={`/api/v1/projects/${projectId}/export/fcpxml`}>FCPXML</a>
        {' · '}
        <a href={`/api/v1/projects/${projectId}/export/edl`}>EDL</a>
        {' · '}
        <a href={`/api/v1/projects/${projectId}/export/srt`}>SRT</a>
        {' · '}
        <a href={`/api/v1/assets/${primary?.id ?? ''}/render`}>download render</a>
      </p>
    </div>
  )
}

/** Project-wide style + re-draft control (restyles every analyzed asset). */
function ProjectRedraftControl({ projectId }: { projectId: string }) {
  const presets = useQuery({
    queryKey: ['styles'],
    queryFn: () =>
      jsonFetch<Array<{ preset_id: string; name: string; pacing: string }>>('/api/v1/styles'),
    staleTime: Infinity,
  })
  const redraft = useProjectRedraft(projectId)
  const [presetId, setPresetId] = useState('default')
  const [brief, setBrief] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function go() {
    setError(null)
    try {
      await redraft.mutateAsync({ preset_id: presetId, user_brief: brief })
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Re-draft failed')
    }
  }

  return (
    <div className="project-redraft">
      <div className="muted">Re-draft everything</div>
      <div className="style-row">
        <select
          value={presetId}
          onChange={(e) => setPresetId(e.target.value)}
          disabled={redraft.isPending}
        >
          {(presets.data ?? []).map((p) => (
            <option key={p.preset_id} value={p.preset_id}>
              {p.name}
            </option>
          ))}
        </select>
        <button onClick={go} disabled={redraft.isPending}>
          {redraft.isPending ? 'Re-drafting…' : 'Re-draft all'}
        </button>
      </div>
      <textarea
        rows={2}
        value={brief}
        placeholder="Direction for the whole project (optional)"
        onChange={(e) => setBrief(e.target.value)}
        disabled={redraft.isPending}
      />
      {error && <p style={{ color: '#ff8f8f' }}>{error}</p>}
    </div>
  )
}
