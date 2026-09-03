/** Timeline editing operations (Plan 3): pure functions + invariants.
 *
 * The timeline here is the single video track of the project's timeline
 * document (clips sorted by record_start, gaps allowed, no overlaps).
 * Every operation returns a NEW document or null when the edit is a
 * no-op/illegal — the store layers undo/redo and snapping on top, and
 * the server re-validates on save.
 */

import type { EditorTimeline, TimelineClip, TimelineTrack } from './types'

export const MIN_CLIP_S = 0.1 // one clip never shrinks below this
export const EPS = 1e-6

export function sortClips(clips: TimelineClip[]): TimelineClip[] {
  return [...clips].sort((a, b) => a.record_start_s - b.record_start_s)
}

/** Replace the video track's clips, keeping invariants. */
export function withClips(timeline: EditorTimeline, clips: TimelineClip[]): EditorTimeline {
  const tracks = timeline.tracks.map((track, i) =>
    track.kind === 'video' && i === videoTrackIndex(timeline)
      ? { ...track, clips: sortClips(clips) }
      : track,
  )
  return { ...timeline, tracks }
}

export function videoTrackIndex(timeline: EditorTimeline): number {
  const idx = timeline.tracks.findIndex((t) => t.kind === 'video')
  if (idx >= 0) return idx
  throw new Error('timeline has no video track')
}

export function videoClips(timeline: EditorTimeline): TimelineClip[] {
  return sortClips(timeline.tracks[videoTrackIndex(timeline)].clips).filter((c) => c.enabled)
}

export function clipEnd(clip: TimelineClip): number {
  return clip.record_start_s + (clip.source.out_s - clip.source.in_s)
}

export function duration(timeline: EditorTimeline): number {
  return videoClips(timeline).reduce((max, c) => Math.max(max, clipEnd(c)), 0)
}

function neighborsAt(
  clips: TimelineClip[],
  id: string,
): { prev?: TimelineClip; next?: TimelineClip } {
  const idx = clips.findIndex((c) => c.id === id)
  if (idx < 0) return {}
  return { prev: clips[idx - 1], next: clips[idx + 1] }
}

/** Trim one edge of a clip. `ripple` pulls (or pushes) subsequent clips to
 * close (or open) the gap created by the trim. */
export function trimClip(
  timeline: EditorTimeline,
  id: string,
  edge: 'in' | 'out',
  targetTime: number,
  ripple = false,
): EditorTimeline | null {
  const clips = videoClips(timeline)
  const idx = clips.findIndex((c) => c.id === id)
  if (idx < 0) return null
  const clip = clips[idx]
  const { prev, next } = neighborsAt(clips, id)
  const sourceLength = clip.source.out_s - clip.source.in_s
  const nextClips = clips.map((c) => ({ ...c }))

  if (edge === 'in') {
    const earliest = prev ? clipEnd(prev) : 0
    const latest = clipEnd(clip) - MIN_CLIP_S
    // Source-in moves with the record head. Dragging the head LEFT of the
    // current position extends the clip into already-trimmed source (the
    // source window slides back toward 0); dragging right shrinks it.
    // (Trim-out cannot extend: the asset's total length is unknown here.)
    const delta = clamp(targetTime, earliest, latest) - clip.record_start_s
    const newStart = clamp(clip.source.in_s + delta, 0, clip.source.out_s - MIN_CLIP_S)
    const updated = {
      ...clip,
      record_start_s: clip.record_start_s + (newStart - clip.source.in_s),
      source: { ...clip.source, in_s: newStart },
    }
    nextClips[idx] = updated
    if (ripple && updated.record_start_s !== clip.record_start_s && next) {
      const shift = updated.record_start_s - clip.record_start_s
      for (let i = idx + 1; i < nextClips.length; i++) nextClips[i].record_start_s += shift
    }
  } else {
    const earliest = clip.record_start_s + MIN_CLIP_S
    const latest = next && !ripple ? next.record_start_s : Number.POSITIVE_INFINITY
    const newEnd = clamp(targetTime, earliest, latest)
    const newLength = newEnd - clip.record_start_s
    if (newLength > sourceLength + EPS) return null // would need more source than exists
    nextClips[idx] = { ...clip, source: { ...clip.source, out_s: clip.source.in_s + newLength } }
    if (ripple && next) {
      const shift = newLength - sourceLength
      for (let i = idx + 1; i < nextClips.length; i++) nextClips[i].record_start_s += shift
    }
  }
  if (JSON.stringify(nextClips) === JSON.stringify(clips)) return null // no-op
  return withClips(timeline, nextClips)
}

