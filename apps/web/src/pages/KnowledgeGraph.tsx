import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { useTaxonomySummary, useTaxonomyTopic, useTaxonomyTopics } from '../api/queries/taxonomy'
import type { TaxonomyDetail, TaxonomyTopic } from '../api/queries/taxonomy'

const CN_NUM = ['一', '二', '三', '四', '五', '六', '七', '八', '九']

const SUBJECT_LABELS: Record<string, string> = {
  math: '数学',
  chinese: '语文',
  english: '英语',
  physics: '物理',
  chemistry: '化学',
  biology: '生物',
  history: '历史',
  geography: '地理',
  politics: '政治',
  morality: '道德与法治',
  science: '科学',
}

const TYPE_LABEL: Record<string, string> = {
  conceptual: '概念',
  procedural: '程序性',
  representational: '表征',
  strategic: '策略',
}

const BOOK_RE =
  /^(选择性必修[一二三四五六七八九十\d]*|选必[一二三四五六七八九十\d]*|必修第?[一二三四五六七八九十\d]*册?)\s*/

function bookOf(chapter: string | null): string | null {
  if (!chapter) return null
  const match = chapter.match(BOOK_RE)
  return match ? match[1] : null
}

function gradeLabel(grade: number | null, book?: string | null): string {
  if (grade == null) return '未分级'
  if (grade <= 9) return `${CN_NUM[grade - 1] ?? grade}年级`
  return book || `高中 G${grade}`
}

function TopicDetail({ topic, onPick }: { topic: TaxonomyDetail; onPick: (id: string) => void }) {
  const [showAnswer, setShowAnswer] = useState(false)
  const [showAllAncestors, setShowAllAncestors] = useState(false)
  const diagnostic = topic.diagnostic_question
  const ancestors = showAllAncestors ? topic.ancestors : topic.ancestors.slice(0, 12)

  return (
    <Card
      title={topic.name}
      subtitle={`${SUBJECT_LABELS[topic.subject ?? ''] ?? topic.subject ?? ''} · ${gradeLabel(
        topic.grade,
        bookOf(topic.chapter),
      )}${topic.semester ? ` · ${topic.semester}` : ''}${topic.chapter ? ` · ${topic.chapter}` : ''}`}
    >
      <div className="stack" style={{ gap: 18 }}>
        <div className="row-wrap" style={{ gap: 6 }}>
          {topic.subject && <Chip>{SUBJECT_LABELS[topic.subject] ?? topic.subject}</Chip>}
          {topic.domain && <Chip>{topic.domain}</Chip>}
          {topic.topic_type && <Chip>{TYPE_LABEL[topic.topic_type] ?? topic.topic_type}</Chip>}
          <Chip title={topic.external_id}>{topic.external_id}</Chip>
        </div>

        {topic.description && <p style={{ margin: 0, color: 'var(--ink-2)' }}>{topic.description}</p>}

        {topic.mastery_criteria.length > 0 && (
          <section>
            <div className="card-sub" style={{ marginBottom: 6 }}>
              掌握标准
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)', fontSize: 13 }}>
              {topic.mastery_criteria.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        {diagnostic?.question && (
          <section
            style={{
              border: '1px solid var(--line)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--surface-2)',
              padding: 'var(--space-4)',
            }}
          >
            <div className="card-sub" style={{ marginBottom: 6 }}>
              诊断题
            </div>
            <div style={{ fontSize: 13 }}>{diagnostic.question}</div>
            {diagnostic.answer && (
              <div style={{ marginTop: 8 }}>
                {showAnswer ? (
                  <div style={{ color: 'var(--ok)', fontSize: 13 }}>答案：{diagnostic.answer}</div>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setShowAnswer(true)}
                  >
                    显示答案
                  </button>
                )}
              </div>
            )}
          </section>
        )}

        <section>
          <div className="card-sub" style={{ marginBottom: 6 }}>
            直接先修（{topic.prerequisites.length}）
          </div>
          {topic.prerequisites.length ? (
            <div className="row-wrap" style={{ gap: 6 }}>
              {topic.prerequisites.map((item) => (
                <Chip key={item.id} onClick={() => onPick(item.id)} title={item.reason || undefined}>
                  {item.name}
                  <span className="muted" style={{ fontSize: 11 }}>
                    {item.strength === 'hard' ? '强' : '弱'}
                  </span>
                </Chip>
              ))}
            </div>
          ) : (
            <span className="muted" style={{ fontSize: 13 }}>
              无先修依赖（起点知识点）
            </span>
          )}
        </section>

        <section>
          <div className="card-sub" style={{ marginBottom: 6 }}>
            后继知识点（{topic.dependents.length}）
          </div>
          {topic.dependents.length ? (
            <div className="row-wrap" style={{ gap: 6 }}>
              {topic.dependents.map((item) => (
                <Chip key={item.id} onClick={() => onPick(item.id)}>
                  {item.name}
                </Chip>
              ))}
            </div>
          ) : (
            <span className="muted" style={{ fontSize: 13 }}>
              暂无后继
            </span>
          )}
        </section>

        {topic.ancestors.length > 0 && (
          <section>
            <div className="card-sub" style={{ marginBottom: 6 }}>
              完整前置链（{topic.ancestors.length}）
            </div>
            <div className="row-wrap" style={{ gap: 6 }}>
              {ancestors.map((item) => (
                <Chip key={item.id} onClick={() => onPick(item.id)} title={item.chapter ?? undefined}>
                  {item.name}
                </Chip>
              ))}
              {topic.ancestors.length > ancestors.length && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setShowAllAncestors(true)}
                >
                  展开全部
                </button>
              )}
            </div>
          </section>
        )}
      </div>
    </Card>
  )
}

