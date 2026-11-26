import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { TaxonomyGraphEdge, TaxonomyTopic } from '../../api/queries/taxonomy'

export type GraphCanvasHandle = {
  zoomIn: () => void
  zoomOut: () => void
  reset: () => void
}

type GraphCanvasProps = {
  nodes: TaxonomyTopic[]
  edges: TaxonomyGraphEdge[]
  selectedId?: string
  onSelect: (id: string) => void
}

type SimNode = TaxonomyTopic & {
  x: number
  y: number
  vx: number
  vy: number
  fixed: boolean
  degree: number
}

type SimEdge = {
  source: string
  target: string
  strength: string
  a: SimNode
  b: SimNode
}

type Transform = { k: number; x: number; y: number }

type DragState = {
  mode: 'pan' | 'node'
  pointerId: number
  startX: number
  startY: number
  originX: number
  originY: number
  nodeId?: string
  offsetX: number
  offsetY: number
  moved: boolean
}

const TYPE_COLOR: Record<string, string> = {
  conceptual: '#2f5bd7',
  procedural: '#0e8f7e',
  representational: '#7c3aed',
  strategic: '#c27c0e',
}
const FALLBACK_COLOR = '#8a8378'
const ZOOM_MIN = 0.25
const ZOOM_MAX = 2.4

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function seedOf(id: string) {
  let hash = 0
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) | 0
  return Math.abs(hash)
}

function nodeRadius(degree: number) {
  return 6 + Math.min(5, Math.sqrt(degree) * 2.1)
}

function shortLabel(name: string) {
  return name.length > 13 ? `${name.slice(0, 13)}…` : name
}

/**
 * 力导向图谱画布：SVG 渲染 + 简易物理布局，支持平移、缩放、拖动节点与点击选中。
 */
