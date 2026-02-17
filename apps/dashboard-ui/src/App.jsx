import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';

import Overview from './pages/Overview';
import DevOps from './pages/DevOps';
import DevSecOps from './pages/DevSecOps';
import CodeQuality from './pages/CodeQuality';
import Governance from './pages/Governance';
import ValueStream from './pages/ValueStream';
import LoggingMonitor from './pages/LoggingMonitor';
import Repos from './pages/Repos';
import RepoDetail from './pages/RepoDetail';
import AdminSettings from './pages/AdminSettings';

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="devops" element={<DevOps />} />
          <Route path="devsecops" element={<DevSecOps />} />
          <Route path="quality" element={<CodeQuality />} />
          <Route path="governance" element={<Governance />} />
          <Route path="value-stream" element={<ValueStream />} />
          <Route path="logging" element={<LoggingMonitor />} />
          <Route path="repos" element={<Repos />} />
          <Route path="repos/:name" element={<RepoDetail />} />
          <Route path="admin" element={<AdminSettings />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}
