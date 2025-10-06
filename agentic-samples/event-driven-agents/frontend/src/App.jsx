import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import UserDashboard from './components/UserDashboard';
import HumanReviewerDashboard from './components/HumanReviewerDashboard';
import './App.css';

function App() {
  return (
    <Router>
      <div className="min-h-screen">
        <Routes>
          <Route path="/" element={<Navigate to="/user" replace />} />
          <Route path="/user" element={<UserDashboard />} />
          <Route path="/reviewer" element={<HumanReviewerDashboard />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
