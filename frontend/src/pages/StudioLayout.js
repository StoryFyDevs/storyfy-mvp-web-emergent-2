import React, { useState, useEffect } from 'react';
import { useParams, Outlet, NavLink, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { ArrowLeft, FileText, Users, Music, Mic2, Globe, FileEdit } from 'lucide-react';
import { toast } from 'sonner';
import { StudioProvider, useStudio } from '../contexts/StudioContext';
import LoadingScreen from '../components/LoadingScreen';

function StudioContent({ story, fetchStory }) {
  const { studioLoading } = useStudio();

  if (studioLoading) {
    return <LoadingScreen message="Loading your studio..." />;
  }

  const isPublished = story?.status === 'published';

  return (
    <main className="flex-1 overflow-auto">
      <Outlet context={{ story, refreshStory: fetchStory }} />
    </main>
  );
}

function StudioLayout() {
  const { storyId } = useParams();
  const [story, setStory] = useState(null);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const navigate = useNavigate();

  const authHeaders = {
    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
  };

  useEffect(() => {
    fetchStory();
  }, [storyId]);

  const fetchStory = async () => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/stories/${storyId}`, {
        credentials: 'include', headers: authHeaders
      });
      if (!response.ok) throw new Error('Failed to fetch story');
      setStory(await response.json());
    } catch (error) {
      toast.error('Failed to load story');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  };

  const handleTogglePublish = async () => {
    const action = story.status === 'published' ? 'unpublish' : 'publish';
    setPublishing(true);
    setShowConfirm(false);
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/creator/stories/${storyId}/${action}`, {
        method: 'POST', credentials: 'include', headers: authHeaders
      });
      if (!res.ok) throw new Error(`Failed to ${action}`);
      const data = await res.json();
      setStory(prev => ({ ...prev, status: data.status }));
      toast.success(action === 'publish' ? 'Story published!' : 'Story unpublished');
    } catch (error) {
      toast.error(`Failed to ${action} story`);
    } finally {
      setPublishing(false);
    }
  };

  if (loading) {
    return <LoadingScreen message="Loading your story..." />;
  }

  const isPublished = story?.status === 'published';

  return (
    <StudioProvider storyId={storyId}>
      <div className="min-h-screen bg-obsidian flex flex-col" data-testid="studio-layout">
        <header className="border-b border-white/10 bg-charcoal px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button onClick={() => navigate('/dashboard')} variant="ghost" size="icon" className="text-text-secondary hover:text-white" data-testid="back-to-dashboard">
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-space font-bold text-white">{story?.title}</h1>
                {isPublished ? (
                  <span className="px-2 py-0.5 text-xs bg-signal-green/20 text-signal-green rounded-sm flex items-center gap-1" data-testid="story-publish-badge">
                    <Globe className="w-3 h-3" /> Published
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-xs bg-amber-500/20 text-amber-400 rounded-sm flex items-center gap-1" data-testid="story-publish-badge">
                    <FileEdit className="w-3 h-3" /> Draft
                  </span>
                )}
              </div>
              <p className="text-sm text-text-secondary">{story?.genre} &bull; {story?.story_type}</p>
            </div>
          </div>

          <Button
            onClick={() => setShowConfirm(true)}
            disabled={publishing}
            className={isPublished
              ? 'border border-red-500/50 text-red-400 bg-transparent hover:bg-red-500/10'
              : 'bg-signal-green text-obsidian hover:bg-signal-green/90'
            }
            data-testid="story-publish-toggle"
          >
            {publishing ? '...' : isPublished ? 'Unpublish Story' : 'Publish Story'}
          </Button>

          <Dialog open={showConfirm} onOpenChange={setShowConfirm}>
            <DialogContent className="bg-charcoal border-white/10 text-white max-w-md">
              <DialogHeader>
                <DialogTitle className="text-xl font-space">
                  {isPublished ? 'Unpublish Story?' : 'Publish Story?'}
                </DialogTitle>
              </DialogHeader>
              <p className="text-text-secondary text-sm mb-4">
                {isPublished
                  ? 'This will remove the story from the listener app. All episodes will also be unpublished.'
                  : 'This will make the story visible in the listener app. Make sure to publish individual episodes you want listeners to access.'}
              </p>
              <div className="flex gap-3 justify-end">
                <Button variant="ghost" onClick={() => setShowConfirm(false)} className="text-text-secondary">Cancel</Button>
                <Button
                  onClick={handleTogglePublish}
                  className={isPublished ? 'bg-red-500 hover:bg-red-600 text-white' : 'bg-signal-green text-obsidian hover:bg-signal-green/90'}
                  data-testid="confirm-publish-btn"
                >
                  {isPublished ? 'Yes, Unpublish' : 'Yes, Publish'}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </header>

        <nav className="border-b border-white/10 bg-charcoal px-6">
          <div className="flex gap-1">
            <NavLink to="script" className={({ isActive }) => `flex items-center gap-2 px-4 py-3 font-medium transition-colors ${isActive ? 'text-neon-cyan border-b-2 border-neon-cyan' : 'text-text-secondary hover:text-white'}`} data-testid="nav-script">
              <FileText className="w-4 h-4" /> Script
            </NavLink>
            <NavLink to="characters" className={({ isActive }) => `flex items-center gap-2 px-4 py-3 font-medium transition-colors ${isActive ? 'text-neon-cyan border-b-2 border-neon-cyan' : 'text-text-secondary hover:text-white'}`} data-testid="nav-characters">
              <Users className="w-4 h-4" /> Characters
            </NavLink>
            <NavLink to="audio" className={({ isActive }) => `flex items-center gap-2 px-4 py-3 font-medium transition-colors ${isActive ? 'text-signal-green border-b-2 border-signal-green' : 'text-text-secondary hover:text-white'}`} data-testid="nav-audio">
              <Music className="w-4 h-4" /> Audio Studio
            </NavLink>
            <NavLink to="voice-generator" className={({ isActive }) => `flex items-center gap-2 px-4 py-3 font-medium transition-colors ${isActive ? 'text-neon-purple border-b-2 border-neon-purple' : 'text-text-secondary hover:text-white'}`} data-testid="nav-voice-generator">
              <Mic2 className="w-4 h-4" /> Voice Generator
            </NavLink>
          </div>
        </nav>

        <StudioContent story={story} fetchStory={fetchStory} />
      </div>
    </StudioProvider>
  );
}

export default StudioLayout;
