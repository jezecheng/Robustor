import type { CSSProperties, MouseEvent } from 'react'
import { Card } from '../../ui/Card'
import { Meter } from '../../ui/Meter'
import { Latex } from '../common/Latex'

export type StemCardProps = {
  value: string
  onChange: (value: string) => void
  confidence: number
  subject: string
  onSubjectChange: (subject: string) => void
  onActivate?: () => void
}

const SUBJECTS = ['math', 'physics', 'chemistry', 'biology', 'chinese', 'english']

const TEXTAREA_STYLE: CSSProperties = {
  width: '100%',
  minHeight: 92,
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
  minHeight: 38,
}

export function StemCard({ value, onChange, confidence, subject, onSubjectChange, onActivate }: StemCardProps) {
  const handleClick = (event: MouseEvent<HTMLDivElement>) => {
    const tag = (event.target as HTMLElement).tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'BUTTON' || tag === 'OPTION') return
    onActivate?.()
  }

  return (
    <div onClick={handleClick} style={{ cursor: onActivate ? 'pointer' : 'default' }}>
      <Card
        title="题干"
        subtitle="编辑 LaTeX，右侧实时预览"
        actions={<Meter value={confidence} width={96} />}
      >
        <div className="stack">
          <div className="row">
            <span className="muted" style={{ fontSize: 12, width: 32 }}>
              学科
            </span>
            <input
              list="stem-subject-options"
              value={subject}
              onChange={(event) => onSubjectChange(event.target.value)}
              style={{ ...TEXTAREA_STYLE, minHeight: 0, width: 160, padding: '5px 8px' }}
            />
            <datalist id="stem-subject-options">
              {SUBJECTS.map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
            <span className="muted mono" style={{ fontSize: 11 }}>
              识别置信度
            </span>
          </div>

          <textarea
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="题干 LaTeX，例如 x^2-5x+6=0"
            style={TEXTAREA_STYLE}
            spellCheck={false}
          />

          <div style={PREVIEW_STYLE}>
            <Latex value={value} block />
          </div>
        </div>
      </Card>
    </div>
  )
}

export default StemCard
