import { useEffect, useMemo, useRef } from 'react'
import * as ops from './operations'
import { snapCandidates, useEditorStore } from './store'
import type { EditorTimeline, TimelineClip } from './types'

const TRACK_H = 44
const WAVE_H = 30
const RULER_H = 24

interface TimelineProps {
  timeline: EditorTimeline
  peaks: { bucket_seconds: number; buckets: number[][] } | null
}

/** The timeline: ruler, clip lane, per-clip waveforms, playhead.
 * Interactions: scrub (ruler), drag body to move, drag edges to trim
 * (Shift = ripple), wheel zoom, selection. */
export default function Timeline({ timeline, peaks }: TimelineProps) {
  const clips = ops.videoClips(timeline)
  const total = Math.max(ops.duration(timeline), 10)
  const pps = useEditorStore((s) => s.pixelsPerSecond)
  const setZoom = useEditorStore((s) => s.setZoom)
  const playhead = useEditorStore((s) => s.playhead)
  const setPlayhead = useEditorStore((s) => s.setPlayhead)
  const selection = useEditorStore((s) => s.selection)
  const select = useEditorStore((s) => s.select)

  const scrollRef = useRef<HTMLDivElement | null>(null)
  const drag = useRef<null | {
    kind: 'move' | 'trim-in' | 'trim-out'
    clipId: string
    startX: number
    origin: number
    ripple: boolean
  }>(null)

  const width = total * pps

  // Ctrl+wheel zooms around the cursor; plain wheel scrolls natively.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      const atCursor = (el.scrollLeft + e.clientX - rect.left) / pps
      setZoom(pps * (e.deltaY < 0 ? 1.2 : 1 / 1.2))
      requestAnimationFrame(() => {
        el.scrollLeft = Math.max(
          0,
          atCursor * useEditorStore.getState().pixelsPerSecond - (e.clientX - rect.left),
        )
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [pps, setZoom])

  function scrub(e: React.PointerEvent) {
    const rect = e.currentTarget.getBoundingClientRect()
    setPlayhead((e.clientX - rect.left) / pps)
  }

  function onClipPointerDown(
    e: React.PointerEvent,
    clip: TimelineClip,
    kind: 'move' | 'trim-in' | 'trim-out',
  ) {
    e.stopPropagation()
    const ripple = e.shiftKey
    select([clip.id])
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    const origin =
      kind === 'move'
        ? clip.record_start_s
        : kind === 'trim-in'
          ? clip.source.in_s
          : ops.clipEnd(clip)
    drag.current = { kind, clipId: clip.id, startX: e.clientX, origin, ripple }
  }

  function onPointerMove(e: React.PointerEvent) {
    const state = drag.current
    if (!state) return
    const dt = (e.clientX - state.startX) / pps
    const threshold = 8 / pps
    const candidates = snapCandidates(timeline, [state.clipId])
    if (state.kind === 'move') {
      const next = ops.moveClip(
        timeline,
        state.clipId,
        ops.snap(state.origin + dt, candidates, threshold),
      )
      if (next) {
        // Live-preview: apply without history; history is committed on drop.
        useEditorStore.setState({ timeline: next, dirty: true })
      }
      return
    }
    const target = ops.snap(
      state.origin + dt,
      candidates.filter((c) => c !== state.origin),
      threshold,
    )
    const edited =
      state.kind === 'trim-in'
        ? ops.trimClip(timeline, state.clipId, 'in', target, state.ripple)
        : ops.trimClip(timeline, state.clipId, 'out', target, state.ripple)
    if (edited) useEditorStore.setState({ timeline: edited, dirty: true })
  }

  function onPointerUp() {
    const state = drag.current
    drag.current = null
    if (!state) return
    // A drag that changed the document counts as one history command:
    // push the PRE-drag document (kept in a ref via first move) — simplest
    // correct approach: re-apply the same op on the pre-drag snapshot.
    const pre = preDrag.current
    preDrag.current = null
    if (!pre) return
    if (JSON.stringify(pre) !== JSON.stringify(useEditorStore.getState().timeline)) {
      useEditorStore.setState({
        past: [...useEditorStore.getState().past, pre].slice(-100),
        future: [],
      })
    }
  }
  const preDrag = useRef<EditorTimeline | null>(null)

  // Capture the pre-drag document when a drag starts.
  function onClipPointerDownCapture(
    e: React.PointerEvent,
    clip: TimelineClip,
    kind: 'move' | 'trim-in' | 'trim-out',
  ) {
    preDrag.current = timeline
    onClipPointerDown(e, clip, kind)
  }

  const ticks = useMemo(() => {
    // Choose a tick step that keeps labels ~80px apart.
    const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
    const step = steps.find((s) => s * pps >= 80) ?? 900
    const out: number[] = []
    for (let t = 0; t <= total; t += step) out.push(t)
    return { step, out }
  }, [total, pps])

  return (
    <div className="timeline-editor">
      <div className="timeline-scroll" ref={scrollRef}>
        <div className="timeline-inner" style={{ width: width + 40 }}>
          <div className="tl-ruler" style={{ height: RULER_H }} onPointerDown={scrub}>
            {ticks.out.map((t) => (
              <div key={t} className="tl-tick" style={{ left: t * pps }}>
                <span>{fmtTick(t, ticks.step)}</span>
              </div>
            ))}
          </div>

          <div
            className="tl-track"
            style={{ height: TRACK_H + WAVE_H }}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          >
            {clips.map((clip) => {
              const len = clip.source.out_s - clip.source.in_s
              const selected = selection.includes(clip.id)
              return (
                <div
                  key={clip.id}
                  className={`tl-clip${selected ? ' selected' : ''}`}
                  style={{ left: clip.record_start_s * pps, width: Math.max(6, len * pps) }}
                  onPointerDown={(e) => onClipPointerDownCapture(e, clip, 'move')}
                  title={clip.reason || clip.name}
                >
                  <canvas
                    className="tl-wave"
                    width={Math.max(6, Math.round(len * pps))}
                    height={WAVE_H}
                    ref={(canvas) => drawWave(canvas, clip, peaks, pps)}
                  />
                  <span className="tl-clip-name">{clip.name || clip.id}</span>
                  <div
                    className="tl-edge left"
                    onPointerDown={(e) => onClipPointerDownCapture(e, clip, 'trim-in')}
                  />
                  <div
                    className="tl-edge right"
                    onPointerDown={(e) => onClipPointerDownCapture(e, clip, 'trim-out')}
                  />
                </div>
              )
            })}
            <div className="tl-playhead" style={{ left: playhead * pps }} />
          </div>
        </div>
      </div>
    </div>
  )
}

function drawWave(
  canvas: HTMLCanvasElement | null,
  clip: TimelineClip,
  peaksData: { bucket_seconds: number; buckets: number[][] } | null,
  pps: number,
) {
  if (!canvas || !peaksData) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  const { bucket_seconds, buckets } = peaksData
  const first = Math.floor(clip.source.in_s / bucket_seconds)
  const last = Math.min(buckets.length, Math.ceil(clip.source.out_s / bucket_seconds))
  const span = Math.max(1, last - first)
  const mid = canvas.height / 2
  ctx.fillStyle = 'rgba(255,255,255,0.55)'
  for (let x = 0; x < canvas.width; x++) {
    const bucket = first + Math.floor((x / canvas.width) * span)
    const pair = buckets[bucket]
    if (!pair) continue
    const [lo, hi] = pair
    const yLo = mid - hi * (mid - 2)
    const yHi = mid - lo * (mid - 2)
    ctx.fillRect(x, yLo, 1, Math.max(1, yHi - yLo))
  }
  void pps
}

function fmtTick(t: number, step: number): string {
  if (step >= 60) {
    const m = Math.floor(t / 60)
    return `${m}:${String(Math.round(t % 60)).padStart(2, '0')}`
  }
  return `${t}s`
}
