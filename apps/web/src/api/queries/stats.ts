import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../client'
import type { components } from '../types'

export type StatsOverview = components['schemas']['StatsOverview']
export type StatItem = components['schemas']['StatItem']

export function getStats() {
  return apiFetch<StatsOverview>('/stats/overview')
}

export function useStats() {
  return useQuery({
    queryKey: ['stats', 'overview'],
    queryFn: getStats,
    staleTime: 30_000,
  })
}
