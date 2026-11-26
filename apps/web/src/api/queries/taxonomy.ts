import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../client'

export type TaxonomyTopic = {
  id: string
  name: string
  subject: string | null
  domain: string | null
  grade: number | null
  semester: string | null
  chapter: string | null
  topic_type: string | null
}

export type TaxonomyNeighbor = TaxonomyTopic & {
  strength: string
  reason: string
}

export type TaxonomyDetail = TaxonomyTopic & {
  external_id: string
  description: string
  mastery_criteria: string[]
  diagnostic_question: { question?: string; answer?: string } | null
  standards: Record<string, unknown>[]
  prerequisites: TaxonomyNeighbor[]
  dependents: TaxonomyNeighbor[]
  ancestors: TaxonomyTopic[]
}

export type TaxonomyFacet = { value: string; count: number }

export type TaxonomySummary = {
  topics: number
  edges: number
  subjects: TaxonomyFacet[]
  source: string
  license: string
  commit: string
}

export type TaxonomyPath = {
  problem_id: string
  knowledge: TaxonomyTopic[]
  prerequisites: TaxonomyTopic[]
}

export type TaxonomyTopicParams = {
  subject?: string
  domain?: string
  grade?: number
  q?: string
}

export function getTaxonomySummary() {
  return apiFetch<TaxonomySummary>('/taxonomy/summary')
}

export function listTaxonomyTopics(params: TaxonomyTopicParams = {}) {
  const search = new URLSearchParams()
  if (params.subject) search.set('subject', params.subject)
  if (params.domain) search.set('domain', params.domain)
  if (params.grade !== undefined) search.set('grade', String(params.grade))
  if (params.q?.trim()) search.set('q', params.q.trim())
  const qs = search.toString()
  return apiFetch<TaxonomyTopic[]>(`/taxonomy/topics${qs ? `?${qs}` : ''}`)
}

export function getTaxonomyTopic(tagId: string) {
  return apiFetch<TaxonomyDetail>(`/taxonomy/topics/${tagId}`)
}

export function getProblemPath(problemId: string) {
  return apiFetch<TaxonomyPath>(`/taxonomy/problems/${problemId}/path`)
}

// ---------------------------------------------------------------- hooks

export function useTaxonomySummary() {
  return useQuery({ queryKey: ['taxonomy', 'summary'], queryFn: getTaxonomySummary })
}

export function useTaxonomyTopics(params: TaxonomyTopicParams) {
  return useQuery({
    queryKey: ['taxonomy', 'topics', params],
    queryFn: () => listTaxonomyTopics(params),
  })
}

export function useTaxonomyTopic(tagId: string | undefined) {
  return useQuery({
    queryKey: ['taxonomy', 'topic', tagId],
    queryFn: () => getTaxonomyTopic(tagId as string),
    enabled: Boolean(tagId),
  })
}

export function useProblemPath(problemId: string | undefined) {
  return useQuery({
    queryKey: ['taxonomy', 'problem', problemId],
    queryFn: () => getProblemPath(problemId as string),
    enabled: Boolean(problemId),
  })
}
