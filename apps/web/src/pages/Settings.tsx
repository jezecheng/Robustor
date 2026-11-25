import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { Tag } from '../ui/Tag'
import { useDocuments } from '../api/queries/documents'
import {
  useAiConfig,
  useCreateAiProvider,
  useCreateInkProfile,
  useCreateTag,
  useDeleteAiProvider,
  useInkProfiles,
  useMergeTags,
  usePatchAiProvider,
  usePatchInkProfile,
  usePendingTags,
  useReidentifyDocument,
  useTags,
  useTestAiProvider,
} from '../api/queries/settings'
import type { components } from '../api/types'

type AiProviderOut = components['schemas']['AiProviderOut']
type AiProviderTestOut = components['schemas']['AiProviderTestOut']
type InkProfileOut = components['schemas']['InkProfileOut']
type TagOut = components['schemas']['TagOut']

type TabKey = 'ink' | 'tags' | 'ai' | 'model'

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

// ---------------------------------------------------------------- Tab 3 AI API

const KEY_SOURCE_LABEL: Record<string, string> = {
  db: '数据库',
  env: '环境变量',
  none: '未配置',
}

function AiApiTab() {
  const config = useAiConfig()
  const createProvider = useCreateAiProvider()
  const patchProvider = usePatchAiProvider()
  const deleteProvider = useDeleteAiProvider()
  const testProvider = useTestAiProvider()

  const [editingId, setEditingId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [notice, setNotice] = useState('')
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, AiProviderTestOut>>({})

  const resetForm = () => {
    setEditingId(null)
    setName('')
    setBaseUrl('')
    setModel('')
    setApiKey('')
  }

  const startEdit = (provider: AiProviderOut) => {
    setEditingId(provider.id)
    setName(provider.name)
    setBaseUrl(provider.base_url)
    setModel(provider.model)
    setApiKey('')
    setNotice('')
  }

  const saving = createProvider.isPending || patchProvider.isPending
  const canSave =
    name.trim().length > 0 &&
    baseUrl.trim().length > 0 &&
    model.trim().length > 0 &&
    (editingId !== null || apiKey.trim().length > 0)

  const save = () => {
    if (!canSave || saving) return
    const body = { name: name.trim(), base_url: baseUrl.trim(), model: model.trim() }
    if (editingId) {
      patchProvider.mutate(
        { id: editingId, patch: { ...body, api_key: apiKey.trim() || undefined } },
        {
          onSuccess: () => {
            setNotice(`已更新「${body.name}」，下一个识别任务立即生效。`)
            resetForm()
          },
          onError: () => setNotice('保存失败，请检查 Base URL 与必填项。'),
        },
      )
      return
    }
    createProvider.mutate(
      { ...body, api_key: apiKey.trim() },
      {
        onSuccess: (data) => {
          const active = data.providers?.find((item) => item.is_active)
          setNotice(
            active ? `已保存「${active.name}」并设为当前使用。` : `已保存「${body.name}」。`,
          )
          resetForm()
        },
        onError: () => setNotice('保存失败，请检查 Base URL 与必填项。'),
      },
    )
  }

  const activate = (provider: AiProviderOut) => {
    if (saving) return
    patchProvider.mutate(
      { id: provider.id, patch: { is_active: true } },
      { onSuccess: () => setNotice(`已切换到「${provider.name}」。`) },
    )
  }

  const test = (provider: AiProviderOut) => {
    if (testingId) return
    setTestingId(provider.id)
    testProvider.mutate(provider.id, {
      onSuccess: (result) =>
        setTestResults((prev) => ({ ...prev, [provider.id]: result })),
      onError: () =>
        setTestResults((prev) => ({
          ...prev,
          [provider.id]: { ok: false, latency_ms: 0, message: '请求失败，请查看服务端日志' },
        })),
      onSettled: () => setTestingId(null),
    })
  }

  const remove = (provider: AiProviderOut) => {
    if (deleteProvider.isPending) return
    if (!window.confirm(`确认删除配置「${provider.name}」？删除后无法恢复。`)) return
    deleteProvider.mutate(provider.id, {
      onSuccess: () => {
        setNotice(`已删除「${provider.name}」。`)
        if (editingId === provider.id) resetForm()
      },
    })
  }

  const data = config.data
  const providers = data?.providers ?? []
  const vlmWithoutKey = data?.effective_provider === 'vlm' && !data.effective_api_key_set

  return (
    <div className="stack">
      <Card
        title="AI 配置"
        subtitle="名称、Base URL、模型、Key 作为一个整体保存；只有标注「使用中」的一条参与识别。"
      >
        <div className="stack" style={{ gap: 'var(--space-3)' }}>
          {!providers.length ? (
            <div className="muted">还没有保存配置，可在下方新增；未配置时回落到环境变量。</div>
          ) : (
            providers.map((provider) => (
              <div
                key={provider.id}
                className="stack"
                style={{ paddingBottom: 8, borderBottom: '1px solid var(--line)', gap: 4 }}
              >
                <div className="row-wrap">
                  <strong style={{ minWidth: 110 }}>{provider.name}</strong>
                  <span
                    className="mono muted"
                    title={provider.base_url}
                    style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                  >
                    {provider.base_url}
                  </span>
                  <Tag>{provider.model}</Tag>
                  {provider.is_active && <Tag>使用中</Tag>}
                  <span className="muted" style={{ fontSize: 12 }}>
                    {provider.has_key ? 'Key 已保存' : '未设置 Key'}
                  </span>
                  <div className="grow" />
                  <Button
                    size="sm"
                    disabled={testingId === provider.id}
                    onClick={() => test(provider)}
                  >
                    {testingId === provider.id ? '测试中…' : '测试'}
                  </Button>
                  <Button size="sm" disabled={saving} onClick={() => startEdit(provider)}>
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    disabled={provider.is_active || saving}
                    onClick={() => activate(provider)}
                  >
                    使用
                  </Button>
                  <Button
                    size="sm"
                    disabled={deleteProvider.isPending}
                    onClick={() => remove(provider)}
                  >
                    删除
                  </Button>
                </div>
                {testResults[provider.id] && (
                  <span
                    className="mono"
                    style={{
                      fontSize: 12,
                      color: testResults[provider.id].ok ? 'var(--ok)' : 'var(--danger)',
                    }}
                  >
                    {testResults[provider.id].ok
                      ? `连接正常 · ${testResults[provider.id].latency_ms}ms · ${testResults[provider.id].message}`
                      : `测试失败 · ${testResults[provider.id].message}`}
                  </span>
                )}
              </div>
            ))
          )}
          {notice && (
            <span className="mono" style={{ color: 'var(--ok)' }}>
              {notice}
            </span>
          )}
        </div>
      </Card>

      <Card
        title={editingId ? `编辑配置${name ? `：${name}` : ''}` : '新增配置'}
        subtitle="保存后 Key 不再显示、无法查看；更换需重新填写覆盖。"
      >
        <div className="stack" style={{ gap: 'var(--space-3)' }}>
          <label className="stack" style={{ gap: 4 }}>
            <span className="muted">名称</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如 主力模型 / 备用 Key"
              style={{ ...inputStyle, maxWidth: 320 }}
            />
          </label>

          <label className="stack" style={{ gap: 4 }}>
            <span className="muted">Base URL（完整 chat/completions 端点）</span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://api.openai.com/v1/chat/completions"
              style={inputStyle}
            />
          </label>

          <label className="stack" style={{ gap: 4 }}>
            <span className="muted">模型</span>
            <input
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="gpt-4o-mini"
              style={{ ...inputStyle, maxWidth: 320 }}
            />
          </label>

          <label className="stack" style={{ gap: 4 }}>
            <span className="muted">API Key</span>
            <input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              autoComplete="new-password"
              placeholder={editingId ? '已保存，留空则不修改' : '粘贴 API Key'}
              style={inputStyle}
            />
          </label>

          <div className="row-wrap">
            <Button variant="primary" onClick={save} disabled={!canSave || saving}>
              {saving ? '保存中…' : editingId ? '保存修改' : '保存配置'}
            </Button>
            {editingId && (
              <Button onClick={resetForm} disabled={saving}>
                取消
              </Button>
            )}
          </div>
        </div>
      </Card>

      <Card title="实际生效" subtitle="优先级：数据库保存值 > 环境变量 > 默认值。">
        <div className="stack" style={{ gap: 'var(--space-2)' }}>
          <div className="row-wrap">
            <span className="muted" style={{ width: 96 }}>
              provider
            </span>
            <span className="mono">{data?.effective_provider ?? '—'}</span>
          </div>
          <div className="row-wrap">
            <span className="muted" style={{ width: 96 }}>
              Base URL
            </span>
            <span className="mono">{data?.effective_base_url ?? '—'}</span>
          </div>
          <div className="row-wrap">
            <span className="muted" style={{ width: 96 }}>
              模型
            </span>
            <span className="mono">{data?.effective_model ?? '—'}</span>
          </div>
          <div className="row-wrap">
            <span className="muted" style={{ width: 96 }}>
              API Key
            </span>
            <span className="mono">
              {data?.effective_api_key_set
                ? `已配置（来源：${KEY_SOURCE_LABEL[data.api_key_source] ?? data.api_key_source}）`
                : '未配置'}
            </span>
          </div>
          {vlmWithoutKey && (
            <div className="muted" style={{ color: 'var(--danger)', fontSize: 12 }}>
              provider 为 vlm 但没有可用 Key，识别会自动回落到 mock。
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- Tab 4 模型

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

      <Card title="API Key" subtitle="在「AI API」页配置，仅存本地数据库，不回传明文">
        <div className="stack">
          <div>
            云端识别的 Key 可在「AI API」页保存，优先级高于环境变量 <code className="mono">VLM_API_KEY</code>；
            两者都没有时自动回落到 mock。
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            本页仅作说明，配置请到「AI API」页。
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
        <Chip active={tab === 'ai'} onClick={() => setTab('ai')}>
          AI API
        </Chip>
        <Chip active={tab === 'model'} onClick={() => setTab('model')}>
          模型
        </Chip>
      </div>

      {tab === 'ink' && <InkTab />}
      {tab === 'tags' && <TagsTab />}
      {tab === 'ai' && <AiApiTab />}
      {tab === 'model' && <ModelTab />}
    </div>
  )
}
