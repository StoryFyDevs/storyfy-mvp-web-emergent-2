import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { toast } from 'sonner';
import { Plus, Mic, Book, LogOut, Zap, HardDrive, Globe, FileEdit } from 'lucide-react';

function UsageBar({ label, used, total, unit, accent }) {
  const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;
  const isHigh = pct > 80;
  const barColor = isHigh ? 'bg-red-500' : accent === 'cyan' ? 'bg-neon-cyan' : 'bg-electric-purple';
  return (
    <div className="flex-1" data-testid={`usage-bar-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-text-secondary text-xs">{label}</span>
        <span className={`text-xs font-mono ${isHigh ? 'text-red-400' : 'text-white'}`}>{used.toLocaleString()} / {total.toLocaleString()} {unit}</span>
      </div>
      <div className="h-2 bg-slate rounded-full overflow-hidden">
        <div className={`h-full ${barColor} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Dashboard() {
  const [stories, setStories] = useState([]);
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [publishingId, setPublishingId] = useState(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newStory, setNewStory] = useState({
    title: '',
    genre: 'fiction',
    language: 'English',
    description: '',
    story_type: 'story'
  });
  const navigate = useNavigate();

  const authHeaders = {
    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
  };

  useEffect(() => {
    fetchStories();
    fetchUsage();
  }, []);

  const fetchUsage = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/usage/me`, {
        credentials: 'include', headers: authHeaders
      });
      if (res.ok) setUsage(await res.json());
    } catch (e) { /* silent */ }
  };

  const fetchStories = async () => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/stories`, {
        credentials: 'include', headers: authHeaders
      });
      if (!response.ok) throw new Error('Failed to fetch stories');
      setStories(await response.json());
    } catch (error) {
      toast.error('Failed to load stories');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateStory = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/stories`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(newStory)
      });
      if (!response.ok) throw new Error('Failed to create story');
      const story = await response.json();
      setStories([...stories, story]);
      setShowCreateDialog(false);
      setNewStory({ title: '', genre: 'fiction', language: 'English', description: '', story_type: 'story' });
      toast.success('Story created successfully!');
      navigate(`/studio/${story.story_id}`);
    } catch (error) {
      toast.error('Failed to create story');
    }
  };

  const handleTogglePublish = async (e, storyId, currentStatus) => {
    e.stopPropagation();
    const action = currentStatus === 'published' ? 'unpublish' : 'publish';
    setPublishingId(storyId);
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/creator/stories/${storyId}/${action}`, {
        method: 'POST', credentials: 'include', headers: authHeaders
      });
      if (!res.ok) throw new Error(`Failed to ${action}`);
      const data = await res.json();
      setStories(prev => prev.map(s => s.story_id === storyId ? { ...s, status: data.status } : s));
      toast.success(action === 'publish' ? 'Story published!' : 'Story unpublished');
    } catch (error) {
      toast.error(`Failed to ${action} story`);
    } finally {
      setPublishingId(null);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' });
      localStorage.removeItem('token');
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-obsidian flex items-center justify-center">
        <div className="text-neon-cyan text-xl font-space">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-obsidian" data-testid="dashboard">
      <header className="border-b border-white/10 bg-charcoal">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <h1 className="text-3xl font-bold font-syne text-white">StoryFy</h1>
          <Button onClick={handleLogout} variant="ghost" className="text-text-secondary hover:text-white" data-testid="logout-button">
            <LogOut className="w-5 h-5 mr-2" /> Logout
          </Button>
        </div>
      </header>

      {usage && (
        <div className="border-b border-white/5 bg-charcoal/40">
          <div className="max-w-7xl mx-auto px-6 py-3 flex gap-6" data-testid="usage-summary-bar">
            <UsageBar label="Credits" used={usage.total_credits_used || 0} total={(usage.total_credits_used || 0) + (usage.limits_remaining || 0)} unit="chars" accent="cyan" />
            <UsageBar label="Storage" used={usage.storage_used_mb || 0} total={usage.storage_limit_mb || 500} unit="MB" accent="purple" />
            <div className="flex items-center gap-4 text-xs shrink-0">
              <div className="flex items-center gap-1.5" data-testid="credits-remaining">
                <Zap className="w-3.5 h-3.5 text-neon-cyan" />
                <span className="text-text-secondary">Left:</span>
                <span className={`font-mono ${(usage.limits_remaining || 0) < 100 ? 'text-red-400' : 'text-neon-cyan'}`}>{(usage.limits_remaining || 0).toLocaleString()}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <HardDrive className="w-3.5 h-3.5 text-electric-purple" />
                <span className="text-text-secondary">Gens:</span>
                <span className="text-white font-mono">{usage.total_generations || 0}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-4xl font-bold text-white mb-2">Your Stories</h2>
            <p className="text-text-secondary text-lg">Create, produce, and publish audio stories</p>
          </div>
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 font-semibold" data-testid="create-story-button">
                <Plus className="w-5 h-5 mr-2" /> New Story
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-charcoal border-white/10 text-white">
              <DialogHeader>
                <DialogTitle className="text-2xl font-space">Create New Story</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreateStory} className="space-y-4">
                <div>
                  <Label htmlFor="title">Title</Label>
                  <Input id="title" value={newStory.title} onChange={(e) => setNewStory({ ...newStory, title: e.target.value })} className="mt-2 bg-slate border-white/10 text-white" placeholder="The Midnight Chronicles" required data-testid="story-title-input" />
                </div>
                <div>
                  <Label htmlFor="type">Type</Label>
                  <Select value={newStory.story_type} onValueChange={(value) => setNewStory({ ...newStory, story_type: value })}>
                    <SelectTrigger className="mt-2 bg-slate border-white/10 text-white" data-testid="story-type-select"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-charcoal border-white/10">
                      <SelectItem value="story">Story</SelectItem>
                      <SelectItem value="audiobook">Audiobook</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="genre">Genre</Label>
                  <Select value={newStory.genre} onValueChange={(value) => setNewStory({ ...newStory, genre: value })}>
                    <SelectTrigger className="mt-2 bg-slate border-white/10 text-white" data-testid="story-genre-select"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-charcoal border-white/10">
                      <SelectItem value="fiction">Fiction</SelectItem>
                      <SelectItem value="fantasy">Fantasy</SelectItem>
                      <SelectItem value="sci-fi">Sci-Fi</SelectItem>
                      <SelectItem value="mystery">Mystery</SelectItem>
                      <SelectItem value="thriller">Thriller</SelectItem>
                      <SelectItem value="romance">Romance</SelectItem>
                      <SelectItem value="horror">Horror</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="language">Language</Label>
                  <Input id="language" value={newStory.language} onChange={(e) => setNewStory({ ...newStory, language: e.target.value })} className="mt-2 bg-slate border-white/10 text-white" data-testid="story-language-input" />
                </div>
                <div>
                  <Label htmlFor="description">Description</Label>
                  <Textarea id="description" value={newStory.description} onChange={(e) => setNewStory({ ...newStory, description: e.target.value })} className="mt-2 bg-slate border-white/10 text-white" rows={3} placeholder="A thrilling adventure through..." data-testid="story-description-input" />
                </div>
                <Button type="submit" className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 font-semibold" data-testid="create-story-submit">
                  Create Story
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {stories.length === 0 ? (
          <div className="text-center py-20">
            <div className="inline-block p-6 bg-charcoal rounded-lg border border-white/10 mb-4">
              <Mic className="w-16 h-16 text-neon-cyan mx-auto" />
            </div>
            <h3 className="text-2xl font-space text-white mb-2">No stories yet</h3>
            <p className="text-text-secondary mb-6">Create your first audio story to get started</p>
            <Button onClick={() => setShowCreateDialog(true)} className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 font-semibold" data-testid="empty-create-story-button">
              <Plus className="w-5 h-5 mr-2" /> Create Your First Story
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {stories.map((story) => (
              <div
                key={story.story_id}
                onClick={() => navigate(`/studio/${story.story_id}`)}
                className="bg-charcoal border border-white/10 rounded-sm p-6 cursor-pointer hover:border-neon-cyan/50 transition-all group"
                data-testid={`story-card-${story.story_id}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl font-space font-bold text-white mb-2 truncate">{story.title}</h3>
                    <div className="flex items-center gap-2 text-sm text-text-secondary flex-wrap">
                      <span className="px-2 py-1 bg-slate rounded-sm">{story.genre}</span>
                      <span className="px-2 py-1 bg-slate rounded-sm">{story.story_type}</span>
                      {story.status === 'published' ? (
                        <span className="px-2 py-1 bg-signal-green/20 text-signal-green rounded-sm flex items-center gap-1" data-testid={`story-status-${story.story_id}`}>
                          <Globe className="w-3 h-3" /> Published
                        </span>
                      ) : (
                        <span className="px-2 py-1 bg-amber-500/20 text-amber-400 rounded-sm flex items-center gap-1" data-testid={`story-status-${story.story_id}`}>
                          <FileEdit className="w-3 h-3" /> Draft
                        </span>
                      )}
                    </div>
                  </div>
                  {story.story_type === 'audiobook' ? (
                    <Book className="w-8 h-8 text-neon-cyan shrink-0" />
                  ) : (
                    <Mic className="w-8 h-8 text-signal-green shrink-0" />
                  )}
                </div>
                <p className="text-text-secondary text-sm line-clamp-2 mb-4">{story.description}</p>
                <div className="flex items-center justify-end">
                  <Button
                    size="sm"
                    variant={story.status === 'published' ? 'outline' : 'default'}
                    className={story.status === 'published'
                      ? 'border-red-500/50 text-red-400 hover:bg-red-500/10 hover:text-red-300'
                      : 'bg-signal-green text-obsidian hover:bg-signal-green/90'
                    }
                    onClick={(e) => handleTogglePublish(e, story.story_id, story.status)}
                    disabled={publishingId === story.story_id}
                    data-testid={`publish-btn-${story.story_id}`}
                  >
                    {publishingId === story.story_id ? '...' : story.status === 'published' ? 'Unpublish' : 'Publish'}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default Dashboard;
