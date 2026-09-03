/** Editor store + operations, tested headlessly (no React, no DOM).
 *
 * Model invariant: a clip's record span ALWAYS equals its source span
 * (no speed changes) — so trim-out can only shorten, never stretch.
 * Fixture convention: clip(id, sourceIn, sourceOut, recordStart). */

import { beforeEach, describe, expect, it } from 'vitest'
import * as ops from './operations'
import { snapThreshold, useEditorStore } from './store'
import type { EditorTimeline, TimelineClip, TimelineTrack } from './types'

function clip(id: string, sourceIn: number, sourceOut: number, recordStart: number): TimelineClip {
  return {
    id,
    name: id,
    source: { asset_id: 'a1', in_s: sourceIn, out_s: sourceOut },
    record_start_s: recordStart,
    reason: '',
    confidence: 1,
    enabled: true,
  }
}

function timeline(clips: TimelineClip[]): EditorTimeline {
  const track: TimelineTrack = { id: 't1', kind: 'video', name: 'V1', clips }
  return { schema_version: 1, name: 'main', frame_rate: 30, tracks: [track] }
}

function ranges(t: EditorTimeline): Array<[number, number]> {
  return ops.videoClips(t).map((c) => [c.record_start_s, ops.clipEnd(c)] as [number, number])
}

// a: record 0–20 (source 10–30), b: record 20–40 (source 40–60).
const FRESH = () => timeline([clip('a', 10, 30, 0), clip('b', 40, 60, 20)])

describe('operations', () => {
  it('trim-in slides record + source together, clamped to the previous clip', () => {
    // b has source slack (30–60) so in-trims have room to slide.
    const t = timeline([clip('a', 10, 30, 0), clip('b', 30, 60, 20)])
    // Trim b's in to record 25: source-in slides 30 → 35.
    const out = ops.trimClip(t, 'b', 'in', 25, false)!
    expect(ranges(out)[1][0]).toBeCloseTo(25)
    expect(ops.videoClips(out)[1].source.in_s).toBeCloseTo(35)
    // From there, trimming to record 5 clamps at a's end (record 20).
    const clamped = ops.trimClip(out, 'b', 'in', 5, false)!
    expect(ranges(clamped)[1][0]).toBeCloseTo(20)
    expect(ops.videoClips(clamped)[1].source.in_s).toBeCloseTo(30)
    // Already at the clamp point → no-op → null (no history pollution).
    expect(ops.trimClip(clamped, 'b', 'in', 5, false)).toBeNull()
  })

  it('trim-out can only shorten (record span == source span)', () => {
    const t = FRESH()
    // Stretching a to 30s would need 30s of source; it has 20.
    expect(ops.trimClip(t, 'a', 'out', 30, false)).toBeNull()
    // Shorten to record 10: source-out slides 30 → 20.
    const ok = ops.trimClip(t, 'a', 'out', 10, false)!
    expect(ranges(ok)[0][1]).toBeCloseTo(10)
    expect(ops.videoClips(ok)[0].source.out_s).toBeCloseTo(20)
  })

  it('ripple trim-out shortens and pulls following clips', () => {
    const t = FRESH()
    const out = ops.trimClip(t, 'a', 'out', 10, true)!
    expect(ranges(out)[0][1]).toBeCloseTo(10)
    expect(ranges(out)[1][0]).toBeCloseTo(10) // b pulled -10
    // Without ripple the gap stays and b doesn't move.
    const gap = ops.trimClip(t, 'a', 'out', 10, false)!
    expect(ranges(gap)[1][0]).toBeCloseTo(20)
  })

  it('move slides a clip within a legal gap and refuses overlaps', () => {
    const t = FRESH()
    // Slide b right: gap after a is [20, ∞), so record 30 fits (a 10s gap
    // opens at 20). Moving into occupied space is rejected, and so is
    // staying put.
    const moved = ops.moveClip(t, 'b', 30)!
    expect(ranges(moved)).toEqual([
      [0, 20],
      [30, 50],
    ])
    expect(ops.moveClip(t, 'b', 10)).toBeNull() // would overlap a
    expect(ops.moveClip(t, 'b', 20)).toBeNull() // already there
  })

  it('split divides clip and source at the same offsets', () => {
    const t = timeline([clip('a', 10, 30, 0)])
    const out = ops.splitClip(t, 'a', 15)!
    const clips = ops.videoClips(out)
    expect(clips).toHaveLength(2)
    expect(ranges(out)).toEqual([
      [0, 15],
      [15, 20],
    ])
    expect(clips[0].source.out_s).toBeCloseTo(25)
    expect(clips[1].source.in_s).toBeCloseTo(25)
    // Split points closer than MIN_CLIP_S to an edge are rejected.
    expect(ops.splitClip(t, 'a', 0.05)).toBeNull()
    expect(ops.splitClip(t, 'a', 19.95)).toBeNull()
  })

  it('delete and ripple-delete behave as named', () => {
    // a: record 0–20, b: record 20–40, c: record 40–60.
    const t = timeline([clip('a', 10, 30, 0), clip('b', 40, 60, 20), clip('c', 70, 90, 40)])
    const removed = ops.deleteClips(t, ['b'], false)!
    expect(ranges(removed)).toEqual([
      [0, 20],
      [40, 60],
    ]) // gap stays
    const rippled = ops.deleteClips(t, ['b'], true)!
    expect(ranges(rippled)).toEqual([
      [0, 20],
      [20, 40],
    ]) // c pulled back by b's 20s span
  })

  it('snap picks the nearest candidate within threshold', () => {
    expect(ops.snap(9.96, [10, 25], 0.1)).toBe(10)
    expect(ops.snap(9.9, [10, 25], 0.05)).toBe(9.9) // outside threshold → unchanged
  })
})

