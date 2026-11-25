import { createBrowserRouter, Navigate } from 'react-router-dom'
import Layout from './ui/Layout'
import Upload from './pages/Upload'
import Console from './pages/Console'
import WrongBook from './pages/WrongBook'
import ProblemDetail from './pages/ProblemDetail'
import Stats from './pages/Stats'
import Settings from './pages/Settings'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/upload" replace /> },
      { path: 'upload', element: <Upload /> },
      { path: 'console/:documentId', element: <Console /> },
      { path: 'problems', element: <WrongBook /> },
      { path: 'problems/:problemId', element: <ProblemDetail /> },
      { path: 'stats', element: <Stats /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
])
