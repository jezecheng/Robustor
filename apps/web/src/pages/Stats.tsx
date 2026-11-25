import { Link } from 'react-router-dom'
import { Card } from '../ui/Card'
import { useStats } from '../api/queries/stats'
import type { StatItem } from '../api/queries/stats'

const SUBJECT_LABEL: Record<string, string> = {
  math: '数学',
  physics: '物理',
  chemistry: '化学',
}

function Bar({
  name,
  count,
  max,
  color,
}: {
  name: string
  count: number
  max: number
  color: string
}) {
  const percent = max > 0 ? Math.max(4, Math.round((count / max) * 100)) : 0
  return (
    <div className="row" style={{ gap: 10 }}>
      <span
        style={{
          width: 120,
          flexShrink: 0,
          fontSize: 13,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
        title={name}
      >
        {name}
      </span>
      <span
        style={{
          position: 'relative',
          flex: 1,
          height: 10,
          borderRadius: 999,
          background: 'var(--surface-3)',
          overflow: 'hidden',
        }}
      >
        <span
          style={{
            position: 'absolute',
            inset: '0 auto 0 0',
            width: `${percent}%`,
            borderRadius: 999,
            background: color,
          }}
        />
      </span>
      <span className="mono muted" style={{ width: 32, textAlign: 'right', fontSize: 12 }}>
        {count}
      </span>
    </div>
  )
}

function maxCount(items: StatItem[]): number {
  return items.reduce((acc, item) => Math.max(acc, item.count), 0)
}

export default function Stats() {
  const stats = useStats()
  const data = stats.data

  if (stats.isLoading) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-title">加载中…</div>
          <div>正在汇总统计。</div>
        </div>
      </div>
    )
  }

  if (stats.isError || !data) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-title">统计加载失败</div>
          <div>{stats.error?.message ?? '请确认后端 8000 已启动。'}</div>
        </div>
      </div>
    )
  }

  const knowledge = (data.by_knowledge ?? []).slice(0, 10)
  const methods = data.by_method ?? []
  const subjects = data.by_subject ?? []

  if (!data.total) {
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">统计</h1>
            <p className="page-desc">知识点分布、方法论覆盖率、今日到期。</p>
          </div>
        </div>
        <div className="empty">
          <div className="empty-title">还没有数据</div>
          <div>入库题目 ≥1 后，这里展示学科分布与知识点 Top10。</div>
          <div className="row-wrap" style={{ justifyContent: 'center', gap: 8, marginTop: 12 }}>
            <Link to="/upload" className="btn btn-primary btn-sm">
              去上传作业
            </Link>
          </div>
          <div className="empty-hint">下一步：校对台确认入库 → 回到这里看统计。</div>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">统计</h1>
          <p className="page-desc">
            共 {data.total} 题 · 学科 {subjects.length} 个 · 知识点 {knowledge.length} 个
          </p>
        </div>
        <div className="page-actions">
          <Link to="/problems" className="btn btn-secondary">
            去错题本
          </Link>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 300px) minmax(0, 1fr)',
          gap: 'var(--space-4)',
          alignItems: 'stretch',
        }}
      >
        <Card title="今日到期" subtitle="含已逾期的复习项">
          <div className="stack" style={{ gap: 6 }}>
            <div
              style={{
                fontSize: 56,
                fontWeight: 700,
                lineHeight: 1.05,
                color: data.due_today > 0 ? 'var(--danger)' : 'var(--ok)',
              }}
            >
              {data.due_today}
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              {data.due_today > 0 ? '该复习了，从错题本“今日”筛选开始。' : '今天没有到期的题目。'}
            </div>
            <div>
              <Link to="/problems" className="btn btn-secondary btn-sm">
                去复习
              </Link>
            </div>
          </div>
        </Card>

        <Card title="学科分布" subtitle="按 problem.subject 统计">
          <div className="stack" style={{ gap: 10 }}>
            {subjects.map((item, index) => (
              <Bar
                key={item.name}
                name={SUBJECT_LABEL[item.name] ?? item.name}
                count={item.count}
                max={maxCount(subjects)}
                color={index === 0 ? 'var(--accent)' : 'var(--role-correction)'}
              />
            ))}
            {!subjects.length && <span className="muted">暂无学科数据</span>}
          </div>
        </Card>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
          gap: 'var(--space-4)',
          alignItems: 'start',
        }}
      >
        <Card title="知识点 Top10" subtitle="仅统计 approved 标签">
          <div className="stack" style={{ gap: 10 }}>
            {knowledge.map((item) => (
              <Bar
                key={item.name}
                name={item.name}
                count={item.count}
                max={maxCount(knowledge)}
                color="var(--accent)"
              />
            ))}
            {!knowledge.length && <span className="muted">暂无知识点标签</span>}
          </div>
        </Card>

        <Card title="方法论" subtitle={`共 ${methods.length} 个标签`}>
          <div className="stack" style={{ gap: 8 }}>
            {methods.map((item) => (
              <div key={item.name} className="row" style={{ gap: 8 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 999,
                    background: 'var(--role-figure)',
                    display: 'inline-block',
                    flexShrink: 0,
                  }}
                />
                <span className="grow" style={{ fontSize: 13 }}>
                  {item.name}
                </span>
                <span className="mono muted" style={{ fontSize: 12 }}>
                  {item.count}
                </span>
              </div>
            ))}
            {!methods.length && <span className="muted">暂无方法论标签</span>}
          </div>
        </Card>
      </div>
    </div>
  )
}
