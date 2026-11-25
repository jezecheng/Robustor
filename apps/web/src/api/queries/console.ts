import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, patchJSON, postJSON, putJSON } from '../client'
import type { components } from '../types'

export type DocumentOut = components['schemas']['DocumentOut']
export type PageOut = components['schemas']['PageOut']
export type RegionOut = components['schemas']['RegionOut']
export type RegionPatch = components['schemas']['RegionPatch']
export type ProblemOut = components['schemas']['ProblemOut']
export type ProblemPatch = components['schemas']['ProblemPatch']
export type SolutionIn = components['schemas']['SolutionIn']
export type SolutionOut = components['schemas']['SolutionOut']
export type ProblemTagOut = components['schemas']['ProblemTagOut']
export type TagOut = components['schemas']['TagOut']
export type JobOut = components['schemas']['JobOut']
export type BlockType = RegionOut['block_type']
export type Verdict = NonNullable<ProblemOut['marks']>[number]['verdict']

/** 区域类型的中文标签与颜色变量，画布 / 图例 / 类型菜单共用。 */
export const BLOCK_TYPE_META: { value: BlockType; label: string; color: string }[] = [
  { value: 'stem', label: '题干', color: 'var(--role-stem)' },
  { value: 'figure', label: '图示', color: 'var(--role-figure)' },
  { value: 'answer', label: '解答', color: 'var(--role-answer)' },
  { value: 'mark', label: '批改', color: 'var(--role-mark)' },
  { value: 'correction', label: '订正', color: 'var(--role-correction)' },
  { value: 'noise', label: '噪声', color: 'var(--role-noise)' },
]

export function blockMeta(type: BlockType) {
  return BLOCK_TYPE_META.find((meta) => meta.value === type) ?? BLOCK_TYPE_META[0]
}

export type Box = [number, number, number, number]

/** 后端 bbox 是 number[]，统一收窄成四元组，避免下游反复判空。 */
export function toBox(bbox: number[] | undefined): Box {
  if (!bbox || bbox.length < 4) return [0, 0, 0, 0]
  return [bbox[0], bbox[1], bbox[2], bbox[3]]
}

export const STAGE_LABELS: Record<JobOut['stage'], string> = {
  preprocess: '预处理',
  layout: '版面切分',
  ink: '墨迹分色',
  recognize: '文字识别',
  assemble: '装配',
  tag: '打标签',
}

const EMPTY_STAGE = 'preprocess'

// ---------------------------------------------------------------- 查询

export function useDocument(documentId: string | undefined) {
  return useQuery({
    queryKey: ['document', documentId],
    queryFn: () => apiFetch<DocumentOut>(`/documents/${documentId}`),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const job = query.state.data?.job
      return job && (job.status === 'queued' || job.status === 'running') ? 1500 : false
    },
  })
}

export function useRegions(documentId: string | undefined) {
  return useQuery({
    queryKey: ['regions', documentId],
    queryFn: () => apiFetch<RegionOut[]>(`/documents/${documentId}/regions`),
    enabled: Boolean(documentId),
  })
}

export function useProblem(problemId: string | null | undefined) {
  return useQuery({
    queryKey: ['problem', problemId],
    queryFn: () => apiFetch<ProblemOut>(`/problems/${problemId}`),
    enabled: Boolean(problemId),
  })
}

export function useTagSearch(q: string) {
  const keyword = q.trim()
  return useQuery({
    queryKey: ['tags', 'approved', keyword],
    queryFn: () => apiFetch<TagOut[]>(`/tags?status=approved&q=${encodeURIComponent(keyword)}`),
    enabled: keyword.length > 0,
    staleTime: 10_000,
  })
}

// ---------------------------------------------------------------- 变更

export function usePatchRegion(documentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ regionId, patch }: { regionId: string; patch: RegionPatch }) =>
      patchJSON<RegionOut>(`/regions/${regionId}`, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
    },
  })
}

export function useMergeRegions(documentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (regionIds: string[]) =>
      postJSON<RegionOut[]>('/regions/merge', { region_ids: regionIds }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
    },
  })
}

export function useRetryJob(documentId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) =>
      postJSON<JobOut>(`/jobs/${jobId}/retry`, { from_stage: EMPTY_STAGE }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['document', documentId] })
      void queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
    },
  })
}

export function useCreateProblem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: components['schemas']['ProblemCreate']) =>
      postJSON<ProblemOut>('/problems', body),
    onSuccess: (problem) => {
      void queryClient.invalidateQueries({ queryKey: ['problems'] })
      void queryClient.invalidateQueries({ queryKey: ['regions', problem.document_id] })
      void queryClient.invalidateQueries({ queryKey: ['document', problem.document_id] })
    },
  })
}

export function usePatchProblem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ problemId, patch }: { problemId: string; patch: ProblemPatch }) =>
      patchJSON<ProblemOut>(`/problems/${problemId}`, patch),
    onSuccess: (problem) => {
      void queryClient.invalidateQueries({ queryKey: ['problem', problem.id] })
      void queryClient.invalidateQueries({ queryKey: ['problems'] })
    },
  })
}

export function useReplaceSolutions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ problemId, body }: { problemId: string; body: SolutionIn[] }) =>
      putJSON<SolutionOut[]>(`/problems/${problemId}/solutions`, body),
    onSuccess: (_solutions, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['problem', variables.problemId] })
    },
  })
}

export function useReplaceTags() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ problemId, body }: { problemId: string; body: { knowledge: string[]; method: string[] } }) =>
      putJSON<ProblemTagOut[]>(`/problems/${problemId}/tags`, body),
    onSuccess: (_tags, variables) => {
      void queryClient.invalidateQueries({ queryKey: ['problem', variables.problemId] })
    },
  })
}

export function useCreateTag() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { type: 'knowledge' | 'method'; name: string }) =>
      postJSON<TagOut>('/tags', body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tags'] })
    },
  })
}
