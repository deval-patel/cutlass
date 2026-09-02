import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import StylePanel from './StylePanel'
import type { Asset } from '../../types'

const asset: Asset = {
  id: 'a1',
  project_id: 'p1',
  filename: 'day1.mp4',
  status: 'ready',
  error: null,
  meta: { duration_s: 100, fps: 30, width: 1920, height: 1080 },
  segments: [{ start_s: 0, end_s: 20, reason: 'r', confidence: 1 }],
  has_render: false,
  created_at: null,
  progress: null,
  frame_notes: [],
  transcript: [],
  style_preset: 'default',
  user_brief: '',
}

const presets = [
  { preset_id: 'default', name: 'Auto', description: 'Balanced', pacing: 'natural' },
  { preset_id: 'shorts', name: 'Shorts', description: 'Punchy', pacing: 'fast' },
]

function installFetch(putShouldFail = false) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/v1/styles') {
      return new Response(JSON.stringify(presets), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    if (url === '/api/v1/assets/a1/redraft' && init?.method === 'POST') {
      if (putShouldFail) return new Response('{"detail":"nope"}', { status: 400 })
      return new Response(JSON.stringify({ status: 'redrafting' }), { status: 200 })
    }
    return new Response('not found', { status: 404 })
  })
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <StylePanel asset={asset} />
    </QueryClientProvider>,
  )
}

describe('StylePanel', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists preset styles and disables re-draft until something changes', async () => {
    const fetchMock = installFetch()
    vi.stubGlobal('fetch', fetchMock)
    renderPanel()

    const select = (await screen.findByRole('combobox')) as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBe(2))
    expect(select.value).toBe('default')

    const button = screen.getByText('Re-draft') as HTMLButtonElement
    expect(button.disabled).toBe(true) // unchanged state

    fireEvent.change(select, { target: { value: 'shorts' } })
    expect(button.disabled).toBe(false)

    fireEvent.click(button)
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([u, i]) => String(u).endsWith('/redraft') && i?.method === 'POST',
        ),
      ).toBe(true),
    )
    const body = JSON.parse(
      String(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/redraft'))?.[1]?.body),
    )
    expect(body).toEqual({ preset_id: 'shorts', user_brief: '' })
  })

  it('surfaces server errors from the redraft call', async () => {
    vi.stubGlobal('fetch', installFetch(true))
    renderPanel()
    const select = (await screen.findByRole('combobox')) as HTMLSelectElement
    await waitFor(() => expect(select.options.length).toBe(2))
    fireEvent.change(select, { target: { value: 'shorts' } })
    fireEvent.click(screen.getByText('Re-draft'))
    expect(await screen.findByText('nope')).toBeTruthy()
  })
})
