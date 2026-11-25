import type { ReactNode } from 'react'

export type ChipProps = {
  children: ReactNode
  active?: boolean
  onClick?: () => void
  title?: string
}

export function Chip({ children, active = false, onClick, title }: ChipProps) {
  const classes = ['chip', active ? 'active' : '', onClick ? '' : 'chip-static'].filter(Boolean).join(' ')
  return (
    <button type="button" className={classes} onClick={onClick} title={title} disabled={!onClick}>
      {children}
    </button>
  )
}
