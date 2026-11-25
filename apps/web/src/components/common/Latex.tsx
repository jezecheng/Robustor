import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

export type LatexProps = {
  value: string
  block?: boolean
  className?: string
}

/** 全站唯一 KaTeX 渲染入口。throwOnError=false，失败降级为原文，绝不白屏。 */
export function Latex({ value, block = false, className = '' }: LatexProps) {
  const html = useMemo(() => {
    const source = (value ?? '').trim()
    if (!source) return ''
    try {
      return katex.renderToString(source, {
        throwOnError: false,
        displayMode: block,
        output: 'html',
        strict: false,
      })
    } catch {
      return ''
    }
  }, [value, block])

  if (!html) {
    return value ? <code className="latex-raw">{value}</code> : <span className="muted">—</span>
  }
  return (
    <span
      className={['latex', block ? 'latex-block' : '', className].filter(Boolean).join(' ')}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

export default Latex
