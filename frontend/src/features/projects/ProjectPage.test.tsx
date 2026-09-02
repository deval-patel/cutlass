import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ProjectPage from './ProjectPage'
import type { ProjectDetail } from '../../types'

const readyDetail: ProjectDetail = {
  project: { id: 'p1', name: 'Japan trip', user_id: null, created_at: '2026-09-01 10:00:00' },
  assets: [
    {
      id: 'a1',
      project_id: 'p1',
      filename: 'day1.mp4',
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
      style_preset: 'default',
      user_brief: '',
    },
  ],
  timeline: {
    id: 't1',
    project_id: 'p1',
    name: 'main',
    version: 1,
    document: { schema_version: 1, name: 'main', frame_rate: 30, tracks: [] },
  },
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetch(detail: ProjectDetail = readyDetail) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/v1/projects/p1') return json(detail)
    if (url === '/api/v1/assets/a1/frames') return json([])
    if (url === '/api/jobs/a1/segments' && init?.method === 'PUT') {
      return json({ ...detail.assets[0], segments: JSON.parse(String(init.body)) })
    }
    return new Response('not found', { status: 404 })
  })
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/p/p1']}>
        <Routes>
          <Route path="/p/:projectId" element={<ProjectPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProjectPage', () => {
  let fetchMock: ReturnType<typeof installFetch>
  beforeEach(() => {
    fetchMock = installFetch()
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('renders the draft: keep blocks, reasons, transcript, player source', async () => {
    renderPage()
    expect(await screen.findByText(/opening scene/)).toBeTruthy()
    expect(screen.getByText(/main content/)).toBeTruthy()
    expect(document.querySelectorAll('.timeline .keep').length).toBe(2)
    expect(screen.getByText(/welcome to japan/)).toBeTruthy()
    const video = document.querySelector('video')
    expect(video?.getAttribute('src')).toBe('/api/v1/assets/a1/source')
  })

  it('edits and saves segments through the legacy endpoint', async () => {
    renderPage()
    fireEvent.click(await screen.findByText('Edit segments'))

    const start = screen.getByDisplayValue('0')
    fireEvent.change(start, { target: { value: '3' } })
    // Partial numeric input is ignored rather than pushing NaN.
    fireEvent.change(start, { target: { value: '' } })
    expect((start as HTMLInputElement).value).toBe('3')

    fireEvent.click(screen.getByText('Save'))
    await screen.findByText(/opening scene/)

    const put = fetchMock.mock.calls.find(
      ([u, i]) => String(u).endsWith('/segments') && i?.method === 'PUT',
    )
    expect(put).toBeTruthy()
    const body = JSON.parse(String(put?.[1]?.body))
    expect(body[0].start_s).toBe(3)
  })

  it('does not poll once every asset is terminal', async () => {
    renderPage()
    await screen.findByText(/opening scene/)
    await new Promise((r) => setTimeout(r, 30))
    const calls = fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/projects/p1')).length
    expect(calls).toBe(1)
  })

  it('surfaces a missing project as an error with a way back', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{"detail":"project not found"}', { status: 404 })),
    )
    renderPage()
    expect(await screen.findByText(/project not found/i)).toBeTruthy()
    expect(screen.getByText('All projects')).toBeTruthy()
  })
})
