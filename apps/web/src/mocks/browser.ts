import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'

let worker: ReturnType<typeof setupWorker> | null = null

export async function startMockWorker() {
  if (!worker) worker = setupWorker(...handlers)
  try {
    await worker.start({ onUnhandledRequest: 'bypass', quiet: true })
    console.info('[msw] mock 已启用')
  } catch (error) {
    console.warn('[msw] 启动失败，回落到真实后端', error)
  }
}
