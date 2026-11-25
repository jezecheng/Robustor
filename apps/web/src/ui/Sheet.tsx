import { useEffect } from 'react'
import type { ReactNode } from 'react'

export type SheetProps = {
  open: boolean
  title?: ReactNode
  onClose: () => void
  footer?: ReactNode
  children?: ReactNode
}

export function Sheet({ open, title, onClose, footer, children }: SheetProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="sheet-backdrop" onClick={onClose} role="presentation">
      <aside className="sheet" onClick={(event) => event.stopPropagation()}>
        <header className="sheet-head">
          <div className="grow card-title">{title}</div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            关闭
          </button>
        </header>
        <div className="sheet-body">{children}</div>
        {footer && <footer className="sheet-foot">{footer}</footer>}
      </aside>
    </div>
  )
}
