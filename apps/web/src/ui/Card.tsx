import type { ReactNode } from 'react'

export type CardProps = {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  footer?: ReactNode
  children?: ReactNode
  className?: string
}

export function Card({ title, subtitle, actions, footer, children, className = '' }: CardProps) {
  return (
    <section className={`card ${className}`.trim()}>
      {(title || actions) && (
        <header className="card-head">
          <div className="grow">
            {title && <div className="card-title">{title}</div>}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {actions}
        </header>
      )}
      <div className="card-body">{children}</div>
      {footer && <footer className="card-foot">{footer}</footer>}
    </section>
  )
}
