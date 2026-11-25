import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { Button } from '../ui/Button'
import { Chip } from '../ui/Chip'
import { Meter } from '../ui/Meter'
import { PageCanvas } from '../components/canvas/PageCanvas'
import { StemCard } from '../components/result/StemCard'
import { SolutionCard } from '../components/result/SolutionCard'
import { TagEditor } from '../components/result/TagEditor'
import type { SelectedTag } from '../components/result/TagEditor'
import {
  BLOCK_TYPE_META,
  STAGE_LABELS,
  blockMeta,
  useCreateProblem,
  useDocument,
  useMergeRegions,
  usePatchProblem,
  usePatchRegion,
  useProblem,
  useRegions,
  useReplaceSolutions,
  useReplaceTags,
  useRetryJob,
} from '../api/queries/console'
import type {
  BlockType,
  JobOut,
  RegionOut,
  SolutionIn,
  SolutionOut,
  Verdict,
} from '../api/queries/console'

type Draft = {
  stemLatex: string
  subject: string
  studentLatex: string
  correctionLatex: string
  studentConfidence: number
  correctionConfidence: number
  tags: SelectedTag[]
}

const VERDICT_META: Record<Verdict, { label: string; fg: string; bg: string }> = {
  right: { label: '判定：对', fg: 'var(--ok)', bg: 'var(--ok-soft)' },
  wrong: { label: '判定：错', fg: 'var(--danger)', bg: 'var(--danger-soft)' },
  partial: { label: '判定：部分对', fg: 'var(--warn)', bg: 'var(--warn-soft)' },
  unknown: { label: '判定：未知', fg: 'var(--ink-3)', bg: 'var(--surface-3)' },
}

const JOB_STATUS_LABELS: Record<JobOut['status'], string> = {
  queued: '排队中',
  running: '识别中',
  done: '已完成',
  failed: '失败',
}

const JOB_DOT_COLORS: Record<JobOut['status'], string> = {
  queued: 'var(--ink-3)',
  running: 'var(--accent)',
  done: 'var(--ok)',
  failed: 'var(--danger)',
}

const LEGEND = BLOCK_TYPE_META.filter((meta) => meta.value !== 'noise')

function notify(message: string) {
  window.dispatchEvent(new CustomEvent('api-error', { detail: new ApiError(message, 0) }))
}

function buildSolutions(draft: Draft, existing?: SolutionOut[] | null): SolutionIn[] {
  const list: SolutionIn[] = []
  // 保留 reference / ai 等人工不编辑的解答，避免保存时被删。
  for (const solution of existing ?? []) {
    if (solution.kind === 'student' || solution.kind === 'correction') continue
    list.push({
      kind: solution.kind,
      latex: solution.latex,
      ink_role: solution.ink_role,
      confidence: solution.confidence,
    })
  }
  if (draft.studentLatex.trim()) {
    list.push({
      kind: 'student',
      latex: draft.studentLatex,
      ink_role: 'answer',
      confidence: draft.studentConfidence,
    })
  }
  if (draft.correctionLatex.trim()) {
    list.push({
      kind: 'correction',
      latex: draft.correctionLatex,
      ink_role: 'correction',
      confidence: draft.correctionConfidence,
    })
  }
  return list
}

const buildTagBody = (tags: SelectedTag[]) => ({
  knowledge: tags.filter((tag) => tag.type === 'knowledge').map((tag) => tag.id),
  method: tags.filter((tag) => tag.type === 'method').map((tag) => tag.id),
})

