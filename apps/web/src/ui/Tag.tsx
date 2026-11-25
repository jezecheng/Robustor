import type { ReactNode } from 'react'

export type TagProps = {
  children: ReactNode
  type?: 'knowledge' | 'method' | 'pending'
  onRemove?: () => void
  title?: string
}

export function Tag({ children, type = 'knowledge', onRemove, title }: TagProps) {
  return (
    <span className="tag" data-type={type} title={title}>
      {children}
      {onRemove && (
        <button type="button" className="tag-x" onClick={onRemove} aria-label="移除">
          ×
        </button>
      )}
    </span>
  )
}
