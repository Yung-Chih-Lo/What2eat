// src/index.jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css'; // 確保包含 Tailwind CSS 或其他樣式
import { BrowserRouter as Router } from 'react-router-dom'; // 導入 BrowserRouter

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Router> {/* 包裹 App */}
      <App />
    </Router>
  </React.StrictMode>
);
