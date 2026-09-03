/** Editor timeline document types — structural mirrors of the backend
 * timeline schema (app/timelines/schema.py), import-free so the store
 * stays testable headlessly and the API types stay generated. */

export interface ClipSource {
  asset_id: string
  in_s: number
  out_s: number
}

export interface TimelineClip {
  id: string
  name: string
  source: ClipSource
  record_start_s: number
  reason: string
  confidence: number
  enabled: boolean
}

export interface TimelineTrack {
  id: string
  kind: 'video' | 'audio'
  name: string
  clips: TimelineClip[]
}

export interface EditorTimeline {
  schema_version: number
  name: string
  frame_rate: number | null
  tracks: TimelineTrack[]
  meta?: unknown
}
