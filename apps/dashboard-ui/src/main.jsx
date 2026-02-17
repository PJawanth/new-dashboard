import React from 'react';
import ReactDOM from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import { DashboardProvider } from './context/DashboardContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <DashboardProvider>
        <App />
      </DashboardProvider>
    </HashRouter>
  </React.StrictMode>,
);
