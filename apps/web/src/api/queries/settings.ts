import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, patchJSON, postJSON } from '../client'
import type { components } from '../types'

type DocumentOut = components['schemas']['DocumentOut']
type InkProfileIn = components['schemas']['InkProfileIn']
type InkProfileOut = components['schemas']['InkProfileOut']
type InkProfilePatch = components['schemas']['InkProfilePatch']
type JobOut = components['schemas']['JobOut']
type TagIn = components['schemas']['TagIn']
type TagOut = components['schemas']['TagOut']

const INK_PROFILES_KEY = ['ink-profiles'] as const
const TAGS_KEY = ['tags'] as const

export function useInkProfiles() {
  return useQuery({
    queryKey: INK_PROFILES_KEY,
    queryFn: () => apiFetch<InkProfileOut[]>('/ink-profiles'),
  })
}

export function useCreateInkProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: InkProfileIn) => postJSON<InkProfileOut>('/ink-profiles', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: INK_PROFILES_KEY })
    },
  })
}

export function usePatchInkProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: InkProfilePatch }) =>
      patchJSON<InkProfileOut>(`/ink-profiles/${id}`, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: INK_PROFILES_KEY })
    },
  })
}

/** 先取文档最新 job，再从墨迹分色阶段重跑（rules_json 只影响 s3 及之后）。 */
export function useReidentifyDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (documentId: string) => {
      const document = await apiFetch<DocumentOut>(`/documents/${documentId}`)
      if (!document.job) return null
      return postJSON<JobOut>(`/jobs/${document.job.id}/retry`, { from_stage: 'ink' })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['job'] })
    },
  })
}

export function useTags(type: 'knowledge' | 'method', status: 'approved' | 'pending') {
  return useQuery({
    queryKey: [...TAGS_KEY, type, status],
    queryFn: () => apiFetch<TagOut[]>(`/tags?type=${type}&status=${status}`),
  })
}

export function usePendingTags() {
  return useQuery({
    queryKey: [...TAGS_KEY, 'pending'],
    queryFn: () => apiFetch<TagOut[]>('/tags/pending'),
  })
}

export function useCreateTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: TagIn) => postJSON<TagOut>('/tags', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TAGS_KEY })
    },
  })
}

export function useMergeTags() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { from_id: string; to_id: string }) =>
      postJSON<TagOut>('/tags/merge', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TAGS_KEY })
    },
  })
}