describe('store commands + undo/redo', () => {
  beforeEach(() => {
    useEditorStore.getState().load(FRESH())
  })

  it('commit applies and history navigates both ways', () => {
    const store = useEditorStore
    store.getState().split('a', 10)
    expect(ops.videoClips(store.getState().timeline)).toHaveLength(3) // a→2 + b
    expect(store.getState().dirty).toBe(true)

    store.getState().undo()
    expect(ops.videoClips(store.getState().timeline)).toHaveLength(2)
    store.getState().redo()
    expect(ops.videoClips(store.getState().timeline)).toHaveLength(3)
  })

  it('no-op commands leave history untouched', () => {
    const store = useEditorStore
    const before = store.getState().timeline
    store.getState().split('a', 19.95) // too close to the edge
    store.getState().trim('b', 'in', 20, false) // no change
    expect(store.getState().timeline).toBe(before)
    expect(store.getState().past).toHaveLength(0)
  })

  it('trim through the store snaps to a neighboring clip edge', () => {
    const store = useEditorStore
    // 20.06 is within the snap threshold of b's record start (20) at pps 20.
    store.getState().trim('b', 'in', 20.06, false)
    expect(ranges(store.getState().timeline)[1][0]).toBeCloseTo(20)
  })

  it('selection and playhead are plain state', () => {
    const store = useEditorStore
    store.getState().select(['a'])
    expect(store.getState().selection).toEqual(['a'])
    store.getState().setPlayhead(12.5)
    expect(store.getState().playhead).toBe(12.5)
    expect(snapThreshold(8)).toBe(0.5) // clamped high bound
    expect(snapThreshold(400)).toBeCloseTo(0.02) // clamped low bound
  })
})

describe('appendClip (asset browser)', () => {
  it('appends a full-source clip at the timeline end', () => {
    const t = FRESH()
    const out = ops.appendClip(t, { asset_id: 'a2', in_s: 0, out_s: 45 }, 'day2.mp4')!
    const clips = ops.videoClips(out)
    expect(clips).toHaveLength(3)
    expect(ranges(out)[2]).toEqual([40, 85])
    expect(clips[2].source.asset_id).toBe('a2')
    expect(clips[2].reason).toBe('added from browser')
    expect(new Set(clips.map((c) => c.id)).size).toBe(3)
  })

  it('appends onto an empty timeline', () => {
    const out = ops.appendClip(timeline([]), { asset_id: 'a2', in_s: 0, out_s: 12 }, 'x.mp4')!
    expect(ranges(out)).toEqual([[0, 12]])
  })
})
