import { Chip } from '../../ui/Chip'
import { mediaUrl } from '../../api/client'
import type { BlockType, PageOut, RegionOut } from '../../api/queries/console'
import { RegionLayer } from './RegionLayer'

export type PageCanvasProps = {
  pages: PageOut[]
  page: PageOut | null
  activeIdx: number
  onPageChange: (idx: number) => void
  regions: RegionOut[]
  selectedIds: string[]
  onSelect: (regionId: string, additive: boolean) => void
  onCommitBbox: (regionId: string, bbox: number[], original: number[]) => Promise<unknown>
  onChangeBlockType: (regionId: string, blockType: BlockType) => void
}

export function PageCanvas({
  pages,
  page,
  activeIdx,
  onPageChange,
  regions,
  selectedIds,
  onSelect,
  onCommitBbox,
  onChangeBlockType,
}: PageCanvasProps) {
  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '10px 12px',
          borderBottom: '1px solid var(--line)',
          flexWrap: 'wrap',
        }}
      >
        <span className="muted" style={{ fontSize: 12 }}>
          页面
        </span>
        {pages.map((item) => (
          <Chip key={item.id} active={item.idx === activeIdx} onClick={() => onPageChange(item.idx)}>
            第 {item.idx} 页
          </Chip>
        ))}
        <span className="grow" />
        {page && (
          <span className="muted mono" style={{ fontSize: 11 }}>
            {page.width}×{page.height} · 旋转 {page.rotation}°
          </span>
        )}
      </div>

      <div style={{ padding: 12, background: 'var(--surface-3)' }}>
        {page ? (
          <div style={{ position: 'relative', width: '100%', maxWidth: '100%' }}>
            <img
              src={mediaUrl(page.image_path)}
              alt={`第 ${page.idx} 页`}
              draggable={false}
              style={{
                display: 'block',
                width: '100%',
                maxWidth: '100%',
                height: 'auto',
                borderRadius: 6,
                background: 'var(--surface)',
                userSelect: 'none',
              }}
            />
            <RegionLayer
              regions={regions}
              selectedIds={selectedIds}
              onSelect={onSelect}
              onCommitBbox={onCommitBbox}
              onChangeBlockType={onChangeBlockType}
            />
          </div>
        ) : (
          <div className="empty">
            <div className="empty-title">暂无页面</div>
            <div>文档还没有可显示的页面图像。</div>
          </div>
        )}
      </div>

      <div
        style={{
          padding: '8px 12px',
          borderTop: '1px solid var(--line)',
          fontSize: 12,
          color: 'var(--ink-3)',
        }}
      >
        拖动框体移动 · 拖四角/四边改尺寸 · 双击改类型 · Shift 点击多选
      </div>
    </div>
  )
}

export default PageCanvas
