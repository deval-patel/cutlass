import type { RefObject } from 'react'
import type { Segment } from '../types'

interface MediaPlayerProps {
  src: string
  segments: Segment[]
  videoRef: RefObject<HTMLVideoElement>
  /** When true (segment edit mode), auto-skip is suspended. */
  skipDisabled?: boolean
}

/** Video element that auto-skips ranges outside the keep-segments. */
export default function MediaPlayer({ src, segments, videoRef, skipDisabled }: MediaPlayerProps) {
  function onTimeUpdate() {
    if (skipDisabled) return
    const v = videoRef.current
    if (!v) return
    const inKeep = segments.some((s) => v.currentTime >= s.start_s && v.currentTime < s.end_s)
    if (!inKeep && segments.length) {
      const next = segments.find((s) => s.start_s > v.currentTime)
      if (next) v.currentTime = next.start_s
      else v.pause()
    }
  }

  return <video ref={videoRef} src={src} controls onTimeUpdate={onTimeUpdate} />
}
