import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiFetch } from '../client'
import type { components } from '../types'

export type AiUsageSummary = components['schemas']['AiUsageSummaryOut']
export type AiUsageBucket = components['schemas']['AiUsageBucketOut']
export type AiUsageRequestList = components['schemas']['AiUsageRequestListOut']

export type AiUsageRange = {
  start: string
  end: string
  bucket: 'day' | 'month'
}

function rangeParams(range: AiUsageRange): string {
  const params = new URLSearchParams({
    start: range.start,
    end: range.end,
    bucket: range.bucket,
  })
  return params.toString()
}

export function useAiUsageSummary(range: AiUsageRange) {
  return useQuery({
    queryKey: ['ai-usage', 'summary', range.start, range.end, range.bucket],
    queryFn: () => apiFetch<AiUsageSummary>(`/ai-usage/summary?${rangeParams(range)}`),
  })
}

export function useAiUsageRequests(range: AiUsageRange, page: number, size: number) {
  return useQuery({
    queryKey: ['ai-usage', 'requests', range.start, range.end, page, size],
    queryFn: () =>
      apiFetch<AiUsageRequestList>(
        `/ai-usage/requests?${rangeParams(range)}&page=${page}&size=${size}`,
      ),
    placeholderData: keepPreviousData,
  })
}
