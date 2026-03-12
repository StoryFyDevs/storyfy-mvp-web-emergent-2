import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { toast } from 'sonner';
import { Shield } from 'lucide-react';

function AdminLogin() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  // Auto-redirect if already authenticated
  useEffect(() => {
    const token = localStorage.getItem('admin_token');
    if (token) {
      navigate('/admin-access/dashboard', { replace: true });
    }
  }, [navigate]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin-9821/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      localStorage.setItem('admin_token', data.token);
      toast.success('Admin access granted');
      // Navigate AFTER state is set, with replace to prevent back-button loop
      navigate('/admin-access/dashboard', { replace: true });
      return; // Exit before finally resets loading
    } catch (error) {
      toast.error(error.message);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-obsidian flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-electric-purple/20 border border-electric-purple/40 mb-4">
            <Shield className="w-7 h-7 text-electric-purple" />
          </div>
          <h1 className="text-3xl font-bold font-syne text-white">Admin Portal</h1>
          <p className="text-text-secondary text-sm mt-1">Restricted access</p>
        </div>

        <div className="bg-charcoal border border-electric-purple/20 rounded-sm p-6">
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <Label htmlFor="admin-email" className="text-white text-sm">Email</Label>
              <Input
                id="admin-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 bg-slate border-white/10 text-white"
                placeholder="admin@storyfy.com"
                required
                data-testid="admin-login-email-input"
              />
            </div>

            <div>
              <Label htmlFor="admin-password" className="text-white text-sm">Password</Label>
              <Input
                id="admin-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 bg-slate border-white/10 text-white"
                placeholder="••••••••"
                required
                data-testid="admin-login-password-input"
              />
            </div>

            <Button
              type="submit"
              className="w-full bg-electric-purple text-white hover:bg-electric-purple/80 font-semibold"
              disabled={loading}
              data-testid="admin-login-submit-button"
            >
              {loading ? 'Authenticating...' : 'Access Admin Panel'}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default AdminLogin;