const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(function GraphCanvas(
  { nodes, edges, selectedId, onSelect },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const simRef = useRef<{ nodes: SimNode[]; edges: SimEdge[] }>({ nodes: [], edges: [] })
  const rafRef = useRef<number | null>(null)
  const alphaRef = useRef(1)
  const needsFitRef = useRef(true)
  const dragRef = useRef<DragState | null>(null)
  const sizeRef = useRef({ w: 0, h: 0 })
  const transformRef = useRef<Transform>({ k: 1, x: 0, y: 0 })

  const [, setFrame] = useState(0)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [transform, setTransform] = useState<Transform>({ k: 1, x: 0, y: 0 })

  sizeRef.current = size
  transformRef.current = transform

  const fit = useCallback(() => {
    const list = simRef.current.nodes
    const { w, h } = sizeRef.current
    if (!w || !h) return
    if (!list.length) {
      setTransform({ k: 1, x: w / 2, y: h / 2 })
      needsFitRef.current = false
      return
    }
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const node of list) {
      minX = Math.min(minX, node.x)
      minY = Math.min(minY, node.y)
      maxX = Math.max(maxX, node.x)
      maxY = Math.max(maxY, node.y)
    }
    const pad = 76
    const bw = Math.max(maxX - minX, 60)
    const bh = Math.max(maxY - minY, 60)
    const k = clamp(Math.min((w - pad * 2) / bw, (h - pad * 2) / bh), ZOOM_MIN, 1.55)
    setTransform({
      k,
      x: w / 2 - ((minX + maxX) / 2) * k,
      y: h / 2 - ((minY + maxY) / 2) * k,
    })
    needsFitRef.current = false
  }, [])
  const fitRef = useRef(fit)
  fitRef.current = fit

  const step = useCallback(() => {
    const { nodes: list, edges: links } = simRef.current
    if (!list.length) {
      rafRef.current = null
      return
    }
    const alpha = Math.max(alphaRef.current, 0.02)
    const repulsion = list.length > 120 ? 1050 : list.length > 60 ? 1500 : 2200

    for (let i = 0; i < list.length; i += 1) {
      const a = list[i]
      for (let j = i + 1; j < list.length; j += 1) {
        const b = list[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        let d2 = dx * dx + dy * dy
        if (d2 < 1) {
          dx = (seedOf(a.id + b.id) % 17) - 8 || 0.5
          dy = (seedOf(b.id + a.id) % 13) - 6 || 0.5
          d2 = dx * dx + dy * dy
        }
        const d = Math.sqrt(d2)
        const force = (repulsion / d2) * alpha
        const fx = (dx / d) * force
        const fy = (dy / d) * force
        a.vx -= fx
        a.vy -= fy
        b.vx += fx
        b.vy += fy
      }
    }

    for (const link of links) {
      const { a, b } = link
      const dx = b.x - a.x
      const dy = b.y - a.y
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01
      const soft = link.strength === 'soft'
      const target = soft ? 118 : 88
      const strength = (soft ? 0.012 : 0.032) * alpha
      const diff = (d - target) * strength
      const fx = (dx / d) * diff
      const fy = (dy / d) * diff
      a.vx += fx
      a.vy += fy
      b.vx -= fx
      b.vy -= fy
    }

    for (const node of list) {
      if (node.fixed) {
        node.vx = 0
        node.vy = 0
        continue
      }
      node.vx -= node.x * 0.012 * alpha
      node.vy -= node.y * 0.012 * alpha
      node.vx *= 0.84
      node.vy *= 0.84
      node.x += node.vx
      node.y += node.vy
    }

    alphaRef.current = alpha * 0.97
    setFrame((value) => value + 1)
    if (alphaRef.current > 0.005) {
      rafRef.current = window.requestAnimationFrame(step)
    } else {
      rafRef.current = null
      if (needsFitRef.current) fitRef.current()
    }
  }, [])

  const wake = useCallback(() => {
    alphaRef.current = Math.max(alphaRef.current, 0.4)
    if (rafRef.current === null) rafRef.current = window.requestAnimationFrame(step)
  }, [step])

  useEffect(() => {
    if (rafRef.current !== null) {
      window.cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    return () => {
      if (rafRef.current !== null) {
        window.cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  const dataKey = `${nodes.map((node) => node.id).join('|')}#${edges
    .map((edge) => `${edge.source}>${edge.target}`)
    .join('|')}`

  useEffect(() => {
    const previous = new Map(simRef.current.nodes.map((node) => [node.id, node]))
    const simNodes: SimNode[] = nodes.map((node, index) => {
      const old = previous.get(node.id)
      if (old) {
        return { ...node, x: old.x, y: old.y, vx: old.vx * 0.4, vy: old.vy * 0.4, fixed: false, degree: 0 }
      }
      const seed = seedOf(node.id)
      const angle = ((seed % 360) / 180) * Math.PI
      const radius = 70 + Math.sqrt(index + 1) * 18 + (seed % 40)
      return {
        ...node,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        fixed: false,
        degree: 0,
      }
    })
    const map = new Map(simNodes.map((node) => [node.id, node]))
    const simEdges: SimEdge[] = []
    for (const edge of edges) {
      const a = map.get(edge.source)
      const b = map.get(edge.target)
      if (!a || !b || a.id === b.id) continue
      a.degree += 1
      b.degree += 1
      simEdges.push({ source: edge.source, target: edge.target, strength: edge.strength, a, b })
    }
    simRef.current = { nodes: simNodes, edges: simEdges }
    alphaRef.current = 1
    needsFitRef.current = true
    setFrame((value) => value + 1)
    if (rafRef.current !== null) window.cancelAnimationFrame(rafRef.current)
    rafRef.current = window.requestAnimationFrame(step)
  }, [dataKey, step])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect
      if (rect) setSize({ w: rect.width, h: rect.height })
    })
    observer.observe(element)
    setSize({ w: element.clientWidth, h: element.clientHeight })
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!size.w || !size.h) return
    if (needsFitRef.current) fitRef.current()
    else {
      setTransform((current) =>
        current.x === 0 && current.y === 0 ? { k: 1, x: size.w / 2, y: size.h / 2 } : current,
      )
    }
  }, [size.w, size.h])

  useEffect(() => {
    const element = svgRef.current
    if (!element) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = element.getBoundingClientRect()
      const cx = event.clientX - rect.left
      const cy = event.clientY - rect.top
      const factor = Math.exp(-event.deltaY * 0.0015)
      setTransform((current) => {
        const k = clamp(current.k * factor, ZOOM_MIN, ZOOM_MAX)
        const ratio = k / current.k
        return { k, x: cx - (cx - current.x) * ratio, y: cy - (cy - current.y) * ratio }
      })
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [])

  const zoomBy = useCallback((factor: number) => {
    const { w, h } = sizeRef.current
    setTransform((current) => {
      const k = clamp(current.k * factor, ZOOM_MIN, ZOOM_MAX)
      const ratio = k / current.k
      return { k, x: w / 2 - (w / 2 - current.x) * ratio, y: h / 2 - (h / 2 - current.y) * ratio }
    })
  }, [])

  useImperativeHandle(
    ref,
    () => ({
      zoomIn: () => zoomBy(1.3),
      zoomOut: () => zoomBy(1 / 1.3),
      reset: () => fitRef.current(),
    }),
    [zoomBy],
  )

  const toWorld = (clientX: number, clientY: number) => {
    const element = svgRef.current
    const current = transformRef.current
    if (!element) return { x: 0, y: 0 }
    const rect = element.getBoundingClientRect()
    return {
      x: (clientX - rect.left - current.x) / current.k,
      y: (clientY - rect.top - current.y) / current.k,
    }
  }

  const onBackgroundDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = {
      mode: 'pan',
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: transformRef.current.x,
      originY: transformRef.current.y,
      offsetX: 0,
      offsetY: 0,
      moved: false,
    }
  }

  const onNodeDown = (event: ReactPointerEvent<SVGGElement>, node: SimNode) => {
    if (event.button !== 0) return
    event.stopPropagation()
    const element = svgRef.current
    if (!element) return
    element.setPointerCapture(event.pointerId)
    const point = toWorld(event.clientX, event.clientY)
    dragRef.current = {
      mode: 'node',
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: 0,
      originY: 0,
      nodeId: node.id,
      offsetX: node.x - point.x,
      offsetY: node.y - point.y,
      moved: false,
    }
    alphaRef.current = Math.max(alphaRef.current, 0.35)
  }

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    if (Math.abs(event.clientX - drag.startX) + Math.abs(event.clientY - drag.startY) > 3) {
      drag.moved = true
    }
    if (drag.mode === 'pan') {
      const dx = event.clientX - drag.startX
      const dy = event.clientY - drag.startY
      setTransform((current) => ({ ...current, x: drag.originX + dx, y: drag.originY + dy }))
      return
    }
    const node = simRef.current.nodes.find((item) => item.id === drag.nodeId)
    if (!node) return
    const point = toWorld(event.clientX, event.clientY)
    node.x = point.x + drag.offsetX
    node.y = point.y + drag.offsetY
    node.vx = 0
    node.vy = 0
    node.fixed = true
    wake()
    setFrame((value) => value + 1)
  }

  const onPointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== event.pointerId) return
    dragRef.current = null
    if (drag.mode === 'node') {
      const node = simRef.current.nodes.find((item) => item.id === drag.nodeId)
      if (node) {
        node.fixed = false
        node.vx = 0
        node.vy = 0
      }
      if (!drag.moved && drag.nodeId) onSelect(drag.nodeId)
      wake()
    }
  }

  const { nodes: simNodes, edges: simEdges } = simRef.current
  const selectedNeighbors = new Set<string>()
  if (selectedId) {
    for (const edge of simEdges) {
      if (edge.source === selectedId) selectedNeighbors.add(edge.target)
      if (edge.target === selectedId) selectedNeighbors.add(edge.source)
    }
  }
  const showAllLabels = simNodes.length <= 80

  return (
    <div ref={containerRef} className="kg-canvas">
      <svg
        ref={svgRef}
        className="kg-svg"
        role="img"
        aria-label="知识图谱节点关系网络"
        onPointerDown={onBackgroundDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={(event) => event.preventDefault()}
      >
        <defs>
          <marker
            id="kg-arrow"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L8 4 L0 8 Z" fill="#c9c2b5" />
          </marker>
          <marker
            id="kg-arrow-active"
            viewBox="0 0 8 8"
            refX="7"
            refY="4"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M0 0 L8 4 L0 8 Z" fill="#2f5bd7" />
          </marker>
        </defs>
        <g transform={`translate(${transform.x} ${transform.y}) scale(${transform.k})`}>
          {simEdges.map((edge) => {
            const active = selectedId === edge.source || selectedId === edge.target
            const dimmed = Boolean(selectedId) && !active
            return (
              <line
                key={`${edge.source}-${edge.target}`}
                className={`kg-link${active ? ' is-active' : ''}${dimmed ? ' is-dim' : ''}`}
                x1={edge.a.x}
                y1={edge.a.y}
                x2={edge.b.x}
                y2={edge.b.y}
                strokeDasharray={edge.strength === 'soft' ? '4 5' : undefined}
                markerEnd={`url(#${active ? 'kg-arrow-active' : 'kg-arrow'})`}
              />
            )
          })}
          {simNodes.map((node) => {
            const selected = node.id === selectedId
            const near = selectedNeighbors.has(node.id)
            const color = TYPE_COLOR[node.topic_type ?? ''] ?? FALLBACK_COLOR
            const radius = nodeRadius(node.degree) + (selected ? 2 : 0)
            const dimmed = Boolean(selectedId) && !selected && !near
            const showLabel = !dimmed && (showAllLabels || selected || near || node.degree >= 3)
            return (
              <g
                key={node.id}
                className={`kg-node${selected ? ' is-selected' : ''}${near ? ' is-near' : ''}${
                  dimmed ? ' is-dim' : ''
                }`}
                transform={`translate(${node.x} ${node.y})`}
                onPointerDown={(event) => onNodeDown(event, node)}
              >
                <title>{`${node.name}${node.chapter ? ` · ${node.chapter}` : ''}`}</title>
                {selected && <circle className="kg-node-ring" r={radius + 5} stroke={color} />}
                <circle r={radius} fill={color} />
                {showLabel && (
                  <text y={radius + 12} textAnchor="middle">
                    {shortLabel(node.name)}
                  </text>
                )}
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
})

export default GraphCanvas
