import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, mediaUrl } from '../api/client'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Tag } from '../ui/Tag'
import Latex from '../components/common/Latex'
import { useProblem, usePutTags, useReviewProblem, useTags } from '../api/queries/problems'
import { useProblemPath } from '../api/queries/taxonomy'
import type { ProblemOut, TagType, Verdict } from '../api/queries/problems'

const SUBJECT_LABEL: Record<string, string> = {
  math: '数学',
  physics: '物理',
  chemistry: '化学',
}

const VERDICT_META: Record<Verdict, { label: string; fg: string; bg: string }> = {
  right: { label: '判定：对', fg: 'var(--ok)', bg: 'var(--ok-soft)' },
  wrong: { label: '判定：错', fg: 'var(--danger)', bg: 'var(--danger-soft)' },
  partial: { label: '判定：部分对', fg: 'var(--warn)', bg: 'var(--warn-soft)' },
  unknown: { label: '判定：未知', fg: 'var(--ink-3)', bg: 'var(--surface-3)' },
}

const REVIEW_ACTIONS: { grade: number; label: string; variant: 'primary' | 'secondary' | 'ghost' }[] = [
  { grade: 3, label: '记得', variant: 'primary' },
  { grade: 2, label: '模糊', variant: 'secondary' },
  { grade: 0, label: '忘了', variant: 'ghost' },
]

const TONE_STYLE = {
  stem: { background: 'var(--surface-2)', borderColor: 'var(--line)' },
  student: { background: 'var(--danger-soft)', borderColor: 'var(--danger)' },
  correction: { background: 'var(--accent-soft)', borderColor: 'var(--accent)' },
} as const

function SolutionList({ problem, kind }: { problem: ProblemOut; kind: 'student' | 'correction' }) {
  const items = (problem.solutions ?? []).filter((solution) => solution.kind === kind)
  if (!items.length) {
    return (
      <div className="muted" style={{ fontSize: 13 }}>
        {kind === 'student' ? '没有识别到学生解法' : '没有识别到订正'}
      </div>
    )
  }
  return (
    <div className="stack" style={{ gap: 10 }}>
      {items.map((solution) => (
        <div key={solution.id}>
          <Latex value={solution.latex} block />
          <div className="muted mono" style={{ fontSize: 11 }}>
            置信度 {solution.confidence.toFixed(2)} · {solution.ink_role}
          </div>
        </div>
      ))}
    </div>
  )
}

function Panel({
  title,
  tone,
  badge,
  children,
}: {
  title: string
  tone: keyof typeof TONE_STYLE
  badge?: ReactNode
  children: ReactNode
}) {
  return (
    <section
      style={{
        border: `1px solid ${TONE_STYLE[tone].borderColor}`,
        background: TONE_STYLE[tone].background,
        borderRadius: 'var(--radius)',
        padding: 'var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        minWidth: 0,
      }}
    >
      <div className="row" style={{ gap: 8 }}>
        <strong style={{ fontSize: 13 }}>{title}</strong>
        {badge}
      </div>
      <div style={{ minWidth: 0 }}>{children}</div>
    </section>
  )
}

