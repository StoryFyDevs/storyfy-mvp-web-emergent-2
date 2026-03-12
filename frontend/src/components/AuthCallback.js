import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'sonner';
import nhost from '../lib/nhost';

function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const hasProcessed = useRef(false);
  const [status, setStatus] = useState('Processing authentication...');

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processNhostCallback = async () => {
      try {
        setStatus('Verifying authentication...');
        
        // Get URL parameters - Nhost OAuth returns params in URL hash or query
        const hashParams = new URLSearchParams(location.hash.substring(1));
        const queryParams = new URLSearchParams(location.search);
        
        // Check for refresh token in URL (Nhost OAuth flow)
        const refreshToken = hashParams.get('refreshToken') || queryParams.get('refreshToken');
        const type = hashParams.get('type') || queryParams.get('type');
        
        // Handle legacy Emergent Auth session_id (if present)
        const sessionId = hashParams.get('session_id');
        if (sessionId) {
          // Legacy flow - redirect to login with error
          toast.error('Legacy authentication no longer supported. Please use email/password or Google login.');
          navigate('/login', { replace: true });
          return;
        }

        // Handle Nhost OAuth callback with refresh token
        if (refreshToken) {
          setStatus('Setting up your session...');
          
          // The nhost client will automatically handle the refresh token from URL
          // We need to wait for it to be processed
          await new Promise(resolve => setTimeout(resolve, 1000));
          
          const session = nhost.auth.getSession();
          
          if (session) {
            const accessToken = session.accessToken;
            localStorage.setItem('token', accessToken);
            
            // Optionally sync with backend
            try {
              const user = session.user;
              await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/auth/oauth-sync`, {
                method: 'POST',
                headers: { 
                  'Content-Type': 'application/json',
                  'Authorization': `Bearer ${accessToken}`
                },
                body: JSON.stringify({
                  auth_id: user.id,
                  email: user.email,
                  name: user.displayName || user.email.split('@')[0],
                })
              }).catch(() => {}); // Ignore sync errors
            } catch (e) {
              console.log('Backend sync optional:', e);
            }
            
            toast.success('Login successful!');
            navigate('/dashboard', { replace: true });
            return;
          }
        }
        
        // If no refresh token, check if user is already authenticated
        const existingSession = nhost.auth.getSession();
        if (existingSession) {
          localStorage.setItem('token', existingSession.accessToken);
          toast.success('Login successful!');
          navigate('/dashboard', { replace: true });
          return;
        }
        
        // Handle error in URL
        const error = hashParams.get('error') || queryParams.get('error');
        const errorDescription = hashParams.get('error_description') || queryParams.get('error_description');
        
        if (error) {
          throw new Error(errorDescription || error || 'Authentication failed');
        }
        
        // No valid auth data found
        throw new Error('No authentication data received');
        
      } catch (error) {
        console.error('Auth callback error:', error);
        toast.error(error.message || 'Authentication failed');
        navigate('/login', { replace: true });
      }
    };

    processNhostCallback();
  }, [navigate, location]);

  return (
    <div className="min-h-screen bg-obsidian flex items-center justify-center">
      <div className="text-center">
        <div className="text-neon-cyan text-2xl font-space mb-4">{status}</div>
        <div className="text-text-secondary">Please wait</div>
      </div>
    </div>
  );
}

export default AuthCallback;
