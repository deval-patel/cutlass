// API payload shapes — mirror backend/app/models.py. Generated from the
// OpenAPI schema once Plan 1 lands; hand-maintained until then.

export type JobStatusValue =
  'uploaded' | 'sampling' | 'analyzing' | 'ready' | 'rendering' | 'rendered' | 'failed'

export type FrameNoteLabel = 'core' | 'filler' | 'dead_air' | 'intro_outro' | 'repetition' | 'other'

export interface Segment {
  start_s: number
  end_s: number
  reason: string
  confidence: number
}

export interface FrameNoteItem {
  timestamp_s: number
  description: string
  label: FrameNoteLabel
}

export interface TranscriptLine {
  start_s: number
  end_s: number
  text: string
}

export interface VideoMeta {
  duration_s: number
  fps: number
  width: number
  height: number
}

export interface JobStatus {
  id: string
  filename: string
  status: JobStatusValue
  error: string | null
  meta: VideoMeta | null
  segments: Segment[]
  has_render: boolean
  created_at: string | null
  progress: string | null
  frame_notes: FrameNoteItem[]
  transcript: TranscriptLine[]
}

export interface JobSummary {
  id: string
  filename: string
  status: JobStatusValue
  duration_s: number | null
  segments: number
  has_render: boolean
  created_at: string | null
}

export interface FrameManifestItem {
  t: number
  file: string
}

export interface UploadResponse {
  id: string
}
