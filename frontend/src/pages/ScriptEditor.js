import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { useStudio } from '../contexts/StudioContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Label } from '../components/ui/label';
import { Plus, Save, FileText, Globe, FileEdit, Trash2, GripVertical, Play, Loader2, CheckCircle, AlertCircle, ChevronDown, ChevronUp, Sparkles, MoreHorizontal, RefreshCw } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '../components/ui/dropdown-menu';
import { toast } from 'sonner';

const base = process.env.REACT_APP_BACKEND_URL;

function ScriptEditor() {
  const { storyId } = useParams();
  const { story } = useOutletContext();
  const {
    episodes, refreshEpisodes,
    characters,
    voices,
    selectedEpisode, setSelectedEpisode,
    requestEpisodeSwitch,
    setIsProjectDirty,
    registerSaveCallback,
  } = useStudio();
  const [dialogues, setDialogues] = useState([]);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newEpisode, setNewEpisode] = useState({ title: '', order: 1 });
  const [publishingEp, setPublishingEp] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [genJobId, setGenJobId] = useState(null);
  const [genProgress, setGenProgress] = useState({ completed: 0, total: 0, status: '' });
  const pollRef = useRef(null);

  // Per-dialogue regeneration loading (Set of indices)
  const [regenLoading, setRegenLoading] = useState(new Set());

  const authHeaders = {
    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
  };

  useEffect(() => {
    if (selectedEpisode && characters.length > 0) {
      loadDialogues(selectedEpisode.episode_id);
    }
  }, [selectedEpisode?.episode_id, characters]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const getVoiceName = (voiceId) => {
    if (!voiceId) return '';
    const v = voices.find(x => x.voice_id === voiceId);
    return v ? v.name : voiceId;
  };

  const loadDialogues = async (episodeId) => {
    try {
      const res = await fetch(`${base}/api/script/${episodeId}/dialogues`, {
        credentials: 'include', headers: authHeaders
      });
      if (!res.ok) throw new Error('Failed to load script');
      const data = await res.json();
      if (data.dialogues && data.dialogues.length > 0) {
        // Resolve current voice_id from characters for each dialogue
        const resolved = data.dialogues.map(d => {
          const char = characters.find(c => c.character_id === d.character_id);
          return {
            ...d,
            // Always resolve voice_id from the character's CURRENT voice
            voice_id: char ? (char.voice_id || '') : (d.voice_id || ''),
            // Preserve the generated_voice_id snapshot from saved data
            generated_voice_id: d.generated_voice_id || '',
          };
        });
        setDialogues(resolved);
      } else {
        setDialogues([createEmptyDialogue(0)]);
      }
      setDirty(false);
    } catch (error) {
      setDialogues([createEmptyDialogue(0)]);
    }
  };

  const createEmptyDialogue = (index) => ({
    index,
    character_id: '',
    character_name: '',
    voice_id: '',
    text: '',
    director_notes: '',
    generated_voice_id: '',
  });

  const handleCreateEpisode = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${base}/api/episodes`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ story_id: storyId, title: newEpisode.title, order: newEpisode.order, script: '' })
      });
      if (!response.ok) throw new Error('Failed to create episode');
      const episode = await response.json();
      await refreshEpisodes();
      setSelectedEpisode(episode);
      setDialogues([createEmptyDialogue(0)]);
      setShowCreateDialog(false);
      setNewEpisode({ title: '', order: episodes.length + 1 });
      toast.success('Episode created!');
    } catch (error) {
      toast.error('Failed to create episode');
    }
  };

  const handleSaveScript = useCallback(async () => {
    if (!selectedEpisode) return;
    setSaving(true);
    try {
      const indexed = dialogues.map((d, i) => ({ ...d, index: i }));
      const res = await fetch(`${base}/api/script/${selectedEpisode.episode_id}/dialogues`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ dialogues: indexed })
      });
      if (!res.ok) throw new Error('Failed to save script');
      setDialogues(indexed);
      setDirty(false);
      toast.success('Script saved!');
    } catch (error) {
      toast.error('Failed to save script');
    } finally {
      setSaving(false);
    }
  }, [selectedEpisode, dialogues, base]);

  // Sync local dirty state to global context
  useEffect(() => {
    setIsProjectDirty(dirty);
  }, [dirty, setIsProjectDirty]);

  // Register handleSaveScript as the save callback for the unsaved changes modal
  useEffect(() => {
    registerSaveCallback(handleSaveScript);
    return () => registerSaveCallback(null);
  }, [registerSaveCallback, handleSaveScript]);

  // Browser refresh/close guard
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [dirty]);

  // ========== DIALOGUE MANAGEMENT ==========

  const updateDialogue = (index, field, value) => {
    setDialogues(prev => prev.map((d, i) => {
      if (i !== index) return d;
      const updated = { ...d, [field]: value };
      // Auto-fill character details when character is selected
      if (field === 'character_id') {
        const char = characters.find(c => c.character_id === value);
        if (char) {
          updated.character_name = char.name;
          updated.voice_id = char.voice_id || '';
        }
      }
      return updated;
    }));
    setDirty(true);
  };

  const addDialogue = (afterIndex) => {
    const newD = createEmptyDialogue(afterIndex + 1);
    setDialogues(prev => {
      const next = [...prev];
      next.splice(afterIndex + 1, 0, newD);
      return next.map((d, i) => ({ ...d, index: i }));
    });
    setDirty(true);
  };

  const removeDialogue = (index) => {
    if (dialogues.length <= 1) {
      toast.error('Cannot remove the last dialogue');
      return;
    }
    setDialogues(prev => prev.filter((_, i) => i !== index).map((d, i) => ({ ...d, index: i })));
    setDirty(true);
  };

  const moveDialogue = (index, direction) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= dialogues.length) return;
    setDialogues(prev => {
      const next = [...prev];
      [next[index], next[newIndex]] = [next[newIndex], next[index]];
      return next.map((d, i) => ({ ...d, index: i }));
    });
    setDirty(true);
  };

  // ========== GENERATION ==========

  const handleGenerate = async () => {
    if (!selectedEpisode) return;

    // Validate: all dialogues need character + text
    const valid = dialogues.filter(d => d.character_id && d.text.trim());
    if (valid.length === 0) {
      toast.error('Add at least one dialogue with a character and text');
      return;
    }

    const incomplete = dialogues.filter(d => d.text.trim() && !d.character_id);
    if (incomplete.length > 0) {
      toast.error('Some dialogues are missing a character assignment');
      return;
    }

    // Save first
    await handleSaveScript();

    setGenerating(true);
    setGenProgress({ completed: 0, total: valid.length, status: 'Starting...' });

    try {
      // Resolve voice_id from characters (always use current character voice)
      const indexed = valid.map((d, i) => {
        const char = characters.find(c => c.character_id === d.character_id);
        return {
          ...d,
          index: i,
          voice_id: char ? (char.voice_id || '') : (d.voice_id || ''),
        };
      });
      const res = await fetch(`${base}/api/script/${selectedEpisode.episode_id}/generate`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ dialogues: indexed })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Generation failed');
      }

      const data = await res.json();
      setGenJobId(data.job_id);
      setGenProgress({ completed: 0, total: data.total_dialogues, status: 'Generating audio...' });

      // Store removed clips info for later timeline cleanup (scoped to episode)
      if (data.removed_clips && data.removed_clips.length > 0) {
        const removedKey = `removed_clips_${storyId}_${selectedEpisode.episode_id}`;
        localStorage.setItem(removedKey, JSON.stringify(data.removed_clips));
      }

      // Start polling
      startPolling(data.job_id);
    } catch (error) {
      toast.error(error.message || 'Failed to start generation');
      setGenerating(false);
    }
  };

  const startPolling = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${base}/api/script/job/${jobId}/status`, {
          credentials: 'include', headers: authHeaders
        });
        if (!res.ok) return;
        const data = await res.json();

        setGenProgress({
          completed: data.completed_dialogues,
          total: data.total_dialogues,
          status: data.status === 'processing' ? 'Generating audio...'
            : data.status === 'completed' ? 'Complete!'
            : data.status === 'completed_with_errors' ? 'Completed with some errors'
            : data.status === 'failed' ? 'Generation failed'
            : 'Waiting...',
        });

        if (['completed', 'completed_with_errors', 'failed'].includes(data.status)) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setGenerating(false);

          if (data.status === 'failed') {
            toast.error(data.error_message || 'Generation failed');
          } else {
            // Push clips to Audio Studio via localStorage
            pushClipsToTimeline(data.results);

            // Update generated_voice_id snapshot for each dialogue
            updateVoiceSnapshots(data.results);

            toast.success(`Audio generated! ${data.completed_dialogues} clips ready.`);
          }
        }
      } catch (err) {
        // Ignore polling errors
      }
    }, 2000);
  };

  const pushClipsToTimeline = (results) => {
    if (!results || Object.keys(results).length === 0) return;

    // Collect all valid clips and sort by dialogue_index for deterministic ordering
    const allClips = [];
    for (const [key, r] of Object.entries(results)) {
      if (!r.audio_url || r.error) continue;
      const dialogueIndex = r.dialogue_index !== undefined ? r.dialogue_index : parseInt(key);
      const d = dialogues[dialogueIndex] || {};
      const charName = r.character_name || d.character_name || 'Unknown';
      const duration = r.duration_seconds || 3;
      const filename = r.filename || `${charName.replace(/\s/g, '_')}_${String(dialogueIndex + 1).padStart(2, '0')}.wav`;

      allClips.push({
        dialogueIndex,
        charName,
        duration,
        filename,
        url: r.audio_url,
        text: d.text || '',
      });
    }

    // Sort by dialogue_index to guarantee script order
    allClips.sort((a, b) => a.dialogueIndex - b.dialogueIndex);

    // Build per-character tracks with sequential timing based on script order
    const tracksByChar = {};
    let globalOffset = 0;

    for (const clip of allClips) {
      if (!tracksByChar[clip.charName]) {
        tracksByChar[clip.charName] = [];
      }

      tracksByChar[clip.charName].push({
        id: `scrclip-${Date.now()}-${clip.dialogueIndex}`,
        name: clip.filename.replace('.wav', ''),
        url: clip.url,
        duration: clip.duration,
        characterName: clip.charName,
        text: clip.text,
        type: 'voice',
        dialogueIndex: clip.dialogueIndex,
        start: globalOffset,
      });

      globalOffset += clip.duration + 0.3;
    }

    // Convert to track array format for AudioStudio
    const tracks = Object.entries(tracksByChar).map(([charName, clips]) => ({
      characterName: charName,
      clips,
    }));

    if (tracks.length > 0) {
      const pendingKey = `pending_clips_${storyId}_${selectedEpisode.episode_id}`;
      localStorage.setItem(pendingKey, JSON.stringify(tracks));
    }
  };

  const updateVoiceSnapshots = (results) => {
    if (!results) return;
    setDialogues(prev => {
      const updated = prev.map((d, i) => {
        const r = results[String(i)];
        if (r && r.generated_voice_id) {
          return { ...d, generated_voice_id: r.generated_voice_id };
        }
        return d;
      });
      // Auto-save script with updated generated_voice_id snapshots
      const indexed = updated.map((d, i) => ({ ...d, index: i }));
      fetch(`${base}/api/script/${selectedEpisode.episode_id}/dialogues`, {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ dialogues: indexed })
      }).catch(() => {});
      return updated;
    });
  };

  // ========== SINGLE-DIALOGUE REGENERATE ==========

  const handleRegenerateDialogue = async (index) => {
    const d = dialogues[index];
    if (!d || !d.text?.trim()) {
      toast.error('Dialogue has no text to regenerate');
      return;
    }
    const char = characters.find(c => c.character_id === d.character_id);
    if (!char?.voice_id) {
      toast.error('Assign a character with a voice before regenerating');
      return;
    }

    setRegenLoading(prev => new Set([...prev, index]));
    toast.loading(`Regenerating dialogue ${index + 1}...`, { id: `regen-${index}` });

    try {
      const res = await fetch(
        `${base}/api/script/${selectedEpisode.episode_id}/dialogue/${index}/regenerate`,
        {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json', ...authHeaders },
          body: JSON.stringify({
            dialogue_index: index,
            character_id: d.character_id,
            character_name: char.name || d.character_name || 'Unknown',
            voice_id: char.voice_id,
            text: d.text,
            director_notes: d.director_notes || '',
          }),
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      toast.dismiss(`regen-${index}`);
      toast.success(`Dialogue ${index + 1} regenerated`);

      // Update voice snapshot for this dialogue
      setDialogues(prev =>
        prev.map((item, i) =>
          i === index ? { ...item, generated_voice_id: data.generated_voice_id } : item
        )
      );

      // Write a targeted single-clip replacement for AudioStudio
      const charName = char.name || d.character_name || 'Unknown';
      const filename = data.filename || `${charName.replace(/\s/g, '_')}_${String(index + 1).padStart(2, '0')}.wav`;
      const replaceKey = `pending_clip_replace_${storyId}_${selectedEpisode.episode_id}`;
      localStorage.setItem(replaceKey, JSON.stringify({
        dialogueIndex: index,
        url: data.audio_url,
        duration: data.duration_seconds,
        name: filename.replace('.wav', ''),
        characterName: charName,
        text: d.text,
      }));
    } catch (err) {
      toast.dismiss(`regen-${index}`);
      toast.error(`Regeneration failed: ${err.message}`);
    } finally {
      setRegenLoading(prev => {
        const next = new Set(prev);
        next.delete(index);
        return next;
      });
    }
  };

  // ========== PUBLISH ==========

  const handleToggleEpisodePublish = async (e, episodeId, isPublished) => {
    e.stopPropagation();
    const ep = episodes.find(ep => ep.episode_id === episodeId);
    if (!isPublished) {
      if (!ep?.finalAudioUrl) {
        toast.error('Cannot publish: no rendered audio. Use Audio Studio to render first.');
        return;
      }
    }
    const action = isPublished ? 'unpublish' : 'publish';
    setPublishingEp(episodeId);
    try {
      const res = await fetch(`${base}/api/creator/episodes/${episodeId}/${action}`, {
        method: 'POST', credentials: 'include', headers: authHeaders
      });
      if (!res.ok) throw new Error(`Failed to ${action}`);
      const data = await res.json();
      setEpisodes(prev => prev.map(ep =>
        ep.episode_id === episodeId ? { ...ep, isPublished: data.isPublished } : ep
      ));
      if (selectedEpisode?.episode_id === episodeId) {
        setSelectedEpisode(prev => ({ ...prev, isPublished: data.isPublished }));
      }
      toast.success(action === 'publish' ? 'Episode published!' : 'Episode unpublished');
    } catch (error) {
      toast.error(`Failed to ${action} episode`);
    } finally {
      setPublishingEp(null);
    }
  };

  const handleEpisodeSelect = (episode) => {
    requestEpisodeSwitch(episode);
  };

  const progressPct = genProgress.total > 0 ? Math.round((genProgress.completed / genProgress.total) * 100) : 0;

  // Count dialogues needing regeneration due to voice changes
  const regenCount = dialogues.filter(d => {
    if (!d.generated_voice_id || !d.character_id) return false;
    const char = characters.find(c => c.character_id === d.character_id);
    return char && char.voice_id && d.generated_voice_id !== char.voice_id;
  }).length;

  return (
    <div className="h-full flex" data-testid="script-editor">
      {/* Episode Sidebar */}
      <div className="w-72 border-r border-white/10 bg-charcoal p-4 flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-space font-bold text-white">Episodes</h2>
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button size="sm" className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90" data-testid="create-episode-button">
                <Plus className="w-4 h-4" />
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-charcoal border-white/10 text-white">
              <DialogHeader>
                <DialogTitle className="font-space">New Episode</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreateEpisode} className="space-y-4">
                <div>
                  <Label>Title</Label>
                  <Input value={newEpisode.title} onChange={(e) => setNewEpisode({ ...newEpisode, title: e.target.value })} className="mt-2 bg-slate border-white/10 text-white" placeholder="Episode 1: The Beginning" required data-testid="episode-title-input" />
                </div>
                <div>
                  <Label>Order</Label>
                  <Input type="number" value={newEpisode.order} onChange={(e) => setNewEpisode({ ...newEpisode, order: parseInt(e.target.value) })} className="mt-2 bg-slate border-white/10 text-white" min="1" required data-testid="episode-order-input" />
                </div>
                <Button type="submit" className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90" data-testid="create-episode-submit">
                  Create Episode
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="space-y-2 flex-1 overflow-y-auto">
          {episodes.length === 0 ? (
            <p className="text-text-secondary text-sm text-center py-8">No episodes yet</p>
          ) : (
            episodes.map((episode) => (
              <div
                key={episode.episode_id}
                onClick={() => handleEpisodeSelect(episode)}
                className={`p-3 rounded-sm cursor-pointer transition-all ${
                  selectedEpisode?.episode_id === episode.episode_id
                    ? 'bg-slate border border-neon-cyan/50'
                    : 'bg-slate/50 border border-transparent hover:border-white/20'
                }`}
                data-testid={`episode-${episode.episode_id}`}
              >
                <h3 className="text-white font-medium text-sm mb-1 truncate">{episode.title}</h3>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-secondary">Ep {episode.order}</span>
                  <button
                    onClick={(e) => handleToggleEpisodePublish(e, episode.episode_id, episode.isPublished)}
                    disabled={publishingEp === episode.episode_id}
                    className={`text-xs px-1.5 py-0.5 rounded-sm transition-colors ${
                      episode.isPublished
                        ? 'bg-signal-green/20 text-signal-green hover:bg-signal-green/30'
                        : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-white'
                    }`}
                    data-testid={`ep-publish-${episode.episode_id}`}
                  >
                    {publishingEp === episode.episode_id ? '...' : episode.isPublished ? (
                      <span className="flex items-center gap-0.5"><Globe className="w-3 h-3" /> Live</span>
                    ) : (
                      <span className="flex items-center gap-0.5"><FileEdit className="w-3 h-3" /> Draft</span>
                    )}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Characters hint */}
        {characters.length === 0 && (
          <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-sm">
            <p className="text-amber-300 text-xs">No characters created yet. Go to the Characters tab to create characters with voice assignments.</p>
          </div>
        )}
      </div>

      {/* Main Script Area */}
      <div className="flex-1 flex flex-col">
        {selectedEpisode ? (
          <>
            {/* Header */}
            <div className="border-b border-white/10 bg-charcoal px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div>
                  <h2 className="text-xl font-space font-bold text-white">{selectedEpisode.title}</h2>
                  <p className="text-sm text-text-secondary">
                    {dialogues.filter(d => d.text.trim()).length} dialogue{dialogues.filter(d => d.text.trim()).length !== 1 ? 's' : ''}
                    {dirty && <span className="ml-2 text-amber-400">Unsaved</span>}
                  </p>
                </div>
                {selectedEpisode.isPublished && (
                  <span className="px-2 py-0.5 text-xs bg-signal-green/20 text-signal-green rounded-sm flex items-center gap-1">
                    <Globe className="w-3 h-3" /> Published
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  onClick={handleSaveScript}
                  disabled={saving || !dirty}
                  variant="outline"
                  className="border-white/20 text-white hover:bg-white/5"
                  data-testid="save-script-button"
                >
                  {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />}
                  Save
                </Button>
                <Button
                  onClick={handleGenerate}
                  disabled={generating || dialogues.filter(d => d.character_id && d.text.trim()).length === 0}
                  className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
                  data-testid="generate-audio-button"
                >
                  {generating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
                  {generating ? 'Generating...' : 'Generate Audio'}
                </Button>
              </div>
            </div>

            {/* Generation Progress Bar */}
            {generating && (
              <div className="bg-charcoal border-b border-neon-cyan/30 px-6 py-3" data-testid="generation-progress">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-4 h-4 text-neon-cyan animate-spin" />
                  <span className="text-neon-cyan text-sm font-medium">{genProgress.status}</span>
                  <span className="text-text-secondary text-xs">
                    {genProgress.completed}/{genProgress.total} clips
                  </span>
                  <div className="flex-1 h-2 bg-slate rounded-full overflow-hidden">
                    <div
                      className="h-full bg-neon-cyan rounded-full transition-all duration-500"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  <span className="text-neon-cyan text-sm font-mono">{progressPct}%</span>
                </div>
              </div>
            )}

            {/* Voice Change Regeneration Banner */}
            {!generating && regenCount > 0 && (
              <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-3 flex items-center justify-between" data-testid="voice-change-banner">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-400" />
                  <span className="text-amber-300 text-sm">
                    {regenCount} dialogue{regenCount !== 1 ? 's' : ''} need{regenCount === 1 ? 's' : ''} regeneration — character voice changed since last generation.
                  </span>
                </div>
                <Button
                  onClick={handleGenerate}
                  size="sm"
                  className="bg-amber-500 text-obsidian hover:bg-amber-400 text-xs"
                  data-testid="regenerate-voice-button"
                >
                  <Sparkles className="w-3 h-3 mr-1" /> Regenerate
                </Button>
              </div>
            )}

            {/* Dialogue Blocks */}
            <div className="flex-1 p-6 bg-obsidian overflow-y-auto">
              <div className="max-w-3xl mx-auto space-y-4">
                {dialogues.map((d, idx) => {
                  const char = characters.find(c => c.character_id === d.character_id);
                  const currentVoice = char ? (char.voice_id || '') : '';
                  const needsRegeneration = d.generated_voice_id && currentVoice && d.generated_voice_id !== currentVoice;
                  return (
                    <DialogueBlock
                      key={`${idx}-${d.character_id}`}
                      dialogue={d}
                      index={idx}
                      characters={characters}
                      voices={voices}
                      onUpdate={updateDialogue}
                      onRemove={removeDialogue}
                      onAdd={addDialogue}
                      onMove={moveDialogue}
                      onRegenerate={handleRegenerateDialogue}
                      totalCount={dialogues.length}
                      isGenerating={generating}
                      regenLoading={regenLoading.has(idx)}
                      needsRegeneration={needsRegeneration}
                    />
                  );
                })}

                {/* Add Dialogue at Bottom */}
                <button
                  onClick={() => addDialogue(dialogues.length - 1)}
                  className="w-full py-3 border-2 border-dashed border-white/10 rounded-lg text-text-secondary hover:text-white hover:border-white/30 transition-all flex items-center justify-center gap-2"
                  data-testid="add-dialogue-bottom"
                >
                  <Plus className="w-4 h-4" /> Add Dialogue
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <FileText className="w-16 h-16 text-neon-cyan/50 mx-auto mb-4" />
              <p className="text-text-secondary">Select or create an episode to start writing</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ========== DIALOGUE BLOCK COMPONENT ==========

function DialogueBlock({ dialogue, index, characters, voices, onUpdate, onRemove, onAdd, onMove, onRegenerate, totalCount, isGenerating, regenLoading, needsRegeneration }) {
  const [expanded, setExpanded] = useState(true);
  const selectedChar = characters.find(c => c.character_id === dialogue.character_id);

  const getVoiceName = (voiceId) => {
    if (!voiceId) return '';
    const v = (voices || []).find(x => x.voice_id === voiceId);
    return v ? v.name : voiceId;
  };

  return (
    <div
      className={`bg-charcoal rounded-lg border transition-all ${
        needsRegeneration
          ? 'border-amber-500/50'
          : dialogue.character_id && dialogue.text.trim()
            ? 'border-white/10'
            : 'border-amber-500/20'
      }`}
      data-testid={`dialogue-block-${index}`}
    >
      {/* Voice Changed Banner */}
      {needsRegeneration && (
        <div className="px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2" data-testid={`voice-changed-${index}`}>
          <AlertCircle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
          <span className="text-xs text-amber-300">Voice changed. Regenerate audio to apply the new voice.</span>
        </div>
      )}
      {/* Block Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
        <GripVertical className="w-4 h-4 text-text-secondary/50 cursor-grab" />
        <span className="text-xs font-mono text-text-secondary w-6">{String(index + 1).padStart(2, '0')}</span>

        {/* Character Selector */}
        <Select
          value={dialogue.character_id || 'none'}
          onValueChange={(val) => onUpdate(index, 'character_id', val === 'none' ? '' : val)}
        >
          <SelectTrigger className="w-48 h-8 bg-slate border-white/10 text-white text-sm" data-testid={`dialogue-character-select-${index}`}>
            <SelectValue placeholder="Select character">
              {selectedChar ? (
                <span className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-neon-cyan" />
                  {selectedChar.name}
                </span>
              ) : 'Select character'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent className="bg-charcoal border-white/10">
            {characters.length === 0 ? (
              <div className="px-3 py-2 text-text-secondary text-xs">No characters yet</div>
            ) : (
              characters.map(c => (
                <SelectItem key={c.character_id} value={c.character_id} className="text-white">
                  <span className="flex items-center gap-2">
                    {c.name}
                    {c.voice_id && <span className="text-xs text-text-secondary">({getVoiceName(c.voice_id)})</span>}
                  </span>
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>

        {selectedChar?.voice_id && (
          <span className="text-xs px-2 py-0.5 bg-neon-purple/20 text-neon-purple rounded">
            {getVoiceName(selectedChar.voice_id)}
          </span>
        )}

        <div className="flex-1" />

        {/* Action Buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => onMove(index, -1)}
            disabled={index === 0}
            className="p-1 text-text-secondary hover:text-white disabled:opacity-30 transition-colors"
            title="Move up"
          >
            <ChevronUp className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onMove(index, 1)}
            disabled={index === totalCount - 1}
            className="p-1 text-text-secondary hover:text-white disabled:opacity-30 transition-colors"
            title="Move down"
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => onAdd(index)}
            className="p-1 text-text-secondary hover:text-neon-cyan transition-colors"
            title="Add dialogue below"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>

          {/* Three-dot context menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                className="p-1 text-text-secondary hover:text-white transition-colors"
                title="More options"
                data-testid={`dialogue-menu-${index}`}
              >
                {regenLoading
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin text-neon-cyan" />
                  : <MoreHorizontal className="w-3.5 h-3.5" />
                }
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="bg-charcoal border-white/10 text-white text-sm min-w-[160px]">
              <DropdownMenuItem
                className="flex items-center gap-2 cursor-pointer hover:bg-white/5 focus:bg-white/5 text-white"
                disabled={isGenerating || regenLoading || !dialogue.character_id || !dialogue.text?.trim()}
                onSelect={() => onRegenerate(index)}
                data-testid={`regenerate-dialogue-${index}`}
              >
                <RefreshCw className="w-3.5 h-3.5 text-neon-cyan" />
                Regenerate Audio
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-white/10" />
              <DropdownMenuItem
                className="flex items-center gap-2 cursor-pointer hover:bg-red-500/10 focus:bg-red-500/10 text-red-400"
                onSelect={() => onRemove(index)}
                data-testid={`remove-dialogue-${index}`}
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete Dialogue
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Block Body */}
      <div className="px-4 py-3 space-y-3">
        {/* Dialogue Text */}
        <Textarea
          value={dialogue.text}
          onChange={(e) => onUpdate(index, 'text', e.target.value)}
          className="bg-slate/50 border-white/5 text-white text-sm min-h-[60px] resize-none focus:border-neon-cyan/30"
          placeholder="Enter dialogue text..."
          disabled={isGenerating}
          data-testid={`dialogue-text-${index}`}
        />

        {/* Director Notes (optional, collapsible) */}
        <div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-text-secondary hover:text-white transition-colors flex items-center gap-1"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            Director Notes
          </button>
          {expanded && (
            <Input
              value={dialogue.director_notes || ''}
              onChange={(e) => onUpdate(index, 'director_notes', e.target.value)}
              className="mt-2 bg-slate/30 border-white/5 text-white text-xs h-8"
              placeholder="e.g., whisper, angry, excited..."
              disabled={isGenerating}
              data-testid={`dialogue-notes-${index}`}
            />
          )}
        </div>
      </div>
    </div>
  );
}

export default ScriptEditor;
