export type MeterProps = {
  value: number // 0–1
  width?: number
  showValue?: boolean
}

export function Meter({ value, width, showValue = true }: MeterProps) {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0))
  const level = clamped >= 0.9 ? 'ok' : clamped >= 0.75 ? 'warn' : 'alert'
  return (
    <span className="meter" data-level={level} style={width ? { width } : undefined}>
      <span className="meter-track">
        <span className="meter-fill" style={{ width: `${clamped * 100}%` }} />
      </span>
      {showValue && <span className="meter-value">{clamped.toFixed(2)}</span>}
    </span>
  )
}
