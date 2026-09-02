import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import JobView from './JobView'
import type { JobStatus } from './types'

const readyJob: JobStatus = {
  id: 'abc123',
  filename: 'trip.mp4',
  status: 'ready',
  error: null,
  meta: { duration_s: 100, fps: 30, width: 1920, height: 1080 },
  segments: [
    { start_s: 0, end_s: 20, reason: 'opening scene', confidence: 0.9 },
    { start_s: 50, end_s: 80, reason: 'main content', confidence: 0.85 },
  ],
  has_render: false,
  created_at: '2026-09-01 10:00:00',
  progress: null,
  frame_notes: [
    { timestamp_s: 2, description: 'a street', label: 'core' },
    { timestamp_s: 60, description: 'a temple', label: 'core' },
  ],
  transcript: [{ start_s: 0, end_s: 5, text: 'welcome to japan' }],
}

function installFetch(job: JobStatus) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === `/api/jobs/${job.id}`) {
      return new Response(JSON.stringify(job), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (url === `/api/jobs/${job.id}/frames`) {
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return new Response('not found', { status: 404 })
  })
}

describe('JobView', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', installFetch(readyJob))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the draft: keep blocks, reasons, transcript', async () => {
    render(<JobView jobId="abc123" onReset={() => {}} />)
    expect(await screen.findByText(/opening scene/)).toBeTruthy()
    expect(screen.getByText(/main content/)).toBeTruthy()
    const keepBlocks = document.querySelectorAll('.timeline .keep')
    expect(keepBlocks.length).toBe(2)
    expect(screen.getByText(/welcome to japan/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Render final cut' })).toBeTruthy()
  })

  it('stops polling once the job reaches a terminal status', async () => {
    render(<JobView jobId="abc123" onReset={() => {}} />)
    await screen.findByText(/opening scene/)
    const fetchMock = vi.mocked(fetch)
    // Let any stray poll timers fire — none should, the job is terminal.
    await new Promise((r) => setTimeout(r, 30))
    expect(
      fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/api/jobs/abc123')).length,
    ).toBe(1)
  })
})

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((ev: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

describe('JobView over SSE', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('fetch', installFetch(readyJob))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('subscribes to the events stream, patches live state, closes on terminal', async () => {
    render(<JobView jobId="abc123" onReset={() => {}} />)

    // Full payload arrives via the initial fetch; the stream is subscribed.
    await screen.findByText(/opening scene/)
    expect(FakeEventSource.instances.length).toBe(1)
    expect(FakeEventSource.instances[0].url).toBe('/api/jobs/abc123/events')

    // A terminal event closes the stream and refetches the full payload.
    const source = FakeEventSource.instances[0]
    source.emit({ status: 'ready', progress: null, error: null })
    expect(source.closed).toBe(true)
    expect(await screen.findByText(/main content/)).toBeTruthy()
  })

  it('falls back to polling when the stream errors mid-flight', async () => {
    render(<JobView jobId="abc123" onReset={() => {}} />)
    await screen.findByText(/opening scene/)

    const source = FakeEventSource.instances[0]
    source.onerror?.()
    // The fallback loop takes over; the ready job renders via polling too.
    expect(await screen.findByText(/main content/)).toBeTruthy()
  })
})
