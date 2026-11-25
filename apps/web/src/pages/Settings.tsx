import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { Tag } from '../ui/Tag'
import { useDocuments } from '../api/queries/documents'
import {
  useCreateInkProfile,
  useCreateTag,
  useInkProfiles,
  useMergeTags,
  usePatchInkProfile,
  usePendingTags,
  useReidentifyDocument,
  useTags,
} from '../api/queries/settings'
import type { components } from '../api/types'

type InkProfileOut = components['schemas']['InkProfileOut']
type TagOut = components['schemas']['TagOut']

type TabKey = 'ink' | 'tags' | 'model'

const inputStyle: CSSProperties = {
  padding: '6px 10px',
  border: '1px solid var(--line-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface)',
  color: 'var(--ink)',
  fontSize: 13,
}

const COLOR_SWATCHES = [
  { value: 'black', label: '黑', css: 'var(--ink)' },
  { value: 'red', label: '红', css: 'var(--danger)' },
  { value: 'blue', label: '蓝', css: 'var(--accent)' },
  { value: 'green', label: '绿', css: 'var(--ok)' },
]

const ROLE_ORDER = ['print', 'answer', 'mark', 'correction'] as const
type RoleKey = (typeof ROLE_ORDER)[number]

const ROLE_META: Record<RoleKey, { title: string; desc: string }> = {
  print: { title: '印刷体', desc: '印刷字体与图示，低饱和度即视为印刷。' },
  answer: { title: '学生解答', desc: '黑笔手写，靠笔宽与饱和度阈值和印刷体区分。' },
  mark: { title: '批改标记', desc: '红笔勾、叉、圈画与分数；hue 为 HSV 色相区间。' },
  correction: { title: '订正', desc: '蓝笔订正内容，按蓝色相区间取出。' },
}

type RoleRule = {
  role: string
  color: string
  mode?: string
  hue?: number[]
  sat_min?: number
  sat_max?: number
  shapes?: string[]
  [key: string]: unknown
}

type Rules = {
  name?: string
  roles: RoleRule[]
  page_overrides?: Record<string, unknown>
  [key: string]: unknown
}

function normalizeRules(raw: unknown): Rules {
  const source = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const existing = Array.isArray(source.roles) ? (source.roles as RoleRule[]) : []
  const roles = ROLE_ORDER.map((role) => {
    const found = existing.find((item) => item?.role === role)
    if (found) return found
    const color = role === 'mark' ? 'red' : role === 'correction' ? 'blue' : 'black'
    return { role, color }
  })
  const pageOverrides = (source.page_overrides as Record<string, unknown> | undefined) ?? {}
  return { ...source, roles, page_overrides: pageOverrides }
}

function roleRule(draft: Rules, role: RoleKey): RoleRule {
  return draft.roles.find((item) => item.role === role) ?? { role, color: 'black' }
}

// ---------------------------------------------------------------- Tab 1 墨迹方案