/** Slide a clip along the track into a legal gap (source content unchanged). */
export function moveClip(
  timeline: EditorTimeline,
  id: string,
  targetStart: number,
): EditorTimeline | null {
  const clips = videoClips(timeline)
  const clip = clips.find((c) => c.id === id)
  if (!clip) return null
  const others = clips.filter((c) => c.id !== id)
  const length = clipEnd(clip) - clip.record_start_s
  const start = Math.max(0, targetStart)

  // Find the gap containing/nearest start that fits the clip.
  const gaps: Array<[number, number]> = []
  let cursor = 0
  for (const other of others) {
    if (other.record_start_s - cursor >= length - EPS)
      gaps.push([cursor, other.record_start_s - length])
    cursor = Math.max(cursor, clipEnd(other))
  }
  gaps.push([cursor, Number.POSITIVE_INFINITY])

  const best = gaps
    .filter(([lo, hi]) => start >= lo - EPS && start <= hi + EPS)
    .sort(([loA], [loB]) => Math.abs(loA - start) - Math.abs(loB - start))[0]
  if (!best) return null

  const snapped = clamp(start, best[0], best[1])
  if (Math.abs(snapped - clip.record_start_s) < EPS) return null
  return withClips(timeline, [...others, { ...clip, record_start_s: snapped }])
}

/** Split the clip under the playhead into two at `time`. */
export function splitClip(
  timeline: EditorTimeline,
  id: string,
  time: number,
): EditorTimeline | null {
  const clips = videoClips(timeline)
  const idx = clips.findIndex((c) => c.id === id)
  if (idx < 0) return null
  const clip = clips[idx]
  const offset = time - clip.record_start_s
  const sourceLength = clip.source.out_s - clip.source.in_s
  if (offset <= MIN_CLIP_S || sourceLength - offset <= MIN_CLIP_S) return null

  const left: TimelineClip = {
    ...clip,
    source: { ...clip.source, out_s: clip.source.in_s + offset },
  }
  const right: TimelineClip = {
    ...clip,
    id: `${clip.id}-b${Math.random().toString(36).slice(2, 6)}`,
    record_start_s: clip.record_start_s + offset,
    source: { ...clip.source, in_s: clip.source.in_s + offset },
    reason: clip.reason ? `${clip.reason} (cont.)` : clip.reason,
  }
  return withClips(timeline, [...clips.slice(0, idx), left, right, ...clips.slice(idx + 1)])
}

/** Append a clip spanning a whole source range at the timeline end. */
export function appendClip(
  timeline: EditorTimeline,
  source: TimelineClip['source'],
  name = '',
): EditorTimeline {
  const end = duration(timeline)
  const clip: TimelineClip = {
    id: `c${Math.random().toString(36).slice(2, 10)}`,
    name,
    source: { ...source },
    record_start_s: end,
    reason: 'added from browser',
    confidence: 1,
    enabled: true,
  }
  return withClips(timeline, [...videoClips(timeline), clip])
}

/** Add (or replace) a crossfade at the clip's outgoing junction: the next
 * enabled clip shifts left to overlap by the transition duration. Returns
 * null when there is no following clip or the duration doesn't fit. */
