import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { Tag } from '../ui/Tag'
import Latex from '../components/common/Latex'
import { useProblems, useTags } from '../api/queries/problems'
import type { ProblemOut, Verdict } from '../api/queries/problems'

const SIZE = 12

const SUBJECTS = [
  { value: 'math', label: '数学' },
  { value: 'physics', label: '物理' },
  { value: 'chemistry', label: '化学' },
]

const SUBJECT_LABEL: Record<string, string> = Object.fromEntries(
  SUBJECTS.map((item) => [item.value, item.label]),
)

const VERDICTS: { value: Verdict; label: string }[] = [
  { value: 'right', label: '对' },
  { value: 'wrong', label: '错' },
  { value: 'partial', label: '部分对' },
]

const VERDICT_META: Record<Verdict, { label: string; fg: string; bg: string }> = {
  right: { label: '判定：对', fg: 'var(--ok)', bg: 'var(--ok-soft)' },
  wrong: { label: '判定：错', fg: 'var(--danger)', bg: 'var(--danger-soft)' },
  partial: { label: '判定：部分对', fg: 'var(--warn)', bg: 'var(--warn-soft)' },
  unknown: { label: '判定：未知', fg: 'var(--ink-3)', bg: 'var(--surface-3)' },
}

const DUE_OPTIONS: { value: '' | 'today' | 'overdue'; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'today', label: '今日' },
  { value: 'overdue', label: '逾期' },
]

const FIELD_STYLE = {
  padding: '6px 10px',
  border: '1px solid var(--line-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)',
  color: 'var(--ink)',
} as const

function ProblemCard({ problem }: { problem: ProblemOut }) {
  const verdict = problem.marks?.[0]?.verdict ?? 'unknown'
  const badge = VERDICT_META[verdict]
  const stem = problem.stem_latex || problem.stem_text || ''

  return (
    <Link
      to={`/problems/${problem.id}`}
      className="card"
      style={{
        color: 'inherit',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: 'var(--space-4)',
      }}
    >
      <div className="row" style={{ gap: 8 }}>
        <span
          className="tag"
          style={{ background: 'var(--surface-3)', color: 'var(--ink-2)' }}
        >
          {SUBJECT_LABEL[problem.subject] ?? problem.subject}
        </span>
        <span
          style={{
            padding: '2px 10px',
            borderRadius: 999,
            background: badge.bg,
            color: badge.fg,
            fontSize: 11,
            fontWeight: 700,
            whiteSpace: 'nowrap',
          }}
        >
          {badge.label}
        </span>
        <span className="grow" />
        <span className="muted" style={{ fontSize: 11 }}>
          {new Date(problem.created_at).toLocaleDateString('zh-CN')}
        </span>
      </div>

      <div style={{ maxHeight: '4.8em', overflow: 'hidden', lineHeight: 1.6 }}>
        {stem ? (
          <Latex value={stem} block />
        ) : (
          <span className="muted">（无题干文本）</span>
        )}
      </div>

      <div className="row-wrap" style={{ gap: 6 }}>
        {(problem.tags ?? []).map((tag) => (
          <Tag key={tag.id} type={tag.type}>
            {tag.name}
          </Tag>
        ))}
        {!(problem.tags ?? []).length && (
          <span className="muted" style={{ fontSize: 12 }}>
            暂无标签
          </span>
        )}
      </div>
    </Link>
  )
}

