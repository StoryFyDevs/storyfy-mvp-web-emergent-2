import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, LogOut, ArrowLeft, Layers, User, ChevronRight } from 'lucide-react';
import { Button } from '../../components/ui/button';

function AdminStoryDetail() {
  const { storyId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const token = localStorage.getItem('admin_token');

  useEffect(() => {
    if (!token) { navigate('/admin-access/login'); return; }
    fetchData();
  }, [storyId]);

  const fetchData = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin-9821/stories/${storyId}/episodes`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem('admin_token');
        navigate('/admin-access/login');
        return;
      }
      if (!res.ok) throw new Error('Failed to fetch story');
      setData(await res.json());
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('admin_token');
    navigate('/admin-access/login');
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-obsidian flex items-center justify-center">
        <div className="text-neon-cyan font-space">Loading story...</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-obsidian flex items-center justify-center">
        <div className="text-text-secondary">Story not found</div>
      </div>
    );
  }

  const { story, creator_name, creator_email, episodes } = data;

  return (
    <div className="min-h-screen bg-obsidian" data-testid="admin-story-detail">
      <header className="border-b border-white/5 bg-charcoal/60 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-electric-purple" />
            <span className="font-syne font-bold text-white text-lg">StoryFy Admin</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link to="/admin-access/dashboard" className="text-text-secondary hover:text-white text-sm" data-testid="nav-dashboard">Dashboard</Link>
            <Link to="/admin-access/creators" className="text-text-secondary hover:text-white text-sm" data-testid="nav-creators">Creators</Link>
            <Link to="/admin-access/stories" className="text-neon-cyan text-sm font-medium" data-testid="nav-stories">Stories</Link>
            <Link to="/admin-access/usage" className="text-text-secondary hover:text-white text-sm" data-testid="nav-usage">Usage</Link>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-text-secondary hover:text-white" data-testid="admin-logout-btn">
              <LogOut className="w-4 h-4 mr-1" /> Logout
            </Button>
          </nav>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        <Button variant="ghost" size="sm" className="text-text-secondary hover:text-white mb-4" onClick={() => navigate('/admin-access/stories')} data-testid="back-to-stories">
          <ArrowLeft className="w-4 h-4 mr-1" /> Back to Stories
        </Button>

        {/* Story Info */}
        <div className="bg-charcoal border border-white/5 rounded-sm p-5 mb-6">
          <h1 className="text-xl font-syne font-bold text-white mb-2">{story.title}</h1>
          <div className="flex flex-wrap items-center gap-4 text-sm text-text-secondary">
            <span className="flex items-center gap-1"><User className="w-3.5 h-3.5" /> {creator_name} ({creator_email})</span>
            <span className="px-2 py-0.5 rounded-full border border-warm-gold/30 text-warm-gold bg-warm-gold/10 text-xs">{story.genre}</span>
            <span>{story.story_type}</span>
            <span>{story.language}</span>
          </div>
          {story.description && <p className="text-text-secondary text-sm mt-3">{story.description}</p>}
        </div>

        {/* Episodes */}
        <h2 className="text-lg font-syne font-bold text-white mb-3 flex items-center gap-2">
          <Layers className="w-4 h-4 text-neon-cyan" /> Episodes ({episodes.length})
        </h2>

        {episodes.length === 0 ? (
          <div className="text-center py-12 text-text-secondary bg-charcoal border border-white/5 rounded-sm">
            No episodes in this story
          </div>
        ) : (
          <div className="grid gap-2">
            {episodes.map((ep) => {
              const hasProject = ep.project_state && ep.project_state.tracks && ep.project_state.tracks.length > 0;
              const trackCount = hasProject ? ep.project_state.tracks.length : 0;
              const clipCount = hasProject ? ep.project_state.tracks.reduce((sum, t) => sum + (t.clips?.length || 0), 0) : 0;

              return (
                <div
                  key={ep.episode_id}
                  className={`bg-charcoal border rounded-sm p-4 flex items-center justify-between transition-colors ${
                    hasProject ? 'border-white/10 hover:border-neon-cyan/30 cursor-pointer' : 'border-white/5 opacity-60'
                  }`}
                  onClick={() => hasProject && navigate(`/admin-access/projects/${ep.episode_id}`)}
                  data-testid={`episode-row-${ep.episode_id}`}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-secondary font-mono">#{ep.order}</span>
                      <span className="text-white font-medium">{ep.title}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded border ${
                        ep.status === 'published' ? 'border-signal-green/30 text-signal-green' :
                        ep.status === 'in_production' ? 'border-neon-cyan/30 text-neon-cyan' :
                        'border-white/10 text-text-secondary'
                      }`}>{ep.status}</span>
                    </div>
                    {hasProject && (
                      <p className="text-xs text-text-secondary mt-1">{trackCount} tracks, {clipCount} clips — v{ep.project_state.version || 0}</p>
                    )}
                    {!hasProject && <p className="text-xs text-text-secondary mt-1">No project data</p>}
                  </div>
                  {hasProject && <ChevronRight className="w-4 h-4 text-text-secondary" />}
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

export default AdminStoryDetail;
