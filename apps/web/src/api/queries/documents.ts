import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, postJSON } from '../client'
import type { components } from '../types'

type DocumentListItem = components['schemas']['DocumentListItem']
type DocumentOut = components['schemas']['DocumentOut']
type DocumentCreated = components['schemas']['DocumentCreated']
type JobOut = components['schemas']['JobOut']

export function useDocuments() {
  return useQuery({
    queryKey: ['documents'],
    queryFn: () => apiFetch<DocumentListItem[]>('/documents'),
  })
}

export function useDocument(documentId: string | undefined) {
  return useQuery({
    queryKey: ['document', documentId],
    queryFn: () => apiFetch<DocumentOut>(`/documents/${documentId}`),
    enabled: Boolean(documentId),
  })
}

/** 任务进度：未结束前每 1s 轮询，done/failed 自动停止。 */
export function useJob(jobId: string | undefined, pollMs = 1000) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => apiFetch<JobOut>(`/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const job = query.state.data
      if (!job) return pollMs
      return job.status === 'done' || job.status === 'failed' ? false : pollMs
    },
  })
}

export function useUploadDocuments() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ files, subject }: { files: File[]; subject: string }) => {
      const form = new FormData()
      files.forEach((file) => form.append('files', file))
      form.append('subject', subject)
      return apiFetch<DocumentCreated>('/documents', { method: 'POST', body: form })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}

export function useRetryJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, fromStage = 'preprocess' }: { jobId: string; fromStage?: string }) =>
      postJSON<JobOut>(`/jobs/${jobId}/retry`, { from_stage: fromStage }),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['job', job.id] })
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}