function InkTab() {
  const profiles = useInkProfiles()
  const patch = usePatchInkProfile()
  const create = useCreateInkProfile()
  const documents = useDocuments()
  const reidentify = useReidentifyDocument()

  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState<Rules | null>(null)
  const [newName, setNewName] = useState('')
  const [documentId, setDocumentId] = useState('')
  const [saveNotice, setSaveNotice] = useState('')
  const [retryNotice, setRetryNotice] = useState('')

  const selectProfile = (profile: InkProfileOut) => {
    setSelectedId(profile.id)
    setDraft(normalizeRules(profile.rules_json))
    setSaveNotice('')
  }

  useEffect(() => {
    if (!profiles.data?.length) return
    if (selectedId && profiles.data.some((item) => item.id === selectedId)) return
    const preferred = profiles.data.find((item) => item.is_default) ?? profiles.data[0]
    setSelectedId(preferred.id)
    setDraft(normalizeRules(preferred.rules_json))
  }, [profiles.data, selectedId])

  const updateRole = (role: RoleKey, changes: Partial<RoleRule>) => {
    setDraft((prev) =>
      prev
        ? { ...prev, roles: prev.roles.map((item) => (item.role === role ? { ...item, ...changes } : item)) }
        : prev,
    )
  }

  const updateHue = (role: RoleKey, index: 0 | 1, value: number) => {
    const current = draft ? roleRule(draft, role).hue ?? [0, 255] : [0, 255]
    const next = [...current]
    next[index] = value
    updateRole(role, { hue: next })
  }

  const save = () => {
    if (!selectedId || !draft || patch.isPending) return
    patch.mutate(
      { id: selectedId, patch: { rules_json: draft } },
      { onSuccess: () => setSaveNotice('方案已保存。重新识别后生效。') },
    )
  }

  const onCreate = () => {
    const name = newName.trim()
    if (!name || !draft || create.isPending) return
    create.mutate(
      { name, is_default: false, rules_json: draft },
      {
        onSuccess: (profile) => {
          setNewName('')
          selectProfile(profile)
          setSaveNotice(`已新建方案「${profile.name}」，可继续调整后保存。`)
        },
      },
    )
  }

  const retry = () => {
    if (!documentId || reidentify.isPending) return
    reidentify.mutate(documentId, {
      onSuccess: (job) =>
        setRetryNotice(job ? '已从墨迹分色阶段重新识别，完成后到校对台查看。' : '该文档还没有任务记录。'),
    })
  }

  if (profiles.isLoading) {
    return (
      <Card title="墨迹方案">
        <div className="muted">加载中…</div>
      </Card>
    )
  }

  return (
    <div className="stack">
      <Card title="选择方案" subtitle="规则作用于 s3 墨迹分色；改动需重新识别才写回区域。">
        <div className="row-wrap">
          {profiles.data?.map((profile) => (
            <Chip key={profile.id} active={profile.id === selectedId} onClick={() => selectProfile(profile)}>
              {profile.name}
              {profile.is_default ? ' · 默认' : ''}
            </Chip>
          ))}
          {!profiles.data?.length && <span className="muted">还没有方案，可在下方新建。</span>}
        </div>
      </Card>

      {!draft ? (
        <Card title="新建方案" subtitle="当前没有可编辑的方案">
          <div className="row-wrap">
            <input
              value={newName}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="方案名称，如：蓝笔订正版"
              style={{ ...inputStyle, minWidth: 240 }}
            />
            <Button variant="primary" onClick={onCreate} disabled={!newName.trim() || create.isPending}>
              {create.isPending ? '创建中…' : '新建方案'}
            </Button>
          </div>
        </Card>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 'var(--space-4)' }}>
            {ROLE_ORDER.map((role) => {
              const rule = roleRule(draft, role)
              const meta = ROLE_META[role]
              const showHue = role === 'mark' || role === 'correction'
              const hue = rule.hue ?? [0, 255]
              return (
                <Card key={role} title={meta.title} subtitle={meta.desc}>
                  <div className="stack" style={{ gap: 'var(--space-3)' }}>
                    <div className="row">
                      <span className="muted" style={{ width: 56 }}>
                        颜色
                      </span>
                      <div className="row" style={{ gap: 6 }}>
                        {COLOR_SWATCHES.map((swatch) => {
                          const selected = (rule.color ?? 'black') === swatch.value
                          return (
                            <button
                              key={swatch.value}
                              type="button"
                              aria-label={swatch.label}
                              title={swatch.label}
                              onClick={() => updateRole(role, { color: swatch.value })}
                              style={{
                                width: 22,
                                height: 22,
                                padding: 0,
                                borderRadius: '50%',
                                cursor: 'pointer',
                                background: swatch.css,
                                border: selected ? '2px solid var(--ink)' : '2px solid var(--line)',
                                boxShadow: selected ? '0 0 0 2px var(--accent-soft)' : 'none',
                              }}
                            />
                          )
                        })}
                        <span className="muted" style={{ fontSize: 12 }}>
                          {COLOR_SWATCHES.find((item) => item.value === (rule.color ?? 'black'))?.label ??
                            rule.color ??
                            'black'}
                        </span>
                      </div>
                    </div>

                    {showHue && (
                      <div className="row">
                        <span className="muted" style={{ width: 56 }}>
                          色相
                        </span>
                        {[0, 1].map((index) => (
                          <input
                            key={index}
                            type="number"
                            value={hue[index] ?? 0}
                            aria-label={`${meta.title}色相${index === 0 ? '下界' : '上界'}`}
                            onChange={(event) => updateHue(role, index as 0 | 1, Number(event.target.value))}
                            style={{ ...inputStyle, width: 74 }}
                          />
                        ))}
                      </div>
                    )}

                    <label className="stack" style={{ gap: 4 }}>
                      <span className="muted">
                        sat_min <span className="mono">{rule.sat_min ?? 0}</span>
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={255}
                        value={rule.sat_min ?? 0}
                        onChange={(event) => updateRole(role, { sat_min: Number(event.target.value) })}
                      />
                    </label>
                    <label className="stack" style={{ gap: 4 }}>
                      <span className="muted">
                        sat_max <span className="mono">{rule.sat_max ?? 255}</span>
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={255}
                        value={rule.sat_max ?? 255}
                        onChange={(event) => updateRole(role, { sat_max: Number(event.target.value) })}
                      />
                    </label>
                  </div>
                </Card>
              )
            })}
          </div>

          <Card title="保存与生效" subtitle="保存后需重新识别，新规则才会落到区域上。">
            <div className="stack">
              <div className="row-wrap">
                <Button variant="primary" onClick={save} disabled={!selectedId || patch.isPending}>
                  {patch.isPending ? '保存中…' : '保存方案'}
                </Button>
                <span className="muted" style={{ fontSize: 12 }}>
                  提交完整 roles 与 page_overrides。
                </span>
                {saveNotice && (
                  <span className="mono" style={{ color: 'var(--ok)' }}>
                    {saveNotice}
                  </span>
                )}
              </div>
              <div
                className="row-wrap"
                style={{ paddingTop: 'var(--space-3)', borderTop: '1px solid var(--line)' }}
              >
                <span className="muted">重新识别</span>
                <select
                  value={documentId}
                  onChange={(event) => setDocumentId(event.target.value)}
                  style={{ ...inputStyle, minWidth: 220 }}
                >
                  <option value="">选择文档…</option>
                  {documents.data?.map((document) => (
                    <option key={document.id} value={document.id}>
                      {(document.source_name || document.id.slice(0, 8)) + ` · ${document.page_count} 页`}
                    </option>
                  ))}
                </select>
                <Button onClick={retry} disabled={!documentId || reidentify.isPending}>
                  {reidentify.isPending ? '触发中…' : '重新识别'}
                </Button>
                {retryNotice && (
                  <span className="mono" style={{ color: 'var(--ok)' }}>
                    {retryNotice}
                  </span>
                )}
              </div>
            </div>
          </Card>

          <Card title="新建方案" subtitle="复制当前规则作为起点，新建后不会自动设为默认。">
            <div className="row-wrap">
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="方案名称，如：蓝笔订正版"
                style={{ ...inputStyle, minWidth: 240 }}
              />
              <Button onClick={onCreate} disabled={!newName.trim() || create.isPending}>
                {create.isPending ? '创建中…' : '新建方案'}
              </Button>
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- Tab 2 标签词表

function TagListCard({
  title,
  tags,
  query,
  onQuery,
  placeholder,
}: {
  title: string
  tags: TagOut[] | undefined
  query: string
  onQuery: (value: string) => void
  placeholder: string
}) {
  const filtered = (tags ?? []).filter((tag) => (query.trim() ? tag.name.includes(query.trim()) : true))
  return (
    <Card title={title} subtitle={`已通过 ${tags?.length ?? 0} 个`}>
      <div className="stack">
        <input
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder={placeholder}
          style={{ ...inputStyle, maxWidth: 280 }}
        />
        {filtered.length ? (
          <div className="row-wrap">
            {filtered.map((tag) => (
              <Tag key={tag.id}>{tag.name}</Tag>
            ))}
          </div>
        ) : (
          <span className="muted">没有匹配的标签</span>
        )}
      </div>
    </Card>
  )
}

function TagsTab() {
  const knowledge = useTags('knowledge', 'approved')
  const method = useTags('method', 'approved')
  const pending = usePendingTags()
  const createTag = useCreateTag()
  const mergeTag = useMergeTags()

  const [knowledgeQuery, setKnowledgeQuery] = useState('')
  const [methodQuery, setMethodQuery] = useState('')
  const [newName, setNewName] = useState('')
  const [newType, setNewType] = useState<'knowledge' | 'method'>('knowledge')
  const [targets, setTargets] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState('')

  return (
    <div className="stack">
      <TagListCard
        title="知识点（已通过）"
        tags={knowledge.data}
        query={knowledgeQuery}
        onQuery={setKnowledgeQuery}
        placeholder="本地搜索知识点"
      />
      <TagListCard
        title="方法论（已通过）"
        tags={method.data}
        query={methodQuery}
        onQuery={setMethodQuery}
        placeholder="本地搜索方法论"
      />

      <Card title="待审池" subtitle="s6 打标产生的新词先进入这里">
        <div className="stack">
          <div className="muted" style={{ fontSize: 12 }}>
            审批通过与合并同义：把待审标签合并到已通过的标签，题目关联随之迁移，源标签随即删除。
          </div>
          {pending.isLoading ? (
            <div className="muted">加载中…</div>
          ) : !pending.data?.length ? (
            <div className="empty">
              <div className="empty-title">待审池为空</div>
              <div>新识别的知识词与方法词会出现在这里，等待人工归并。</div>
            </div>
          ) : (
            pending.data.map((tag) => {
              const approved = tag.type === 'knowledge' ? knowledge.data ?? [] : method.data ?? []
              const target = targets[tag.id] ?? ''
              return (
                <div
                  key={tag.id}
                  className="row"
                  style={{ paddingBottom: 8, borderBottom: '1px solid var(--line)' }}
                >
                  <Tag type="pending">{tag.name}</Tag>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {tag.type === 'knowledge' ? '知识点' : '方法论'}
                  </span>
                  <div className="grow" />
                  <select
                    value={target}
                    aria-label={`把 ${tag.name} 合并到`}
                    onChange={(event) =>
                      setTargets((prev) => ({ ...prev, [tag.id]: event.target.value }))
                    }
                    style={{ ...inputStyle, minWidth: 180 }}
                  >
                    <option value="">合并到已通过标签…</option>
                    {approved
                      .filter((item) => item.id !== tag.id)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                  </select>
                  <Button
                    size="sm"
                    disabled={!target || mergeTag.isPending}
                    onClick={() =>
                      mergeTag.mutate(
                        { from_id: tag.id, to_id: target },
                        { onSuccess: (merged) => setNotice(`已把「${tag.name}」合并到「${merged.name}」。`) },
                      )
                    }
                  >
                    合并
                  </Button>
                </div>
              )
            })
          )}
          {notice && (
            <span className="mono" style={{ color: 'var(--ok)' }}>
              {notice}
            </span>
          )}
        </div>
      </Card>

      <Card title="新建标签" subtitle="新标签一律进入待审，不会直接进入统计">
        <div className="row-wrap">
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="标签名"
            style={{ ...inputStyle, minWidth: 220 }}
          />
          <select
            value={newType}
            onChange={(event) => setNewType(event.target.value as 'knowledge' | 'method')}
            style={inputStyle}
          >
            <option value="knowledge">知识点</option>
            <option value="method">方法论</option>
          </select>
          <Button
            onClick={() =>
              createTag.mutate(
                { type: newType, name: newName.trim() },
                {
                  onSuccess: (tag) => {
                    setNewName('')
                    setNotice(`「${tag.name}」已进入待审。`)
                  },
                },
              )
            }
            disabled={!newName.trim() || createTag.isPending}
          >
            {createTag.isPending ? '提交中…' : '提交'}
          </Button>
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- Tab 3 模型

function ModelTab() {
  return (
    <div className="stack">
      <Card title="模型 provider" subtitle="默认全部走 mock，保证离线也能跑通全链路">
        <div className="stack">
          <div>
            <strong>版面检测 LayoutProvider</strong>
            <div className="muted">默认 mock（读 fixture 坐标）；设为 opencv 走 OpenCV 传统图像方法。</div>
          </div>
          <div>
            <strong>识别 OcrProvider</strong>
            <div className="muted">默认 mock（读 canned JSON）；设为 vlm 走云端视觉模型。</div>
          </div>
        </div>
      </Card>

      <Card title="切换方式" subtitle="启动 8000 服务前用环境变量指定，重启后生效">
        <pre
          className="mono"
          style={{
            margin: 0,
            padding: 'var(--space-3)',
            background: 'var(--surface-3)',
            borderRadius: 'var(--radius-sm)',
            overflowX: 'auto',
          }}
        >
          LAYOUT_PROVIDER=opencv OCR_PROVIDER=vlm make dev
        </pre>
      </Card>

      <Card title="API Key" subtitle="只从环境变量读取，永不入库、不在页面回显">
        <div className="stack">
          <div>
            云端识别的 Key 通过环境变量 <code className="mono">VLM_API_KEY</code> 提供；未设置时自动回落到 mock。
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            本页为只读说明，不提供读取或写入环境变量的接口。
          </div>
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- 页面

export default function Settings() {
  const [tab, setTab] = useState<TabKey>('ink')

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">设置</h1>
          <p className="page-desc">墨迹方案、标签词表、模型 provider。</p>
        </div>
      </div>

      <div className="row-wrap">
        <Chip active={tab === 'ink'} onClick={() => setTab('ink')}>
          墨迹方案
        </Chip>
        <Chip active={tab === 'tags'} onClick={() => setTab('tags')}>
          标签词表
        </Chip>
        <Chip active={tab === 'model'} onClick={() => setTab('model')}>
          模型
        </Chip>
      </div>

      {tab === 'ink' && <InkTab />}
      {tab === 'tags' && <TagsTab />}
      {tab === 'model' && <ModelTab />}
    </div>
  )
}
