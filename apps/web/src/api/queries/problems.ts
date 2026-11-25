import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, patchJSON, postJSON, putJSON } from '../client'
import type { components } from '../types'

export type ProblemOut = components['schemas']['ProblemOut']
export type ProblemListOut = components['schemas']['ProblemListOut']
export type ProblemTagOut = components['schemas']['ProblemTagOut']
export type ProblemPatch = components['schemas']['ProblemPatch']
export type ProblemTagsIn = components['schemas']['ProblemTagsIn']
export type ReviewOut = components['schemas']['ReviewOut']
export type TagOut = components['schemas']['TagOut']
export type TagType = TagOut['type']
export type Verdict = NonNullable<ProblemOut['marks']>[number]['verdict']

export type ProblemListParams = {
  subject?: string
  /** 可重复传，后端语义为 AND。 */
  tagIds?: string[]
  verdict?: Verdict
  due?: 'today' | 'overdue'
  q?: string
  page?: number
  size?: number
}

export type TagListParams = {
  type?: TagType
  status?: 'approved' | 'pending'
  q?: string
}

export function listProblems(params: ProblemListParams = {}) {
  const search = new URLSearchParams()
  if (params.subject) search.set('subject', params.subject)
  for (const tagId of params.tagIds ?? []) search.append('tag_id', tagId)
  if (params.verdict) search.set('verdict', params.verdict)
  if (params.due) search.set('due', params.due)
  if (params.q?.trim()) search.set('q', params.q.trim())
  if (params.page) search.set('page', String(params.page))
  if (params.size) search.set('size', String(params.size))
  const qs = search.toString()
  return apiFetch<ProblemListOut>(`/problems${qs ? `?${qs}` : ''}`)
}

export function getProblem(problemId: string) {
  return apiFetch<ProblemOut>(`/problems/${problemId}`)
}

export function listTags(params: TagListParams = {}) {
  const search = new URLSearchParams()
  if (params.type) search.set('type', params.type)
  if (params.status) search.set('status', params.status)
  if (params.q?.trim()) search.set('q', params.q.trim())
  const qs = search.toString()
  return apiFetch<TagOut[]>(`/tags${qs ? `?${qs}` : ''}`)
}

export function putTags(problemId: string, body: ProblemTagsIn) {
  return putJSON<ProblemTagOut[]>(`/problems/${problemId}/tags`, body)
}

export function patchProblem(problemId: string, body: ProblemPatch) {
  return patchJSON<ProblemOut>(`/problems/${problemId}`, body)
}

export function reviewProblem(problemId: string, grade: number) {
  return postJSON<ReviewOut>(`/problems/${problemId}/review`, { grade })
}

// ---------------------------------------------------------------- hooks

export function useProblems(params: ProblemListParams) {
  return useQuery({
    queryKey: ['problems', params],
    queryFn: () => listProblems(params),
    placeholderData: keepPreviousData,
  })
}

export function useProblem(problemId: string | undefined) {
  return useQuery({
    queryKey: ['problem', problemId],
    queryFn: () => getProblem(problemId as string),
    enabled: Boolean(problemId),
  })
}

/** 标签下拉 / 搜索；搜索场景传 q，启用条件由调用方用 enabled 控制。 */
export function useTags(params: TagListParams, enabled = true) {
  return useQuery({
    queryKey: ['tags', params.type ?? 'all', params.status ?? 'all', params.q ?? ''],
    queryFn: () => listTags(params),
    enabled,
    staleTime: 30_000,
  })
}

export function usePutTags(problemId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ProblemTagsIn) => putTags(problemId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['problem', problemId] })
      void queryClient.invalidateQueries({ queryKey: ['problems'] })
      void queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}

export function usePatchProblem(problemId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: ProblemPatch) => patchProblem(problemId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['problem', problemId] })
      void queryClient.invalidateQueries({ queryKey: ['problems'] })
    },
  })
}

export function useReviewProblem(problemId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (grade: number) => reviewProblem(problemId, grade),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['problems'] })
      void queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}
