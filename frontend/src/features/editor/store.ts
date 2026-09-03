/** Editor store (Plan 3): timeline state + command/undo stack.
 *
 * Every mutation goes through `commit` — a command carries the previous
 * document (undo) and the new one (redo). Snapshots are small (hundreds
 * of clips), so structural snapshots beat inverse-patch machinery here.
 */

import { create } from 'zustand'
import * as ops from './operations'
import type { EditorTimeline, TimelineClip } from './types'

const HISTORY_LIMIT = 100

interface EditorState {
  timeline: EditorTimeline
  selection: string[]
  playhead: number
  pixelsPerSecond: number
  dirty: boolean
  past: EditorTimeline[]
  future: EditorTimeline[]

  load(timeline: EditorTimeline): void
  commit(next: EditorTimeline | null): void
  markSaved(): void
  undo(): void
  redo(): void

  select(ids: string[]): void
  setPlayhead(t: number): void
  setZoom(pps: number): void

  trim(id: string, edge: 'in' | 'out', time: number, ripple: boolean): void
  move(id: string, start: number): void
  append(source: TimelineClip['source'], name?: string): void
  addTransition(id: string, durationS?: number): void
  removeTransition(id: string): void
  split(id: string, time: number): void
  remove(ids: string[], ripple: boolean): void
}

export function snapCandidates(timeline: EditorTimeline, excludeIds: string[]): number[] {
  const points = [0, ops.duration(timeline)]
  for (const clip of ops.videoClips(timeline)) {
    if (!excludeIds.includes(clip.id)) {
      points.push(clip.record_start_s, ops.clipEnd(clip))
    }
  }
  return points
}

export const useEditorStore = create<EditorState>((set, get) => ({
  timeline: { schema_version: 1, name: 'main', frame_rate: null, tracks: [] },
  selection: [],
  playhead: 0,
  pixelsPerSecond: 20,
  dirty: false,
  past: [],
  future: [],

  load(timeline) {
    set({ timeline, selection: [], playhead: 0, dirty: false, past: [], future: [] })
  },

  commit(next) {
    if (next === null) return
    const { timeline, past } = get()
    const history = [...past, timeline].slice(-HISTORY_LIMIT)
    set({ timeline: next, past: history, future: [], dirty: true, selection: [] })
  },

  undo() {
    const { past, future, timeline } = get()
    if (!past.length) return
    const previous = past[past.length - 1]
    set({
      timeline: previous,
      past: past.slice(0, -1),
      future: [timeline, ...future].slice(0, HISTORY_LIMIT),
      dirty: true,
      selection: [],
    })
  },

  redo() {
    const { past, future, timeline } = get()
    if (!future.length) return
    set({
      timeline: future[0],
      past: [...past, timeline].slice(-HISTORY_LIMIT),
      future: future.slice(1),
      dirty: true,
      selection: [],
    })
  },

  markSaved() {
    set({ dirty: false })
  },

  select(ids) {
    set({ selection: ids })
  },

  setPlayhead(t) {
    set({ playhead: Math.max(0, t) })
  },

  setZoom(pps) {
    set({ pixelsPerSecond: Math.min(500, Math.max(1, pps)) })
  },

  append(source, name) {
    get().commit(ops.appendClip(get().timeline, source, name))
  },

  addTransition(id, durationS = 0.5) {
    get().commit(ops.addTransition(get().timeline, id, durationS))
  },

  removeTransition(id) {
    get().commit(ops.removeTransition(get().timeline, id))
  },

  trim(id, edge, time, ripple) {
    const { timeline } = get()
    const threshold = snapThreshold(get().pixelsPerSecond)
    const snapped = ops.snap(time, snapCandidates(timeline, [id]), threshold)
    get().commit(ops.trimClip(timeline, id, edge, snapped, ripple))
  },

  move(id, start) {
    const { timeline } = get()
    const threshold = snapThreshold(get().pixelsPerSecond)
    const snapped = ops.snap(start, snapCandidates(timeline, [id]), threshold)
    get().commit(ops.moveClip(timeline, id, snapped))
  },

  split(id, time) {
    get().commit(ops.splitClip(get().timeline, id, time))
  },

  remove(ids, ripple) {
    get().commit(ops.deleteClips(get().timeline, ids, ripple))
  },
}))

/** Snap radius follows zoom: ~half a screen pixel, clamped to a sane band. */
export function snapThreshold(pps: number): number {
  return Math.min(0.5, Math.max(0.02, 8 / pps))
}
