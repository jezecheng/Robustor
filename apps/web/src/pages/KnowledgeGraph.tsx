import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Chip } from '../ui/Chip'
import GraphCanvas, { type GraphCanvasHandle } from '../components/knowledge/GraphCanvas'
import {
  useTaxonomyGraph,
  useTaxonomySummary,
  useTaxonomyTopic,
  useTaxonomyTopics,
} from '../api/queries/taxonomy'
import type {
  TaxonomyDetail,
  TaxonomyGraphParams,
  TaxonomyTopic,
} from '../api/queries/taxonomy'

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

const TYPE_LEGEND = [
  { type: 'conceptual', label: '概念', color: '#2f5bd7' },
  { type: 'procedural', label: '程序性', color: '#0e8f7e' },
  { type: 'representational', label: '表征', color: '#7c3aed' },
  { type: 'strategic', label: '策略', color: '#c27c0e' },
  { type: 'other', label: '其他', color: '#8a8378' },
]

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

function chapterLabel(grade: number | null, chapter: string | null): string {
  const book = bookOf(chapter)
  if (book && chapter) return chapter.replace(BOOK_RE, '')
  if (chapter) return chapter
  return gradeLabel(grade)
}

function TopicDetail({ topic, onPick }: { topic: TaxonomyDetail; onPick: (id: string) => void }) {
  const [showAnswer, setShowAnswer] = useState(false)
  const [showAllAncestors, setShowAllAncestors] = useState(false)
  const diagnostic = topic.diagnostic_question
  const ancestors = showAllAncestors ? topic.ancestors : topic.ancestors.slice(0, 12)

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div>
        <div className="kg-node-name">{topic.name}</div>
        <div className="kg-node-sub">
          {SUBJECT_LABELS[topic.subject ?? ''] ?? topic.subject ?? '未分类'} ·{' '}
          {gradeLabel(topic.grade, bookOf(topic.chapter))}
          {topic.semester ? ` · ${topic.semester}` : ''}
        </div>
      </div>

      <div className="row-wrap" style={{ gap: 6 }}>
        {topic.subject && <Chip>{SUBJECT_LABELS[topic.subject] ?? topic.subject}</Chip>}
        {topic.domain && <Chip>{topic.domain}</Chip>}
        {topic.topic_type && <Chip>{TYPE_LABEL[topic.topic_type] ?? topic.topic_type}</Chip>}
        <Chip title={topic.external_id}>{topic.external_id}</Chip>
      </div>

      {topic.chapter && (
        <div className="kg-node-chapter" title={topic.chapter}>
          {topic.chapter}
        </div>
      )}

      {topic.description && (
        <section>
          <div className="kg-detail-title">知识点说明</div>
          <p style={{ margin: 0, color: 'var(--ink-2)', fontSize: 13 }}>{topic.description}</p>
        </section>
      )}

      {topic.mastery_criteria.length > 0 && (
        <section>
          <div className="kg-detail-title">掌握标准</div>
          <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-2)', fontSize: 13 }}>
            {topic.mastery_criteria.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {diagnostic?.question && (
        <section className="kg-diagnostic">
          <div className="kg-detail-title">诊断题</div>
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
        <div className="kg-detail-title">直接先修（{topic.prerequisites.length}）</div>
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
        <div className="kg-detail-title">后继知识点（{topic.dependents.length}）</div>
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
          <div className="kg-detail-title">完整前置链（{topic.ancestors.length}）</div>
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
  )
}

export default function KnowledgeGraph() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('topic') ?? undefined
  const [subject, setSubject] = useState('math')
  const [domain, setDomain] = useState('')
  const [grade, setGrade] = useState('')
  const [chapter, setChapter] = useState('')
  const [q, setQ] = useState('')
  const [view, setView] = useState<'graph' | 'tree'>('graph')
  const [mode, setMode] = useState<'full' | 'local'>('full')
  const [toolSearch, setToolSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [openChapters, setOpenChapters] = useState<Record<string, boolean>>({})
  const canvasRef = useRef<GraphCanvasHandle | null>(null)

  const summary = useTaxonomySummary()
  const topics = useTaxonomyTopics({})
  const detail = useTaxonomyTopic(selectedId)

  const pick = (id: string) => setSearchParams({ topic: id })

  const jump = (topic: TaxonomyTopic) => {
    if (topic.subject && topic.subject !== subject) {
      setSubject(topic.subject)
      setDomain('')
      setGrade('')
      setChapter('')
    }
    pick(topic.id)
    setToolSearch(topic.name)
    setSearchOpen(false)
  }

  // 从题目详情等外部入口跳进来时，自动切到该知识点所属学科
  useEffect(() => {
    if (detail.data?.subject && detail.data.subject !== subject) {
      setSubject(detail.data.subject)
      setDomain('')
      setGrade('')
      setChapter('')
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

  const scopedTopics = useMemo(() => {
    const gradeNum = grade ? Number(grade) : null
    return subjectTopics.filter((topic) => {
      if (domain && topic.domain !== domain) return false
      if (gradeNum !== null && topic.grade !== gradeNum) return false
      return true
    })
  }, [subjectTopics, domain, grade])

  const chapters = useMemo(() => {
    const map = new Map<string, { chapter: string; grade: number | null; count: number }>()
    for (const topic of scopedTopics) {
      if (!topic.chapter) continue
      const entry = map.get(topic.chapter)
      if (entry) entry.count += 1
      else map.set(topic.chapter, { chapter: topic.chapter, grade: topic.grade, count: 1 })
    }
    return Array.from(map.values()).sort(
      (a, b) => (a.grade ?? 99) - (b.grade ?? 99) || a.chapter.localeCompare(b.chapter, 'zh-CN'),
    )
  }, [scopedTopics])

  const filtered = useMemo(() => {
    const keyword = q.trim()
    return scopedTopics.filter((topic) => {
      if (chapter && topic.chapter !== chapter) return false
      if (!keyword) return true
      return `${topic.name} ${topic.chapter ?? ''}`.includes(keyword)
    })
  }, [scopedTopics, chapter, q])

  const treeGroups = useMemo(() => {
    const map = new Map<string, TaxonomyTopic[]>()
    for (const topic of filtered) {
      const book = topic.grade != null && topic.grade >= 10 ? bookOf(topic.chapter) : null
      const label = `${gradeLabel(topic.grade, book)} · ${chapterLabel(topic.grade, topic.chapter)}`
      const list = map.get(label)
      if (list) list.push(topic)
      else map.set(label, [topic])
    }
    return Array.from(map.entries())
  }, [filtered])

  const graphParams = useMemo<TaxonomyGraphParams | undefined>(() => {
    if (mode === 'local') {
      return selectedId ? { focus: selectedId, depth: 1 } : undefined
    }
    return {
      subject: subject || undefined,
      domain: domain || undefined,
      grade: grade ? Number(grade) : undefined,
      chapter: chapter || undefined,
      q: q.trim() || undefined,
      limit: 160,
    }
  }, [mode, selectedId, subject, domain, grade, chapter, q])

  const graph = useTaxonomyGraph(graphParams)

  const suggestions = useMemo(() => {
    const keyword = toolSearch.trim()
    if (!keyword) return []
    return (topics.data ?? [])
      .filter((topic) => topic.name.includes(keyword))
      .slice(0, 8)
  }, [topics.data, toolSearch])

  const meta = summary.data
  const graphNodes = graph.data?.nodes ?? []
  const graphEdges = graph.data?.edges ?? []
  const localTitle = detail.data?.name ?? '主干视图'
  const canvasTitle =
    mode === 'local'
      ? selectedId
        ? localTitle
        : '主干视图'
      : `${SUBJECT_LABELS[subject] ?? '全部'} · ${chapter || '图谱总览'}`
  const canvasMeta =
    mode === 'local'
      ? selectedId
        ? `直接先修 ${detail.data?.prerequisites.length ?? 0} · 后继 ${
            detail.data?.dependents.length ?? 0
          } · 邻域 ${graphNodes.length} 个知识点`
        : '先在图中或左侧选择一个知识点'
      : graph.data
        ? `${graphNodes.length} 个知识点 · ${graphEdges.length} 条先修关系${
            graph.data.truncated ? `（共 ${graph.data.total} 个，已截断）` : ''
          }`
        : '正在加载图谱数据…'

  const handleSelect = (id: string) => {
    const topic = (topics.data ?? []).find((item) => item.id === id)
    if (topic) jump(topic)
    else pick(id)
  }

  return (
    <div className="kg-layout">
      <aside className="kg-panel kg-side">
        <div className="kg-side-head">
          <div className="kg-eyebrow">KNOWLEDGE GRAPH</div>
          <h1>图谱浏览</h1>
          <p>按学科、学段与章节浏览知识结构</p>
        </div>

        <div className="kg-side-body">
          <div className="kg-section">
            <div className="kg-section-title">
              学科 <span className="kg-count">{subjectFacets.length} 个</span>
            </div>
            <div className="kg-tree-list">
              {(subjectFacets.length
                ? subjectFacets
                : Object.keys(SUBJECT_LABELS).map((key) => [key, 0] as [string, number])
              ).map(([key, count]) => (
                <button
                  key={key}
                  type="button"
                  className={`kg-tree-item${subject === key ? ' active' : ''}`}
                  onClick={() => {
                    setSubject(key)
                    setDomain('')
                    setGrade('')
                    setChapter('')
                  }}
                >
                  <span className="kg-tree-dot" />
                  <span className="kg-tree-label">{SUBJECT_LABELS[key] ?? key}</span>
                  <span className="kg-count">{count}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="kg-section">
            <div className="kg-section-title">筛选</div>
            <div className="kg-filter">
              <input
                value={q}
                onChange={(event) => setQ(event.target.value)}
                placeholder="搜索知识点 / 章节"
                className="kg-input"
              />
              <select
                value={grade}
                onChange={(event) => {
                  setGrade(event.target.value)
                  setChapter('')
                }}
                className="kg-select"
              >
                <option value="">全部学段</option>
                {gradeFacets.map(([value, info]) => (
                  <option key={value} value={value}>
                    {gradeLabel(value, info.book)}（{info.count}）
                  </option>
                ))}
              </select>
              <select
                value={domain}
                onChange={(event) => {
                  setDomain(event.target.value)
                  setChapter('')
                }}
                className="kg-select"
              >
                <option value="">全部领域</option>
                {domainFacets.map(([value, count]) => (
                  <option key={value} value={value}>
                    {value}（{count}）
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="kg-section">
            <div className="kg-section-title">
              章节 <span className="kg-count">{chapters.length} 个</span>
            </div>
            <div className="kg-tree-list">
              <button
                type="button"
                className={`kg-tree-item${chapter ? '' : ' active'}`}
                onClick={() => setChapter('')}
              >
                <span className="kg-tree-label">全部章节</span>
                <span className="kg-count">{scopedTopics.length}</span>
              </button>
              {chapters.map((item) => (
                <button
                  key={item.chapter}
                  type="button"
                  className={`kg-tree-item${chapter === item.chapter ? ' active' : ''}`}
                  title={item.chapter}
                  onClick={() => setChapter(chapter === item.chapter ? '' : item.chapter)}
                >
                  <span className="kg-tree-label">{chapterLabel(item.grade, item.chapter)}</span>
                  <span className="kg-count">{item.count}</span>
                </button>
              ))}
              {!chapters.length && <div className="kg-count kg-empty-row">没有匹配的章节</div>}
            </div>
          </div>
        </div>

        <div className="kg-side-foot">
          <div>
            {filtered.length} / {scopedTopics.length} 个知识点 · {meta?.edges ?? 0} 条先修关系
          </div>
          <div>
            {meta ? `来源 cn-math-taxonomy（${meta.license}）` : '正在载入数据…'}
            {meta?.source && (
              <>
                {' · '}
                <a href={meta.source} target="_blank" rel="noreferrer">
                  数据来源
                </a>
              </>
            )}
          </div>
        </div>
      </aside>

      <section className="kg-panel kg-workspace">
        <div className="kg-toolbar">
          <div className="kg-toolbar-left">
            <div className="kg-view-toggle">
              <button
                type="button"
                className={`kg-view-btn${view === 'graph' ? ' active' : ''}`}
                onClick={() => setView('graph')}
              >
                图谱视图
              </button>
              <button
                type="button"
                className={`kg-view-btn${view === 'tree' ? ' active' : ''}`}
                onClick={() => setView('tree')}
              >
                树形视图
              </button>
            </div>
            <div className="kg-toolbar-search">
              <input
                value={toolSearch}
                onChange={(event) => {
                  setToolSearch(event.target.value)
                  setSearchOpen(true)
                }}
                onFocus={() => setSearchOpen(true)}
                onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
                placeholder="快速定位知识点"
                className="kg-input"
              />
              {searchOpen && suggestions.length > 0 && (
                <div className="kg-search-results">
                  {suggestions.map((topic) => (
                    <button
                      key={topic.id}
                      type="button"
                      className="kg-search-item"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => jump(topic)}
                    >
                      <strong>{topic.name}</strong>
                      <span>
                        {SUBJECT_LABELS[topic.subject ?? ''] ?? topic.subject ?? ''} ·{' '}
                        {gradeLabel(topic.grade, bookOf(topic.chapter))}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <span className="kg-count">
              {mode === 'local'
                ? `${graphNodes.length} 节点 / ${graphEdges.length} 关系`
                : graph.data
                  ? `${graphNodes.length} 节点 / ${graphEdges.length} 关系`
                  : '加载中…'}
            </span>
          </div>

          <div className="kg-toolbar-right">
            <button
              type="button"
              className={`kg-tool-btn${mode === 'local' ? ' active' : ''}`}
              onClick={() => setMode('local')}
            >
              主干视图
            </button>
            <button
              type="button"
              className={`kg-tool-btn${mode === 'full' ? ' active' : ''}`}
              onClick={() => setMode('full')}
            >
              完整视图
            </button>
            <div className="kg-zoom">
              <button
                type="button"
                className="kg-tool-btn"
                title="缩小"
                onClick={() => canvasRef.current?.zoomOut()}
              >
                −
              </button>
              <button
                type="button"
                className="kg-tool-btn"
                title="放大"
                onClick={() => canvasRef.current?.zoomIn()}
              >
                +
              </button>
              <button
                type="button"
                className="kg-tool-btn"
                title="重置视图"
                onClick={() => canvasRef.current?.reset()}
              >
                ↻
              </button>
            </div>
          </div>
        </div>

        <div className="kg-canvas-wrap">
          <div className="kg-canvas-title">
            <strong>{canvasTitle}</strong>
            <span>{canvasMeta}</span>
          </div>

          {view === 'graph' ? (
            <GraphCanvas
              ref={canvasRef}
              nodes={graphNodes}
              edges={graphEdges}
              selectedId={selectedId}
              onSelect={handleSelect}
            />
          ) : (
            <div className="kg-tree-stage">
              <div className="kg-tree-book">
                <div className="kg-tree-book-title">
                  {SUBJECT_LABELS[subject] ?? '全部'} · 知识结构
                </div>
                {treeGroups.map(([key, list], index) => {
                  const containsSelected = Boolean(selectedId && list.some((t) => t.id === selectedId))
                  const open = openChapters[key] ?? (containsSelected || (index < 2 && !selectedId))
                  return (
                    <div key={key} className="kg-tree-group">
                      <button
                        type="button"
                        className="kg-tree-group-head"
                        onClick={() =>
                          setOpenChapters((current) => ({ ...current, [key]: !open }))
                        }
                      >
                        <span className={`kg-chevron${open ? ' open' : ''}`}>▹</span>
                        <span className="kg-tree-group-name">{key}</span>
                        <span className="kg-count">{list.length}</span>
                      </button>
                      {open && (
                        <div className="kg-tree-leaves">
                          {list.map((topic) => (
                            <button
                              key={topic.id}
                              type="button"
                              className={`kg-leaf${topic.id === selectedId ? ' active' : ''}`}
                              title={topic.chapter ?? topic.name}
                              onClick={() => jump(topic)}
                            >
                              {topic.name}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
                {!treeGroups.length && <div className="kg-tree-empty">没有匹配的知识点</div>}
              </div>
            </div>
          )}

          {view === 'graph' && (
            <>
              <div className="kg-legend">
                {TYPE_LEGEND.map((item) => (
                  <span key={item.type}>
                    <i style={{ background: item.color }} />
                    {item.label}
                  </span>
                ))}
                <span className="kg-legend-links">
                  <i className="kg-legend-line" />
                  强先修
                  <i className="kg-legend-line dashed" />
                  弱先修
                </span>
              </div>
              {!graphNodes.length && (
                <div className="kg-canvas-empty">
                  {mode === 'local' && !selectedId
                    ? '请选择一个知识点查看其主干关系'
                    : graph.isLoading
                      ? '正在载入图谱…'
                      : graph.isError
                        ? '图谱数据加载失败，请稍后重试'
                        : '没有符合当前条件的节点'}
                </div>
              )}
            </>
          )}

          <div className="kg-hint">
            {view === 'graph' ? '单击节点查看详情 · 拖动平移 · 滚轮缩放' : '展开章节查看知识点 · 单击选中'}
          </div>
        </div>
      </section>

      <aside className="kg-panel kg-details">
        <div className="kg-details-head">
          <div className="kg-eyebrow">NODE DETAILS</div>
          <h2>节点信息</h2>
          <p>点击图中节点查看属性与直接关系</p>
        </div>
        <div className="kg-details-body">
          {!selectedId && (
            <div className="kg-details-empty">
              请选择一个知识点节点。
              <span>也可以从左侧章节或题目详情的知识点跳转进入。</span>
            </div>
          )}
          {selectedId && detail.isLoading && (
            <div className="kg-details-empty">加载中…</div>
          )}
          {selectedId && detail.isError && (
            <div className="kg-details-empty">
              该知识点不在图谱中。
              <span>可能来自手工标签或种子词表，尚未关联到学科图谱；请从左侧章节或图中选择其他知识点。</span>
            </div>
          )}
          {detail.data && (
            <TopicDetail key={detail.data.id} topic={detail.data} onPick={pick} />
          )}
        </div>
      </aside>
    </div>
  )
}
