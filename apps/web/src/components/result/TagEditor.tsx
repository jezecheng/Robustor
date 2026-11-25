import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Button } from '../../ui/Button'
import { Card } from '../../ui/Card'
import { Chip } from '../../ui/Chip'
import { Tag } from '../../ui/Tag'
import { useCreateTag, useTagSearch } from '../../api/queries/console'
import type { TagOut } from '../../api/queries/console'

export type SelectedTag = {
  id: string
  type: 'knowledge' | 'method'
  name: string
  pending?: boolean
}

export type TagEditorProps = {
  tags: SelectedTag[]
  onChange: (tags: SelectedTag[]) => void
}

const INPUT_STYLE: CSSProperties = {
  width: '100%',
  padding: '6px 10px',
  border: '1px solid var(--line-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)',
  color: 'var(--ink)',
  fontSize: 13,
}

const groupOf = (tags: SelectedTag[], type: SelectedTag['type']) => tags.filter((tag) => tag.type === type)

export function TagEditor({ tags, onChange }: TagEditorProps) {
  const [q, setQ] = useState('')
  const [newType, setNewType] = useState<SelectedTag['type']>('knowledge')
  const [notice, setNotice] = useState('')
  const tagQuery = useTagSearch(q.trim())
  const createTag = useCreateTag()

  const results = (tagQuery.data ?? [])
    .filter((tag) => !tags.some((selected) => selected.id === tag.id))
    .slice(0, 8)

  const addTag = (tag: TagOut) => {
    onChange([...tags, { id: tag.id, type: tag.type, name: tag.name }])
    setQ('')
    setNotice('')
  }

  const removeTag = (id: string) => {
    onChange(tags.filter((tag) => tag.id !== id))
  }

  const create = async () => {
    const name = q.trim()
    if (!name) return
    try {
      const tag = await createTag.mutateAsync({ type: newType, name })
      onChange([...tags, { id: tag.id, type: tag.type, name: tag.name, pending: true }])
      setNotice(`已提交新建标签「${tag.name}」，待审核`)
      setQ('')
    } catch {
      /* client.ts 已统一 toast */
    }
  }

  const renderGroup = (type: SelectedTag['type'], label: string) => {
    const items = groupOf(tags, type)
    return (
      <div className="stack" style={{ gap: 6 }}>
        <span className="muted" style={{ fontSize: 12 }}>
          {label} · {items.length}
        </span>
        <div className="row-wrap">
          {items.length === 0 && <span className="muted" style={{ fontSize: 12 }}>暂无</span>}
          {items.map((tag) => (
            <Tag
              key={tag.id}
              type={tag.pending ? 'pending' : tag.type}
              title={tag.pending ? '待审核' : undefined}
              onRemove={() => removeTag(tag.id)}
            >
              {tag.name}
              {tag.pending ? ' · 待审' : ''}
            </Tag>
          ))}
        </div>
      </div>
    )
  }

  return (
    <Card title="知识点与方法论" subtitle="搜索已审核词表，或新建标签（进入待审池）">
      <div className="stack" style={{ gap: 14 }}>
        {renderGroup('knowledge', '知识点')}
        {renderGroup('method', '方法论')}

        <div style={{ position: 'relative' }}>
          <input
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="搜索标签或输入新名称"
            style={INPUT_STYLE}
          />
          {q.trim().length > 0 && (
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: 'calc(100% + 4px)',
                zIndex: 20,
                background: 'var(--surface)',
                border: '1px solid var(--line-strong)',
                borderRadius: 'var(--radius-sm)',
                boxShadow: 'var(--shadow)',
                maxHeight: 216,
                overflowY: 'auto',
              }}
            >
              {tagQuery.isLoading && (
                <div className="muted" style={{ padding: '8px 10px', fontSize: 12 }}>
                  搜索中…
                </div>
              )}
              {!tagQuery.isLoading && results.length === 0 && (
                <div className="muted" style={{ padding: '8px 10px', fontSize: 12 }}>
                  没有匹配的已审核标签
                </div>
              )}
              {results.map((tag) => (
                <button
                  key={tag.id}
                  type="button"
                  onClick={() => addTag(tag)}
                  style={{
                    display: 'flex',
                    width: '100%',
                    alignItems: 'center',
                    gap: 8,
                    padding: '7px 10px',
                    border: 0,
                    borderBottom: '1px solid var(--line)',
                    background: 'transparent',
                    color: 'var(--ink)',
                    fontSize: 13,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <span className="grow">{tag.name}</span>
                  <span className="muted" style={{ fontSize: 11 }}>
                    {tag.type === 'knowledge' ? '知识点' : '方法论'}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="row-wrap">
          <span className="muted" style={{ fontSize: 12 }}>
            新建类型
          </span>
          <Chip active={newType === 'knowledge'} onClick={() => setNewType('knowledge')}>
            知识点
          </Chip>
          <Chip active={newType === 'method'} onClick={() => setNewType('method')}>
            方法论
          </Chip>
          <span className="grow" />
          <Button size="sm" onClick={() => void create()} disabled={!q.trim() || createTag.isPending}>
            新建「{q.trim() || '…'}」
          </Button>
        </div>

        {notice && (
          <div className="muted" style={{ fontSize: 12 }}>
            {notice}
          </div>
        )}
      </div>
    </Card>
  )
}

export default TagEditor
