import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import { blockMeta, toBox } from '../../api/queries/console'
import type { BlockType, Box, RegionOut } from '../../api/queries/console'
import { RegionEditor } from './RegionEditor'

type ResizeDir = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'
type DragMode = ResizeDir | 'move'

type DragState = {
  id: string
  mode: DragMode
  startX: number
  startY: number
  origin: Box
  width: number
  height: number
  last?: Box
}

const MIN_SIZE = 0.02
const EPS = 1e-4

const HANDLE_DEFS: { dir: ResizeDir; left: string; top: string; cursor: string }[] = [
  { dir: 'nw', left: '0%', top: '0%', cursor: 'nwse-resize' },
  { dir: 'n', left: '50%', top: '0%', cursor: 'ns-resize' },
  { dir: 'ne', left: '100%', top: '0%', cursor: 'nesw-resize' },
  { dir: 'e', left: '100%', top: '50%', cursor: 'ew-resize' },
  { dir: 'se', left: '100%', top: '100%', cursor: 'nwse-resize' },
  { dir: 's', left: '50%', top: '100%', cursor: 'ns-resize' },
  { dir: 'sw', left: '0%', top: '100%', cursor: 'nesw-resize' },
  { dir: 'w', left: '0%', top: '50%', cursor: 'ew-resize' },
]

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const sameBox = (a: Box, b: Box) =>
  Math.abs(a[0] - b[0]) < EPS &&
  Math.abs(a[1] - b[1]) < EPS &&
  Math.abs(a[2] - b[2]) < EPS &&
  Math.abs(a[3] - b[3]) < EPS

function moveBox(origin: Box, dx: number, dy: number): Box {
  const x = clamp(origin[0] + dx, 0, Math.max(0, 1 - origin[2]))
  const y = clamp(origin[1] + dy, 0, Math.max(0, 1 - origin[3]))
  return [x, y, origin[2], origin[3]]
}

function resizeBox(origin: Box, dir: ResizeDir, dx: number, dy: number): Box {
  let x1 = origin[0]
  let y1 = origin[1]
  let x2 = origin[0] + origin[2]
  let y2 = origin[1] + origin[3]
  if (dir.includes('w')) x1 = clamp(x1 + dx, 0, x2 - MIN_SIZE)
  if (dir.includes('e')) x2 = clamp(x2 + dx, x1 + MIN_SIZE, 1)
  if (dir.includes('n')) y1 = clamp(y1 + dy, 0, y2 - MIN_SIZE)
  if (dir.includes('s')) y2 = clamp(y2 + dy, y1 + MIN_SIZE, 1)
  return [x1, y1, x2 - x1, y2 - y1]
}

export type RegionLayerProps = {
  regions: RegionOut[]
  selectedIds: string[]
  onSelect: (regionId: string, additive: boolean) => void
  /** pointerup 才提交；失败由调用方抛错，本层回滚到拖动前的 bbox。 */
  onCommitBbox: (regionId: string, bbox: number[], original: number[]) => Promise<unknown>
  onChangeBlockType: (regionId: string, blockType: BlockType) => void
}

