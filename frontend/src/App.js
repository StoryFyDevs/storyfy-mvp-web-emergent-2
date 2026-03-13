import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import LoadingScreen from './components/LoadingScreen';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import StudioLayout from './pages/StudioLayout';
import ScriptEditor from './pages/ScriptEditor';
import AudioStudio from './pages/AudioStudio';
import Characters from './pages/Characters';
import VoiceGenerator from './pages/VoiceGenerator';
import AuthCallback from './components/AuthCallback';
import AdminLogin from './pages/admin/AdminLogin';
import AdminDashboard from './pages/admin/AdminDashboard';
import CreatorManagement from './pages/admin/CreatorManagement';
import AdminStories from './pages/admin/AdminStories';
import AdminStoryDetail from './pages/admin/AdminStoryDetail';
import AdminProjectViewer from './pages/admin/AdminProjectViewer';
import AdminUsageLogs from './pages/admin/AdminUsageLogs';
import GenerationControls from './pages/admin/GenerationControls';
import './App.css';

function AppRouter() {
  const location = useLocation();
  
  // Check URL fragment for Supabase auth callback or legacy session_id
  if (location.hash?.includes('session_id=') || 
      location.hash?.includes('refreshToken=') ||
      location.pathname === '/auth/callback') {
    return <AuthCallback />;
  }
  
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/studio/:storyId" element={<ProtectedRoute><StudioLayout /></ProtectedRoute>}>
        <Route index element={<Navigate to="script" replace />} />
        <Route path="script" element={<ScriptEditor />} />
        <Route path="audio" element={<AudioStudio />} />
        <Route path="characters" element={<Characters />} />
        <Route path="voice-generator" element={<VoiceGenerator />} />
      </Route>
      {/* Secret Admin Routes */}
      <Route path="/admin-access/login" element={<AdminLogin />} />
      <Route path="/admin-access/dashboard" element={<AdminProtectedRoute><AdminDashboard /></AdminProtectedRoute>} />
      <Route path="/admin-access/creators" element={<AdminProtectedRoute><CreatorManagement /></AdminProtectedRoute>} />
      <Route path="/admin-access/stories" element={<AdminProtectedRoute><AdminStories /></AdminProtectedRoute>} />
      <Route path="/admin-access/stories/:storyId" element={<AdminProtectedRoute><AdminStoryDetail /></AdminProtectedRoute>} />
      <Route path="/admin-access/projects/:episodeId" element={<AdminProtectedRoute><AdminProjectViewer /></AdminProtectedRoute>} />
      <Route path="/admin-access/usage" element={<AdminProtectedRoute><AdminUsageLogs /></AdminProtectedRoute>} />
      <Route path="/admin-access/generation" element={<AdminProtectedRoute><GenerationControls /></AdminProtectedRoute>} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function AdminProtectedRoute({ children }) {
  const token = localStorage.getItem('admin_token');
  if (!token) {
    return <Navigate to="/admin-access/login" replace />;
  }
  return children;
}

function ProtectedRoute({ children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const location = useLocation();
  
  useEffect(() => {
    // If user data passed from AuthCallback, skip auth check
    if (location.state?.user) {
      setIsAuthenticated(true);
      return;
    }
    
    const checkAuth = async () => {
      const token = localStorage.getItem('token');
      if (!token) {
        setIsAuthenticated(false);
        return;
      }
      try {
        const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/auth/me`, {
          credentials: 'include',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        
        if (!response.ok) throw new Error('Not authenticated');
        
        const user = await response.json();
        setIsAuthenticated(true);
      } catch (error) {
        localStorage.removeItem('token');
        setIsAuthenticated(false);
      }
    };
    
    checkAuth();
  }, [location.state]);
  
  if (isAuthenticated === null) {
    return <LoadingScreen />;
  }
  
  if (isAuthenticated === false) {
    return <Navigate to="/login" replace />;
  }
  
  return children;
}

function App() {
  return (
    <Router>
      <AppRouter />
    </Router>
  );
}

export default App;