import { Routes, Route, Navigate } from 'react-router-dom'
import ProjectsListPage from './features/projects/ProjectsListPage'
import ProjectPage from './features/projects/ProjectPage'
import EditorPage from './features/editor/EditorPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ProjectsListPage />} />
      <Route path="/p/:projectId" element={<ProjectPage />} />
      <Route path="/p/:projectId/edit" element={<EditorPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
