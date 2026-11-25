import type { CSSProperties, MouseEvent, ReactNode } from 'react'
import { Card } from '../../ui/Card'
import { Meter } from '../../ui/Meter'
import { Latex } from '../common/Latex'
import type { Verdict } from '../../api/queries/console'

export type SolutionCardProps = {
  verdict: Verdict
  studentLatex: string
  correctionLatex: string
  studentConfidence: number
  correctionConfidence: number
  onChangeStudent: (value: string) => void
  onChangeCorrection: (value: string) => void
  onActivate?: () => void
}

const TEXTAREA_STYLE: CSSProperties = {
  width: '100%',
  minHeight: 76,
  resize: 'vertical',
  padding: '8px 10px',
  border: '1px solid var(--line-strong)',
  borderRadius: 'var(--radius-sm)',
  background: 'var(--surface-2)',
  color: 'var(--ink)',
  fontFamily: 'var(--font-mono)',
  fontSize: 13,
  lineHeight: 1.6,
}

const PREVIEW_STYLE: CSSProperties = {
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius-sm)',
  padding: '8px 10px',
  background: 'var(--surface-2)',
  overflowX: 'auto',
  minHeight: 34,
}

type BlockProps = {
  title: string
  hint: string
  value: string
  confidence: number
  onChange: (value: string) => void
  badge?: ReactNode
}

function SolutionBlock({ title, hint, value, confidence, onChange, badge }: BlockProps) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row">
        <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
        {badge}
        <span className="grow" />
        <Meter value={confidence} width={88} />
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={hint}
        style={TEXTAREA_STYLE}
        spellCheck={false}
      />
      <div style={PREVIEW_STYLE}>
        <Latex value={value} block />
      </div>
    </div>
  )
}

export function SolutionCard({
  verdict,
  studentLatex,
  correctionLatex,
  studentConfidence,
  correctionConfidence,
  onChangeStudent,
  onChangeCorrection,
  onActivate,
}: SolutionCardProps) {
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    const tag = (event.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON') return
    onActivate?.()
  }

  return (
    <div onClick={handleClick} style={{ cursor: onActivate ? 'pointer' : 'default' }}>
      <Card title="学生解答与订正" subtitle="红色批改对应错解，蓝色为学生订正">
        <div className="stack" style={{ gap: 16 }}>
          <SolutionBlock
            title="学生错解"
            hint="学生作答的 LaTeX"
            value={studentLatex}
            confidence={studentConfidence}
            onChange={onChangeStudent}
            badge={
              verdict === 'wrong' ? (
                <span
                  style={{
                    padding: '0 8px',
                    borderRadius: 999,
                    background: 'var(--danger-soft)',
                    color: 'var(--danger)',
                    fontSize: 11,
                    fontWeight: 600,
                    lineHeight: '18px',
                  }}
                >
                  判定：错
                </span>
              ) : null
            }
          />
          <div style={{ height: 1, background: 'var(--line)' }} />
          <SolutionBlock
            title="订正"
            hint="蓝笔订正的 LaTeX"
            value={correctionLatex}
            confidence={correctionConfidence}
            onChange={onChangeCorrection}
          />
        </div>
      </Card>
    </div>
  )
}

export default SolutionCard