export default function WrongBook() {
  const [subject, setSubject] = useState('')
  const [knowledgeTagId, setKnowledgeTagId] = useState('')
  const [methodTagId, setMethodTagId] = useState('')
  const [verdict, setVerdict] = useState<Verdict | ''>('')
  const [due, setDue] = useState<'' | 'today' | 'overdue'>('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)

  const knowledgeTags = useTags({ type: 'knowledge', status: 'approved' })
  const methodTags = useTags({ type: 'method', status: 'approved' })

  const tagIds = [knowledgeTagId, methodTagId].filter(Boolean)
  const params = useMemo(
    () => ({
      subject: subject || undefined,
      tagIds: tagIds.length ? tagIds : undefined,
      verdict: verdict || undefined,
      due: due || undefined,
      q: q.trim() || undefined,
      page,
      size: SIZE,
    }),
    // tagIds 由两个标量派生，直接展开避免数组引用抖动
    [subject, knowledgeTagId, methodTagId, verdict, due, q, page],
  )

  const problems = useProblems(params)
  const items = problems.data?.items ?? []
  const total = problems.data?.total ?? 0
  const maxPage = Math.max(1, Math.ceil(total / SIZE))
  const hasFilters = Boolean(subject || tagIds.length || verdict || due || q.trim())

  const resetPage = () => setPage(1)

  const clearFilters = () => {
    setSubject('')
    setKnowledgeTagId('')
    setMethodTagId('')
    setVerdict('')
    setDue('')
    setQ('')
    resetPage()
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">错题本</h1>
          <p className="page-desc">按学科、知识点、方法论、判定与到期筛选，点卡片进入详情。</p>
        </div>
        <div className="page-actions">
          <Link to="/stats" className="btn btn-secondary">
            看统计
          </Link>
          <Link to="/upload" className="btn btn-primary">
            上传作业
          </Link>
        </div>
      </div>

      <Card title="筛选" subtitle={`共 ${total} 题`}>
        <div className="stack">
          <div className="row-wrap" style={{ gap: 8 }}>
            <span className="muted" style={{ fontSize: 12 }}>
              学科
            </span>
            <Chip active={!subject} onClick={() => { setSubject(''); resetPage() }}>
              全部
            </Chip>
            {SUBJECTS.map((item) => (
              <Chip
                key={item.value}
                active={subject === item.value}
                onClick={() => {
                  setSubject(subject === item.value ? '' : item.value)
                  resetPage()
                }}
              >
                {item.label}
              </Chip>
            ))}
          </div>

          <div className="row-wrap" style={{ gap: 8 }}>
            <select
              value={knowledgeTagId}
              onChange={(event) => {
                setKnowledgeTagId(event.target.value)
                resetPage()
              }}
              style={FIELD_STYLE}
              aria-label="知识点"
            >
              <option value="">全部知识点</option>
              {(knowledgeTags.data ?? []).map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>

            <select
              value={methodTagId}
              onChange={(event) => {
                setMethodTagId(event.target.value)
                resetPage()
              }}
              style={FIELD_STYLE}
              aria-label="方法论"
            >
              <option value="">全部方法论</option>
              {(methodTags.data ?? []).map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>

            <span className="grow" />

            <span className="muted" style={{ fontSize: 12 }}>
              判定
            </span>
            <Chip active={!verdict} onClick={() => { setVerdict(''); resetPage() }}>
              全部
            </Chip>
            {VERDICTS.map((item) => (
              <Chip
                key={item.value}
                active={verdict === item.value}
                onClick={() => {
                  setVerdict(verdict === item.value ? '' : item.value)
                  resetPage()
                }}
              >
                {item.label}
              </Chip>
            ))}
          </div>

          <div className="row-wrap" style={{ gap: 8 }}>
            <span className="muted" style={{ fontSize: 12 }}>
              到期
            </span>
            {DUE_OPTIONS.map((item) => (
              <Chip
                key={item.value || 'all'}
                active={due === item.value}
                onClick={() => {
                  setDue(item.value)
                  resetPage()
                }}
              >
                {item.label}
              </Chip>
            ))}
            <span className="grow" />
            <input
              value={q}
              onChange={(event) => {
                setQ(event.target.value)
                resetPage()
              }}
              placeholder="搜索题干关键词"
              style={{ ...FIELD_STYLE, width: 240 }}
            />
            {hasFilters && (
              <Button size="sm" variant="ghost" onClick={clearFilters}>
                清除筛选
              </Button>
            )}
          </div>
        </div>
      </Card>

      {problems.isLoading ? (
        <div className="empty">
          <div className="empty-title">加载中…</div>
          <div>正在读取错题列表。</div>
        </div>
      ) : problems.isError ? (
        <div className="empty">
          <div className="empty-title">列表加载失败</div>
          <div>{problems.error.message}</div>
          <div className="empty-hint">请确认后端 8000 已启动。</div>
        </div>
      ) : !items.length ? (
        <div className="empty">
          <div className="empty-title">{hasFilters ? '没有匹配的错题' : '错题本还是空的'}</div>
          <div>
            {hasFilters
              ? '换个筛选条件试试，或清除筛选查看全部。'
              : '在校对台点“确认入库”后，题目会出现在这里。'}
          </div>
          <div className="row-wrap" style={{ justifyContent: 'center', gap: 8, marginTop: 12 }}>
            {hasFilters ? (
              <Button size="sm" onClick={clearFilters}>
                清除筛选
              </Button>
            ) : (
              <Link to="/upload" className="btn btn-primary btn-sm">
                去上传作业
              </Link>
            )}
          </div>
          <div className="empty-hint">下一步：进入详情看错解 / 订正，并按记得 / 模糊 / 忘了复习。</div>
        </div>
      ) : (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
              gap: 'var(--space-4)',
            }}
          >
            {items.map((problem) => (
              <ProblemCard key={problem.id} problem={problem} />
            ))}
          </div>

          <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
            <span className="muted" style={{ fontSize: 12 }}>
              第 {page} / {maxPage} 页 · 共 {total} 题
            </span>
            <Button size="sm" onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={page <= 1}>
              上一页
            </Button>
            <Button
              size="sm"
              onClick={() => setPage((prev) => Math.min(maxPage, prev + 1))}
              disabled={page >= maxPage}
            >
              下一页
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
