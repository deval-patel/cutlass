// API payload shapes, generated from the backend's OpenAPI schema
// (src/api/schema.d.ts — regenerate with `npm run gen:api`). Hand-written
// types below cover the few endpoints that return untyped dicts.

import type { components } from './api/schema'

export type Asset = components['schemas']['Asset']
export type JobStatusValue = Asset['status']
export type Segment = components['schemas']['Segment']
export type FrameNoteItem = components['schemas']['FrameNote']
export type TranscriptLine = components['schemas']['TranscriptLine']
export type VideoMeta = components['schemas']['VideoMeta']
export type Project = components['schemas']['Project']
export type ProjectSummary = components['schemas']['ProjectSummary']
export type ProjectDetail = components['schemas']['ProjectDetail']
export type TimelineDoc = components['schemas']['Timeline']
export type TimelineInfo = components['schemas']['TimelineInfo']

export interface FrameManifestItem {
  t: number
  file: string
}

export interface UploadResponse {
  id: string
}
