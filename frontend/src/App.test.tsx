import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import App from './App'
import type { ProjectSummary } from './types'

const projects: ProjectSummary[] = [
  {
    id: 'p1',
    name: 'Japan trip',
    created_at: '2026-09-01 10:00:00',
    assets: 2,
    duration_s: 620,
    timeline_id: 't1',
  },
]

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/projects') return json(projects)
      return new Response('not found', { status: 404 })
    }),
  )
}

function renderApp(route = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  beforeEach(() => installFetch())
  afterEach(() => vi.unstubAllGlobals())

  it('renders the project list on the home route', async () => {
    renderApp('/')
    expect(await screen.findByText('Japan trip')).toBeTruthy()
    expect(screen.getByText(/2 assets/)).toBeTruthy()
    expect(screen.getByText(/10:20/)).toBeTruthy() // duration formatted
  })

  it('renders the upload zone while the list loads or is empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json([])),
    )
    renderApp('/')
    expect(await screen.findByText('Drop a video here, or click to browse')).toBeTruthy()
    expect(screen.queryByText('Projects')).toBeNull()
  })

  it('navigates to a project page via its link', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/v1/projects') return json(projects)
        if (url === '/api/v1/projects/p1') return json(projectDetail)
        if (url === '/api/v1/assets/a1/frames') return json([])
        return new Response('not found', { status: 404 })
      }),
    )
    renderApp('/')
    const link = await screen.findByText('Japan trip')
    link.click()
    expect(await screen.findByText(/nice drone shot/)).toBeTruthy()
  })
})

const projectDetail = {
  project: { id: 'p1', name: 'Japan trip', user_id: null, created_at: '2026-09-01 10:00:00' },
  assets: [
    {
      id: 'a1',
      project_id: 'p1',
      filename: 'day1.mp4',
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
      transcript: [{ start_s: 0, end_s: 5, text: 'welcome to japan' }],
    },
  ],
  timeline: null,
}