export function addTransition(
  timeline: EditorTimeline,
  id: string,
  durationS = 0.5,
): EditorTimeline | null {
  const clips = videoClips(timeline)
  const idx = clips.findIndex((c) => c.id === id)
  if (idx < 0 || idx === clips.length - 1) return null
  const a = clips[idx]
  const b = clips[idx + 1]
  const spanA = clipEnd(a) - a.record_start_s
  const spanB = b.source.out_s - b.source.in_s
  const d = Math.min(durationS, spanA - 0.1, spanB - 0.1)
  if (d <= 0) return null
  const nextClips = clips.map((c) => ({ ...c }))
  nextClips[idx] = {
    ...a,
    transition_out: { type: 'crossfade', duration_s: round3(d) },
  }
  nextClips[idx + 1] = { ...b, record_start_s: clipEnd(a) - d }
  return withClips(timeline, nextClips)
}

/** Remove the clip's outgoing crossfade: the next clip shifts right back
 * to a hard cut. Returns null when there is no transition. */
export function removeTransition(timeline: EditorTimeline, id: string): EditorTimeline | null {
  const clips = videoClips(timeline)
  const idx = clips.findIndex((c) => c.id === id)
  if (idx < 0 || !clips[idx].transition_out || idx === clips.length - 1) return null
  const a = clips[idx]
  const d = a.transition_out!.duration_s
  const nextClips = clips.map((c) => ({ ...c }))
  nextClips[idx] = { ...a, transition_out: null }
  nextClips[idx + 1] = {
    ...nextClips[idx + 1],
    record_start_s: nextClips[idx + 1].record_start_s + d,
  }
  return withClips(timeline, nextClips)
}

/** Invariant oracle mirroring the backend validate(): no junction may
 * overlap without a matching transition, and transitions must fit. */
export function violatesCrossfadeRules(timeline: EditorTimeline): boolean {
  const clips = videoClips(timeline)
  for (let i = 0; i < clips.length - 1; i++) {
    const a = clips[i]
    const b = clips[i + 1]
    const overlap = clipEnd(a) - b.record_start_s
    const transition = a.transition_out
    if (overlap <= EPS) continue
    if (!transition) return true
    const spanA = a.source.out_s - a.source.in_s
    const spanB = b.source.out_s - b.source.in_s
    if (Math.abs(overlap - transition.duration_s) > 1e-6) return true
    if (transition.duration_s >= Math.min(spanA, spanB) - 1e-6) return true
  }
  return clips[clips.length - 1]?.transition_out != null
}

function round3(n: number): number {
  return Math.round(n * 1000) / 1000
}

/** Delete clips; `ripple` closes the gap left behind. */
export function deleteClips(
  timeline: EditorTimeline,
  ids: string[],
  ripple = false,
): EditorTimeline | null {
  const clips = videoClips(timeline)
  const keep = clips.filter((c) => !ids.includes(c.id))
  if (keep.length === clips.length) return null
  if (!ripple) return withClips(timeline, keep)

  // Standard ripple: every kept clip shifts left by the deleted material
  // that preceded it (gaps between kept clips are preserved).
  const deletedSpans = clips
    .filter((c) => ids.includes(c.id))
    .map((c) => ({ start: clipEnd(c) - (c.source.out_s - c.source.in_s), end: clipEnd(c) }))
  const result: TimelineClip[] = keep.map((clip) => {
    const shift = deletedSpans
      .filter((span) => span.end <= clip.record_start_s + EPS)
      .reduce((sum, span) => sum + (span.end - span.start), 0)
    return shift > 0 ? { ...clip, record_start_s: clip.record_start_s - shift } : clip
  })
  return withClips(timeline, result)
}

export function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value))
}

/** Snap a candidate time to the nearest candidate within threshold. */
export function snap(time: number, candidates: number[], thresholdS: number): number {
  let best = time
  let bestDist = thresholdS
  for (const candidate of candidates) {
    const dist = Math.abs(candidate - time)
    if (dist < bestDist) {
      best = candidate
      bestDist = dist
    }
  }
  return best
}

export type { TimelineClip, TimelineTrack }
