import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Chip } from '../ui/Chip'
import { useDocuments, useJob, useRetryJob, useUploadDocuments } from '../api/queries/documents'
import type { components } from '../api/types'

type JobOut = components['schemas']['JobOut']

const STAGES: { key: JobOut['stage']; label: string }[] = [
  { key: 'preprocess', label: '预处理' },
  { key: 'layout', label: '版面切块' },
  { key: 'ink', label: '墨迹分色' },
  { key: 'recognize', label: '识别' },
  { key: 'assemble', label: '装配' },
  { key: 'tag', label: '打标' },
]

const SUBJECTS = [
  { value: 'math', label: '数学' },
  { value: 'physics', label: '物理' },
  { value: 'chemistry', label: '化学' },
]

type Pending = { file: File; key: string }

function Thumb({ file }: { file: File }) {
  const [url, setUrl] = useState('')
  useEffect(() => {
    const objectUrl = URL.createObjectURL(file)
    setUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])
  if (!url) {
    return <div style={{ width: 120, height: 90, background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)' }} />
  }
  return (
    <img
      src={url}
      alt={file.name}
      style={{
        width: 120,
        height: 90,
        objectFit: 'cover',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--line)',
      }}
    />
  )
}

export default function Upload() {
  const [pending, setPending] = useState<Pending[]>([])
  const [subject, setSubject] = useState('math')
  const [dragging, setDragging] = useState(false)
  const [created, setCreated] = useState<{ documentId: string; jobId: string } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const documents = useDocuments()
  const upload = useUploadDocuments()
  const retry = useRetryJob()
  const job = useJob(created?.jobId)

  useEffect(() => {
    if (created && job.data?.status === 'done') {
      navigate(`/console/${created.documentId}`)
    }
  }, [created, job.data?.status, navigate])

  const addFiles = (files: FileList | File[]) => {
    const images = Array.from(files).filter((file) => file.type.startsWith('image/'))
    if (!images.length) return
    setCreated(null)
    setPending((prev) => [
      ...prev,
      ...images.map((file) => ({ file, key: `${file.name}-${file.size}-${file.lastModified}-${Math.random()}` })),
    ])
  }

  const removeFile = (key: string) => {
    setPending((prev) => prev.filter((item) => item.key !== key))
  }

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files)
    event.target.value = ''
  }

  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault()
    setDragging(false)
    if (event.dataTransfer.files) addFiles(event.dataTransfer.files)
  }

  const startUpload = () => {
    if (!pending.length || upload.isPending) return
    upload.mutate(
      { files: pending.map((item) => item.file), subject },
      {
        onSuccess: (data) => {
          setPending([])
          setCreated({ documentId: data.document_id, jobId: data.job_id })
        },
      },
    )
  }

  const progress = job.data?.progress ?? 0
  const percent = Math.round(progress * 100)
  const currentIndex = job.data ? STAGES.findIndex((stage) => stage.key === job.data.stage) : -1
  const currentLabel = currentIndex >= 0 ? STAGES[currentIndex].label : '排队中'

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">上传作业</h1>
          <p className="page-desc">选 3 页数学作业照片，自动切块并进入校对台。</p>
        </div>
      </div>

      <Card title="选择图片" subtitle="支持多选，上传后自动跑完 6 个阶段">
        <div className="stack">
          <label
            className="empty"
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            style={{
              display: 'block',
              cursor: 'pointer',
              borderColor: dragging ? 'var(--accent)' : undefined,
              background: dragging ? 'var(--accent-soft)' : undefined,
            }}
          >
            <div className="empty-title">拖拽图片到此处，或点击选择</div>
            <div>一次上传 = 一份作业，建议按题目顺序选择 1–3 页。</div>
            <div className="empty-hint">接受 JPG / PNG，长边自动压缩到 2000px</div>
            <input ref={inputRef} type="file" accept="image/*" multiple hidden onChange={onPick} />
          </label>

          {pending.length > 0 && (
            <div className="row-wrap">
              {pending.map((item) => (
                <div key={item.key} className="stack" style={{ gap: 6, width: 120 }}>
                  <Thumb file={item.file} />
                  <div className="row" style={{ gap: 4 }}>
                    <span
                      className="muted grow"
                      style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={item.file.name}
                    >
                      {item.file.name}
                    </span>
                    <Button size="sm" variant="ghost" onClick={() => removeFile(item.key)} title="移除">
                      删除
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="row">
            <span className="muted">学科</span>
            <select
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              style={{
                padding: '6px 10px',
                border: '1px solid var(--line-strong)',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--surface)',
                color: 'var(--ink)',
              }}
            >
              {SUBJECTS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <div className="grow" />
            <Button variant="primary" onClick={startUpload} disabled={!pending.length || upload.isPending}>
              {upload.isPending ? '上传中…' : `上传 ${pending.length} 页`}
            </Button>
          </div>
          {upload.isError && <div className="muted">上传失败：{upload.error.message}</div>}
        </div>
      </Card>

      {created && (
        <Card
          title="处理进度"
          subtitle={job.data ? `当前阶段：${currentLabel}` : '正在获取任务状态…'}
        >
          <div className="stack">
            <div className="row-wrap">
              {STAGES.map((stage, index) => (
                <Chip
                  key={stage.key}
                  active={job.data ? stage.key === job.data.stage : false}
                  title={index < currentIndex ? '已完成' : undefined}
                >
                  {stage.label}
                </Chip>
              ))}
            </div>
            <div className="meter" style={{ width: '100%' }}>
              <span className="meter-track">
                <span className="meter-fill" style={{ width: `${percent}%` }} />
              </span>
              <span className="meter-value">{percent}%</span>
            </div>

            {job.data?.status === 'failed' && (
              <div className="stack">
                <div className="muted">任务失败：{job.data.error || '未知错误'}</div>
                <div className="row">
                  <Button
                    variant="primary"
                    onClick={() => retry.mutate({ jobId: created.jobId })}
                    disabled={retry.isPending}
                  >
                    {retry.isPending ? '重试中…' : '重试'}
                  </Button>
                </div>
              </div>
            )}

            {job.isError && (
              <div className="muted">无法获取任务状态：{job.error.message}</div>
            )}
            {job.data?.status === 'running' && (
              <div className="muted">正在运行流水线，完成后将自动跳转校对台。</div>
            )}
          </div>
        </Card>
      )}

      <Card title="最近上传" subtitle="点击进入校对台">
        {documents.isLoading ? (
          <div className="muted">加载中…</div>
        ) : !documents.data?.length ? (
          <div className="empty">
            <div className="empty-title">还没有上传记录</div>
            <div>先选 1–3 页作业照片上传，处理完成后会自动进入校对台。</div>
            <div className="empty-hint">下一步：修正区域框 → 编辑 LaTeX → 确认入库</div>
          </div>
        ) : (
          <div className="stack">
            {documents.data.map((document) => (
              <div
                key={document.id}
                className="row"
                style={{ paddingBottom: 8, borderBottom: '1px solid var(--line)' }}
              >
                <div className="grow">
                  <div className="row" style={{ gap: 8 }}>
                    <strong>{SUBJECTS.find((item) => item.value === document.subject)?.label ?? document.subject}</strong>
                    <span className="muted">{document.page_count} 页</span>
                    <span className="muted">· {document.problem_count} 题</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {document.source_name || '未命名'} · {new Date(document.created_at).toLocaleString('zh-CN')}
                  </div>
                </div>
                <Link to={`/console/${document.id}`} className="btn btn-secondary btn-sm">
                  进入校对台
                </Link>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
