import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import type { ApiError } from '../api/client'

const NAV = [
  { to: '/upload', label: '上传', hint: '拍照 / 选图入库', end: false },
  { to: '/problems', label: '错题本', hint: '筛选、详情、复习', end: false },
  { to: '/knowledge', label: '知识图谱', hint: '知识点与先修关系', end: false },
  { to: '/stats', label: '统计', hint: '知识点与方法论', end: false },
  { to: '/ai-usage', label: 'AI 用量', hint: 'Token 消耗与请求明细', end: false },
  { to: '/settings', label: '设置', hint: '墨迹方案 / 词表', end: false },
]

export default function Layout() {
  const [toast, setToast] = useState<string>('')
  const location = useLocation()

  useEffect(() => {
    const onError = (event: Event) => {
      const detail = (event as CustomEvent<ApiError>).detail
      setToast(detail?.message || '请求失败')
    }
    window.addEventListener('api-error', onError)
    return () => window.removeEventListener('api-error', onError)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 3600)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    document.title = 'Robustor · 错题本 Prototype'
  }, [location.pathname])

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-mark">R</span>
          Robustor
          <span className="topbar-sub">错题本 prototype</span>
        </div>
        <div className="topbar-right">
          <span className="muted mono">mock pipeline</span>
        </div>
      </header>

      <nav className="sidebar">
        <div className="sidebar-group">工作流</div>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            {item.label}
            <small>{item.hint}</small>
          </NavLink>
        ))}
      </nav>

      <main className="content">
        <Outlet />
      </main>

      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}
