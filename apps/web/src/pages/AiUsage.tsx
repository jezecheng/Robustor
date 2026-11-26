import { useMemo, useState, type CSSProperties } from 'react'
import { Card } from '../ui/Card'
import {
  useAiUsageRequests,
  useAiUsageSummary,
  type AiUsageBucket,
  type AiUsageRequestList,
} from '../api/queries/aiUsage'

type PresetKey = '3d' | '7d' | '15d' | '30d' | 'month' | 'year' | 'custom'

const PRESETS: { key: PresetKey; label: string }[] = [
  { key: '3d', label: '近 3 天' },
  { key: '7d', label: '近 7 天' },
  { key: '15d', label: '近 15 天' },
  { key: '30d', label: '近 30 天' },
  { key: 'month', label: '本月' },
  { key: 'year', label: '今年' },
  { key: 'custom', label: '自定义' },
]

const DAY_OFFSET: Record<string, number> = { '3d': 2, '7d': 6, '15d': 14, '30d': 29 }
const DAY_MS = 86_400_000
const AUTO_MONTH_SPAN_DAYS = 92

function startOfDay(date: Date): Date {
  const next = new Date(date)
  next.setHours(0, 0, 0, 0)
  return next
}

function presetRange(key: PresetKey): { start: Date; end: Date } {
  const end = new Date()
  if (key === 'month') {
    return { start: new Date(end.getFullYear(), end.getMonth(), 1), end }
  }
  if (key === 'year') {
    return { start: new Date(end.getFullYear(), 0, 1), end }
  }
  const offset = DAY_OFFSET[key] ?? 6
  return { start: startOfDay(new Date(end.getTime() - offset * DAY_MS)), end }
}

function toInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

function fmtNumber(value: number): string {
  return value.toLocaleString('zh-CN')
}

