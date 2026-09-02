import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import type { JobStatus, JobSummary } from './types'

const jobs: JobSummary[] = [
  {
    id: 'j1',
    filename: 'trip.mp4',
    status: 'ready',
    duration_s: 120,
    segments: 3,
    has_render: false,
    created_at: '2026-09-01 10:00:00',
  },
]

const jobDetail: JobStatus = {
  id: 'j1',
  filename: 'trip.mp4',
  status: 'ready',
  error: null,
  meta: { duration_s: 120, fps: 30, width: 1920, height: 1080 },
  segments: [
    { start_s: 5, end_s: 40, reason: 'nice drone shot', confidence: 0.9 },
    { start_s: 60, end_s: 90, reason: 'temple walkthrough', confidence: 0.8 },
  ],
  has_render: false,
  created_at: '2026-09-01 10:00:00',
  progress: null,
  frame_notes: [],
  transcript: [],
}

function mockFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/jobs') return json(jobs)
      if (url === '/api/jobs/j1') return json(jobDetail)
      if (url === '/api/jobs/j1/frames') return json([])
      return new Response('not found', { status: 404 })
    }),
  )
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('App', () => {
  beforeEach(() => mockFetch())
  afterEach(() => vi.unstubAllGlobals())

  it('renders recent videos from the job list', async () => {
    render(<App />)
    expect(await screen.findByText('trip.mp4')).toBeTruthy()
    expect(screen.getByText('ready')).toBeTruthy()
    expect(screen.getByText(/120s/)).toBeTruthy()
  })

  it('opens a job view when a recent video is clicked', async () => {
    render(<App />)
    fireEvent.click(await screen.findByText('trip.mp4'))
    // JobView shows the draft's segment reasons once its status loads.
    expect(await screen.findByText(/nice drone shot/)).toBeTruthy()
    expect(screen.getByText(/temple walkthrough/)).toBeTruthy()
  })

  it('still renders the upload UI when the job list request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 500 })))
    render(<App />)
    // refreshJobs swallows the failure: no unhandled rejection, page intact.
    expect(await screen.findByText('Drop a video here, or click to browse')).toBeTruthy()
    expect(screen.queryByText('Recent videos')).toBeNull()
  })
})