export function RegionLayer({
  regions,
  selectedIds,
  onSelect,
  onCommitBbox,
  onChangeBlockType,
}: RegionLayerProps) {
  const layerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<DragState | null>(null)
  const [drafts, setDrafts] = useState<Record<string, Box>>({})
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)

  // 服务端 bbox 追上本地草稿后清掉草稿，避免下一次渲染闪回旧位置。
  useEffect(() => {
    setDrafts((prev) => {
      let changed = false
      const next: Record<string, Box> = { ...prev }
      for (const region of regions) {
        const draft = next[region.id]
        if (draft && sameBox(draft, toBox(region.bbox))) {
          delete next[region.id]
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [regions])

  const beginDrag = (event: ReactPointerEvent<HTMLElement>, region: RegionOut, mode: DragMode) => {
    if (event.button !== 0) return
    const layer = layerRef.current
    if (!layer) return
    const rect = layer.getBoundingClientRect()
    if (!rect.width || !rect.height) return
    event.stopPropagation()
    event.preventDefault()
    setEditingId(null)
    const target = event.currentTarget
    target.setPointerCapture(event.pointerId)
    dragRef.current = {
      id: region.id,
      mode,
      startX: event.clientX,
      startY: event.clientY,
      origin: toBox(region.bbox),
      width: rect.width,
      height: rect.height,
    }
    if (mode === 'move') {
      if (event.shiftKey) onSelect(region.id, true)
      else if (!selectedIds.includes(region.id)) onSelect(region.id, false)
    } else if (!selectedIds.includes(region.id)) {
      onSelect(region.id, false)
    }
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag) return
    const dx = (event.clientX - drag.startX) / drag.width
    const dy = (event.clientY - drag.startY) / drag.height
    const next = drag.mode === 'move' ? moveBox(drag.origin, dx, dy) : resizeBox(drag.origin, drag.mode, dx, dy)
    drag.last = next
    setDrafts((prev) => ({ ...prev, [drag.id]: next }))
  }

  const handlePointerUp = () => {
    const drag = dragRef.current
    dragRef.current = null
    if (!drag) return
    const finalBox = drag.last ?? drafts[drag.id]
    if (!finalBox) return
    if (sameBox(finalBox, drag.origin)) {
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[drag.id]
        return next
      })
      return
    }
    void onCommitBbox(drag.id, finalBox, drag.origin).catch(() => {
      setDrafts((prev) => ({ ...prev, [drag.id]: drag.origin }))
    })
  }

  const editingRegion = editingId ? regions.find((region) => region.id === editingId) ?? null : null

  return (
    <div
      ref={layerRef}
      style={{ position: 'absolute', inset: 0, overflow: 'hidden', borderRadius: 6 }}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onPointerDown={() => setEditingId(null)}
    >
      {regions.map((region) => {
        const meta = blockMeta(region.block_type)
        const box = drafts[region.id] ?? toBox(region.bbox)
        const selected = selectedIds.includes(region.id)
        const hovered = hoveredId === region.id
        const boxStyle: CSSProperties = {
          position: 'absolute',
          left: `${box[0] * 100}%`,
          top: `${box[1] * 100}%`,
          width: `${box[2] * 100}%`,
          height: `${box[3] * 100}%`,
          border: `${selected ? 3 : 2}px solid ${meta.color}`,
          borderRadius: 4,
          boxSizing: 'border-box',
          cursor: 'move',
          touchAction: 'none',
          boxShadow: selected
            ? `0 0 0 3px color-mix(in srgb, ${meta.color} 28%, transparent), 0 0 18px color-mix(in srgb, ${meta.color} 50%, transparent)`
            : 'none',
          zIndex: selected ? 3 : 2,
        }
        return (
          <div
            key={region.id}
            style={boxStyle}
            onPointerDown={(event) => beginDrag(event, region, 'move')}
            onPointerEnter={() => setHoveredId(region.id)}
            onPointerLeave={() => setHoveredId((current) => (current === region.id ? null : current))}
            onDoubleClick={(event) => {
              event.stopPropagation()
              setEditingId(region.id)
            }}
            title={`${meta.label} · 置信度 ${region.confidence.toFixed(2)}`}
          >
            <span
              style={{
                position: 'absolute',
                inset: 0,
                background: meta.color,
                opacity: 0.08,
                pointerEvents: 'none',
              }}
            />
            {hovered && (
              <span
                style={{
                  position: 'absolute',
                  left: 2,
                  top: 2,
                  padding: '1px 5px',
                  borderRadius: 4,
                  background: 'rgba(28, 25, 23, 0.8)',
                  color: '#fff',
                  fontSize: 11,
                  lineHeight: 1.5,
                  whiteSpace: 'nowrap',
                  pointerEvents: 'none',
                }}
              >
                {meta.label} · {region.confidence.toFixed(2)}
              </span>
            )}
            {region.page_end > region.page_start && (
              <span
                style={{
                  position: 'absolute',
                  right: 0,
                  top: 0,
                  transform: 'translate(38%, -38%)',
                  padding: '0 5px',
                  borderRadius: 999,
                  background: meta.color,
                  color: '#fff',
                  fontSize: 10,
                  fontWeight: 700,
                  lineHeight: '15px',
                  pointerEvents: 'none',
                  whiteSpace: 'nowrap',
                }}
              >
                {region.page_start}–{region.page_end}
              </span>
            )}
            {selected &&
              HANDLE_DEFS.map((handle) => (
                <span
                  key={handle.dir}
                  onPointerDown={(event) => beginDrag(event, region, handle.dir)}
                  onDoubleClick={(event) => event.stopPropagation()}
                  style={{
                    position: 'absolute',
                    left: handle.left,
                    top: handle.top,
                    width: 10,
                    height: 10,
                    marginLeft: -5,
                    marginTop: -5,
                    borderRadius: 2,
                    background: '#fff',
                    border: `2px solid ${meta.color}`,
                    cursor: handle.cursor,
                    touchAction: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              ))}
          </div>
        )
      })}

      {editingRegion && (
        <RegionEditor
          region={editingRegion}
          onPick={(type) => {
            onChangeBlockType(editingRegion.id, type)
            setEditingId(null)
          }}
          onClose={() => setEditingId(null)}
        />
      )}
    </div>
  )
}

export default RegionLayer
