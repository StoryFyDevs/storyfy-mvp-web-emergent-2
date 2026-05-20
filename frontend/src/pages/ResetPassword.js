import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { API_BASE } from '../lib/config';
import { Eye, EyeOff, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';

function ResetPassword() {
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [tokens, setTokens] = useState({ access: '', refresh: '' });
  const navigate = useNavigate();

  // Extract tokens from URL hash on mount (Supabase redirects with tokens in fragment)
  useEffect(() => {
    const hash = window.location.hash.substring(1);
    const params = new URLSearchParams(hash);

    const accessToken = params.get('access_token') || '';
    const refreshToken = params.get('refresh_token') || '';
    const type = params.get('type') || '';

    if (accessToken && refreshToken) {
      setTokens({ access: accessToken, refresh: refreshToken });
      // Clean up the URL
      window.history.replaceState(null, '', window.location.pathname);
    } else if (type !== 'recovery' && !accessToken) {
      setError('Invalid or expired reset link. Please request a new one.');
    }
  }, []);

  const passwordStrength = (pw) => {
    let score = 0;
    if (pw.length >= 8) score++;
    if (pw.length >= 12) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    if (score <= 1) return { label: 'Weak', color: 'bg-red-500', width: '20%' };
    if (score <= 2) return { label: 'Fair', color: 'bg-orange-500', width: '40%' };
    if (score <= 3) return { label: 'Good', color: 'bg-yellow-500', width: '60%' };
    if (score <= 4) return { label: 'Strong', color: 'bg-signal-green', width: '80%' };
    return { label: 'Very Strong', color: 'bg-signal-green', width: '100%' };
  };

  const strength = newPassword ? passwordStrength(newPassword) : null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (!tokens.access || !tokens.refresh) {
      setError('Reset session expired. Please request a new reset link.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          access_token: tokens.access,
          refresh_token: tokens.refresh,
          new_password: newPassword,
        }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Password reset failed');
      }

      setSuccess(true);
      toast.success('Password updated successfully!');
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-obsidian flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-5xl font-bold font-syne text-white mb-3">StoryFy</h1>
          <p className="text-text-secondary text-lg">Set a new password</p>
        </div>

        <div className="bg-charcoal border border-white/10 rounded-sm p-8">
          {success ? (
            <div className="text-center space-y-4" data-testid="reset-success">
              <div className="w-14 h-14 rounded-full bg-signal-green/10 flex items-center justify-center mx-auto">
                <CheckCircle className="w-7 h-7 text-signal-green" />
              </div>
              <h2 className="text-xl font-semibold text-white">Password updated</h2>
              <p className="text-text-secondary text-sm">
                Your password has been changed successfully. You can now sign in with your new password.
              </p>
              <Button
                onClick={() => navigate('/login')}
                className="w-full bg-neon-cyan text-obsidian font-semibold hover:bg-neon-cyan/90 mt-4"
                data-testid="go-to-login-btn"
              >
                Sign in
              </Button>
            </div>
          ) : error && !tokens.access ? (
            <div className="text-center space-y-4" data-testid="reset-error">
              <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center mx-auto">
                <AlertCircle className="w-7 h-7 text-red-400" />
              </div>
              <h2 className="text-xl font-semibold text-white">Link expired</h2>
              <p className="text-text-secondary text-sm">{error}</p>
              <Button
                onClick={() => navigate('/forgot-password')}
                className="w-full bg-neon-cyan text-obsidian font-semibold hover:bg-neon-cyan/90 mt-4"
                data-testid="request-new-link-btn"
              >
                Request a new link
              </Button>
            </div>
          ) : (
            <>
              <p className="text-text-secondary text-sm mb-6">
                Choose a strong password for your account.
              </p>
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <Label htmlFor="new-password" className="text-white">New password</Label>
                  <div className="relative mt-2">
                    <Input
                      id="new-password"
                      type={showPassword ? 'text' : 'password'}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      className="bg-slate border-white/10 text-white pr-10"
                      placeholder="At least 6 characters"
                      required
                      data-testid="new-password-input"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-secondary hover:text-white transition-colors"
                      data-testid="toggle-password-visibility"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {strength && (
                    <div className="mt-2">
                      <div className="h-1 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${strength.color} rounded-full transition-all duration-300`}
                          style={{ width: strength.width }}
                        />
                      </div>
                      <p className={`text-xs mt-1 ${
                        strength.label === 'Weak' ? 'text-red-400' :
                        strength.label === 'Fair' ? 'text-orange-400' :
                        'text-text-secondary'
                      }`}>
                        {strength.label}
                      </p>
                    </div>
                  )}
                </div>

                <div>
                  <Label htmlFor="confirm-password" className="text-white">Confirm password</Label>
                  <Input
                    id="confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="mt-2 bg-slate border-white/10 text-white"
                    placeholder="Re-enter your password"
                    required
                    data-testid="confirm-password-input"
                  />
                  {confirmPassword && newPassword !== confirmPassword && (
                    <p className="text-xs text-red-400 mt-1">Passwords do not match</p>
                  )}
                </div>

                {error && (
                  <p className="text-xs text-red-400" data-testid="reset-error-message">{error}</p>
                )}

                <Button
                  type="submit"
                  className="w-full bg-neon-cyan text-obsidian font-semibold hover:bg-neon-cyan/90"
                  disabled={loading || !newPassword || !confirmPassword}
                  data-testid="update-password-btn"
                >
                  {loading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Updating...</> : 'Update password'}
                </Button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default ResetPassword;
