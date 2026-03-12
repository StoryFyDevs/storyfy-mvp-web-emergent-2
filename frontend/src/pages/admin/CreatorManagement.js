import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, LogOut, Search, Plus, Minus, Eye, Zap, Clock, HardDrive, Activity, X } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';

function CreatorManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [limitDialog, setLimitDialog] = useState({ open: false, user: null });
  const [limitAmount, setLimitAmount] = useState('');
  const [auditionAmount, setAuditionAmount] = useState('');
  const [limitReason, setLimitReason] = useState('');
  const [usageDetail, setUsageDetail] = useState(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const navigate = useNavigate();

  const token = localStorage.getItem('admin_token');
  const base = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    if (!token) { navigate('/admin-access/login'); return; }
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const res = await fetch(`${base}/api/admin-9821/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem('admin_token');
        navigate('/admin-access/login');
        return;
      }
      if (!res.ok) throw new Error('Failed to fetch users');
      setUsers(await res.json());
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const openUsageDetail = async (user) => {
    setUsageLoading(true);
    setUsageDetail({ user, data: null });
    try {
      const res = await fetch(`${base}/api/admin-9821/creators/${user.user_id}/usage`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        setUsageDetail({ user, data: await res.json() });
      } else {
        toast.error('Failed to load usage detail');
        setUsageDetail(null);
      }
    } catch (err) {
      toast.error(err.message);
      setUsageDetail(null);
    } finally {
      setUsageLoading(false);
    }
  };

  const updateStatus = async (userId, status) => {
    try {
      const res = await fetch(`${base}/api/admin-9821/users/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ user_id: userId, status, reason: `Admin set status to ${status}` })
      });
      const data = await res.json().catch(() => ({ detail: 'Failed to process response' }));
      if (!res.ok) throw new Error(data.detail || 'Status update failed');
      toast.success(`User ${status}`);
      fetchUsers();
    } catch (err) {
      toast.error(err.message || 'Failed to update status');
    }
  };

  const adjustLimits = async (e) => {
    e.preventDefault();
    const genAmt = parseInt(limitAmount, 10) || 0;
    const audAmt = parseInt(auditionAmount, 10) || 0;
    if (genAmt === 0 && audAmt === 0) { toast.error('Enter a valid non-zero amount for at least one credit type'); return; }

    try {
      const reason = limitReason || 'Admin adjustment';
      if (genAmt !== 0) {
        const res = await fetch(`${base}/api/admin-9821/users/limits`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ user_id: limitDialog.user.user_id, amount: genAmt, reason })
        });
        const data = await res.json().catch(() => ({ detail: 'Failed to process response' }));
        if (!res.ok) throw new Error(data.detail || 'Failed to update generation credits');
      }
      if (audAmt !== 0) {
        const res = await fetch(`${base}/api/admin-9821/users/audition-credits`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ user_id: limitDialog.user.user_id, amount: audAmt, reason })
        });
        const data = await res.json().catch(() => ({ detail: 'Failed to process response' }));
        if (!res.ok) throw new Error(data.detail || 'Failed to update audition credits');
      }
      toast.success('Credits updated');
      setLimitDialog({ open: false, user: null });
      setLimitAmount(''); setAuditionAmount(''); setLimitReason('');
      fetchUsers();
    } catch (err) { toast.error(err.message || 'Failed to update credits'); }
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    navigate('/admin-access/login');
  };

  const filtered = users.filter(u =>
    u.email?.toLowerCase().includes(search.toLowerCase()) ||
    u.name?.toLowerCase().includes(search.toLowerCase())
  );

  const statusBadge = (status) => {
    const map = {
      active: 'bg-signal-green/15 text-signal-green border-signal-green/30',
      suspended: 'bg-warm-gold/15 text-warm-gold border-warm-gold/30',
      banned: 'bg-sunset-orange/15 text-sunset-orange border-sunset-orange/30',
    };
    return map[status] || map.active;
  };

  const fmtNum = (n) => n != null ? n.toLocaleString() : '0';
  const fmtBytes = (b) => { if (!b) return '0 B'; if (b < 1024) return `${b} B`; if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`; return `${(b / 1048576).toFixed(1)} MB`; };
  const fmtDate = (d) => d ? new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';

  if (loading) {
    return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-neon-cyan font-space">Loading creators...</div></div>;
  }

  return (
    <div className="min-h-screen bg-obsidian" data-testid="creator-management">
      <header className="border-b border-white/5 bg-charcoal/60 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-electric-purple" />
            <span className="font-syne font-bold text-white text-lg">StoryFy Admin</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link to="/admin-access/dashboard" className="text-text-secondary hover:text-white text-sm" data-testid="nav-dashboard">Dashboard</Link>
            <Link to="/admin-access/creators" className="text-neon-cyan text-sm font-medium" data-testid="nav-creators">Creators</Link>
            <Link to="/admin-access/stories" className="text-text-secondary hover:text-white text-sm" data-testid="nav-stories">Stories</Link>
            <Link to="/admin-access/usage" className="text-text-secondary hover:text-white text-sm" data-testid="nav-usage">Usage</Link>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-text-secondary hover:text-white" data-testid="admin-logout-btn">
              <LogOut className="w-4 h-4 mr-1" /> Logout
            </Button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-syne font-bold text-white">Creator Management</h1>
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
            <Input placeholder="Search users..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-slate border-white/10 text-white text-sm" data-testid="user-search-input" />
          </div>
        </div>

        <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="users-table">
              <thead>
                <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">User</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-right px-4 py-3 font-medium">Gen Credits</th>
                  <th className="text-right px-4 py-3 font-medium">Aud Credits</th>
                  <th className="text-right px-4 py-3 font-medium">Credits Used</th>
                  <th className="text-right px-4 py-3 font-medium">Audio (min)</th>
                  <th className="text-right px-4 py-3 font-medium">Generations</th>
                  <th className="text-right px-4 py-3 font-medium">Storage</th>
                  <th className="text-center px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.length === 0 ? (
                  <tr><td colSpan={8} className="text-center py-8 text-text-secondary">No users found</td></tr>
                ) : (
                  filtered.map((u) => (
                    <tr key={u.user_id} className="border-b border-white/5 hover:bg-slate/40 transition-colors" data-testid={`user-row-${u.user_id}`}>
                      <td className="px-4 py-3">
                        <p className="text-white font-medium">{u.name || 'Unnamed'}</p>
                        <p className="text-text-secondary text-xs">{u.email}</p>
                        <span className="text-xs text-text-secondary/60 capitalize">{u.role || 'creator'}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block text-xs px-2 py-0.5 rounded-full border ${statusBadge(u.status || 'active')}`}>
                          {u.status || 'active'}
                        </span>
                      </td>
                      <td className={`px-4 py-3 text-right font-mono text-xs ${(u.limits_remaining ?? 0) < 100 ? 'text-red-400' : 'text-signal-green'}`} data-testid={`credits-left-${u.user_id}`}>
                        {fmtNum(u.limits_remaining ?? 0)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono text-xs ${(u.audition_credits ?? 0) < 50 ? 'text-red-400' : 'text-electric-purple'}`} data-testid={`audition-credits-${u.user_id}`}>
                        {fmtNum(u.audition_credits ?? 0)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-sunset-orange" data-testid={`credits-used-${u.user_id}`}>
                        {fmtNum(u.total_credits_used || 0)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-white" data-testid={`audio-mins-${u.user_id}`}>
                        {((u.total_audio_seconds || 0) / 60).toFixed(1)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-white" data-testid={`gen-count-${u.user_id}`}>
                        {u.total_generations || 0}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs text-white">
                        {(u.storage_used_mb ?? 0).toFixed(1)} MB
                      </td>
                      <td className="px-4 py-3">
                        {u.role !== 'admin' && (
                          <div className="flex items-center justify-center gap-1">
                            <Button variant="ghost" size="sm" className="text-electric-purple hover:text-electric-purple/80 text-xs h-7 px-2"
                              onClick={() => openUsageDetail(u)} data-testid={`view-usage-${u.user_id}`}>
                              <Eye className="w-3 h-3 mr-1" /> Usage
                            </Button>
                            <Button variant="ghost" size="sm" className="text-neon-cyan hover:text-neon-cyan/80 text-xs h-7 px-2"
                              onClick={() => { setLimitDialog({ open: true, user: u }); setLimitAmount(''); setAuditionAmount(''); setLimitReason(''); }}
                              data-testid={`adjust-limits-${u.user_id}`}>
                              Limits
                            </Button>
                            {(u.status || 'active') === 'active' ? (
                              <Button variant="ghost" size="sm" className="text-warm-gold hover:text-warm-gold/80 text-xs h-7 px-2"
                                onClick={() => updateStatus(u.user_id, 'suspended')} data-testid={`suspend-${u.user_id}`}>
                                Suspend
                              </Button>
                            ) : (
                              <Button variant="ghost" size="sm" className="text-signal-green hover:text-signal-green/80 text-xs h-7 px-2"
                                onClick={() => updateStatus(u.user_id, 'active')} data-testid={`activate-${u.user_id}`}>
                                Activate
                              </Button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      {/* Limit Adjustment Dialog */}
      <Dialog open={limitDialog.open} onOpenChange={(open) => setLimitDialog({ open, user: open ? limitDialog.user : null })}>
        <DialogContent className="bg-charcoal border-white/10 text-white sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-syne">Adjust Limits — {limitDialog.user?.name || limitDialog.user?.email}</DialogTitle>
          </DialogHeader>
          <form onSubmit={adjustLimits} className="space-y-4 mt-2">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-text-secondary text-xs mb-1">Generation Credits</p>
                <p className="text-white font-mono text-sm">{limitDialog.user?.limits_remaining ?? 0}</p>
              </div>
              <div>
                <p className="text-text-secondary text-xs mb-1">Audition Credits</p>
                <p className="text-electric-purple font-mono text-sm">{limitDialog.user?.audition_credits ?? 0}</p>
              </div>
            </div>
            <div>
              <Label className="text-white text-sm">Generation Credits (+/-)</Label>
              <Input type="number" value={limitAmount} onChange={(e) => setLimitAmount(e.target.value)}
                className="mt-1.5 bg-slate border-white/10 text-white" placeholder="e.g. 500 or -200" data-testid="limit-amount-input" />
            </div>
            <div>
              <Label className="text-white text-sm">Audition Credits (+/-)</Label>
              <Input type="number" value={auditionAmount} onChange={(e) => setAuditionAmount(e.target.value)}
                className="mt-1.5 bg-slate border-white/10 text-white" placeholder="e.g. 100 or -50" data-testid="audition-amount-input" />
            </div>
            <div>
              <Label className="text-white text-sm">Reason</Label>
              <Textarea value={limitReason} onChange={(e) => setLimitReason(e.target.value)}
                className="mt-1.5 bg-slate border-white/10 text-white" placeholder="Reason for adjustment..." rows={2} data-testid="limit-reason-input" />
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setLimitDialog({ open: false, user: null })} className="text-text-secondary" data-testid="limit-cancel-btn">Cancel</Button>
              <Button type="submit" className="bg-electric-purple text-white hover:bg-electric-purple/80" data-testid="limit-submit-btn">Apply</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Usage Detail Dialog */}
      <Dialog open={!!usageDetail} onOpenChange={(open) => !open && setUsageDetail(null)}>
        <DialogContent className="bg-charcoal border-white/10 text-white sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-syne flex items-center gap-2">
              <Activity className="w-4 h-4 text-neon-cyan" />
              Usage Detail — {usageDetail?.user?.name || usageDetail?.user?.email}
            </DialogTitle>
          </DialogHeader>
          {usageLoading ? (
            <div className="py-8 text-center text-text-secondary">Loading usage data...</div>
          ) : usageDetail?.data ? (
            <div className="space-y-5 mt-2">
              {/* Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-slate/50 border border-white/5 rounded-sm p-3">
                  <div className="flex items-center gap-1.5 mb-1"><Zap className="w-3 h-3 text-sunset-orange" /><span className="text-text-secondary text-xs">Credits Used</span></div>
                  <p className="text-white text-lg font-mono font-bold" data-testid="detail-credits-used">{fmtNum(usageDetail.data.total_credits_used)}</p>
                </div>
                <div className="bg-slate/50 border border-white/5 rounded-sm p-3">
                  <div className="flex items-center gap-1.5 mb-1"><Zap className="w-3 h-3 text-signal-green" /><span className="text-text-secondary text-xs">Credits Left</span></div>
                  <p className={`text-lg font-mono font-bold ${usageDetail.data.limits_remaining < 100 ? 'text-red-400' : 'text-signal-green'}`} data-testid="detail-credits-left">{fmtNum(usageDetail.data.limits_remaining)}</p>
                </div>
                <div className="bg-slate/50 border border-white/5 rounded-sm p-3">
                  <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-neon-cyan" /><span className="text-text-secondary text-xs">Audio Minutes</span></div>
                  <p className="text-white text-lg font-mono font-bold" data-testid="detail-audio-mins">{usageDetail.data.total_audio_minutes}</p>
                </div>
                <div className="bg-slate/50 border border-white/5 rounded-sm p-3">
                  <div className="flex items-center gap-1.5 mb-1"><HardDrive className="w-3 h-3 text-electric-purple" /><span className="text-text-secondary text-xs">Storage</span></div>
                  <p className="text-white text-lg font-mono font-bold" data-testid="detail-storage">{usageDetail.data.storage_used_mb?.toFixed(1)} MB</p>
                </div>
              </div>

              {/* Generation Stats */}
              <div className="flex gap-4 text-xs">
                <span className="text-text-secondary">Total Generations: <span className="text-white font-mono" data-testid="detail-total-gens">{usageDetail.data.total_generations}</span></span>
                <span className="text-text-secondary">Failed: <span className="text-red-400 font-mono">{usageDetail.data.total_failed_generations}</span></span>
                <span className="text-text-secondary">File Size: <span className="text-white font-mono">{fmtBytes(usageDetail.data.total_file_size_bytes)}</span></span>
              </div>

              {/* By Type */}
              {usageDetail.data.by_type?.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-white mb-2">By Type</h3>
                  <div className="grid grid-cols-3 gap-2">
                    {usageDetail.data.by_type.map(t => (
                      <div key={t.type} className="bg-slate/30 border border-white/5 rounded-sm p-2">
                        <span className="text-xs text-electric-purple font-medium uppercase">{t.type}</span>
                        <p className="text-white text-xs font-mono mt-0.5">{t.count} gens / {fmtNum(t.credits)} credits</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent Generations */}
              {usageDetail.data.recent_generations?.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-white mb-2">Recent Generations</h3>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {usageDetail.data.recent_generations.map((g, i) => (
                      <div key={g.log_id || i} className="flex items-center justify-between bg-slate/20 border border-white/5 rounded-sm px-3 py-2 text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`px-1.5 py-0.5 rounded border text-[10px] ${g.status === 'success' ? 'border-signal-green/30 text-signal-green bg-signal-green/10' : 'border-red-500/30 text-red-400 bg-red-500/10'}`}>{g.status}</span>
                          <span className="text-electric-purple">{g.type}</span>
                          <span className="text-text-secondary">{g.text_length} chars</span>
                        </div>
                        <div className="flex items-center gap-3 text-text-secondary">
                          <span>{g.duration_seconds ? `${g.duration_seconds}s` : '-'}</span>
                          <span>{fmtBytes(g.file_size)}</span>
                          <span>{fmtDate(g.created_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {usageDetail.data.total_generations === 0 && (
                <div className="text-center py-6 text-text-secondary text-sm">No generations yet for this creator.</div>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default CreatorManagement;
