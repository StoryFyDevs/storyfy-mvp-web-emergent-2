import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { toast } from 'sonner';
import { 
  Settings, Users, Activity, Zap, Clock, AlertTriangle, 
  CheckCircle, XCircle, RefreshCw, Save, ChevronLeft
} from 'lucide-react';

const base = process.env.REACT_APP_BACKEND_URL;

function GenerationControls() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  
  // System limits
  const [limits, setLimits] = useState({
    rpd: 50,
    rpm: 5,
    tpm: 10000,
    auto_distribute: true,
    default_creator_rpd: 10,
    default_creator_rpm: 2,
    batch_size: 10
  });
  
  // Analytics
  const [analytics, setAnalytics] = useState(null);
  
  // Creator stats
  const [creators, setCreators] = useState([]);
  const [updatingCreator, setUpdatingCreator] = useState(null);
  
  const token = localStorage.getItem('admin_token');
  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const fetchData = useCallback(async () => {
    try {
      const [limitsRes, analyticsRes, creatorsRes] = await Promise.all([
        fetch(`${base}/api/admin-9821/generation/limits`, { headers }),
        fetch(`${base}/api/admin-9821/generation/analytics`, { headers }),
        fetch(`${base}/api/admin-9821/generation/creators`, { headers })
      ]);
      
      if (limitsRes.ok) {
        const data = await limitsRes.json();
        setLimits(data);
      }
      
      if (analyticsRes.ok) {
        const data = await analyticsRes.json();
        setAnalytics(data);
      }
      
      if (creatorsRes.ok) {
        const data = await creatorsRes.json();
        setCreators(data.creators || []);
      }
    } catch (err) {
      toast.error('Failed to load generation controls');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const saveLimits = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${base}/api/admin-9821/generation/limits`, {
        method: 'POST',
        headers,
        body: JSON.stringify(limits)
      });
      
      if (res.ok) {
        toast.success('System limits updated');
        fetchData();
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to save limits');
      }
    } catch (err) {
      toast.error('Failed to save limits');
    } finally {
      setSaving(false);
    }
  };

  const toggleCreatorStatus = async (userId, currentStatus) => {
    const newStatus = currentStatus === 'active' ? 'inactive' : 'active';
    setUpdatingCreator(userId);
    
    try {
      const res = await fetch(`${base}/api/admin-9821/generation/creators/${userId}/status`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ status: newStatus })
      });
      
      if (res.ok) {
        toast.success(`Creator ${newStatus === 'active' ? 'activated' : 'deactivated'}`);
        fetchData();
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to update status');
      }
    } catch (err) {
      toast.error('Failed to update creator status');
    } finally {
      setUpdatingCreator(null);
    }
  };

  const updateCreatorLimits = async (userId, dailyLimit, perMinuteLimit) => {
    setUpdatingCreator(userId);
    
    try {
      const res = await fetch(`${base}/api/admin-9821/generation/creators/${userId}/limits`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ 
          daily_limit: dailyLimit || null, 
          per_minute_limit: perMinuteLimit || null 
        })
      });
      
      if (res.ok) {
        toast.success('Creator limits updated');
        fetchData();
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to update limits');
      }
    } catch (err) {
      toast.error('Failed to update creator limits');
    } finally {
      setUpdatingCreator(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-obsidian flex items-center justify-center">
        <div className="text-neon-cyan text-xl">Loading generation controls...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-obsidian p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Button variant="ghost" onClick={() => navigate('/admin-access/dashboard')} className="text-text-secondary hover:text-white">
              <ChevronLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <h1 className="text-3xl font-bold font-syne text-white flex items-center gap-3">
              <Zap className="w-8 h-8 text-neon-cyan" />
              Voice Generation Controls
            </h1>
          </div>
          <Button variant="outline" onClick={fetchData} className="border-white/10 text-white">
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
        </div>

        {/* Analytics Overview */}
        {analytics && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="bg-charcoal border border-white/10 rounded-lg p-4">
              <div className="flex items-center gap-2 text-text-secondary mb-2">
                <Activity className="w-4 h-4" />
                <span className="text-sm">Generations Today</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {analytics.usage_today?.total_generations || 0}
                <span className="text-sm text-text-secondary font-normal ml-2">
                  / {analytics.system_limits?.rpd || 50}
                </span>
              </div>
            </div>
            
            <div className="bg-charcoal border border-white/10 rounded-lg p-4">
              <div className="flex items-center gap-2 text-text-secondary mb-2">
                <Clock className="w-4 h-4" />
                <span className="text-sm">Remaining Today</span>
              </div>
              <div className="text-2xl font-bold text-neon-cyan">
                {analytics.usage_today?.generations_remaining || 0}
              </div>
            </div>
            
            <div className="bg-charcoal border border-white/10 rounded-lg p-4">
              <div className="flex items-center gap-2 text-text-secondary mb-2">
                <Users className="w-4 h-4" />
                <span className="text-sm">Active Creators</span>
              </div>
              <div className="text-2xl font-bold text-white">
                {analytics.creators?.active_count || 0}
              </div>
            </div>
            
            <div className="bg-charcoal border border-white/10 rounded-lg p-4">
              <div className="flex items-center gap-2 text-text-secondary mb-2">
                <AlertTriangle className="w-4 h-4" />
                <span className="text-sm">Failed Today</span>
              </div>
              <div className="text-2xl font-bold text-red-400">
                {analytics.usage_today?.total_failed || 0}
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* System Limits */}
          <div className="bg-charcoal border border-white/10 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-6 flex items-center gap-2">
              <Settings className="w-5 h-5 text-neon-cyan" />
              Global System Limits
            </h2>
            
            <div className="space-y-6">
              <div>
                <Label className="text-white">Requests Per Day (RPD)</Label>
                <Input
                  type="number"
                  value={limits.rpd}
                  onChange={(e) => setLimits({ ...limits, rpd: parseInt(e.target.value) || 1 })}
                  className="mt-2 bg-slate border-white/10 text-white"
                  min="1"
                  data-testid="rpd-input"
                />
                <p className="text-text-secondary text-xs mt-1">Maximum total generations per day across all creators</p>
              </div>
              
              <div>
                <Label className="text-white">Requests Per Minute (RPM)</Label>
                <Input
                  type="number"
                  value={limits.rpm}
                  onChange={(e) => setLimits({ ...limits, rpm: parseInt(e.target.value) || 1 })}
                  className="mt-2 bg-slate border-white/10 text-white"
                  min="1"
                  data-testid="rpm-input"
                />
                <p className="text-text-secondary text-xs mt-1">Maximum concurrent requests per minute</p>
              </div>
              
              <div>
                <Label className="text-white">Tokens Per Minute (TPM)</Label>
                <Input
                  type="number"
                  value={limits.tpm}
                  onChange={(e) => setLimits({ ...limits, tpm: parseInt(e.target.value) || 100 })}
                  className="mt-2 bg-slate border-white/10 text-white"
                  min="100"
                  data-testid="tpm-input"
                />
                <p className="text-text-secondary text-xs mt-1">Maximum text characters per minute</p>
              </div>
              
              <div className="flex items-center justify-between py-3 border-t border-white/10">
                <div>
                  <Label className="text-white">Auto-Distribute Limits</Label>
                  <p className="text-text-secondary text-xs mt-1">
                    Automatically divide RPD among active creators
                  </p>
                </div>
                <Switch
                  checked={limits.auto_distribute}
                  onCheckedChange={(checked) => setLimits({ ...limits, auto_distribute: checked })}
                  data-testid="auto-distribute-switch"
                />
              </div>
              
              {!limits.auto_distribute && (
                <>
                  <div>
                    <Label className="text-white">Default Creator Daily Limit</Label>
                    <Input
                      type="number"
                      value={limits.default_creator_rpd}
                      onChange={(e) => setLimits({ ...limits, default_creator_rpd: parseInt(e.target.value) || 1 })}
                      className="mt-2 bg-slate border-white/10 text-white"
                      min="1"
                    />
                  </div>
                  
                  <div>
                    <Label className="text-white">Default Creator Per-Minute Limit</Label>
                    <Input
                      type="number"
                      value={limits.default_creator_rpm}
                      onChange={(e) => setLimits({ ...limits, default_creator_rpm: parseInt(e.target.value) || 1 })}
                      className="mt-2 bg-slate border-white/10 text-white"
                      min="1"
                    />
                  </div>
                </>
              )}

              <div className="border-t border-white/10 pt-4">
                <Label className="text-white">Script Compiler Batch Size</Label>
                <Input
                  type="number"
                  value={limits.batch_size || 10}
                  onChange={(e) => setLimits({ ...limits, batch_size: parseInt(e.target.value) || 5 })}
                  className="mt-2 bg-slate border-white/10 text-white"
                  min="2"
                  max="20"
                  data-testid="batch-size-input"
                />
                <p className="text-text-secondary text-xs mt-1">Max dialogues per API batch when compiling scripts (2-20)</p>
              </div>
              
              <Button 
                onClick={saveLimits} 
                disabled={saving}
                className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
                data-testid="save-limits-btn"
              >
                <Save className="w-4 h-4 mr-2" />
                {saving ? 'Saving...' : 'Save System Limits'}
              </Button>
            </div>
          </div>

          {/* Queue Status */}
          <div className="bg-charcoal border border-white/10 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-white mb-6 flex items-center gap-2">
              <Activity className="w-5 h-5 text-electric-purple" />
              Real-Time Status
            </h2>
            
            {analytics && (
              <div className="space-y-4">
                <div className="bg-slate rounded-lg p-4">
                  <div className="text-text-secondary text-sm mb-2">Queue Status</div>
                  <div className="flex items-center justify-between">
                    <span className="text-white">Pending Requests</span>
                    <span className="text-neon-cyan font-mono">{analytics.queue_status?.pending || 0}</span>
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-white">Processing</span>
                    <span className="text-electric-purple font-mono">{analytics.queue_status?.processing || 0}</span>
                  </div>
                </div>
                
                <div className="bg-slate rounded-lg p-4">
                  <div className="text-text-secondary text-sm mb-2">Current Minute</div>
                  <div className="flex items-center justify-between">
                    <span className="text-white">Requests</span>
                    <span className="font-mono text-white">
                      {analytics.current_minute?.requests || 0} / {limits.rpm}
                    </span>
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-white">Tokens</span>
                    <span className="font-mono text-white">
                      {analytics.current_minute?.tokens || 0} / {limits.tpm}
                    </span>
                  </div>
                </div>
                
                <div className="bg-slate rounded-lg p-4">
                  <div className="text-text-secondary text-sm mb-2">Per-Creator Limit</div>
                  <div className="text-2xl font-bold text-white">
                    {analytics.creators?.per_creator_daily_limit || 0}
                    <span className="text-sm text-text-secondary font-normal ml-2">generations/day</span>
                  </div>
                  {limits.auto_distribute && (
                    <p className="text-text-secondary text-xs mt-2">
                      Auto-calculated: {limits.rpd} RPD / {analytics.creators?.active_count || 1} creators
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Creator Generation Controls */}
        <div className="mt-8 bg-charcoal border border-white/10 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-6 flex items-center gap-2">
            <Users className="w-5 h-5 text-neon-cyan" />
            Creator Generation Controls
          </h2>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-text-secondary border-b border-white/10">
                  <th className="pb-3 font-medium">Creator</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Today's Usage</th>
                  <th className="pb-3 font-medium">Daily Limit</th>
                  <th className="pb-3 font-medium">Credits</th>
                  <th className="pb-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {creators.map((creator) => (
                  <tr key={creator.user_id} className="border-b border-white/5">
                    <td className="py-4">
                      <div className="text-white font-medium">{creator.name || 'Unknown'}</div>
                      <div className="text-text-secondary text-sm">{creator.email}</div>
                    </td>
                    <td className="py-4">
                      {creator.generation_status === 'active' ? (
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircle className="w-4 h-4" /> Active
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-red-400 text-sm">
                          <XCircle className="w-4 h-4" /> Inactive
                        </span>
                      )}
                    </td>
                    <td className="py-4">
                      <div className="text-white">
                        {creator.generations_today} / {creator.daily_limit}
                      </div>
                      <div className="w-24 h-1.5 bg-slate rounded-full mt-1">
                        <div 
                          className="h-full bg-neon-cyan rounded-full" 
                          style={{ width: `${Math.min(100, (creator.generations_today / creator.daily_limit) * 100)}%` }}
                        />
                      </div>
                    </td>
                    <td className="py-4">
                      <span className="text-white font-mono">{creator.daily_limit}</span>
                    </td>
                    <td className="py-4">
                      <div className="text-white text-sm">
                        Gen: {creator.generation_credits?.toLocaleString() || 0}
                      </div>
                      <div className="text-text-secondary text-sm">
                        Aud: {creator.audition_credits?.toLocaleString() || 0}
                      </div>
                    </td>
                    <td className="py-4">
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant={creator.generation_status === 'active' ? 'destructive' : 'default'}
                          onClick={() => toggleCreatorStatus(creator.user_id, creator.generation_status)}
                          disabled={updatingCreator === creator.user_id}
                          className={creator.generation_status === 'active' 
                            ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/30'
                            : 'bg-green-500/20 text-green-400 hover:bg-green-500/30 border border-green-500/30'
                          }
                          data-testid={`toggle-status-${creator.user_id}`}
                        >
                          {creator.generation_status === 'active' ? 'Disable' : 'Enable'}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                
                {creators.length === 0 && (
                  <tr>
                    <td colSpan="6" className="py-8 text-center text-text-secondary">
                      No creators found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default GenerationControls;
