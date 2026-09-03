import { useCallback, useEffect, useRef } from 'react'
import { useEditorStore } from './store'
import * as ops from './operations'
import type { EditorTimeline, TimelineClip } from './types'

export interface MonitorHandle {
  playPause(): void
  stepFrames(n: number): void
}

interface ProgramMonitorProps {
  timeline: EditorTimeline
  fps: number
  onReady(handle: MonitorHandle): void
}

function assetUrl(assetId: string): string {
  return `/api/v1/assets/${assetId}/source`
}

/** Program monitor: plays the TIMELINE, not the source — across assets.
 *
 * One <video> element is re-pointed at each clip's source range in order;
 * crossing an asset boundary swaps the src (a pending seek is applied on
 * loadedmetadata); gaps are skipped. The store's playhead is timeline
 * time — pushed by the rAF loop during playback and honored (seek) when
 * changed externally.
 */
export default function ProgramMonitor({ timeline, fps, onReady }: ProgramMonitorProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const clips = ops.videoClips(timeline)
  const total = ops.duration(timeline)

  const playhead = useEditorStore((s) => s.playhead)
  const setPlayhead = useEditorStore((s) => s.setPlayhead)
  const lastPushed = useRef(0)
  const playing = useRef(false)
  const currentClip = useRef<TimelineClip | null>(null)
  const loadedAsset = useRef<string | null>(null)
  const pendingSeek = useRef<number | null>(null)

  const pointAt = useCallback((clip: TimelineClip, sourceTime: number) => {
    const video = videoRef.current
    if (!video) return
    const target = Math.max(clip.source.in_s, Math.min(clip.source.out_s - 0.05, sourceTime))
    if (loadedAsset.current !== clip.source.asset_id) {
      loadedAsset.current = clip.source.asset_id
      pendingSeek.current = target
      video.src = assetUrl(clip.source.asset_id)
      video.load()
    } else {
      video.currentTime = target
    }
  }, [])

  // Apply a deferred seek once swapped-in source metadata is ready.
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    const onLoadedMetadata = () => {
      if (pendingSeek.current !== null) {
        video.currentTime = pendingSeek.current
        pendingSeek.current = null
      }
      if (playing.current) void video.play()
    }
    video.addEventListener('loadedmetadata', onLoadedMetadata)
    return () => video.removeEventListener('loadedmetadata', onLoadedMetadata)
  }, [])

  const clipAtPlayhead = useCallback(
    (t: number): TimelineClip | null => {
      let last: TimelineClip | null = null
      for (const clip of clips) {
        const end = ops.clipEnd(clip)
        if (t >= clip.record_start_s && t < end) return clip
        if (t < clip.record_start_s) return last ?? clip // next clip at/after t
        last = clip
      }
      return clips.length ? clips[clips.length - 1] : null
    },
    [clips],
  )

  // External playhead changes (scrub, ruler, arrows) → seek the element.
  useEffect(() => {
    const video = videoRef.current
    if (!video || Math.abs(playhead - lastPushed.current) < 1e-3) return
    const clip = clipAtPlayhead(playhead)
    if (!clip) return
    currentClip.current = clip
    const sourceTime = clip.source.in_s + (playhead - clip.record_start_s)
    pointAt(clip, sourceTime)
    if (playing.current && playhead < total - 0.05) void video.play()
  }, [playhead, clipAtPlayhead, total, pointAt])

  // rAF loop: push store.playhead from the element while playing, jumping
  // across clip ends (and gaps) to the next clip's source-in.
  useEffect(() => {
    let raf = 0
    const tick = () => {
      const video = videoRef.current
      const clip = currentClip.current
      if (video && clip && playing.current) {
        if (video.currentTime >= clip.source.out_s - 0.02) {
          const idx = clips.indexOf(clip)
          const next = clips[idx + 1]
          if (next) {
            currentClip.current = next
            lastPushed.current = next.record_start_s
            setPlayhead(next.record_start_s)
            pointAt(next, next.source.in_s)
          } else {
            playing.current = false
            video.pause()
            setPlayhead(total)
          }
        } else {
          const t = clip.record_start_s + (video.currentTime - clip.source.in_s)
          lastPushed.current = t
          setPlayhead(Math.max(0, t))
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [clips, total, setPlayhead, pointAt])

  useEffect(() => {
    const handle: MonitorHandle = {
      playPause() {
        const video = videoRef.current
        if (!video) return
        if (playing.current) {
          playing.current = false
          video.pause()
          return
        }
        const t = useEditorStore.getState().playhead
        const clip = clipAtPlayhead(t)
        if (!clip) return
        currentClip.current = clip
        const inRange = t >= clip.record_start_s && t < ops.clipEnd(clip)
        pointAt(clip, inRange ? clip.source.in_s + (t - clip.record_start_s) : clip.source.in_s)
        playing.current = true
        void video.play()
      },
      stepFrames(n) {
        const step = n / fps
        playing.current = false
        videoRef.current?.pause()
        setPlayhead(Math.max(0, Math.min(total, useEditorStore.getState().playhead + step)))
      },
    }
    onReady(handle)
  }, [clipAtPlayhead, fps, total, onReady, setPlayhead, pointAt])

  return <video ref={videoRef} className="program-monitor" />
}
