import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Users, BookOpen, Layers, Clock, HardDrive, Zap, Shield, LogOut, AlertTriangle, RefreshCw, Activity, TrendingUp, Volume2, ChevronDown, ChevronRight, Database, Cpu, Search } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Input } from '../../components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';

function StatCard({ icon: Icon, label, value, accent, subtext }) {
  const colors = {
    cyan: 'border-neon-cyan/30 text-neon-cyan',
    purple: 'border-electric-purple/30 text-electric-purple',
    green: 'border-signal-green/30 text-signal-green',
    gold: 'border-warm-gold/30 text-warm-gold',
    orange: 'border-sunset-orange/30 text-sunset-orange',
    red: 'border-red-500/30 text-red-500',
  };
  const c = colors[accent] || colors.cyan;

  return (
    <div className={`bg-charcoal border ${c.split(' ')[0]} rounded-sm p-5`} data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center gap-3 mb-3">
        <Icon className={`w-4 h-4 ${c.split(' ')[1]}`} />
        <span className="text-text-secondary text-xs uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-white text-2xl font-syne font-bold">{value}</p>
      {subtext && <p className="text-text-secondary text-xs mt-1">{subtext}</p>}
    </div>
  );
}

function AdminDashboard() {
  const [stats, setStats] = useState(null);
  const [usageStats, setUsageStats] = useState(null);
  const [userSummaries, setUserSummaries] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voiceProvider, setVoiceProvider] = useState('elevenlabs');
  const [savingVoice, setSavingVoice] = useState(false);
  const [adminVoices, setAdminVoices] = useState(null);
  const [showVoiceList, setShowVoiceList] = useState(false);
  const [genAnalytics, setGenAnalytics] = useState(null);
  const [genRuns, setGenRuns] = useState([]);
  const [genRunsTotal, setGenRunsTotal] = useState(0);
  const [genDebugLogs, setGenDebugLogs] = useState([]);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [debugFilter, setDebugFilter] = useState({ creator_id: '', episode_id: '' });
  const navigate = useNavigate();
  const token = localStorage.getItem('admin_token');
  const base = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    if (!token) { navigate('/admin-access/login'); return; }
    fetchAll();
    // Auto-refresh every 30 seconds for real-time data
    const interval = setInterval(() => fetchAll(true), 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchAll = async (silent = false) => {
    try {
      const headers = { 'Authorization': `Bearer ${token}` };
      const [statsRes, usageRes, summRes, alertsRes, voiceRes, voiceDetailRes] = await Promise.all([
        fetch(`${base}/api/admin-9821/stats`, { headers }),
        fetch(`${base}/api/admin-9821/usage/global-stats`, { headers }),
        fetch(`${base}/api/admin-9821/usage/user-summaries`, { headers }),
        fetch(`${base}/api/admin-9821/usage/alerts?resolved=false`, { headers }),
        fetch(`${base}/api/admin-9821/voice-settings`, { headers }),
        fetch(`${base}/api/admin-9821/voice-settings/voices`, { headers }),
      ]);

      if (statsRes.status === 401 || statsRes.status === 403) {
        localStorage.removeItem('admin_token');
        navigate('/admin-access/login');
        return;
      }

      if (statsRes.ok) setStats(await statsRes.json());
      if (usageRes.ok) setUsageStats(await usageRes.json());
      if (summRes.ok) setUserSummaries(await summRes.json());
      if (alertsRes.ok) setAlerts(await alertsRes.json());
      if (voiceRes.ok) {
        const vd = await voiceRes.json();
        setVoiceProvider(vd.activeProvider || 'elevenlabs');
      }
      if (voiceDetailRes.ok) setAdminVoices(await voiceDetailRes.json());

      // Fetch generation analytics
      try {
        const [analyticsRes, runsRes] = await Promise.all([
          fetch(`${base}/api/admin-9821/analytics/generation/summary`, { headers }),
          fetch(`${base}/api/admin-9821/analytics/generation/runs?limit=20`, { headers }),
        ]);
        if (analyticsRes.ok) setGenAnalytics(await analyticsRes.json());
        if (runsRes.ok) {
          const rd = await runsRes.json();
          setGenRuns(rd.runs || []);
          setGenRunsTotal(rd.total || 0);
        }
      } catch (e) { /* analytics non-critical */ }
    } catch (err) {
      if (!silent) toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveVoiceProvider = async (newProvider) => {
    setSavingVoice(true);
    try {
      const res = await fetch(`${base}/api/admin-9821/voice-settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ activeProvider: newProvider })
      });
      if (res.ok) {
        setVoiceProvider(newProvider);
        toast.success(`Voice engine switched to ${newProvider === 'elevenlabs' ? 'Default' : 'Alternate'} engine`);
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to update voice engine');
      }
    } catch (err) { toast.error(err.message); }
    finally { setSavingVoice(false); }
  };

  const triggerELValidation = async () => {
    try {
      const res = await fetch(`${base}/api/admin-9821/usage/validate-elevenlabs`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Validation: ${data.status} (local: ${data.local_total_characters}, EL: ${data.elevenlabs_total_characters})`);
        fetchAll();
      }
    } catch (err) { toast.error(err.message); }
  };

  const resolveAlert = async (alertId) => {
    try {
      const res = await fetch(`${base}/api/admin-9821/usage/alerts/${alertId}/resolve`, {
        method: 'PATCH', headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        toast.success('Alert resolved');
        setAlerts(prev => prev.filter(a => a.alert_id !== alertId));
      }
    } catch (err) { toast.error(err.message); }
  };

  const fetchFilteredRuns = async () => {
    try {
      const params = new URLSearchParams({ limit: '20' });
      if (debugFilter.creator_id) params.append('creator_id', debugFilter.creator_id);
      if (debugFilter.episode_id) params.append('episode_id', debugFilter.episode_id);
      const res = await fetch(`${base}/api/admin-9821/analytics/generation/runs?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const rd = await res.json();
        setGenRuns(rd.runs || []);
        setGenRunsTotal(rd.total || 0);
      }
    } catch (e) { toast.error('Failed to fetch runs'); }
  };

  const fetchDebugLogs = async (genId) => {
    setSelectedRunId(genId);
    try {
      const res = await fetch(`${base}/api/admin-9821/analytics/generation/${genId}/debug`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const rd = await res.json();
        setGenDebugLogs(rd.logs || []);
      }
    } catch (e) { toast.error('Failed to fetch debug logs'); }
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    navigate('/admin-access/login');
  };

  const fmtNum = (n) => n != null ? n.toLocaleString() : '0';
  const fmtBytes = (b) => {
    if (!b) return '0 B';
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  };

  if (loading) {
    return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-neon-cyan font-space">Loading dashboard...</div></div>;
  }

  return (
    <div className="min-h-screen bg-obsidian" data-testid="admin-dashboard">
      <header className="border-b border-white/5 bg-charcoal/60 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-electric-purple" />
            <span className="font-syne font-bold text-white text-lg">StoryFy Admin</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link to="/admin-access/dashboard" className="text-neon-cyan text-sm font-medium" data-testid="nav-dashboard">Dashboard</Link>
            <Link to="/admin-access/creators" className="text-text-secondary hover:text-white text-sm" data-testid="nav-creators">Creators</Link>
            <Link to="/admin-access/stories" className="text-text-secondary hover:text-white text-sm" data-testid="nav-stories">Stories</Link>
            <Link to="/admin-access/usage" className="text-text-secondary hover:text-white text-sm" data-testid="nav-usage">Usage</Link>
            <Link to="/admin-access/generation" className="text-text-secondary hover:text-white text-sm flex items-center gap-1" data-testid="nav-generation">
              <Zap className="w-3 h-3" /> Generation
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-text-secondary hover:text-white" data-testid="admin-logout-btn">
              <LogOut className="w-4 h-4 mr-1" /> Logout
            </Button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Voice Engine Settings */}
        <Card className="bg-charcoal border-electric-purple/20" data-testid="voice-engine-settings">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <Volume2 className="w-5 h-5 text-electric-purple" /> Voice Engine Settings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-4 flex-wrap">
              <div className="flex-1 min-w-[240px]">
                <p className="text-text-secondary text-xs mb-2">Active Voice Engine</p>
                <Select value={voiceProvider} onValueChange={handleSaveVoiceProvider} disabled={savingVoice}>
                  <SelectTrigger className="bg-slate border-white/10 text-white w-full max-w-xs" data-testid="voice-provider-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-charcoal border-white/10">
                    <SelectItem value="elevenlabs">Default Voice Engine</SelectItem>
                    <SelectItem value="gemini">Alternate Voice Engine</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-3">
                <div className={`px-3 py-1.5 rounded-full text-xs font-medium border ${
                  voiceProvider === 'elevenlabs'
                    ? 'border-neon-cyan/30 text-neon-cyan bg-neon-cyan/5'
                    : 'border-electric-purple/30 text-electric-purple bg-electric-purple/5'
                }`} data-testid="voice-engine-status">
                  {voiceProvider === 'elevenlabs' ? 'Default Engine Active' : 'Alternate Engine Active'}
                </div>
              </div>
            </div>
            <p className="text-text-secondary text-xs mt-3">
              Switching the voice engine takes effect instantly for all creators. No redeploy required.
            </p>

            {/* Admin technical details for Gemini voices */}
            {voiceProvider === 'gemini' && adminVoices && (
              <div className="mt-4 border-t border-white/5 pt-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <p className="text-white text-sm font-medium">Alternate Engine: {adminVoices.provider} ({adminVoices.model})</p>
                    <p className="text-text-secondary text-xs">{adminVoices.total_voices} voices available</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => setShowVoiceList(!showVoiceList)} className="text-electric-purple hover:text-electric-purple/80 text-xs" data-testid="toggle-voice-list">
                    {showVoiceList ? 'Hide Voices' : 'Show Voices'}
                  </Button>
                </div>
                {showVoiceList && (
                  <div className="bg-slate/40 border border-white/5 rounded-sm overflow-hidden max-h-[280px] overflow-y-auto">
                    <table className="w-full text-xs" data-testid="admin-voice-table">
                      <thead>
                        <tr className="border-b border-white/5 text-text-secondary uppercase tracking-wider">
                          <th className="text-left px-3 py-2 font-medium">Voice ID</th>
                          <th className="text-left px-3 py-2 font-medium">Display Name</th>
                          <th className="text-left px-3 py-2 font-medium">Gender</th>
                          <th className="text-left px-3 py-2 font-medium">Tone</th>
                          <th className="text-left px-3 py-2 font-medium">Category</th>
                          <th className="text-left px-3 py-2 font-medium">Model</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminVoices.voices.map(v => (
                          <tr key={v.voice_id} className="border-b border-white/5 hover:bg-slate/40">
                            <td className="px-3 py-1.5 font-mono text-neon-cyan">{v.voice_id}</td>
                            <td className="px-3 py-1.5 text-white">{v.display_name}</td>
                            <td className="px-3 py-1.5 text-text-secondary">{v.gender}</td>
                            <td className="px-3 py-1.5 text-text-secondary">{v.tone}</td>
                            <td className="px-3 py-1.5 text-text-secondary">{v.category}</td>
                            <td className="px-3 py-1.5 text-text-secondary font-mono">{v.model}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Platform Stats */}
        <div>
          <h1 className="text-2xl font-syne font-bold text-white mb-4">Platform Overview</h1>
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard icon={Users} label="Total Users" value={fmtNum(stats.total_users)} accent="cyan" />
              <StatCard icon={Users} label="Creators" value={fmtNum(stats.total_creators)} accent="purple" />
              <StatCard icon={BookOpen} label="Stories" value={fmtNum(stats.total_stories)} accent="gold" />
              <StatCard icon={Layers} label="Episodes" value={fmtNum(stats.total_episodes)} accent="gold" />
            </div>
          )}
        </div>

        {/* Usage Stats */}
        {usageStats && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-syne font-bold text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-neon-cyan" /> Real-Time Usage
              </h2>
              <Button variant="ghost" size="sm" onClick={triggerELValidation} className="text-neon-cyan hover:text-neon-cyan/80 text-xs" data-testid="validate-elevenlabs-btn">
                <RefreshCw className="w-3.5 h-3.5 mr-1" /> Validate ElevenLabs
              </Button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard icon={Zap} label="Credits Used" value={fmtNum(usageStats.total_credits_used)} accent="orange" subtext={`${fmtNum(usageStats.total_generations)} generations`} />
              <StatCard icon={Clock} label="Audio Minutes" value={usageStats.total_audio_minutes} accent="green" subtext={`${usageStats.total_audio_seconds}s total`} />
              <StatCard icon={HardDrive} label="Storage" value={`${usageStats.total_storage_mb} MB`} accent="purple" subtext={fmtBytes(usageStats.total_file_size_bytes) + ' audio files'} />
              <StatCard icon={AlertTriangle} label="Active Alerts" value={usageStats.active_alerts} accent={usageStats.active_alerts > 0 ? 'red' : 'green'} subtext={`${usageStats.total_failed_generations} failed gens`} />
            </div>
            {/* ElevenLabs Sync Status */}
            {usageStats.elevenlabs_sync && (
              <div className={`mt-3 p-3 rounded-sm border text-xs ${usageStats.elevenlabs_sync.status === 'ok' ? 'border-signal-green/30 bg-signal-green/5 text-signal-green' : usageStats.elevenlabs_sync.status === 'mismatch' ? 'border-red-500/30 bg-red-500/5 text-red-400' : 'border-warm-gold/30 bg-warm-gold/5 text-warm-gold'}`} data-testid="elevenlabs-sync-status">
                <span className="font-medium">ElevenLabs Sync:</span>{' '}
                Local: {fmtNum(usageStats.elevenlabs_sync.local_total_characters)} chars | API: {fmtNum(usageStats.elevenlabs_sync.elevenlabs_total_characters)} chars | Limit: {fmtNum(usageStats.elevenlabs_sync.elevenlabs_character_limit)} |{' '}
                Diff: {usageStats.elevenlabs_sync.discrepancy_percent}% — <span className="font-bold uppercase">{usageStats.elevenlabs_sync.status}</span>
              </div>
            )}
            {/* Type breakdown */}
            {usageStats.by_type && usageStats.by_type.length > 0 && (
              <div className="grid grid-cols-3 gap-2 mt-3">
                {usageStats.by_type.map(t => (
                  <div key={t.type} className="bg-slate/40 border border-white/5 rounded-sm p-3">
                    <span className="text-xs text-electric-purple font-medium uppercase">{t.type}</span>
                    <p className="text-white text-sm font-mono mt-1">{fmtNum(t.count)} gens / {fmtNum(t.credits)} credits</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Active Alerts */}
        {alerts.length > 0 && (
          <div>
            <h2 className="text-lg font-syne font-bold text-white mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400" /> Active Alerts ({alerts.length})
            </h2>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {alerts.slice(0, 10).map(a => (
                <div key={a.alert_id} className={`flex items-center justify-between p-3 rounded-sm border ${a.severity === 'critical' ? 'border-red-500/30 bg-red-500/5' : 'border-warm-gold/30 bg-warm-gold/5'}`} data-testid={`alert-${a.alert_id}`}>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${a.severity === 'critical' ? 'border-red-500/50 text-red-400 bg-red-500/10' : 'border-warm-gold/50 text-warm-gold bg-warm-gold/10'}`}>{a.severity}</span>
                      <span className="text-xs text-text-secondary px-2 py-0.5 rounded-full border border-white/10">{a.alert_type?.replace(/_/g, ' ')}</span>
                    </div>
                    <p className="text-white text-sm mt-1">{a.message}</p>
                    <p className="text-text-secondary text-xs mt-0.5">{new Date(a.created_at).toLocaleString()}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => resolveAlert(a.alert_id)} className="text-signal-green hover:text-signal-green/80 text-xs ml-3 shrink-0" data-testid={`resolve-alert-${a.alert_id}`}>
                    Resolve
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Per-Creator Usage */}
        {userSummaries.length > 0 && (
          <div>
            <h2 className="text-lg font-syne font-bold text-white mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-electric-purple" /> Per-Creator Usage
            </h2>
            <div className="bg-charcoal border border-white/5 rounded-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="creator-usage-table">
                  <thead>
                    <tr className="border-b border-white/5 text-text-secondary text-xs uppercase tracking-wider">
                      <th className="text-left px-4 py-3 font-medium">Creator</th>
                      <th className="text-right px-4 py-3 font-medium">Credits Used</th>
                      <th className="text-right px-4 py-3 font-medium">Credits Left</th>
                      <th className="text-right px-4 py-3 font-medium">Audio (min)</th>
                      <th className="text-right px-4 py-3 font-medium">Generations</th>
                      <th className="text-right px-4 py-3 font-medium">Storage</th>
                      <th className="text-right px-4 py-3 font-medium">Failed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {userSummaries.map((s, i) => (
                      <tr key={s.user_id || i} className="border-b border-white/5 hover:bg-slate/40">
                        <td className="px-4 py-2.5">
                          <span className="text-white text-xs">{s.user_name}</span>
                          <span className="text-text-secondary text-xs ml-1">({s.user_email})</span>
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-sunset-orange">{fmtNum(s.total_credits_used || 0)}</td>
                        <td className={`px-4 py-2.5 text-right font-mono text-xs ${(s.limits_remaining || 0) < 100 ? 'text-red-400' : 'text-signal-green'}`}>{fmtNum(s.limits_remaining || 0)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{((s.total_audio_seconds || 0) / 60).toFixed(1)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{s.total_generations || 0}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-white">{fmtBytes(s.total_storage_used || 0)}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-text-secondary">{s.total_failed_generations || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ═══════════ GENERATION ANALYTICS ═══════════ */}
        <Card className="bg-charcoal border-neon-cyan/20" data-testid="generation-analytics-section">
          <CardHeader className="pb-0 cursor-pointer" onClick={() => setAnalyticsOpen(!analyticsOpen)}>
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <Database className="w-5 h-5 text-neon-cyan" />
              Generation Analytics
              {analyticsOpen ? <ChevronDown className="w-4 h-4 ml-auto text-text-secondary" /> : <ChevronRight className="w-4 h-4 ml-auto text-text-secondary" />}
            </CardTitle>
          </CardHeader>
          {analyticsOpen && genAnalytics?.today && (
            <CardContent className="pt-4 space-y-4">
              {/* Summary Stats */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <StatCard icon={Zap} label="Dialogues Today" value={genAnalytics.today.total_dialogues} accent="cyan" />
                <StatCard icon={Cpu} label="Gemini Calls" value={genAnalytics.today.gemini_calls_used} accent="purple" subtext={`${genAnalytics.today.gemini_calls_saved} saved`} />
                <StatCard icon={Clock} label="Deepgram Minutes" value={genAnalytics.today.deepgram_minutes.toFixed(2)} accent="green" />
                <StatCard icon={HardDrive} label="Avg Cost/Episode" value={`$${genAnalytics.today.avg_cost_per_episode.toFixed(4)}`} accent="gold" subtext={`$${genAnalytics.today.total_cost.toFixed(4)} total`} />
              </div>

              {/* Batch Efficiency */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-slate/40 border border-white/5 rounded-sm p-3" data-testid="batch-efficiency">
                  <span className="text-xs text-neon-cyan font-medium uppercase">Batch Efficiency</span>
                  <p className="text-white text-xl font-mono mt-1">{genAnalytics.today.batch_efficiency}%</p>
                  <p className="text-text-secondary text-xs mt-0.5">{genAnalytics.today.total_batches} batches</p>
                </div>
                <div className="bg-slate/40 border border-white/5 rounded-sm p-3" data-testid="cache-hit-rate">
                  <span className="text-xs text-electric-purple font-medium uppercase">Cache Hit Rate</span>
                  <p className="text-white text-xl font-mono mt-1">{genAnalytics.today.cache_hit_rate}%</p>
                  <p className="text-text-secondary text-xs mt-0.5">{genAnalytics.today.cache_hits} hits / {genAnalytics.today.cache_misses} misses</p>
                </div>
                <div className="bg-slate/40 border border-white/5 rounded-sm p-3" data-testid="segmentation-rate">
                  <span className="text-xs text-signal-green font-medium uppercase">Segmentation Rate</span>
                  <p className="text-white text-xl font-mono mt-1">{genAnalytics.today.avg_segmentation_rate}%</p>
                  <p className="text-text-secondary text-xs mt-0.5">{genAnalytics.today.fallback_count} fallback(s)</p>
                </div>
                <div className="bg-slate/40 border border-white/5 rounded-sm p-3" data-testid="gemini-health">
                  <span className="text-xs text-amber-400 font-medium uppercase">Gemini Health</span>
                  <p className="text-white text-xl font-mono mt-1">{genAnalytics.today.empty_gemini_responses || 0}</p>
                  <p className="text-text-secondary text-xs mt-0.5">empty responses, {genAnalytics.today.gemini_retries || 0} retries</p>
                </div>
              </div>

              {/* Generation Count & Time */}
              <div className="flex items-center gap-4 text-xs text-text-secondary">
                <span>{genAnalytics.today.generation_count} generation run(s) today</span>
                <span>Avg time: {genAnalytics.today.avg_generation_time}s</span>
              </div>
            </CardContent>
          )}
        </Card>

        {/* ═══════════ GENERATION DEBUG PANEL ═══════════ */}
        <Card className="bg-charcoal border-electric-purple/20" data-testid="generation-debug-section">
          <CardHeader className="pb-0 cursor-pointer" onClick={() => setDebugOpen(!debugOpen)}>
            <CardTitle className="text-white text-lg flex items-center gap-2">
              <Cpu className="w-5 h-5 text-electric-purple" />
              Generation Debug
              <span className="text-xs text-text-secondary font-normal ml-2">({genRunsTotal} runs)</span>
              {debugOpen ? <ChevronDown className="w-4 h-4 ml-auto text-text-secondary" /> : <ChevronRight className="w-4 h-4 ml-auto text-text-secondary" />}
            </CardTitle>
          </CardHeader>
          {debugOpen && (
            <CardContent className="pt-4 space-y-4">
              {/* Filters */}
              <div className="flex items-center gap-2" data-testid="debug-filters">
                <Input
                  placeholder="Creator ID"
                  value={debugFilter.creator_id}
                  onChange={e => setDebugFilter(p => ({ ...p, creator_id: e.target.value }))}
                  className="bg-slate border-white/10 text-white text-xs h-8 max-w-[200px]"
                />
                <Input
                  placeholder="Episode ID"
                  value={debugFilter.episode_id}
                  onChange={e => setDebugFilter(p => ({ ...p, episode_id: e.target.value }))}
                  className="bg-slate border-white/10 text-white text-xs h-8 max-w-[200px]"
                />
                <Button size="sm" onClick={fetchFilteredRuns} className="bg-electric-purple text-white text-xs h-8" data-testid="debug-filter-btn">
                  <Search className="w-3 h-3 mr-1" /> Filter
                </Button>
              </div>

              {/* Runs Table */}
              <div className="bg-slate/40 border border-white/5 rounded-sm overflow-hidden">
                <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                  <table className="w-full text-xs" data-testid="generation-runs-table">
                    <thead className="sticky top-0 bg-slate">
                      <tr className="border-b border-white/5 text-text-secondary uppercase tracking-wider">
                        <th className="text-left px-3 py-2 font-medium">ID</th>
                        <th className="text-left px-3 py-2 font-medium">Episode</th>
                        <th className="text-right px-3 py-2 font-medium">Dialogues</th>
                        <th className="text-right px-3 py-2 font-medium">Batches</th>
                        <th className="text-right px-3 py-2 font-medium">Gemini</th>
                        <th className="text-right px-3 py-2 font-medium">Retries</th>
                        <th className="text-right px-3 py-2 font-medium">Saved</th>
                        <th className="text-right px-3 py-2 font-medium">Cache</th>
                        <th className="text-right px-3 py-2 font-medium">Cost</th>
                        <th className="text-right px-3 py-2 font-medium">Time</th>
                        <th className="text-center px-3 py-2 font-medium">Fallback</th>
                        <th className="px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {genRuns.length === 0 && (
                        <tr><td colSpan={12} className="px-3 py-6 text-center text-text-secondary">No generation runs yet</td></tr>
                      )}
                      {genRuns.map(r => (
                        <React.Fragment key={r.generation_id}>
                          <tr className={`border-b border-white/5 hover:bg-slate/40 cursor-pointer ${selectedRunId === r.generation_id ? 'bg-electric-purple/10' : ''}`}
                              onClick={() => fetchDebugLogs(r.generation_id === selectedRunId ? null : r.generation_id)}
                              data-testid={`run-row-${r.generation_id}`}>
                            <td className="px-3 py-2 font-mono text-neon-cyan">{r.generation_id?.slice(0, 12)}...</td>
                            <td className="px-3 py-2 text-white">{r.episode_id?.slice(0, 16)}</td>
                            <td className="px-3 py-2 text-right text-white">{r.dialogue_count}</td>
                            <td className="px-3 py-2 text-right text-white">{r.batch_count}</td>
                            <td className="px-3 py-2 text-right text-electric-purple">{r.gemini_calls_used}{r.empty_gemini_responses > 0 && <span className="text-red-400 ml-1" title="Empty responses">({r.empty_gemini_responses}x empty)</span>}</td>
                            <td className="px-3 py-2 text-right">{r.gemini_retries > 0 ? <span className="text-amber-400">{r.gemini_retries}</span> : <span className="text-text-secondary">0</span>}</td>
                            <td className="px-3 py-2 text-right text-signal-green">{r.gemini_calls_saved}</td>
                            <td className="px-3 py-2 text-right text-warm-gold">{r.cache_hits}/{r.cache_hits + r.cache_misses}</td>
                            <td className="px-3 py-2 text-right text-sunset-orange">${r.estimated_cost?.toFixed(4)}</td>
                            <td className="px-3 py-2 text-right text-text-secondary">{r.generation_time_seconds}s</td>
                            <td className="px-3 py-2 text-center">
                              {r.fallback_triggered ? <span className="text-red-400">Yes</span> : <span className="text-signal-green">No</span>}
                            </td>
                            <td className="px-3 py-2">
                              {selectedRunId === r.generation_id ? <ChevronDown className="w-3 h-3 text-text-secondary" /> : <ChevronRight className="w-3 h-3 text-text-secondary" />}
                            </td>
                          </tr>
                          {/* Debug Logs Expansion */}
                          {selectedRunId === r.generation_id && (
                            <tr>
                              <td colSpan={12} className="bg-obsidian/50 p-0">
                                <div className="max-h-[280px] overflow-y-auto p-3 space-y-1" data-testid={`debug-logs-${r.generation_id}`}>
                                  {genDebugLogs.length === 0 && (
                                    <p className="text-text-secondary text-xs py-2 text-center">No debug logs for this run</p>
                                  )}
                                  {genDebugLogs.map((log, li) => (
                                    <div key={log.log_id || li} className="flex items-start gap-2 text-xs border-b border-white/5 pb-1">
                                      <span className={`shrink-0 px-1.5 py-0.5 rounded font-mono text-[10px] ${
                                        log.event_type === 'FALLBACK_TRIGGERED' ? 'bg-red-500/20 text-red-400' :
                                        log.event_type?.includes('GEMINI') ? 'bg-electric-purple/20 text-electric-purple' :
                                        log.event_type?.includes('DEEPGRAM') ? 'bg-neon-cyan/20 text-neon-cyan' :
                                        log.event_type?.includes('CLIP') ? 'bg-signal-green/20 text-signal-green' :
                                        'bg-white/10 text-text-secondary'
                                      }`}>
                                        {log.event_type}
                                      </span>
                                      <span className="text-white flex-1">{log.message}</span>
                                      <span className="text-text-secondary shrink-0">{log.created_at ? new Date(log.created_at).toLocaleTimeString() : ''}</span>
                                    </div>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </CardContent>
          )}
        </Card>
      </main>
    </div>
  );
}

export default AdminDashboard;
