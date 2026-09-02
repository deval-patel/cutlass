/** Typed fetch helpers + TanStack Query hooks for the backend API. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Asset, ProjectDetail, ProjectSummary, Segment, UploadResponse } from '../../types'

export const queryKeys = {
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
}

const POLL_MS = 2000
const TERMINAL = ['ready', 'rendered', 'failed']

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string }
    throw new ApiError(body.detail || `request failed (HTTP ${res.status})`, res.status)
  }
  return (await res.json()) as T
}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => jsonFetch<ProjectSummary[]>('/api/v1/projects'),
  })
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => jsonFetch<ProjectDetail>(`/api/v1/projects/${projectId}`),
    // Poll while any asset has work in flight; SSE patches between polls.
    refetchInterval: (query) => {
      const data = query.state.data as ProjectDetail | undefined
      const busy = data?.assets.some((a) => !TERMINAL.includes(a.status))
      return busy ? POLL_MS : false
    },
  })
}

/** Upload via the legacy endpoint (auto-creates a project); returns the asset. */
export function useUploadAsset() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File): Promise<Asset> => {
      const body = new FormData()
      body.append('video', file)
      const { id } = await jsonFetch<UploadResponse>('/api/upload', { method: 'POST', body })
      return jsonFetch<Asset>(`/api/v1/assets/${id}`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  })
}

export function useSaveSegments(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ assetId, segments }: { assetId: string; segments: Segment[] }) =>
      jsonFetch<Asset>(`/api/jobs/${assetId}/segments`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(segments),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

export function useStartRender(projectId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (assetId: string) =>
      jsonFetch<{ status: string }>(`/api/v1/assets/${assetId}/render`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (projectId: string) =>
      jsonFetch<{ deleted: boolean }>(`/api/v1/projects/${projectId}`, { method: 'DELETE' }),
    onSuccess: (_data, projectId) => {
      queryClient.removeQueries({ queryKey: queryKeys.project(projectId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.projects })
    },
  })
}

export { jsonFetch }
