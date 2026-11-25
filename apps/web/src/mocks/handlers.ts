import { http, HttpResponse } from 'msw'

/** 只覆盖 WP0 已知的最小接口，供后端未就绪时前端自测（VITE_USE_MOCK=1 npm run dev）。 */
export const handlers = [
  http.get('/api/documents', () => HttpResponse.json([])),
  http.get('/api/tags', () => HttpResponse.json([])),
  http.get('/api/stats/overview', () =>
    HttpResponse.json({ total: 0, by_subject: [], by_knowledge: [], by_method: [], due_today: 0 }),
  ),
  http.get('/api/problems', () =>
    HttpResponse.json({ items: [], total: 0, page: 1, size: 20 }),
  ),
]
