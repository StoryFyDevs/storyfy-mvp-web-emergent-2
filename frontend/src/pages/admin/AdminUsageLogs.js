import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, LogOut, Search, Activity, Zap, ClipboardList, BarChart3, AlertTriangle, RefreshCw, ChevronLeft, ChevronRight, Database } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';

const TABS = [
  { id: 'generation-logs', label: 'Generation Logs', icon: Database },
  { id: 'transactions', label: 'Limit Transactions', icon: Zap },
  { id: 'actions', label: 'Admin Actions', icon: ClipboardList },
  { id: 'alerts', label: 'Alerts', icon: AlertTriangle },
  { id: 'elevenlabs', label: 'ElevenLabs Sync', icon: RefreshCw },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
];

function AdminUsageLogs() {
  const [activeTab, setActiveTab] = useState('generation-logs');
  const [genLogs, setGenLogs] = useState({ logs: [], total: 0, page: 1, total_pages: 0 });
  const [genPage, setGenPage] = useState(1);
  const [genTypeFilter, setGenTypeFilter] = useState('');
  const [genStatusFilter, setGenStatusFilter] = useState('');
  const [transactions, setTransactions] = useState([]);
  const [actions, setActions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [syncLogs, setSyncLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  const token = localStorage.getItem('admin_token');
  const base = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    if (!token) { navigate('/admin-access/login'); return; }
    fetchAll();
  }, []);

  const fetchGenLogs = useCallback(async (page = 1) => {
    const headers = { 'Authorization': `Bearer ${token}` };
    let url = `${base}/api/admin-9821/usage/generation-logs?page=${page}&per_page=50`;
    if (genTypeFilter) url += `&gen_type=${genTypeFilter}`;
    if (genStatusFilter) url += `&status=${genStatusFilter}`;
    const res = await fetch(url, { headers });
    if (res.ok) {
      const data = await res.json();
      setGenLogs(data);
      setGenPage(page);
    }
  }, [token, base, genTypeFilter, genStatusFilter]);

  useEffect(() => {
    if (activeTab === 'generation-logs') fetchGenLogs(1);
  }, [genTypeFilter, genStatusFilter, activeTab]);

  const fetchAll = async () => {
    try {
      const headers = { 'Authorization': `Bearer ${token}` };
      const [txnRes, actRes, anlRes, alertsRes, syncRes, genRes] = await Promise.all([
        fetch(`${base}/api/admin-9821/usage/transactions`, { headers }),
        fetch(`${base}/api/admin-9821/usage/actions`, { headers }),
        fetch(`${base}/api/admin-9821/usage/analytics`, { headers }),
        fetch(`${base}/api/admin-9821/usage/alerts`, { headers }),
        fetch(`${base}/api/admin-9821/usage/elevenlabs-sync`, { headers }),
        fetch(`${base}/api/admin-9821/usage/generation-logs?page=1&per_page=50`, { headers }),
      ]);

      if (txnRes.status === 401) { localStorage.removeItem('admin_token'); navigate('/admin-access/login'); return; }
      if (txnRes.ok) setTransactions(await txnRes.json());
      if (actRes.ok) setActions(await actRes.json());
      if (anlRes.ok) setAnalytics(await anlRes.json());
      if (alertsRes.ok) setAlerts(await alertsRes.json());
      if (syncRes.ok) setSyncLogs(await syncRes.json());
      if (genRes.ok) setGenLogs(await genRes.json());
    } catch (err) { toast.error(err.message); }
    finally { setLoading(false); }
  };

  const resolveAlert = async (alertId) => {
    try {
      const res = await fetch(`${base}/api/admin-9821/usage/alerts/${alertId}/resolve`, {
        method: 'PATCH', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) { toast.success('Alert resolved'); setAlerts(prev => prev.filter(a => a.alert_id !== alertId)); }
    } catch (err) { toast.error(err.message); }
  };

  const triggerSync = async () => {
    try {
      const res = await fetch(`${base}/api/admin-9821/usage/validate-elevenlabs`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) { toast.success('ElevenLabs validation triggered'); fetchAll(); }
    } catch (err) { toast.error(err.message); }
  };

  const handleLogout = () => { localStorage.removeItem('admin_token'); navigate('/admin-access/login'); };
  const fmtDate = (d) => d ? new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  const fmtNum = (n) => n != null ? n.toLocaleString() : '0';
  const fmtBytes = (b) => { if (!b) return '0 B'; if (b < 1024) return `${b} B`; if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`; return `${(b / 1048576).toFixed(1)} MB`; };

  const txnTypeBadge = (type) => {
    const map = {
      signup_bonus: 'bg-signal-green/15 text-signal-green border-signal-green/30',
      admin_add: 'bg-neon-cyan/15 text-neon-cyan border-neon-cyan/30',
      admin_deduct: 'bg-sunset-orange/15 text-sunset-orange border-sunset-orange/30',
      generation: 'bg-electric-purple/15 text-electric-purple border-electric-purple/30',
      refund: 'bg-warm-gold/15 text-warm-gold border-warm-gold/30',
    };
    return map[type] || 'bg-white/10 text-text-secondary border-white/10';
  };

  const filteredTxn = transactions.filter(t =>
    t.user_email?.toLowerCase().includes(search.toLowerCase()) ||
    t.user_name?.toLowerCase().includes(search.toLowerCase()) ||
    t.transaction_type?.toLowerCase().includes(search.toLowerCase())
  );
  const filteredActions = actions.filter(a =>
    a.admin_email?.toLowerCase().includes(search.toLowerCase()) ||
    a.action_type?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-neon-cyan font-space">Loading logs...</div></div>;

  const unresolvedAlerts = alerts.filter(a => !a.resolved).length;

  return (
    <div className="min-h-screen bg-obsidian" data-testid="admin-usage-logs">
      <header className="border-b border-white/5 bg-charcoal/60 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-electric-purple" />
            <span className="font-syne font-bold text-white text-lg">StoryFy Admin</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link to="/admin-access/dashboard" className="text-text-secondary hover:text-white text-sm" data-testid="nav-dashboard">Dashboard</Link>
            <Link to="/admin-access/creators" className="text-text-secondary hover:text-white text-sm" data-testid="nav-creators">Creators</Link>
            <Link to="/admin-access/stories" className="text-text-secondary hover:text-white text-sm" data-testid="nav-stories">Stories</Link>
            <Link to="/admin-access/usage" className="text-neon-cyan text-sm font-medium" data-testid="nav-usage">Usage</Link>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-text-secondary hover:text-white" data-testid="admin-logout-btn"><LogOut className="w-4 h-4 mr-1" /> Logout</Button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-syne font-bold text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-neon-cyan" /> Usage & Logs
          </h1>
          {!['analytics', 'elevenlabs'].includes(activeTab) && (
            <div className="relative w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
              <Input placeholder="Search logs..." value={search} onChange={e => setSearch(e.target.value)}
                className="pl-9 bg-slate border-white/10 text-white text-sm" data-testid="usage-search-input" />
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-charcoal border border-white/5 rounded-sm p-1 mb-6 w-fit flex-wrap" data-testid="usage-tabs">
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-sm text-xs transition-colors ${activeTab === tab.id ? 'bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/30' : 'text-text-secondary hover:text-white'}`}
              data-testid={`tab-${tab.id}`}>
              <tab.icon className="w-3.5 h-3.5" /> {tab.label}
              {tab.id === 'alerts' && unresolvedAlerts > 0 && (
                <span className="ml-1 bg-red-500 text-white text-[10px] rounded-full w-4 h-4 flex items-center justify-center">{unresolvedAlerts}</span>
              )}
            </button>
          ))}
        </div>

        {/* Generation Logs Tab */}
        {activeTab === 'generation-logs' && (
          <div>
            <div className="flex gap-2 mb-4">
              <Select value={genTypeFilter} onValueChange={v => setGenTypeFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="w-40 bg-slate border-white/10 text-white text-xs" data-testid="filter-type"><SelectValue placeholder="All Types" /></SelectTrigger>
                <SelectContent className="bg-charcoal border-white/10">
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="voice">Voice</SelectItem>
                  <SelectItem value="dialogue">Dialogue</SelectItem>
                  <SelectItem value="sfx">SFX</SelectItem>
                  <SelectItem value="bgm">BGM</SelectItem>
                </SelectContent>
              </Select>
              <Select value={genStatusFilter} onValueChange={v => setGenStatusFilter(v === 'all' ? '' : v)}>
                <SelectTrigger className="w-40 bg-slate border-white/10 text-white text-xs" data-testid="filter-status"><SelectValue placeholder="All Status" /></SelectTrigger>
                <SelectContent className="bg-charcoal border-white/10">
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="generation-logs-table">
                  <thead>
                    <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                      <th className="text-left px-4 py-3 font-medium">Date</th>
                      <th className="text-left px-4 py-3 font-medium">User</th>
                      <th className="text-left px-4 py-3 font-medium">Type</th>
                      <th className="text-right px-4 py-3 font-medium">Credits</th>
                      <th className="text-right px-4 py-3 font-medium">Duration</th>
                      <th className="text-right px-4 py-3 font-medium">Size</th>
                      <th className="text-left px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {genLogs.logs?.length === 0 ? (
                      <tr><td colSpan={7} className="text-center py-8 text-text-secondary">No generation logs</td></tr>
                    ) : genLogs.logs?.map((l, i) => (
                      <tr key={l.log_id || i} className="border-b border-white/5 hover:bg-slate/40">
                        <td className="px-4 py-2.5 text-text-secondary text-xs whitespace-nowrap">{fmtDate(l.created_at)}</td>
                        <td className="px-4 py-2.5"><span className="text-white text-xs">{l.user_name}</span><span className="text-text-secondary text-xs ml-1">({l.user_email})</span></td>
                        <td className="px-4 py-2.5"><span className="text-xs px-2 py-0.5 rounded-full border border-electric-purple/30 bg-electric-purple/15 text-electric-purple">{l.type}</span></td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-sunset-orange">{fmtNum(l.credits_used)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{l.duration_seconds ? `${l.duration_seconds}s` : '-'}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{fmtBytes(l.file_size)}</td>
                        <td className="px-4 py-2.5">
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${l.status === 'success' ? 'border-signal-green/30 bg-signal-green/15 text-signal-green' : 'border-red-500/30 bg-red-500/15 text-red-400'}`}>{l.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              {genLogs.total_pages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-white/5">
                  <span className="text-text-secondary text-xs">{fmtNum(genLogs.total)} total logs, page {genLogs.page}/{genLogs.total_pages}</span>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="sm" disabled={genPage <= 1} onClick={() => fetchGenLogs(genPage - 1)} className="text-text-secondary text-xs h-7" data-testid="gen-prev-page"><ChevronLeft className="w-3.5 h-3.5" /></Button>
                    <Button variant="ghost" size="sm" disabled={genPage >= genLogs.total_pages} onClick={() => fetchGenLogs(genPage + 1)} className="text-text-secondary text-xs h-7" data-testid="gen-next-page"><ChevronRight className="w-3.5 h-3.5" /></Button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Transactions Tab */}
        {activeTab === 'transactions' && (
          <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="transactions-table">
                <thead>
                  <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                    <th className="text-left px-4 py-3 font-medium">Date</th>
                    <th className="text-left px-4 py-3 font-medium">User</th>
                    <th className="text-left px-4 py-3 font-medium">Type</th>
                    <th className="text-right px-4 py-3 font-medium">Amount</th>
                    <th className="text-right px-4 py-3 font-medium">Balance</th>
                    <th className="text-left px-4 py-3 font-medium">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTxn.length === 0 ? (
                    <tr><td colSpan={6} className="text-center py-8 text-text-secondary">No transactions found</td></tr>
                  ) : filteredTxn.map((t, i) => (
                    <tr key={t.transaction_id || i} className="border-b border-white/5 hover:bg-slate/40">
                      <td className="px-4 py-2.5 text-text-secondary text-xs whitespace-nowrap">{fmtDate(t.created_at)}</td>
                      <td className="px-4 py-2.5"><span className="text-white text-xs">{t.user_name}</span><span className="text-text-secondary text-xs ml-1">({t.user_email})</span></td>
                      <td className="px-4 py-2.5"><span className={`text-xs px-2 py-0.5 rounded-full border ${txnTypeBadge(t.transaction_type)}`}>{t.transaction_type?.replace(/_/g, ' ')}</span></td>
                      <td className={`px-4 py-2.5 text-right font-mono text-xs ${t.amount > 0 ? 'text-signal-green' : 'text-sunset-orange'}`}>{t.amount > 0 ? '+' : ''}{t.amount}</td>
                      <td className="px-4 py-2.5 text-right text-white font-mono text-xs">{t.balance_after}</td>
                      <td className="px-4 py-2.5 text-text-secondary text-xs truncate max-w-[200px]">{t.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Admin Actions Tab */}
        {activeTab === 'actions' && (
          <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="actions-table">
                <thead>
                  <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                    <th className="text-left px-4 py-3 font-medium">Date</th>
                    <th className="text-left px-4 py-3 font-medium">Admin</th>
                    <th className="text-left px-4 py-3 font-medium">Action</th>
                    <th className="text-left px-4 py-3 font-medium">Target</th>
                    <th className="text-left px-4 py-3 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredActions.length === 0 ? (
                    <tr><td colSpan={5} className="text-center py-8 text-text-secondary">No admin actions found</td></tr>
                  ) : filteredActions.map((a, i) => (
                    <tr key={a.action_id || i} className="border-b border-white/5 hover:bg-slate/40">
                      <td className="px-4 py-2.5 text-text-secondary text-xs whitespace-nowrap">{fmtDate(a.created_at)}</td>
                      <td className="px-4 py-2.5 text-white text-xs">{a.admin_name} ({a.admin_email})</td>
                      <td className="px-4 py-2.5"><span className="text-xs px-2 py-0.5 rounded-full border border-electric-purple/30 bg-electric-purple/15 text-electric-purple">{a.action_type?.replace(/_/g, ' ')}</span></td>
                      <td className="px-4 py-2.5 text-text-secondary text-xs font-mono">{a.target_type}: {a.target_id?.slice(0, 16)}</td>
                      <td className="px-4 py-2.5 text-text-secondary text-xs truncate max-w-[250px]">{a.details ? JSON.stringify(a.details).slice(0, 80) : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Alerts Tab */}
        {activeTab === 'alerts' && (
          <div className="space-y-2">
            {alerts.length === 0 ? (
              <div className="text-center py-12 text-text-secondary">No alerts</div>
            ) : alerts.map(a => (
              <div key={a.alert_id} className={`flex items-start justify-between p-4 rounded-sm border ${a.resolved ? 'border-white/5 bg-charcoal opacity-60' : a.severity === 'critical' ? 'border-red-500/30 bg-red-500/5' : 'border-warm-gold/30 bg-warm-gold/5'}`} data-testid={`alert-row-${a.alert_id}`}>
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${a.severity === 'critical' ? 'border-red-500/50 text-red-400 bg-red-500/10' : 'border-warm-gold/50 text-warm-gold bg-warm-gold/10'}`}>{a.severity}</span>
                    <span className="text-xs text-text-secondary px-2 py-0.5 rounded-full border border-white/10">{a.alert_type?.replace(/_/g, ' ')}</span>
                    {a.resolved && <span className="text-xs text-signal-green px-2 py-0.5 rounded-full border border-signal-green/30 bg-signal-green/10">resolved</span>}
                  </div>
                  <p className="text-white text-sm mt-2">{a.message}</p>
                  <p className="text-text-secondary text-xs mt-1">{fmtDate(a.created_at)}</p>
                </div>
                {!a.resolved && (
                  <Button variant="ghost" size="sm" onClick={() => resolveAlert(a.alert_id)} className="text-signal-green hover:text-signal-green/80 text-xs ml-3 shrink-0" data-testid={`resolve-${a.alert_id}`}>Resolve</Button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ElevenLabs Sync Tab */}
        {activeTab === 'elevenlabs' && (
          <div>
            <div className="flex justify-end mb-4">
              <Button variant="ghost" size="sm" onClick={triggerSync} className="text-neon-cyan hover:text-neon-cyan/80 text-xs" data-testid="trigger-sync-btn">
                <RefreshCw className="w-3.5 h-3.5 mr-1" /> Run Validation Now
              </Button>
            </div>
            <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="sync-table">
                  <thead>
                    <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                      <th className="text-left px-4 py-3 font-medium">Date</th>
                      <th className="text-right px-4 py-3 font-medium">Local Chars</th>
                      <th className="text-right px-4 py-3 font-medium">ElevenLabs Chars</th>
                      <th className="text-right px-4 py-3 font-medium">EL Limit</th>
                      <th className="text-right px-4 py-3 font-medium">Diff</th>
                      <th className="text-right px-4 py-3 font-medium">Diff %</th>
                      <th className="text-left px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {syncLogs.length === 0 ? (
                      <tr><td colSpan={7} className="text-center py-8 text-text-secondary">No sync logs. Click "Run Validation Now" to start.</td></tr>
                    ) : syncLogs.map((s, i) => (
                      <tr key={s.sync_id || i} className="border-b border-white/5 hover:bg-slate/40">
                        <td className="px-4 py-2.5 text-text-secondary text-xs whitespace-nowrap">{fmtDate(s.created_at)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{fmtNum(s.local_total_characters)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-neon-cyan">{fmtNum(s.elevenlabs_total_characters)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-text-secondary">{fmtNum(s.elevenlabs_character_limit)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{fmtNum(s.discrepancy)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{s.discrepancy_percent}%</td>
                        <td className="px-4 py-2.5">
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${s.status === 'ok' ? 'border-signal-green/30 bg-signal-green/15 text-signal-green' : s.status === 'mismatch' ? 'border-red-500/30 bg-red-500/15 text-red-400' : 'border-warm-gold/30 bg-warm-gold/15 text-warm-gold'}`}>{s.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Analytics Tab */}
        {activeTab === 'analytics' && analytics && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-syne font-bold text-white mb-3">Limit Transactions by Type</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {analytics.transactions_by_type.map(t => (
                  <div key={t.type} className="bg-charcoal border border-white/5 rounded-sm p-4" data-testid={`analytics-txn-${t.type}`}>
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${txnTypeBadge(t.type)} inline-block mb-2`}>{t.type?.replace(/_/g, ' ')}</span>
                    <p className="text-white text-xl font-syne font-bold">{t.count}</p>
                    <p className="text-text-secondary text-xs mt-1">Total: <span className={t.total_amount >= 0 ? 'text-signal-green' : 'text-sunset-orange'}>{t.total_amount > 0 ? '+' : ''}{t.total_amount}</span></p>
                  </div>
                ))}
              </div>
            </div>
            {analytics.daily_signups?.length > 0 && (
              <div>
                <h2 className="text-lg font-syne font-bold text-white mb-3">Daily Signups (Last 30 Days)</h2>
                <div className="bg-charcoal border border-white/5 rounded-sm p-4">
                  <div className="flex items-end gap-1 h-32" data-testid="signups-chart">
                    {analytics.daily_signups.map((d, i) => {
                      const maxCount = Math.max(...analytics.daily_signups.map(s => s.count), 1);
                      const height = (d.count / maxCount) * 100;
                      return (
                        <div key={i} className="flex-1 flex flex-col items-center justify-end" title={`${d.date}: ${d.count} signups`}>
                          <div className="w-full bg-neon-cyan/40 rounded-t-sm min-h-[2px]" style={{ height: `${height}%` }} />
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex justify-between mt-1">
                    <span className="text-xs text-text-secondary">{analytics.daily_signups[0]?.date}</span>
                    <span className="text-xs text-text-secondary">{analytics.daily_signups[analytics.daily_signups.length - 1]?.date}</span>
                  </div>
                </div>
              </div>
            )}
            {analytics.top_creators?.length > 0 && (
              <div>
                <h2 className="text-lg font-syne font-bold text-white mb-3">Creators by Remaining Limits</h2>
                <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
                  <table className="w-full text-sm" data-testid="top-creators-table">
                    <thead>
                      <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                        <th className="text-left px-4 py-3 font-medium">Creator</th>
                        <th className="text-right px-4 py-3 font-medium">Limits Left</th>
                        <th className="text-right px-4 py-3 font-medium">Storage (MB)</th>
                        <th className="text-right px-4 py-3 font-medium">Stories</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.top_creators.map((c, i) => (
                        <tr key={c.user_id || i} className="border-b border-white/5">
                          <td className="px-4 py-2.5"><span className="text-white text-xs">{c.name || 'Unnamed'}</span><span className="text-text-secondary text-xs ml-1">({c.email})</span></td>
                          <td className={`px-4 py-2.5 text-right font-mono text-xs ${(c.limits_remaining || 0) < 100 ? 'text-sunset-orange' : 'text-white'}`}>{c.limits_remaining ?? 0}</td>
                          <td className="px-4 py-2.5 text-right text-white font-mono text-xs">{(c.storage_used_mb || 0).toFixed(1)}</td>
                          <td className="px-4 py-2.5 text-right text-white font-mono text-xs">{c.stories_count || 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
        {activeTab === 'analytics' && !analytics && (
          <div className="text-center py-12 text-text-secondary">No analytics data available</div>
        )}
      </main>
    </div>
  );
}

export default AdminUsageLogs;
