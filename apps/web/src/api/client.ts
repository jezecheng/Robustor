export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export const API_BASE = '/api'

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch (error) {
    const netError = new ApiError('无法连接后端（8000）', 0)
    window.dispatchEvent(new CustomEvent('api-error', { detail: netError }))
    throw netError
  }

  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`
    try {
      const data = await response.json()
      if (typeof data?.detail === 'string') detail = data.detail
      else if (data?.detail) detail = JSON.stringify(data.detail)
    } catch {
      /* 非 JSON 错误体，保留 statusText */
    }
    const apiError = new ApiError(detail, response.status)
    window.dispatchEvent(new CustomEvent('api-error', { detail: apiError }))
    throw apiError
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/** 后端 image_path 形如 media/pages/xxx/p1.jpg */
export function mediaUrl(path: string): string {
  if (!path) return ''
  return path.startsWith('/') ? path : `/${path}`
}

export function postJSON<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export function patchJSON<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}

export function putJSON<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, { method: 'PUT', body: JSON.stringify(body) })
}
