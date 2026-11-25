import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
}

export function Button({ variant = 'secondary', size = 'md', className = '', ...rest }: ButtonProps) {
  const classes = ['btn', `btn-${variant}`, size === 'md' ? '' : `btn-${size}`, className]
    .filter(Boolean)
    .join(' ')
  return <button className={classes} {...rest} />
}