export default function Console() {
  const { documentId } = useParams<{ documentId: string }>()
  const navigate = useNavigate()
  const activeDocumentId = documentId ?? ''

  const documentQuery = useDocument(documentId)
  const regionsQuery = useRegions(documentId)
  const document = documentQuery.data
  const regions = useMemo(() => regionsQuery.data ?? [], [regionsQuery.data])

  const [activePageIdx, setActivePageIdx] = useState(1)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [actionNotice, setActionNotice] = useState('')

  const pages = useMemo(
    () => [...(document?.pages ?? [])].sort((a, b) => a.idx - b.idx),
    [document],
  )
  const resolvedIdx = pages.some((item) => item.idx === activePageIdx)
    ? activePageIdx
    : pages[0]?.idx ?? 1
  const page = pages.find((item) => item.idx === resolvedIdx) ?? null
  const pageRegions = useMemo(
    () => regions.filter((region) => region.page_start === page?.idx),
    [regions, page?.idx],
  )

  const selectedRegionId = selectedIds.length ? selectedIds[selectedIds.length - 1] : null
  const selectedRegion = regions.find((region) => region.id === selectedRegionId) ?? null
  const problemQuery = useProblem(selectedRegion?.problem_id ?? null)
  const problem = problemQuery.data ?? null

  const questionRegions = useMemo(() => {
    if (!selectedRegion) return []
    if (selectedRegion.problem_id) {
      return regions.filter((region) => region.problem_id === selectedRegion.problem_id)
    }
    return selectedIds
      .map((id) => regions.find((region) => region.id === id))
      .filter((region): region is RegionOut => Boolean(region))
  }, [regions, selectedIds, selectedRegion])

  const queryClient = useQueryClient()
  const patchRegion = usePatchRegion(activeDocumentId)
  const mergeRegions = useMergeRegions(activeDocumentId)
  const retryJob = useRetryJob(activeDocumentId)
  const createProblem = useCreateProblem()
  const patchProblem = usePatchProblem()
  const replaceSolutions = useReplaceSolutions()
  const replaceTags = useReplaceTags()

  const seedKey = problem ? `problem:${problem.id}` : `region:${selectedRegionId ?? ''}`

  useEffect(() => {
    setActionNotice('')
    if (!selectedRegion) {
      setDraft(null)
      return
    }
    if (problem) {
      const student = problem.solutions?.find((solution) => solution.kind === 'student')
      const correction = problem.solutions?.find((solution) => solution.kind === 'correction')
      setDraft({
        stemLatex: problem.stem_latex ?? '',
        subject: problem.subject || document?.subject || 'math',
        studentLatex: student?.latex ?? '',
        correctionLatex: correction?.latex ?? '',
        studentConfidence: student?.confidence ?? 0,
        correctionConfidence: correction?.confidence ?? 0,
        tags: (problem.tags ?? []).map((tag) => ({ id: tag.id, type: tag.type, name: tag.name })),
      })
      return
    }
    const stem = questionRegions.find((region) => region.block_type === 'stem')
    const answer = questionRegions.find((region) => region.block_type === 'answer')
    const correction = questionRegions.find((region) => region.block_type === 'correction')
    setDraft({
      stemLatex: stem?.text ?? '',
      subject: document?.subject || 'math',
      studentLatex: answer?.text ?? '',
      correctionLatex: correction?.text ?? '',
      studentConfidence: answer?.confidence ?? 0,
      correctionConfidence: correction?.confidence ?? 0,
      tags: [],
    })
    // 只在“选中的题 / 区域”切换时重播远端数据，画布拖动引起的 regions 刷新不覆盖输入。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedKey])

  const handleSelect = useCallback((regionId: string, additive: boolean) => {
    setSelectedIds((prev) => {
      if (!additive) return [regionId]
      return prev.includes(regionId)
        ? prev.filter((id) => id !== regionId)
        : [...prev, regionId]
    })
  }, [])

  const handleCommitBbox = useCallback(
    async (regionId: string, bbox: number[]) => {
      await patchRegion.mutateAsync({ regionId, patch: { bbox } })
    },
    [patchRegion],
  )

  const handleChangeBlockType = (regionId: string, blockType: BlockType) => {
    void patchRegion.mutateAsync({ regionId, patch: { block_type: blockType } }).catch(() => {})
  }

  const changePage = (idx: number) => {
    setActivePageIdx(idx)
    setSelectedIds([])
  }

  const handleMerge = () => {
    if (selectedIds.length < 2) return
    const selected = regions.filter((region) => selectedIds.includes(region.id))
    if (new Set(selected.map((region) => region.page_start)).size > 1) {
      notify('只能合并同一页的区域')
      return
    }
    mergeRegions.mutate(selectedIds, { onSuccess: () => setSelectedIds([]) })
  }

  const crossPage = Boolean(selectedRegion && selectedRegion.page_end > selectedRegion.page_start)

  const toggleCrossPage = () => {
    if (!selectedRegion) return
    if (crossPage) {
      patchRegion.mutate({
        regionId: selectedRegion.id,
        patch: { page_end: selectedRegion.page_start },
      })
      return
    }
    const next = selectedRegion.page_start + 1
    if (next > (document?.page_count ?? 1)) {
      notify('已经是最后一页')
      return
    }
    patchRegion.mutate({ regionId: selectedRegion.id, patch: { page_end: next } })
  }

  const locate = (types: BlockType[]) => {
    const target = questionRegions.find((region) => types.includes(region.block_type))
    if (!target) return
    setSelectedIds([target.id])
    if (target.page_start !== resolvedIdx) setActivePageIdx(target.page_start)
  }

  const job = document?.job ?? null
  const canRetry =
    Boolean(job) &&
    !retryJob.isPending &&
    job?.status !== 'running' &&
    job?.status !== 'queued'

  // 流水线跑完后自动拉一次最新区域，避免用户手动刷新。
  useEffect(() => {
    if (!documentId || job?.status !== 'done') return
    void queryClient.invalidateQueries({ queryKey: ['regions', documentId] })
  }, [documentId, job?.status, queryClient])

  const verdict: Verdict = problem?.marks?.[0]?.verdict ?? 'unknown'
  const badge = VERDICT_META[verdict]
  const stemConfidence =
    questionRegions.find((region) => region.block_type === 'stem')?.confidence ??
    selectedRegion?.confidence ??
    0

  const counts = useMemo(() => {
    const result: Record<BlockType, number> = {
      stem: 0,
      figure: 0,
      answer: 0,
      mark: 0,
      correction: 0,
      noise: 0,
    }
    for (const region of pageRegions) result[region.block_type] += 1
    return result
  }, [pageRegions])

  const confirm = async () => {
    if (!documentId || !draft || !selectedRegion) return
    const regionIds = questionRegions.length
      ? questionRegions.map((region) => region.id)
      : selectedIds
    try {
      const created = await createProblem.mutateAsync({
        document_id: documentId,
        region_ids: regionIds,
        stem_latex: draft.stemLatex,
        subject: draft.subject,
        solutions: buildSolutions(draft, problem?.solutions),
      })
      const tagBody = buildTagBody(draft.tags)
      if (tagBody.knowledge.length || tagBody.method.length) {
        try {
          await replaceTags.mutateAsync({ problemId: created.id, body: tagBody })
        } catch {
          /* 标签写入失败不阻断入库，错误已由 client.ts toast */
        }
      }
      navigate(`/problems/${created.id}`)
    } catch {
      /* client.ts 已统一 toast */
    }
  }

  const save = async () => {
    if (!problem || !draft) return
    setActionNotice('')
    try {
      await patchProblem.mutateAsync({
        problemId: problem.id,
        patch: { stem_latex: draft.stemLatex, subject: draft.subject },
      })
      await replaceSolutions.mutateAsync({
        problemId: problem.id,
        body: buildSolutions(draft, problem.solutions),
      })
      await replaceTags.mutateAsync({ problemId: problem.id, body: buildTagBody(draft.tags) })
      setActionNotice('已保存')
    } catch {
      /* client.ts 已统一 toast */
    }
  }

  if (!documentId) {
    return (
      <div className="page">
        <div className="empty">
          <div className="empty-title">缺少 documentId</div>
          <div>请从上传页进入校对台。</div>
        </div>
      </div>
    )
  }

  return (
    <div className="page" style={{ maxWidth: 'none' }}>
      <div className="page-head">
        <div>
          <h1 className="page-title">校对台</h1>
          <p className="page-desc">
            {document
              ? `${document.source_name} · ${document.subject} · ${document.page_count} 页`
              : '加载文档…'}
            <span className="mono" style={{ marginLeft: 8 }}>
              {documentId}
            </span>
          </p>
        </div>
      </div>

      <div
        className="card"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '10px 16px',
          flexWrap: 'wrap',
        }}
      >
        <span className="row" style={{ gap: 8 }}>
          <span
            className="dot"
            data-state={job?.status === 'failed' ? 'down' : undefined}
            style={
              job
                ? job.status === 'failed'
                  ? undefined
                  : { background: JOB_DOT_COLORS[job.status] }
                : { background: 'var(--ink-3)' }
            }
          />
          <strong style={{ fontSize: 13 }}>{job ? JOB_STATUS_LABELS[job.status] : '无任务'}</strong>
        </span>
        {job && (
          <>
            <span className="muted" style={{ fontSize: 12 }}>
              阶段 {STAGE_LABELS[job.stage]} · {Math.round(job.progress * 100)}%
            </span>
            <Meter value={job.progress} width={120} showValue={false} />
          </>
        )}
        {job?.error && (
          <span style={{ color: 'var(--danger)', fontSize: 12 }}>{job.error}</span>
        )}
        <span className="grow" />
        {regionsQuery.isFetching && (
          <span className="muted" style={{ fontSize: 11 }}>
            同步中…
          </span>
        )}
        <span className="muted" style={{ fontSize: 11 }}>
          区域 {regions.length} 个
        </span>
      </div>

      {documentQuery.isLoading ? (
        <div className="empty">
          <div className="empty-title">加载中…</div>
          <div>正在读取文档与页面信息。</div>
        </div>
      ) : documentQuery.isError ? (
        <div className="empty">
          <div className="empty-title">文档加载失败</div>
          <div>请确认后端 8000 已启动，或返回上传页重新选择。</div>
          <div className="empty-hint">
            <Link to="/upload">去上传</Link>
          </div>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 62fr) minmax(0, 38fr)',
            gap: 'var(--space-5)',
            alignItems: 'start',
          }}
        >
          <div className="stack" style={{ minWidth: 0 }}>
            {regionsQuery.isLoading ? (
              <div className="empty">
                <div className="empty-title">加载区域…</div>
                <div>正在读取版面切分结果。</div>
              </div>
            ) : regions.length === 0 ? (
              <div className="empty">
                <div className="empty-title">流水线未完成或未识别到区域</div>
                <div>等任务跑完后刷新，或回到上传页重新导入作业照片。</div>
                <div className="row-wrap" style={{ justifyContent: 'center', gap: 8 }}>
                  <Link to="/upload" className="btn btn-secondary btn-sm">
                    去上传
                  </Link>
                  <Button
                    size="sm"
                    onClick={() => job && retryJob.mutate(job.id)}
                    disabled={!canRetry}
                  >
                    重新识别
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <PageCanvas
                  pages={pages}
                  page={page}
                  activeIdx={resolvedIdx}
                  onPageChange={changePage}
                  regions={pageRegions}
                  selectedIds={selectedIds}
                  onSelect={handleSelect}
                  onCommitBbox={handleCommitBbox}
                  onChangeBlockType={handleChangeBlockType}
                />

                <div className="row-wrap" style={{ justifyContent: 'space-between', gap: 12 }}>
                  <div className="row-wrap" style={{ gap: 14 }}>
                    {LEGEND.map((meta) => (
                      <span
                        key={meta.value}
                        className="row"
                        style={{ gap: 6, fontSize: 12, color: 'var(--ink-2)' }}
                      >
                        <span
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: 3,
                            background: meta.color,
                            display: 'inline-block',
                          }}
                        />
                        {meta.label}
                        <span className="muted mono">{counts[meta.value]}</span>
                      </span>
                    ))}
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    {selectedIds.length >= 2 && (
                      <Button size="sm" onClick={handleMerge} disabled={mergeRegions.isPending}>
                        合并为题干（{selectedIds.length}）
                      </Button>
                    )}
                    {selectedRegion && (
                      <Chip
                        active={crossPage}
                        onClick={toggleCrossPage}
                        title="把该区域的 page_end 设为下一页"
                      >
                        接下一页
                        {crossPage
                          ? `：${selectedRegion.page_start}–${selectedRegion.page_end}`
                          : '：关'}
                      </Chip>
                    )}
                    <Button
                      size="sm"
                      onClick={() => job && retryJob.mutate(job.id)}
                      disabled={!canRetry}
                    >
                      重新识别
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>

          <aside
            style={{
              position: 'sticky',
              top: 'calc(var(--topbar-h) + var(--space-4))',
              alignSelf: 'start',
              minWidth: 0,
            }}
          >
            <div
              className="card"
              style={{
                display: 'flex',
                flexDirection: 'column',
                maxHeight: 'calc(100vh - var(--topbar-h) - 32px)',
              }}
            >
              <header className="card-head" style={{ alignItems: 'flex-start' }}>
                <div className="grow">
                  <div className="card-title">题目校对</div>
                  <div className="card-sub">
                    {selectedRegion
                      ? `${blockMeta(selectedRegion.block_type).label} · 置信度 ${selectedRegion.confidence.toFixed(2)}`
                      : '未选中区域'}
                    {problem ? ` · 草稿 ${problem.id.slice(0, 8)}` : ' · 尚未装配'}
                  </div>
                </div>
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
              </header>

              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: 'auto',
                  padding: 'var(--space-4)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--space-3)',
                }}
              >
                {!selectedRegion || !draft ? (
                  <div className="empty">
                    <div className="empty-title">未选中区域</div>
                    <div>在左侧画布点击一个彩色框，题干与解答会出现在这里。</div>
                    <div className="empty-hint">Shift 点击可多选并合并为题干</div>
                  </div>
                ) : (
                  <>
                    <StemCard
                      value={draft.stemLatex}
                      onChange={(value) =>
                        setDraft((prev) => (prev ? { ...prev, stemLatex: value } : prev))
                      }
                      confidence={stemConfidence}
                      subject={draft.subject}
                      onSubjectChange={(value) =>
                        setDraft((prev) => (prev ? { ...prev, subject: value } : prev))
                      }
                      onActivate={() => locate(['stem'])}
                    />
                    <SolutionCard
                      verdict={verdict}
                      studentLatex={draft.studentLatex}
                      correctionLatex={draft.correctionLatex}
                      studentConfidence={draft.studentConfidence}
                      correctionConfidence={draft.correctionConfidence}
                      onChangeStudent={(value) =>
                        setDraft((prev) => (prev ? { ...prev, studentLatex: value } : prev))
                      }
                      onChangeCorrection={(value) =>
                        setDraft((prev) => (prev ? { ...prev, correctionLatex: value } : prev))
                      }
                      onActivate={() => locate(['answer', 'correction'])}
                    />
                    <TagEditor
                      tags={draft.tags}
                      onChange={(tags) => setDraft((prev) => (prev ? { ...prev, tags } : prev))}
                    />
                    {problemQuery.isFetching && (
                      <span className="muted" style={{ fontSize: 11 }}>
                        正在同步题目详情…
                      </span>
                    )}
                  </>
                )}
              </div>

              <footer
                style={{
                  position: 'sticky',
                  bottom: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: 'var(--space-3) var(--space-4)',
                  borderTop: '1px solid var(--line)',
                  background: 'var(--surface)',
                }}
              >
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void save()}
                  disabled={!problem || !draft || patchProblem.isPending}
                  title={problem ? '保存题干/解答/标签' : '当前区域尚未绑定题目'}
                >
                  仅保存
                </Button>
                <span className="grow" />
                {actionNotice && (
                  <span className="muted" style={{ fontSize: 12 }}>
                    {actionNotice}
                  </span>
                )}
                <Button
                  variant="primary"
                  onClick={() => void confirm()}
                  disabled={!draft || !selectedRegion || createProblem.isPending}
                >
                  确认入库
                </Button>
              </footer>
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}
