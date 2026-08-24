import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import DashboardPage from './pages/DashboardPage.tsx'
import ProfilePage from './pages/ProfilePage.tsx'
import DiscoveryPage from './pages/DiscoveryPage.tsx'
import RecommendationsPage from './pages/RecommendationsPage.tsx'
import JobsPage from './pages/JobsPage.tsx'
import JobDetailPage from './pages/JobDetailPage.tsx'
import ApplicationsPage from './pages/ApplicationsPage.tsx'
import ApplicationDetailPage from './pages/ApplicationDetailPage.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<App />}>
          <Route index element={<DashboardPage />} />
          <Route path="profile" element={<ProfilePage />} />
          <Route path="discovery" element={<DiscoveryPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="jobs/:jobId" element={<JobDetailPage />} />
          <Route path="applications" element={<ApplicationsPage />} />
          <Route path="applications/:applicationId" element={<ApplicationDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
