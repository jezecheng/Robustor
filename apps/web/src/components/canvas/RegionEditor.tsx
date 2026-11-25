import { BLOCK_TYPE_META, toBox } from '../../api/queries/console'
import type { BlockType, RegionOut } from '../../api/queries/console'

export type RegionEditorProps = {
  region: RegionOut
  onPick: (type: BlockType) => void
  onClose: () => void
}

/** 双击区域后浮出的小菜单：只做 block_type 的六选一。 */
export function RegionEditor({ region, onPick, onClose }: RegionEditorProps) {
  const [x, y] = toBox(region.bbox)
  const above = y > 0.28

  return (
    <div
      style={{
        position: 'absolute',
        left: `${Math.min(Math.max(x, 0), 0.55) * 100}%`,
        top: `${y * 100}%`,
        transform: above ? 'translateY(calc(-100% - 10px))' : 'translateY(10px)',
        zIndex: 6,
      }}
      onPointerDown={(event) => event.stopPropagation()}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <div
        className="card"
        style={{ padding: 10, boxShadow: 'var(--shadow)', background: 'var(--surface)', width: 216 }}
      >
        <div style={{ fontSize: 11, color: 'var(--ink-3)', marginBottom: 8 }}>区域类型 · 双击修改</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {BLOCK_TYPE_META.map((meta) => {
            const active = meta.value === region.block_type
            return (
              <button
                key={meta.value}
                type="button"
                className={`btn btn-sm ${active ? 'btn-primary' : 'btn-secondary'}`}
                style={active ? { background: meta.color, borderColor: meta.color } : undefined}
                onClick={() => onPick(meta.value)}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: 2,
                    background: active ? '#fff' : meta.color,
                    display: 'inline-block',
                  }}
                />
                {meta.label}
              </button>
            )
          })}
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          style={{ width: '100%', marginTop: 8 }}
          onClick={onClose}
        >
          关闭
        </button>
      </div>
    </div>
  )
}

export default RegionEditor