export default function ProblemDetail() {
  const { problemId } = useParams<{ problemId: string }>()
  const problemQuery = useProblem(problemId)
  const putTags = usePutTags(problemId ?? '')
  const review = useReviewProblem(problemId ?? '')
  const [tagQuery, setTagQuery] = useState('')
  const [tagNotice, setTagNotice] = useState('')
  const [nextDue, setNextDue] = useState<string | null>(null)

  const problem = problemQuery.data
  const tagResults = useTags(
    { status: 'approved', q: tagQuery.trim() },
    tagQuery.trim().length > 0,
  )
  const taxonomyPath = useProblemPath(problemId)

  if (!problemId) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-title">缺少题目 ID</div>
          <div>请从错题本进入详情页。</div>
        </div>
      </div>
    )
  }

  if (problemQuery.isLoading) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-title">加载中…</div>
          <div>正在读取题目详情。</div>
        </div>
      </div>
    )
  }

  if (problemQuery.isError || !problem) {
    const notFound = problemQuery.error instanceof ApiError && problemQuery.error.status === 404
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-title">{notFound ? '题目不存在' : '详情加载失败'}</div>
          <div>
            {notFound
              ? '该题目可能已被删除。'
              : problemQuery.error?.message ?? '请确认后端 8000 已启动。'}
          </div>
          <div className="empty-hint">
            <Link to="/problems">返回错题本</Link>
          </div>
        </div>
      </div>
    )
  }

  const verdict = problem.marks?.[0]?.verdict ?? 'unknown'
  const badge = VERDICT_META[verdict]
  const tags = problem.tags ?? []
  const knowledgeIds = tags.filter((tag) => tag.type === 'knowledge').map((tag) => tag.id)
  const methodIds = tags.filter((tag) => tag.type === 'method').map((tag) => tag.id)
  const existingIds = new Set(tags.map((tag) => tag.id))
  const taxonomyIds = new Set((taxonomyPath.data?.knowledge ?? []).map((topic) => topic.id))

  const saveTags = (knowledge: string[], method: string[]) => {
    setTagNotice('')
    putTags.mutate(
      { knowledge, method },
      { onSuccess: () => setTagNotice('标签已保存') },
    )
  }

  const addTag = (id: string, type: TagType) => {
    if (type === 'knowledge') saveTags([...knowledgeIds, id], methodIds)
    else saveTags(knowledgeIds, [...methodIds, id])
    setTagQuery('')
  }

  const removeTag = (id: string, type: TagType) => {
    if (type === 'knowledge') saveTags(knowledgeIds.filter((item) => item !== id), methodIds)
    else saveTags(knowledgeIds, methodIds.filter((item) => item !== id))
  }

  const submitReview = (grade: number) => {
    setNextDue(null)
    review.mutate(grade, {
      onSuccess: (result) => setNextDue(new Date(result.due_at).toLocaleString('zh-CN')),
    })
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">题目详情</h1>
          <p className="page-desc">
            {SUBJECT_LABEL[problem.subject] ?? problem.subject} · {problem.status === 'confirmed' ? '已入库' : '草稿'} ·{' '}
            {new Date(problem.created_at).toLocaleString('zh-CN')}
          </p>
        </div>
        <div className="page-actions">
          <Link to="/problems" className="btn btn-ghost">
            ← 返回错题本
          </Link>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: 'var(--space-4)',
          alignItems: 'start',
        }}
      >
        <Panel title="题干" tone="stem">
          <Latex value={problem.stem_latex || problem.stem_text} block />
          {(problem.images ?? []).map((image) => (
            <img
              key={image.id}
              src={mediaUrl(image.image_path)}
              alt={image.caption || '题干附图'}
              style={{
                width: '100%',
                marginTop: 10,
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--line)',
              }}
            />
          ))}
        </Panel>

        <Panel
          title="学生错解"
          tone="student"
          badge={
            <span
              style={{
                padding: '2px 10px',
                borderRadius: 999,
                background: badge.bg,
                color: badge.fg,
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              {badge.label}
            </span>
          }
        >
          <SolutionList problem={problem} kind="student" />
        </Panel>

        <Panel title="订正" tone="correction">
          <SolutionList problem={problem} kind="correction" />
        </Panel>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 320px)',
          gap: 'var(--space-4)',
          alignItems: 'start',
        }}
      >
        <Card title="标签" subtitle="搜索 approved 标签添加，点 × 移除">
          <div className="stack">
            <div className="row-wrap" style={{ gap: 6 }}>
              {tags.map((tag) => (
                <Tag
                  key={tag.id}
                  type={tag.type}
                  onRemove={() => removeTag(tag.id, tag.type)}
                  title={tag.type === 'knowledge' ? '知识点' : '方法论'}
                >
                  {taxonomyIds.has(tag.id) ? (
                    <Link
                      to={`/knowledge?topic=${tag.id}`}
                      style={{ color: 'inherit' }}
                      title="在知识图谱中查看"
                    >
                      {tag.name}
                    </Link>
                  ) : (
                    tag.name
                  )}
                </Tag>
              ))}
              {!tags.length && <span className="muted">暂无标签</span>}
            </div>

            <input
              value={tagQuery}
              onChange={(event) => setTagQuery(event.target.value)}
              placeholder="搜索标签名称"
              style={{
                padding: '6px 10px',
                border: '1px solid var(--line-strong)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                color: 'var(--ink)',
                width: 280,
              }}
            />

            {tagQuery.trim() && (
              <div className="row-wrap" style={{ gap: 6 }}>
                {tagResults.isLoading && <span className="muted">搜索中…</span>}
                {!tagResults.isLoading && !(tagResults.data ?? []).length && (
                  <span className="muted">没有匹配的标签</span>
                )}
                {(tagResults.data ?? [])
                  .filter((tag) => !existingIds.has(tag.id))
                  .slice(0, 8)
                  .map((tag) => (
                    <Tag key={tag.id} type={tag.type}>
                      <button
                        type="button"
                        onClick={() => addTag(tag.id, tag.type)}
                        style={{
                          border: 0,
                          background: 'transparent',
                          color: 'inherit',
                          cursor: 'pointer',
                          padding: 0,
                          fontSize: 12,
                        }}
                      >
                        + {tag.name}
                      </button>
                    </Tag>
                  ))}
              </div>
            )}

            {tagNotice && <span className="muted">{tagNotice}</span>}
          </div>
        </Card>

        <Card title="前置知识" subtitle="来自知识图谱的先修关系">
          <div className="stack" style={{ gap: 10 }}>
            {taxonomyPath.isLoading && <span className="muted">加载中…</span>}
            {!taxonomyPath.isLoading && !(taxonomyPath.data?.knowledge ?? []).length && (
              <span className="muted" style={{ fontSize: 12 }}>
                为本题添加已收录的知识点后，这里会展示它的前置知识链。
              </span>
            )}
            {(taxonomyPath.data?.knowledge ?? []).length > 0 && (
              <>
                <div className="row-wrap" style={{ gap: 6 }}>
                  {taxonomyPath.data!.knowledge.map((topic) => (
                    <Link key={topic.id} to={`/knowledge?topic=${topic.id}`} className="tag">
                      {topic.name}
                    </Link>
                  ))}
                </div>
                {taxonomyPath.data!.prerequisites.length > 0 ? (
                  <>
                    <div className="card-sub">
                      全部前置 {taxonomyPath.data!.prerequisites.length} 个（按学段排序）
                    </div>
                    <div className="row-wrap" style={{ gap: 6 }}>
                      {taxonomyPath.data!.prerequisites.slice(0, 12).map((topic) => (
                        <Link
                          key={topic.id}
                          to={`/knowledge?topic=${topic.id}`}
                          className="tag"
                          title={topic.chapter ?? undefined}
                        >
                          {topic.name}
                        </Link>
                      ))}
                      {taxonomyPath.data!.prerequisites.length > 12 && (
                        <span className="muted" style={{ fontSize: 12 }}>
                          +{taxonomyPath.data!.prerequisites.length - 12}
                        </span>
                      )}
                    </div>
                    <Link
                      to={`/knowledge?topic=${taxonomyPath.data!.knowledge[0].id}`}
                      className="muted"
                      style={{ fontSize: 12 }}
                    >
                      在知识图谱中查看完整前置链 →
                    </Link>
                  </>
                ) : (
                  <span className="muted" style={{ fontSize: 12 }}>
                    该知识点无先修依赖。
                  </span>
                )}
              </>
            )}
          </div>
        </Card>

        <Card title="复习" subtitle="记得 / 模糊 / 忘了，自动更新下次到期">
          <div className="stack">
            <div className="row-wrap" style={{ gap: 8 }}>
              {REVIEW_ACTIONS.map((action) => (
                <Button
                  key={action.grade}
                  variant={action.variant}
                  onClick={() => submitReview(action.grade)}
                  disabled={review.isPending}
                >
                  {action.label}
                </Button>
              ))}
            </div>
            {nextDue && (
              <div style={{ color: 'var(--ok)', fontSize: 13 }}>下次到期：{nextDue}</div>
            )}
            {review.isError && (
              <div style={{ color: 'var(--danger)', fontSize: 13 }}>{review.error.message}</div>
            )}
            <span className="muted" style={{ fontSize: 12 }}>
              记得 = 3 天后起算并逐步拉长；忘了 = 重置为 1 天。
            </span>
          </div>
        </Card>
      </div>
    </div>
  )
}