function fmtCompact(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

function niceMax(value: number): number {
  if (value <= 0) return 1
  const exponent = Math.floor(Math.log10(value))
  const base = 10 ** exponent
  const ratio = value / base
  const step = ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 5 ? 5 : 10
  return step * base
}

function formatTime(value: string): string {
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  if (Number.isNaN(date.getTime())) return value
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}:${pad(date.getSeconds())}`
}

function formatDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const COLORS = {
  input: '#2f5bd7',
  cached: '#a9bcf0',
  output: '#1f7a4d',
  reasoning: '#93d3b1',
}

function UsageChart({ series, bucket }: { series: AiUsageBucket[]; bucket: 'day' | 'month' }) {
  const width = 960
  const height = 300
  const padLeft = 62
  const padRight = 18
  const padTop = 16
  const padBottom = 38
  const innerWidth = width - padLeft - padRight
  const innerHeight = height - padTop - padBottom

  const maxValue = Math.max(
    1,
    ...series.map((row) => row.prompt_tokens + row.completion_tokens),
  )
  const top = niceMax(maxValue)
  const band = innerWidth / Math.max(1, series.length)
  const barWidth = Math.min(48, Math.max(3, band * 0.6))
  const tickCount = 4
  const labelStep = Math.max(1, Math.ceil(series.length / 9))

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Token 消耗趋势"
        style={{ width: '100%', minWidth: 720, display: 'block' }}
      >
        {Array.from({ length: tickCount + 1 }, (_, index) => {
          const ratio = index / tickCount
          const y = padTop + innerHeight * (1 - ratio)
          return (
            <g key={ratio}>
              <line
                x1={padLeft}
                x2={width - padRight}
                y1={y}
                y2={y}
                stroke="var(--line)"
                strokeWidth={1}
              />
              <text
                x={padLeft - 8}
                y={y + 3}
                textAnchor="end"
                fontSize={10}
                fill="var(--ink-3)"
              >
                {fmtCompact(top * ratio)}
              </text>
            </g>
          )
        })}

        {series.map((row, index) => {
          const prompt = row.prompt_tokens
          const completion = row.completion_tokens
          const total = prompt + completion
          const barHeight = (total / top) * innerHeight
          const x = padLeft + band * index + (band - barWidth) / 2
          const baseY = padTop + innerHeight

          const inputNoCache = Math.max(0, prompt - row.cached_tokens)
          const outputNoReason = Math.max(0, completion - row.reasoning_tokens)
          const segments = [
            { value: inputNoCache, color: COLORS.input },
            { value: Math.min(row.cached_tokens, prompt), color: COLORS.cached },
            { value: outputNoReason, color: COLORS.output },
            { value: Math.min(row.reasoning_tokens, completion), color: COLORS.reasoning },
          ]

          let cursor = baseY
          const title = [
            row.bucket,
            `输入 ${fmtNumber(prompt)}（缓存 ${fmtNumber(row.cached_tokens)}）`,
            `输出 ${fmtNumber(completion)}（推理 ${fmtNumber(row.reasoning_tokens)}）`,
            `请求 ${row.requests} · 失败 ${row.failed}`,
          ].join('\n')

          const showLabel = index % labelStep === 0 || index === series.length - 1
          return (
            <g key={row.bucket}>
              <rect
                x={padLeft + band * index}
                y={padTop}
                width={band}
                height={innerHeight}
                fill="transparent"
              >
                <title>{title}</title>
              </rect>
              {segments.map((segment, segIndex) => {
                if (segment.value <= 0) return null
                const segmentHeight = (segment.value / top) * innerHeight
                cursor -= segmentHeight
                return (
                  <rect
                    key={segIndex}
                    x={x}
                    y={cursor}
                    width={barWidth}
                    height={Math.max(1, segmentHeight)}
                    fill={segment.color}
                  >
                    <title>{title}</title>
                  </rect>
                )
              })}
              {barHeight === 0 && (
                <rect x={x} y={baseY - 1} width={barWidth} height={1} fill="var(--line-strong)" />
              )}
              {showLabel && (
                <text
                  x={padLeft + band * index + band / 2}
                  y={height - 14}
                  textAnchor="middle"
                  fontSize={10}
                  fill="var(--ink-3)"
                >
                  {bucket === 'month' ? row.bucket : row.bucket.slice(5)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function Metric({
  label,
  value,
  hint,
  title,
}: {
  label: string
  value: string
  hint?: string
  title?: string
}) {
  return (
    <div className="card" style={{ padding: '12px 14px' }} title={title}>
      <div className="muted" style={{ fontSize: 11.5 }}>
        {label}
      </div>
      <div className="mono" style={{ fontSize: 19, fontWeight: 650, marginTop: 2 }}>
        {value}
      </div>
      {hint && (
        <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>
          {hint}
        </div>
      )}
    </div>
  )
}

const TH_STYLE: CSSProperties = {
  padding: '9px 12px',
  textAlign: 'left',
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--ink-3)',
  background: 'var(--surface-2)',
  borderBottom: '1px solid var(--line)',
  whiteSpace: 'nowrap',
}

const TD_STYLE: CSSProperties = {
  padding: '9px 12px',
  borderBottom: '1px solid var(--line)',
  verticalAlign: 'top',
}

function RequestTable({
  data,
  loading,
  page,
  size,
  onPage,
  onSize,
}: {
  data?: AiUsageRequestList
  loading: boolean
  page: number
  size: number
  onPage: (page: number) => void
  onSize: (size: number) => void
}) {
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / size))
  const items = data?.items ?? []

  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">请求明细</div>
        <div className="card-sub">按时间倒序 · 共 {total} 条</div>
      </div>

      {items.length === 0 ? (
        <div className="card-body">
          <div className="empty">
            <div className="empty-title">{loading ? '加载中…' : '暂无 AI 请求记录'}</div>
            <div>
              {loading
                ? '正在读取用量明细。'
                : '配置 AI Provider 并完成一次识别 / 打标 / 连接测试后，这里会出现每一条请求。'}
            </div>
          </div>
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr>
                <th style={TH_STYLE}>时间</th>
                <th style={TH_STYLE}>状态</th>
                <th style={TH_STYLE}>业务场景</th>
                <th style={TH_STYLE}>Key</th>
                <th style={TH_STYLE}>模型</th>
                <th style={{ ...TH_STYLE, textAlign: 'right' }}>输入 / 输出 / 推理 / 缓存</th>
                <th style={{ ...TH_STYLE, textAlign: 'right' }}>总计</th>
                <th style={{ ...TH_STYLE, textAlign: 'right' }}>耗时</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td style={{ ...TD_STYLE, whiteSpace: 'nowrap' }} className="mono">
                    {formatTime(item.created_at)}
                  </td>
                  <td style={TD_STYLE}>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        borderRadius: 999,
                        padding: '2px 8px',
                        fontSize: 11,
                        fontWeight: 600,
                        background: item.success ? 'var(--ok-soft)' : 'var(--danger-soft)',
                        color: item.success ? 'var(--ok)' : 'var(--danger)',
                      }}
                      title={item.error ?? undefined}
                    >
                      {item.success ? '成功' : '失败'}
                    </span>
                    {item.error && (
                      <div
                        className="muted"
                        style={{
                          marginTop: 3,
                          maxWidth: 190,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          fontSize: 10.5,
                        }}
                        title={item.error}
                      >
                        {item.error}
                      </div>
                    )}
                  </td>
                  <td style={TD_STYLE}>{item.scene || '未标注'}</td>
                  <td style={{ ...TD_STYLE, maxWidth: 150 }}>
                    <span
                      className="mono"
                      style={{
                        display: 'inline-block',
                        maxWidth: 140,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        verticalAlign: 'bottom',
                      }}
                      title={item.provider_name}
                    >
                      {item.provider_name || '—'}
                    </span>
                  </td>
                  <td style={{ ...TD_STYLE, maxWidth: 160 }}>
                    <span
                      className="mono"
                      style={{
                        display: 'inline-block',
                        maxWidth: 150,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        verticalAlign: 'bottom',
                      }}
                      title={item.model}
                    >
                      {item.model || '—'}
                    </span>
                  </td>
                  <td
                    className="mono"
                    style={{ ...TD_STYLE, textAlign: 'right', whiteSpace: 'nowrap' }}
                    title="输入（含缓存）/ 输出（含推理）/ 推理 / 缓存"
                  >
                    {fmtNumber(item.prompt_tokens)} / {fmtNumber(item.completion_tokens)} /{' '}
                    {fmtNumber(item.reasoning_tokens)} / {fmtNumber(item.cached_tokens)}
                  </td>
                  <td className="mono" style={{ ...TD_STYLE, textAlign: 'right' }}>
                    {fmtNumber(item.total_tokens)}
                  </td>
                  <td className="mono" style={{ ...TD_STYLE, textAlign: 'right' }}>
                    {item.latency_ms >= 1000
                      ? `${(item.latency_ms / 1000).toFixed(1)}s`
                      : `${item.latency_ms}ms`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 18px',
          borderTop: '1px solid var(--line)',
        }}
      >
        <span className="muted" style={{ fontSize: 12 }}>
          第 {page} / {pages} 页 · 共 {total} 条
        </span>
        <div className="grow" />
        <select
          value={size}
          onChange={(event) => onSize(Number(event.target.value))}
          style={{
            border: '1px solid var(--line-strong)',
            borderRadius: 'var(--radius-sm)',
            padding: '5px 8px',
            background: 'var(--surface)',
            fontSize: 12,
          }}
        >
          {[20, 50, 100].map((option) => (
            <option key={option} value={option}>
              每页 {option} 条
            </option>
          ))}
        </select>
        <button
          className="btn btn-secondary btn-sm"
          disabled={page <= 1 || loading}
          onClick={() => onPage(page - 1)}
        >
          上一页
        </button>
        <button
          className="btn btn-secondary btn-sm"
          disabled={page >= pages || loading}
          onClick={() => onPage(page + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  )
}

export default function AiUsage() {
  const [preset, setPreset] = useState<PresetKey>('7d')
  const [range, setRange] = useState(() => presetRange('7d'))
  const [customStart, setCustomStart] = useState(() => toInputValue(presetRange('7d').start))
  const [customEnd, setCustomEnd] = useState(() => toInputValue(new Date()))
  const [customError, setCustomError] = useState('')
  const [page, setPage] = useState(1)
  const [size, setSize] = useState(20)

  const bucket: 'day' | 'month' =
    (range.end.getTime() - range.start.getTime()) / DAY_MS > AUTO_MONTH_SPAN_DAYS
      ? 'month'
      : 'day'

  const queryRange = useMemo(
    () => ({
      start: range.start.toISOString(),
      end: range.end.toISOString(),
      bucket,
    }),
    [range, bucket],
  )

  const summary = useAiUsageSummary(queryRange)
  const requests = useAiUsageRequests(queryRange, page, size)

  function pickPreset(key: PresetKey) {
    setPreset(key)
    setCustomError('')
    if (key === 'custom') {
      setCustomStart(toInputValue(range.start))
      setCustomEnd(toInputValue(range.end))
      return
    }
    setRange(presetRange(key))
    setPage(1)
  }

  function applyCustom() {
    const start = new Date(customStart)
    const end = new Date(customEnd)
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
      setCustomError('请填写完整的开始与结束时间')
      return
    }
    if (start.getTime() > end.getTime()) {
      setCustomError('开始时间不能晚于结束时间')
      return
    }
    setCustomError('')
    setRange({ start, end })
    setPage(1)
  }

  const data = summary.data
  const totals = data?.totals
  const series = data?.series ?? []

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">AI 用量</h1>
          <p className="page-desc">
            Token 消耗趋势与每一次 AI 请求的明细，统计口径为东八区自然日。
          </p>
        </div>
        <div className="page-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => {
              summary.refetch()
              requests.refetch()
            }}
            disabled={summary.isFetching || requests.isFetching}
          >
            {summary.isFetching || requests.isFetching ? '刷新中…' : '刷新'}
          </button>
        </div>
      </div>

      <Card>
        <div className="card-body" style={{ padding: '12px 16px' }}>
          <div className="row-wrap" style={{ gap: 8 }}>
            {PRESETS.map((item) => (
              <button
                key={item.key}
                className={`chip${preset === item.key ? ' active' : ''}`}
                onClick={() => pickPreset(item.key)}
              >
                {item.label}
              </button>
            ))}
            <div className="grow" />
            <span className="muted" style={{ fontSize: 12 }}>
              {bucket === 'day' ? '按日' : '按月'} · {formatDate(range.start)} 至{' '}
              {formatDate(range.end)}
            </span>
          </div>

          {preset === 'custom' && (
            <div className="row-wrap" style={{ gap: 8, marginTop: 12 }}>
              <label className="muted" style={{ fontSize: 12 }}>
                开始
              </label>
              <input
                type="datetime-local"
                value={customStart}
                onChange={(event) => setCustomStart(event.target.value)}
                style={INPUT_STYLE}
              />
              <label className="muted" style={{ fontSize: 12 }}>
                结束
              </label>
              <input
                type="datetime-local"
                value={customEnd}
                onChange={(event) => setCustomEnd(event.target.value)}
                style={INPUT_STYLE}
              />
              <button className="btn btn-primary btn-sm" onClick={applyCustom}>
                应用
              </button>
              {customError && (
                <span style={{ color: 'var(--danger)', fontSize: 11.5 }}>{customError}</span>
              )}
            </div>
          )}
        </div>
      </Card>

      {summary.isLoading ? (
        <div className="empty">
          <div className="empty-title">加载中…</div>
          <div>正在汇总 AI 用量。</div>
        </div>
      ) : summary.isError || !totals ? (
        <div className="empty">
          <div className="empty-title">AI 用量加载失败</div>
          <div>{summary.error?.message ?? '请确认后端 8000 已启动。'}</div>
        </div>
      ) : (
        <>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(112px, 1fr))',
              gap: 12,
            }}
          >
            <Metric
              label="请求数"
              value={fmtNumber(totals.requests)}
              hint={`平均 ${totals.avg_latency_ms} ms`}
            />
            <Metric
              label="成功率"
              value={totals.requests ? `${(totals.success_rate * 100).toFixed(1)}%` : '—'}
              hint={`失败 ${totals.failed} 次`}
            />
            <Metric
              label="输入 Token"
              value={fmtCompact(totals.prompt_tokens)}
              hint={`含缓存 ${fmtCompact(totals.cached_tokens)}`}
              title={fmtNumber(totals.prompt_tokens)}
            />
            <Metric
              label="输出 Token"
              value={fmtCompact(totals.completion_tokens)}
              hint={`含推理 ${fmtCompact(totals.reasoning_tokens)}`}
              title={fmtNumber(totals.completion_tokens)}
            />
            <Metric
              label="推理 Token"
              value={fmtCompact(totals.reasoning_tokens)}
              hint="输出的一部分"
              title={fmtNumber(totals.reasoning_tokens)}
            />
            <Metric
              label="缓存 Token"
              value={fmtCompact(totals.cached_tokens)}
              hint="输入的一部分"
              title={fmtNumber(totals.cached_tokens)}
            />
            <Metric
              label="总 Token"
              value={fmtCompact(totals.total_tokens)}
              hint="输入 + 输出"
              title={fmtNumber(totals.total_tokens)}
            />
          </div>

          <Card>
            <div className="card-head">
              <div className="card-title">Token 消耗趋势</div>
              <div className="card-sub">柱高 = 输入 + 输出；缓存 / 推理分别是输入 / 输出的其中一部分</div>
            </div>
            <div className="card-body" style={{ paddingTop: 10 }}>
              <div className="row-wrap" style={{ gap: 16, marginBottom: 4 }}>
                {[
                  { label: '输入', color: COLORS.input },
                  { label: '其中缓存', color: COLORS.cached },
                  { label: '输出', color: COLORS.output },
                  { label: '其中推理', color: COLORS.reasoning },
                ].map((item) => (
                  <span
                    key={item.label}
                    className="row"
                    style={{ gap: 6, fontSize: 11.5, color: 'var(--ink-2)' }}
                  >
                    <span
                      style={{
                        width: 9,
                        height: 9,
                        borderRadius: 2,
                        background: item.color,
                        display: 'inline-block',
                      }}
                    />
                    {item.label}
                  </span>
                ))}
              </div>
              <UsageChart series={series} bucket={bucket} />
            </div>
          </Card>

          <RequestTable
            data={requests.data}
            loading={requests.isLoading}
            page={page}
            size={size}
            onPage={setPage}
            onSize={(next) => {
              setSize(next)
              setPage(1)
            }}
          />
        </>
      )}
    </div>
  )
}

const INPUT_STYLE: CSSProperties = {
  border: '1px solid var(--line-strong)',
  borderRadius: 'var(--radius-sm)',
  padding: '5px 8px',
  background: 'var(--surface)',
  fontSize: 12,
  color: 'var(--ink)',
}
