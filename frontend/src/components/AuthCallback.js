import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import supabase from '../lib/supabase';
import { API_BASE } from '../lib/config';

function AuthCallback() {
  const navigate = useNavigate();
  const hasProcessed = useRef(false);
  const [status, setStatus] = useState('Processing authentication...');

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const processCallback = async () => {
      try {
        setStatus('Verifying authentication...');

        const { data, error } = await supabase.auth.getSession();

        if (error) {
          throw new Error(error.message || 'Authentication failed');
        }

        if (data?.session) {
          const accessToken = data.session.access_token;
          localStorage.setItem('token', accessToken);

          try {
            await fetch(`${API_BASE}/api/auth/oauth-sync`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
              },
            }).catch(() => {});
          } catch (e) {
            // Sync is optional
          }

          toast.success('Login successful!');
          navigate('/dashboard', { replace: true });
          return;
        }

        throw new Error('No authentication session received');
      } catch (error) {
        toast.error(error.message || 'Authentication failed');
        navigate('/login', { replace: true });
      }
    };

    processCallback();
  }, [navigate]);

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