export default function KnowledgeGraph() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('topic') ?? undefined
  const [q, setQ] = useState('')
  const [subject, setSubject] = useState('math')
  const [domain, setDomain] = useState('')
  const [grade, setGrade] = useState('')

  const summary = useTaxonomySummary()
  const topics = useTaxonomyTopics({})
  const detail = useTaxonomyTopic(selectedId)

  const pick = (id: string) => setSearchParams({ topic: id })

  // 从题目详情等外部入口跳进来时，自动切到该知识点所属学科
  useEffect(() => {
    if (detail.data?.subject && detail.data.subject !== subject) {
      setSubject(detail.data.subject)
      setDomain('')
      setGrade('')
    }
  }, [detail.data?.subject])

  const subjectTopics = useMemo(
    () => (topics.data ?? []).filter((topic) => !subject || topic.subject === subject),
    [topics.data, subject],
  )

  const subjectFacets = useMemo(() => {
    const map = new Map<string, number>()
    for (const topic of topics.data ?? []) {
      if (!topic.subject) continue
      map.set(topic.subject, (map.get(topic.subject) ?? 0) + 1)
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1])
  }, [topics.data])

  const domainFacets = useMemo(() => {
    const map = new Map<string, number>()
    for (const topic of subjectTopics) {
      if (!topic.domain) continue
      map.set(topic.domain, (map.get(topic.domain) ?? 0) + 1)
    }
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1])
  }, [subjectTopics])

  const gradeFacets = useMemo(() => {
    const map = new Map<number, { count: number; book: string | null }>()
    for (const topic of subjectTopics) {
      if (topic.grade == null) continue
      const entry = map.get(topic.grade)
      if (entry) entry.count += 1
      else map.set(topic.grade, { count: 1, book: bookOf(topic.chapter) })
    }
    return Array.from(map.entries()).sort((a, b) => a[0] - b[0])
  }, [subjectTopics])

  const filtered = useMemo(() => {
    const keyword = q.trim()
    const gradeNum = grade ? Number(grade) : null
    return subjectTopics.filter((topic) => {
      if (domain && topic.domain !== domain) return false
      if (gradeNum !== null && topic.grade !== gradeNum) return false
      if (!keyword) return true
      return `${topic.name} ${topic.chapter ?? ''}`.includes(keyword)
    })
  }, [subjectTopics, q, domain, grade])

  const groups = useMemo(() => {
    const map = new Map<string, TaxonomyTopic[]>()
    for (const topic of filtered) {
      const book = topic.grade != null && topic.grade >= 10 ? bookOf(topic.chapter) : null
      const chapter = book ? (topic.chapter ?? '').replace(BOOK_RE, '') : topic.chapter ?? '未分章'
      const key = `${gradeLabel(topic.grade, book)}|${chapter}`
      const list = map.get(key)
      if (list) list.push(topic)
      else map.set(key, [topic])
    }
    return Array.from(map.entries())
  }, [filtered])

  const meta = summary.data

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">知识图谱</h1>
          <p className="page-desc">
            {meta
              ? `${meta.topics} 个知识点 · ${meta.edges} 条先修关系 · ${meta.subjects.length} 个学科 · 来源 cn-math-taxonomy（${meta.license}）`
              : '按学科、学段、章节浏览知识点与先修关系'}
          </p>
        </div>
        {meta?.source && (
          <div className="page-actions">
            <a className="btn btn-secondary btn-sm" href={meta.source} target="_blank" rel="noreferrer">
              数据来源
            </a>
          </div>
        )}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 420px) minmax(0, 1fr)',
          gap: 'var(--space-4)',
          alignItems: 'start',
        }}
      >
        <Card
          title="知识点"
          subtitle={
            topics.isLoading
              ? '加载中…'
              : `${SUBJECT_LABELS[subject] ?? '全部'} ${filtered.length} / 全部 ${topics.data?.length ?? 0}`
          }
        >
          <div className="stack" style={{ gap: 10 }}>
            <div className="row-wrap" style={{ gap: 6 }}>
              {(subjectFacets.length
                ? subjectFacets
                : Object.keys(SUBJECT_LABELS).map((key) => [key, 0] as [string, number])
              ).map(
                ([key, count]) => (
                  <Chip
                    key={key}
                    active={subject === key}
                    onClick={() => {
                      setSubject(key)
                      setDomain('')
                      setGrade('')
                    }}
                  >
                    {SUBJECT_LABELS[key] ?? key}
                    {count > 0 && <span className="muted"> {count}</span>}
                  </Chip>
                ),
              )}
            </div>

            <input
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="搜索名称 / 章节"
              style={{
                padding: '6px 10px',
                border: '1px solid var(--line-strong)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                color: 'var(--ink)',
                width: '100%',
              }}
            />

            <div className="row-wrap" style={{ gap: 6 }}>
              <Chip active={!domain} onClick={() => setDomain('')}>
                全部领域
              </Chip>
              {domainFacets.map(([value, count]) => (
                <Chip
                  key={value}
                  active={domain === value}
                  onClick={() => setDomain(domain === value ? '' : value)}
                >
                  {value} {count}
                </Chip>
              ))}
            </div>

            <select
              value={grade}
              onChange={(event) => setGrade(event.target.value)}
              style={{
                padding: '6px 10px',
                border: '1px solid var(--line-strong)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                color: 'var(--ink)',
                width: 200,
              }}
            >
              <option value="">全部学段</option>
              {gradeFacets.map(([value, info]) => (
                <option key={value} value={value}>
                  {gradeLabel(value, info.book)}（{info.count}）
                </option>
              ))}
            </select>

            <div style={{ maxHeight: 'calc(100vh - 420px)', minHeight: 340, overflow: 'auto' }}>
              {topics.isLoading && <div className="muted">正在载入知识图谱…</div>}
              {!topics.isLoading && !filtered.length && (
                <div className="muted">没有匹配的知识点。</div>
              )}
              {groups.map(([key, list]) => {
                const [gradeText, chapter] = key.split('|')
                return (
                  <div key={key}>
                    <div
                      style={{
                        position: 'sticky',
                        top: 0,
                        zIndex: 1,
                        background: 'var(--surface)',
                        padding: '8px 0 4px',
                        fontSize: 12,
                        color: 'var(--ink-3)',
                      }}
                    >
                      {gradeText} · {chapter}
                    </div>
                    {list.map((topic) => {
                      const active = topic.id === selectedId
                      return (
                        <button
                          key={topic.id}
                          type="button"
                          onClick={() => pick(topic.id)}
                          style={{
                            display: 'block',
                            width: '100%',
                            textAlign: 'left',
                            border: 0,
                            borderRadius: 'var(--radius-sm)',
                            background: active ? 'var(--accent-soft)' : 'transparent',
                            color: active ? 'var(--accent-ink)' : 'var(--ink)',
                            padding: '5px 8px',
                            fontSize: 13,
                            cursor: 'pointer',
                          }}
                          title={topic.chapter ?? topic.name}
                        >
                          {topic.name}
                        </button>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </div>
        </Card>

        <div className="stack" style={{ gap: 'var(--space-4)' }}>
          {!selectedId && (
            <div className="empty">
              <div className="empty-title">选择一个知识点</div>
              <div>左侧按学科、学段与章节浏览；也可以从题目详情的知识点直接跳进来。</div>
              <div className="empty-hint">节点详情包含掌握标准、诊断题、先修与后继知识点。</div>
            </div>
          )}

          {selectedId && detail.isLoading && (
            <div className="empty">
              <div className="empty-title">加载中…</div>
            </div>
          )}

          {selectedId && detail.isError && (
            <div className="empty">
              <div className="empty-title">该知识点不在图谱中</div>
              <div>可能来自手工标签或种子词表，尚未关联到 cn-math-taxonomy。</div>
              <div className="empty-hint">
                返回 <Link to="/knowledge">图谱列表</Link> 重新选择。
              </div>
            </div>
          )}

          {detail.data && <TopicDetail key={detail.data.id} topic={detail.data} onPick={pick} />}
        </div>
      </div>
    </div>
  )
}
