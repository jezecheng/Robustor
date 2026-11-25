import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './ui/tokens.css'

async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === '1') {
    const { startMockWorker } = await import('./mocks/browser')
    await startMockWorker()
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

bootstrap()
