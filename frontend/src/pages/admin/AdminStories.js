import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, LogOut, Search, BookOpen, ChevronRight, User, Layers } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';

function AdminStories() {
  const [stories, setStories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  const token = localStorage.getItem('admin_token');

  useEffect(() => {
    if (!token) { navigate('/admin-access/login'); return; }
    fetchStories();
  }, []);

  const fetchStories = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin-9821/stories`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem('admin_token');
        navigate('/admin-access/login');
        return;
      }
      if (!res.ok) throw new Error('Failed to fetch stories');
      setStories(await res.json());
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

  const filtered = stories.filter(s =>
    s.title?.toLowerCase().includes(search.toLowerCase()) ||
    s.creator_name?.toLowerCase().includes(search.toLowerCase()) ||
    s.creator_email?.toLowerCase().includes(search.toLowerCase()) ||
    s.genre?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-obsidian flex items-center justify-center">
        <div className="text-neon-cyan font-space">Loading stories...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-obsidian" data-testid="admin-stories">
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
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-syne font-bold text-white">Stories & Projects</h1>
          <div className="relative w-72">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
            <Input
              placeholder="Search by title, creator, genre..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 bg-slate border-white/10 text-white text-sm"
              data-testid="story-search-input"
            />
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-16 text-text-secondary">
            <BookOpen className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>No stories found</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {filtered.map((story) => (
              <div
                key={story.story_id}
                className="bg-charcoal border border-white/5 rounded-sm p-4 hover:border-white/15 transition-colors cursor-pointer"
                onClick={() => navigate(`/admin-access/stories/${story.story_id}`)}
                data-testid={`story-card-${story.story_id}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <h3 className="text-white font-medium truncate">{story.title}</h3>
                      <span className="text-xs px-2 py-0.5 rounded-full border border-warm-gold/30 text-warm-gold bg-warm-gold/10 shrink-0">
                        {story.genre}
                      </span>
                      <span className="text-xs text-text-secondary shrink-0">{story.story_type}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-text-secondary">
                      <span className="flex items-center gap-1">
                        <User className="w-3 h-3" /> {story.creator_name} ({story.creator_email})
                      </span>
                      <span className="flex items-center gap-1">
                        <Layers className="w-3 h-3" /> {story.episodes_count} episodes
                      </span>
                      <span>{story.language}</span>
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-text-secondary shrink-0 ml-4" />
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default AdminStories;
