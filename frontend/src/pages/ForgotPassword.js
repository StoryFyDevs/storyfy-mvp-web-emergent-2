import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { API_BASE } from '../lib/config';
import { ArrowLeft, Mail, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          redirect_url: window.location.origin,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Request failed');
      }

      setSent(true);
    } catch (err) {
      toast.error(err.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-obsidian flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-5xl font-bold font-syne text-white mb-3">StoryFy</h1>
          <p className="text-text-secondary text-lg">Reset your password</p>
        </div>

        <div className="bg-charcoal border border-white/10 rounded-sm p-8">
          {sent ? (
            <div className="text-center space-y-4" data-testid="reset-email-sent">
              <div className="w-14 h-14 rounded-full bg-neon-cyan/10 flex items-center justify-center mx-auto">
                <Mail className="w-7 h-7 text-neon-cyan" />
              </div>
              <h2 className="text-xl font-semibold text-white">Check your email</h2>
              <p className="text-text-secondary text-sm leading-relaxed">
                If an account exists for <span className="text-white font-medium">{email}</span>,
                we've sent a link to reset your password. Check your inbox and spam folder.
              </p>
              <Button
                onClick={() => { setSent(false); setEmail(''); }}
                variant="outline"
                className="border-white/10 text-white hover:bg-slate mt-4"
                data-testid="try-another-email-btn"
              >
                Try a different email
              </Button>
            </div>
          ) : (
            <>
              <p className="text-text-secondary text-sm mb-6">
                Enter the email address associated with your account and we'll send you a link to reset your password.
              </p>
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <Label htmlFor="email" className="text-white">Email address</Label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-2 bg-slate border-white/10 text-white"
                    placeholder="you@example.com"
                    required
                    data-testid="forgot-email-input"
                  />
                </div>

                <Button
                  type="submit"
                  className="w-full bg-neon-cyan text-obsidian font-semibold hover:bg-neon-cyan/90"
                  disabled={loading}
                  data-testid="send-reset-link-btn"
                >
                  {loading ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Sending...</> : 'Send reset link'}
                </Button>
              </form>
            </>
          )}

          <div className="mt-6 text-center">
            <Link
              to="/login"
              className="text-text-secondary hover:text-white text-sm inline-flex items-center gap-1.5 transition-colors"
              data-testid="back-to-login-link"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back to sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ForgotPassword;
