import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, patchJSON, postJSON } from '../client'
import type { components } from '../types'

type RegionOut = components['schemas']['RegionOut']
type RegionPatch = components['schemas']['RegionPatch']

export function useDocumentRegions(documentId: string | undefined) {
  return useQuery({
    queryKey: ['regions', documentId],
    queryFn: () => apiFetch<RegionOut[]>(`/documents/${documentId}/regions`),
    enabled: Boolean(documentId),
  })
}

export function usePatchRegion(documentId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ regionId, patch }: { regionId: string; patch: RegionPatch }) =>
      patchJSON<RegionOut>(`/regions/${regionId}`, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
    },
  })
}

export function useMergeRegions(documentId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (regionIds: string[]) =>
      postJSON<RegionOut[]>('/regions/merge', { region_ids: regionIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
    },
  })
}

export function useDeleteRegion(documentId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (regionId: string) =>
      apiFetch<void>(`/regions/${regionId}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
    },
  })
}
