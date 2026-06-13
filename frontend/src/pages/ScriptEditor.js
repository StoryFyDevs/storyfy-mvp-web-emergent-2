import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { useStudio } from '../contexts/StudioContext';
import { useGenerationStatus } from '../contexts/GenerationStatusContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Label } from '../components/ui/label';
import {
  Plus, Save, FileText, Globe, FileEdit, Trash2, GripVertical,
  Loader2, AlertCircle, ChevronDown, ChevronUp, Sparkles,
  MoreHorizontal, RefreshCw, BookOpen, MessageSquare, Lock, Info
} from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '../components/ui/dropdown-menu';
import { toast } from 'sonner';

const base = process.env.REACT_APP_BACKEND_URL;
const NARRATION_CHAR_LIMIT = 15000;

const ERROR_MESSAGES = {
  audio_access_disabled: 'Audio generation access is currently disabled. Please wait for approval or contact support.',
  insufficient_generation_credits: 'You have no generation credits remaining.',
  insufficient_audition_credits: 'You have no audition credits remaining.',
  content_too_long: 'This section is too long to generate audio. Please break it into smaller parts or reduce your text.',
};
const friendlyError = (detail) => ERROR_MESSAGES[detail] || detail;

function ScriptEditor() {
  const { storyId } = useParams();
  const { story } = useOutletContext();
  const {
    episodes, refreshEpisodes,
    characters, voices,
    selectedEpisode, setSelectedEpisode,
    requestEpisodeSwitch,
    setIsProjectDirty,
    registerSaveCallback,
  } = useStudio();
  const { trackNewJob } = useGenerationStatus();

  // ===== MODE STATE =====
  const [mode, setMode] = useState('narration');
  const [dialogueModeEnabled, setDialogueModeEnabled] = useState(false);
  const [showComingSoon, setShowComingSoon] = useState(false);

  // ===== NARRATION STATE =====
  const [narrationParts, setNarrationParts] = useState([{ part_number: 1, text: '', director_notes: '' }]);
  const [narrationVoiceId, setNarrationVoiceId] = useState('');

  // ===== DIALOGUE STATE (existing) =====
  const [dialogues, setDialogues] = useState([]);

  // ===== COMMON STATE =====
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newEpisode, setNewEpisode] = useState({ title: '', order: 1 });
  const [publishingEp, setPublishingEp] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  // Generation state
  const [generating, setGenerating] = useState(false);
  const [genProgress, setGenProgress] = useState({ completed: 0, total: 0, status: '' });
  const pollRef = useRef(null);

  // Version review state
  const [partVersions, setPartVersions] = useState({});

  // Per-dialogue regeneration
  const [regenLoading, setRegenLoading] = useState(new Set());

  // Audio access
  const [audioAccess, setAudioAccess] = useState({ status: 'loading', generation_status: 'inactive' });

  const authHeaders = { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` };
  const audioDisabled = audioAccess.generation_status !== 'active';

  // ===== FETCH SETTINGS ON MOUNT =====
  useEffect(() => {
    fetch(`${base}/api/generation/status`, { headers: authHeaders })
      .then(r => r.json())
      .then(data => setAudioAccess({
        status: data.status || 'inactive',
        generation_credits: data.generation_credits || 0,
        audition_credits: data.audition_credits || 0,
        generation_status: data.generation_status || data.status || 'inactive',
      }))
      .catch(() => setAudioAccess(prev => ({ ...prev, status: 'error' })));

    fetch(`${base}/api/settings/dialogue-mode`, { headers: authHeaders })
      .then(r => r.json())
      .then(data => setDialogueModeEnabled(data.enabled === true))
      .catch(() => setDialogueModeEnabled(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ===== LOAD SCRIPT DATA WHEN EPISODE CHANGES =====
  useEffect(() => {
    if (selectedEpisode) {
      loadScriptData(selectedEpisode.episode_id);
      fetchVersions(selectedEpisode.episode_id);
    }
  }, [selectedEpisode?.episode_id, characters.length]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const loadScriptData = async (episodeId) => {
    try {
      const res = await fetch(`${base}/api/script/${episodeId}/script-data`, { headers: authHeaders });
      if (!res.ok) throw new Error('Failed to load script');
      const data = await res.json();

      if (data.mode === 'narration') {
        setMode('narration');
        const parts = data.parts && data.parts.length > 0
          ? data.parts
          : [{ part_number: 1, text: '', director_notes: '' }];
        setNarrationParts(parts);
        setNarrationVoiceId(data.voice_id || '');
        // Also load any preserved dialogue data
        if (data.dialogues && data.dialogues.length > 0) {
          const resolved = resolveDialogueVoices(data.dialogues);
          setDialogues(resolved);
        } else {
          setDialogues([createEmptyDialogue(0)]);
        }
      } else if (data.mode === 'dialogue') {
        setMode('dialogue');
        if (data.dialogues && data.dialogues.length > 0) {
          const resolved = resolveDialogueVoices(data.dialogues);
          setDialogues(resolved);
        } else {
          setDialogues([createEmptyDialogue(0)]);
        }
        // Load preserved narration data
        if (data.parts && data.parts.length > 0) {
          setNarrationParts(data.parts);
        }
        if (data.voice_id) setNarrationVoiceId(data.voice_id);
      } else {
        // Default to narration for fresh episodes
        setMode('narration');
        setNarrationParts([{ part_number: 1, text: '', director_notes: '' }]);
        setDialogues([createEmptyDialogue(0)]);
      }
      setDirty(false);
    } catch {
      setMode('narration');
      setNarrationParts([{ part_number: 1, text: '', director_notes: '' }]);
      setDialogues([createEmptyDialogue(0)]);
      setDirty(false);
    }
  };

  const resolveDialogueVoices = (dlgs) => {
    return dlgs.map(d => {
      const char = characters.find(c => c.character_id === d.character_id);
      return {
        ...d,
        voice_id: char ? (char.voice_id || '') : (d.voice_id || ''),
        generated_voice_id: d.generated_voice_id || '',
      };
    });
  };

  const createEmptyDialogue = (index) => ({
    index, character_id: '', character_name: '', voice_id: '',
    text: '', director_notes: '', generated_voice_id: '',
  });

  // ===== SAVE (MODE-AWARE) =====
  const handleSave = useCallback(async () => {
    if (!selectedEpisode) return;
    setSaving(true);
    try {
      const payload = {
        mode,
        voice_id: narrationVoiceId,
        parts: narrationParts,
        dialogues: dialogues.map((d, i) => ({ ...d, index: i })),
      };
      const res = await fetch(`${base}/api/script/${selectedEpisode.episode_id}/script-data`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to save');
      setDirty(false);
      toast.success('Script saved!');
    } catch {
      toast.error('Failed to save script');
    } finally {
      setSaving(false);
    }
  }, [selectedEpisode, mode, narrationParts, narrationVoiceId, dialogues]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setIsProjectDirty(dirty); }, [dirty, setIsProjectDirty]);
  useEffect(() => {
    registerSaveCallback(handleSave);
    return () => registerSaveCallback(null);
  }, [registerSaveCallback, handleSave]);

  useEffect(() => {
    const handler = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  // ===== NARRATION PART MANAGEMENT =====
  const updateNarrationPart = (index, field, value) => {
    setNarrationParts(prev => prev.map((p, i) => i === index ? { ...p, [field]: value } : p));
    setDirty(true);
  };

  const addNarrationPart = () => {
    setNarrationParts(prev => [...prev, { part_number: prev.length + 1, text: '', director_notes: '' }]);
    setDirty(true);
  };

  const removeNarrationPart = (index) => {
    if (narrationParts.length <= 1) { toast.error('Cannot remove the only part'); return; }
    setNarrationParts(prev => prev.filter((_, i) => i !== index).map((p, i) => ({ ...p, part_number: i + 1 })));
    setDirty(true);
  };

  const getPartCharCount = (part) => (part.text?.length || 0) + (part.director_notes?.length || 0);

  // ===== VERSION MANAGEMENT =====
  const fetchVersions = async (episodeId) => {
    try {
      const res = await fetch(`${base}/api/episodes/${episodeId}/versions`, { headers: authHeaders });
      if (!res.ok) return;
      const data = await res.json();
      setPartVersions(data.versions || {});
    } catch { /* silent */ }
  };

  const handleSelectVersion = async (clipId) => {
    if (!selectedEpisode) return;
    try {
      const res = await fetch(`${base}/api/episodes/${selectedEpisode.episode_id}/versions/${clipId}/select`, {
        method: 'POST', headers: authHeaders,
      });
      if (!res.ok) throw new Error('Failed to select version');
      toast.success('Version selected for episode');
      fetchVersions(selectedEpisode.episode_id);
    } catch (err) {
      toast.error(err.message || 'Failed to select version');
    }
  };

  // ===== NARRATION GENERATION =====
  const handleGenerateNarration = async () => {
    if (!selectedEpisode) return;
    if (!narrationVoiceId) { toast.error('Please select a narrator voice'); return; }
    const validParts = narrationParts.filter(p => p.text.trim());
    if (validParts.length === 0) { toast.error('Add some narration text before generating'); return; }
    const overLimit = validParts.find(p => getPartCharCount(p) > NARRATION_CHAR_LIMIT);
    if (overLimit) {
      toast.error(`Part ${overLimit.part_number} exceeds the ${NARRATION_CHAR_LIMIT.toLocaleString()} character limit`);
      return;
    }

    await handleSave();
    setGenerating(true);
    setGenProgress({ completed: 0, total: validParts.length, status: 'Queued...' });

    try {
      const res = await fetch(`${base}/api/script/${selectedEpisode.episode_id}/narration/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ voice_id: narrationVoiceId, parts: validParts }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(friendlyError(err.detail) || 'Generation failed');
      }
      const data = await res.json();
      trackNewJob({
        job_id: data.job_id,
        queue_id: data.queue_id,
        job_type: 'narration_batch',
        total_dialogues: data.total_dialogues || validParts.length,
        episode_id: selectedEpisode.episode_id,
      });
      setGenProgress({ completed: 0, total: data.total_dialogues || validParts.length, status: 'Queued...' });
      startPolling(data.job_id);
    } catch (error) {
      toast.error(error.message || 'Failed to start generation');
      setGenerating(false);
    }
  };

  // ===== DIALOGUE MANAGEMENT (existing) =====
  const updateDialogue = (index, field, value) => {
    setDialogues(prev => prev.map((d, i) => {
      if (i !== index) return d;
      const updated = { ...d, [field]: value };
      if (field === 'character_id') {
        const char = characters.find(c => c.character_id === value);
        if (char) { updated.character_name = char.name; updated.voice_id = char.voice_id || ''; }
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
    if (dialogues.length <= 1) { toast.error('Cannot remove the last dialogue'); return; }
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

  // ===== DIALOGUE GENERATION (existing) =====
  const handleGenerateDialogue = async () => {
    if (!selectedEpisode) return;
    const valid = dialogues.filter(d => d.character_id && d.text.trim());
    if (valid.length === 0) { toast.error('Add at least one dialogue with a character and text'); return; }
    const incomplete = dialogues.filter(d => d.text.trim() && !d.character_id);
    if (incomplete.length > 0) { toast.error('Some dialogues are missing a character assignment'); return; }

    await handleSave();
    setGenerating(true);
    setGenProgress({ completed: 0, total: valid.length, status: 'Queued...' });

    try {
      const indexed = valid.map((d, i) => {
        const char = characters.find(c => c.character_id === d.character_id);
        return { ...d, index: i, voice_id: char ? (char.voice_id || '') : (d.voice_id || '') };
      });
      const res = await fetch(`${base}/api/script/${selectedEpisode.episode_id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ dialogues: indexed }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(friendlyError(err.detail) || 'Generation failed');
      }
      const data = await res.json();
      trackNewJob({
        job_id: data.job_id,
        queue_id: data.queue_id,
        job_type: 'dialogue_batch',
        total_dialogues: data.total_dialogues,
        episode_id: selectedEpisode.episode_id,
      });
      setGenProgress({ completed: 0, total: data.total_dialogues, status: 'Queued...' });
      startPolling(data.job_id);
    } catch (error) {
      toast.error(error.message || 'Failed to start generation');
      setGenerating(false);
    }
  };

  // ===== SINGLE-DIALOGUE REGENERATION =====
  const handleRegenerateDialogue = async (index) => {
    const d = dialogues[index];
    if (!d || !d.text?.trim()) { toast.error('Dialogue has no text to regenerate'); return; }
    const char = characters.find(c => c.character_id === d.character_id);
    if (!char?.voice_id) { toast.error('Assign a character with a voice before regenerating'); return; }

    setRegenLoading(prev => new Set([...prev, index]));
    try {
      const res = await fetch(`${base}/api/script/${selectedEpisode.episode_id}/dialogue/${index}/regenerate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({
          dialogue_index: index, character_id: d.character_id,
          character_name: char.name || d.character_name || 'Unknown',
          voice_id: char.voice_id, text: d.text, director_notes: d.director_notes || '',
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = err.detail;
        const errorMsg = typeof detail === 'object' ? (detail.error || JSON.stringify(detail)) : (friendlyError(detail) || `Server error ${res.status}`);
        throw new Error(errorMsg);
      }
      const data = await res.json();
      if (data.status === 'queued' && data.job_id) {
        toast.loading(`Dialogue ${index + 1} queued for regeneration...`, { id: `regen-${index}` });
        pollRegenJob(data.job_id, index, d, char);
      } else if (data.success) {
        toast.success(`Dialogue ${index + 1} regenerated`);
        if (data.generated_voice_id) {
          setDialogues(prev => prev.map((item, i) => i === index ? { ...item, generated_voice_id: data.generated_voice_id } : item));
        }
        setRegenLoading(prev => { const next = new Set(prev); next.delete(index); return next; });
      }
    } catch (err) {
      toast.dismiss(`regen-${index}`);
      toast.error(`Regeneration failed: ${err.message}`);
      setRegenLoading(prev => { const next = new Set(prev); next.delete(index); return next; });
    }
  };

  const pollRegenJob = (jobId, index) => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetch(`${base}/api/jobs/${jobId}`, { headers: authHeaders });
        if (!res.ok) return;
        const data = await res.json();
        if (data.status === 'queued') {
          const pos = data.position_in_queue || 0;
          toast.loading(pos > 0 ? `${pos} job${pos > 1 ? 's' : ''} ahead...` : 'In queue...', { id: `regen-${index}` });
        } else if (data.status === 'processing') {
          toast.loading('Processing...', { id: `regen-${index}` });
        } else if (data.status === 'completed' && data.result) {
          clearInterval(interval);
          toast.dismiss(`regen-${index}`);
          toast.success(`Dialogue ${index + 1} regenerated`);
          if (data.result.generated_voice_id) {
            setDialogues(prev => prev.map((item, i) => i === index ? { ...item, generated_voice_id: data.result.generated_voice_id } : item));
          }
          setRegenLoading(prev => { const next = new Set(prev); next.delete(index); return next; });
        } else if (data.status === 'failed') {
          clearInterval(interval);
          toast.dismiss(`regen-${index}`);
          toast.error(`Regeneration failed: ${data.error || 'Unknown error'}`);
          setRegenLoading(prev => { const next = new Set(prev); next.delete(index); return next; });
        }
        if (attempts >= 90) {
          clearInterval(interval);
          toast.dismiss(`regen-${index}`);
          toast.error('Regeneration timed out.');
          setRegenLoading(prev => { const next = new Set(prev); next.delete(index); return next; });
        }
      } catch { /* ignore */ }
    }, 2000);
  };

  // ===== SHARED POLLING =====
  const startPolling = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${base}/api/script/job/${jobId}/status`, { headers: authHeaders });
        if (!res.ok) return;
        const data = await res.json();
        setGenProgress({
          completed: data.completed_dialogues, total: data.total_dialogues,
          status: data.status === 'processing' ? 'Generating audio...'
            : data.status === 'completed' ? 'Complete!'
            : data.status === 'completed_with_errors' ? 'Completed with some errors'
            : data.status === 'failed' ? 'Generation failed'
            : data.status === 'queued' ? 'In queue...'
            : 'Waiting...',
        });
        if (['completed', 'completed_with_errors', 'failed'].includes(data.status)) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setGenerating(false);
          if (data.status === 'failed') {
            toast.error(data.error_message || 'Generation failed');
          } else {
            toast.success(`Audio generated! ${data.completed_dialogues} clip${data.completed_dialogues !== 1 ? 's' : ''} ready for review.`);
          }
          // Refresh versions so the new generation appears in the review UI
          if (selectedEpisode) fetchVersions(selectedEpisode.episode_id);
        }
      } catch { /* ignore */ }
    }, 2000);
  };

  // ===== EPISODE MANAGEMENT =====
  const handleCreateEpisode = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${base}/api/episodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders },
        body: JSON.stringify({ story_id: storyId, title: newEpisode.title, order: newEpisode.order, script: '' }),
      });
      if (!response.ok) throw new Error('Failed to create episode');
      const episode = await response.json();
      await refreshEpisodes();
      setSelectedEpisode(episode);
      setNarrationParts([{ part_number: 1, text: '', director_notes: '' }]);
      setDialogues([createEmptyDialogue(0)]);
      setShowCreateDialog(false);
      setNewEpisode({ title: '', order: episodes.length + 1 });
      toast.success('Episode created!');
    } catch { toast.error('Failed to create episode'); }
  };

  const handleToggleEpisodePublish = async (e, episodeId, isPublished) => {
    e.stopPropagation();
    const ep = episodes.find(ep2 => ep2.episode_id === episodeId);
    if (!isPublished && !ep?.finalAudioUrl) {
      toast.error('Cannot publish: no rendered audio.');
      return;
    }
    const action = isPublished ? 'unpublish' : 'publish';
    setPublishingEp(episodeId);
    try {
      const res = await fetch(`${base}/api/creator/episodes/${episodeId}/${action}`, { method: 'POST', headers: authHeaders });
      if (!res.ok) throw new Error(`Failed to ${action}`);
      await refreshEpisodes();
      toast.success(action === 'publish' ? 'Episode published!' : 'Episode unpublished');
    } catch { toast.error(`Failed to ${action} episode`); }
    finally { setPublishingEp(null); }
  };

  const handleModeSwitch = (newMode) => {
    if (newMode === mode) return;
    if (newMode === 'dialogue' && !dialogueModeEnabled) {
      setShowComingSoon(true);
      return;
    }
    setMode(newMode);
    setDirty(true);
  };

  const progressPct = genProgress.total > 0 ? Math.round((genProgress.completed / genProgress.total) * 100) : 0;

  // Dialogue regen count
  const regenCount = dialogues.filter(d => {
    if (!d.generated_voice_id || !d.character_id) return false;
    const char = characters.find(c => c.character_id === d.character_id);
    return char && char.voice_id && d.generated_voice_id !== char.voice_id;
  }).length;

  // ===== RENDER =====
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
              <DialogHeader><DialogTitle className="font-space">New Episode</DialogTitle></DialogHeader>
              <form onSubmit={handleCreateEpisode} className="space-y-4">
                <div>
                  <Label>Title</Label>
                  <Input value={newEpisode.title} onChange={(e) => setNewEpisode({ ...newEpisode, title: e.target.value })} className="mt-2 bg-slate border-white/10 text-white" placeholder="Episode 1: The Beginning" required data-testid="episode-title-input" />
                </div>
                <div>
                  <Label>Order</Label>
                  <Input type="number" value={newEpisode.order} onChange={(e) => setNewEpisode({ ...newEpisode, order: parseInt(e.target.value) })} className="mt-2 bg-slate border-white/10 text-white" min="1" required data-testid="episode-order-input" />
                </div>
                <Button type="submit" className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90" data-testid="create-episode-submit">Create Episode</Button>
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
                onClick={() => requestEpisodeSwitch(episode)}
                className={`p-3 rounded-sm cursor-pointer transition-all ${selectedEpisode?.episode_id === episode.episode_id ? 'bg-slate border border-neon-cyan/50' : 'bg-slate/50 border border-transparent hover:border-white/20'}`}
                data-testid={`episode-${episode.episode_id}`}
              >
                <h3 className="text-white font-medium text-sm mb-1 truncate">{episode.title}</h3>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-text-secondary">Ep {episode.order}</span>
                  <button
                    onClick={(e) => handleToggleEpisodePublish(e, episode.episode_id, episode.isPublished)}
                    disabled={publishingEp === episode.episode_id}
                    className={`text-xs px-1.5 py-0.5 rounded-sm transition-colors ${episode.isPublished ? 'bg-signal-green/20 text-signal-green hover:bg-signal-green/30' : 'bg-white/5 text-text-secondary hover:bg-white/10 hover:text-white'}`}
                    data-testid={`ep-publish-${episode.episode_id}`}
                  >
                    {publishingEp === episode.episode_id ? '...' : episode.isPublished
                      ? <span className="flex items-center gap-0.5"><Globe className="w-3 h-3" /> Live</span>
                      : <span className="flex items-center gap-0.5"><FileEdit className="w-3 h-3" /> Draft</span>}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

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
            {/* Header with mode toggle */}
            <div className="border-b border-white/10 bg-charcoal px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div>
                  <h2 className="text-xl font-space font-bold text-white">{selectedEpisode.title}</h2>
                  <p className="text-sm text-text-secondary">
                    {mode === 'narration'
                      ? `${narrationParts.filter(p => p.text.trim()).length} part${narrationParts.filter(p => p.text.trim()).length !== 1 ? 's' : ''}`
                      : `${dialogues.filter(d => d.text.trim()).length} dialogue${dialogues.filter(d => d.text.trim()).length !== 1 ? 's' : ''}`}
                    {dirty && <span className="ml-2 text-amber-400">Unsaved</span>}
                  </p>
                </div>
              </div>

              {/* Mode Toggle */}
              <div className="flex items-center gap-3">
                <div className="flex bg-slate rounded-lg p-0.5" data-testid="mode-toggle">
                  <button
                    onClick={() => handleModeSwitch('narration')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${mode === 'narration' ? 'bg-neon-cyan text-obsidian' : 'text-text-secondary hover:text-white'}`}
                    data-testid="mode-narration-btn"
                  >
                    <BookOpen className="w-3.5 h-3.5" /> Narration
                  </button>
                  <button
                    onClick={() => handleModeSwitch('dialogue')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${mode === 'dialogue' ? 'bg-neon-cyan text-obsidian' : 'text-text-secondary hover:text-white'}`}
                    data-testid="mode-dialogue-btn"
                  >
                    <MessageSquare className="w-3.5 h-3.5" />
                    {dialogueModeEnabled ? 'Dialogue' : <><Lock className="w-3 h-3 mr-0.5" />Dialogue</>}
                  </button>
                </div>

                <Button onClick={handleSave} disabled={saving || !dirty} variant="outline" className="border-white/20 text-white hover:bg-white/5" data-testid="save-script-button">
                  {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />} Save
                </Button>

                {mode === 'narration' ? (
                  <Button
                    onClick={handleGenerateNarration}
                    disabled={audioDisabled || generating || !narrationVoiceId || narrationParts.filter(p => p.text.trim()).length === 0}
                    className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 disabled:opacity-40"
                    data-testid="generate-narration-button"
                  >
                    {generating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
                    {generating ? 'Generating...' : 'Generate Audio'}
                  </Button>
                ) : (
                  <Button
                    onClick={handleGenerateDialogue}
                    disabled={audioDisabled || generating || dialogues.filter(d => d.character_id && d.text.trim()).length === 0}
                    className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 disabled:opacity-40"
                    data-testid="generate-audio-button"
                  >
                    {generating ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
                    {generating ? 'Generating...' : 'Generate Audio'}
                  </Button>
                )}
              </div>
            </div>

            {/* Audio Access Disabled Warning */}
            {audioDisabled && (
              <div className="bg-red-500/10 border-b border-red-500/30 px-6 py-3 flex items-center gap-2" data-testid="audio-disabled-banner">
                <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
                <span className="text-red-300 text-sm">Audio generation access is currently disabled. Please wait for approval or contact support.</span>
              </div>
            )}

            {/* Generation Progress */}
            {generating && (
              <div className="bg-charcoal border-b border-neon-cyan/30 px-6 py-3" data-testid="generation-progress">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-4 h-4 text-neon-cyan animate-spin" />
                  <span className="text-neon-cyan text-sm font-medium">{genProgress.status}</span>
                  <span className="text-text-secondary text-xs">{genProgress.completed}/{genProgress.total} clips</span>
                  <div className="flex-1 h-2 bg-slate rounded-full overflow-hidden">
                    <div className="h-full bg-neon-cyan rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }} />
                  </div>
                  <span className="text-neon-cyan text-sm font-mono">{progressPct}%</span>
                </div>
              </div>
            )}

            {/* NARRATION MODE */}
            {mode === 'narration' && (
              <div className="flex-1 p-6 bg-obsidian overflow-y-auto">
                <div className="max-w-3xl mx-auto space-y-6">
                  {/* Narrator Voice Selector */}
                  <div className="bg-charcoal rounded-lg border border-white/10 p-4" data-testid="narrator-voice-selector">
                    <Label className="text-white text-sm font-medium mb-2 block">Narrator Voice</Label>
                    <Select value={narrationVoiceId || 'none'} onValueChange={(val) => { setNarrationVoiceId(val === 'none' ? '' : val); setDirty(true); }}>
                      <SelectTrigger className="bg-slate border-white/10 text-white" data-testid="narrator-voice-select">
                        <SelectValue placeholder="Select a narrator voice" />
                      </SelectTrigger>
                      <SelectContent className="bg-charcoal border-white/10 max-h-60">
                        {voices.map(v => (
                          <SelectItem key={v.voice_id} value={v.voice_id} className="text-white">
                            <span className="flex items-center gap-2">
                              {v.name} <span className="text-xs text-text-secondary">({v.tone})</span>
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {!narrationVoiceId && (
                      <p className="text-amber-400 text-xs mt-2">Select a voice to enable audio generation</p>
                    )}
                  </div>

                  {/* Narration Parts */}
                  {narrationParts.map((part, idx) => (
                    <NarrationPartBlock
                      key={idx}
                      part={part}
                      index={idx}
                      totalParts={narrationParts.length}
                      onUpdate={updateNarrationPart}
                      onRemove={removeNarrationPart}
                      charCount={getPartCharCount(part)}
                      charLimit={NARRATION_CHAR_LIMIT}
                      isGenerating={generating}
                      versions={partVersions[idx] || []}
                      onSelectVersion={handleSelectVersion}
                      base={base}
                      authHeaders={authHeaders}
                    />
                  ))}

                  {/* Add Next Part */}
                  <button
                    onClick={addNarrationPart}
                    className="w-full py-4 border-2 border-dashed border-neon-cyan/30 rounded-lg text-neon-cyan hover:text-white hover:border-neon-cyan/60 hover:bg-neon-cyan/5 transition-all flex items-center justify-center gap-2 font-medium"
                    data-testid="add-next-part-btn"
                  >
                    <Plus className="w-5 h-5" /> Add Next Part
                  </button>
                </div>
              </div>
            )}

            {/* DIALOGUE MODE */}
            {mode === 'dialogue' && (
              <>
                {/* Credit warning */}
                <div className="bg-amber-500/5 border-b border-amber-500/20 px-6 py-2.5 flex items-center gap-2" data-testid="dialogue-credit-warning">
                  <Info className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  <span className="text-amber-300 text-xs">Advanced Mode (Multiple Characters) — This mode uses more credits. Use Narration Mode for faster generation.</span>
                </div>

                {/* Voice Change Regeneration Banner */}
                {!generating && regenCount > 0 && (
                  <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-3 flex items-center justify-between" data-testid="voice-change-banner">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-amber-400" />
                      <span className="text-amber-300 text-sm">{regenCount} dialogue{regenCount !== 1 ? 's' : ''} need{regenCount === 1 ? 's' : ''} regeneration.</span>
                    </div>
                    <Button onClick={handleGenerateDialogue} size="sm" disabled={audioDisabled} className="bg-amber-500 text-obsidian hover:bg-amber-400 text-xs" data-testid="regenerate-voice-button">
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
                          dialogue={d} index={idx} characters={characters} voices={voices}
                          onUpdate={updateDialogue} onRemove={removeDialogue} onAdd={addDialogue}
                          onMove={moveDialogue} onRegenerate={handleRegenerateDialogue}
                          totalCount={dialogues.length} isGenerating={generating}
                          regenLoading={regenLoading.has(idx)} needsRegeneration={needsRegeneration}
                          audioDisabled={audioDisabled}
                        />
                      );
                    })}
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
            )}
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

      {/* Coming Soon Dialog */}
      <Dialog open={showComingSoon} onOpenChange={setShowComingSoon}>
        <DialogContent className="bg-charcoal border-white/10 text-white max-w-md" data-testid="coming-soon-dialog">
          <DialogHeader>
            <DialogTitle className="text-xl font-space flex items-center gap-2">
              <MessageSquare className="w-5 h-5 text-neon-cyan" /> Dialogue Mode
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-text-secondary text-sm leading-relaxed">
              This feature is coming soon! We'll enable advanced multi-character storytelling shortly.
            </p>
            <p className="text-text-secondary text-xs">
              In the meantime, use Narration Mode for fast, credit-efficient audio generation.
            </p>
            <Button onClick={() => setShowComingSoon(false)} className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90">
              Got it
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ===== NARRATION PART BLOCK =====

function NarrationPartBlock({ part, index, totalParts, onUpdate, onRemove, charCount, charLimit, isGenerating, versions, onSelectVersion, base, authHeaders }) {
  const pct = charLimit > 0 ? (charCount / charLimit) * 100 : 0;
  const isNearLimit = pct > 80;
  const isOverLimit = charCount > charLimit;
  const [expandVersions, setExpandVersions] = React.useState(false);

  return (
    <div className={`bg-charcoal rounded-lg border transition-all ${isOverLimit ? 'border-red-500/50' : isNearLimit ? 'border-amber-500/40' : 'border-white/10'}`} data-testid={`narration-part-${index}`}>
      {/* Part Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="text-neon-cyan font-mono text-xs font-bold bg-neon-cyan/10 px-2 py-0.5 rounded">Part {part.part_number}</span>
          {versions.length > 0 && (
            <span className="text-xs text-text-secondary">
              {versions.filter(v => v.is_selected).length > 0 ? (
                <span className="text-signal-green">Audio selected</span>
              ) : (
                <span className="text-warm-gold">{versions.length} version{versions.length !== 1 ? 's' : ''} — none selected</span>
              )}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-mono ${isOverLimit ? 'text-red-400' : isNearLimit ? 'text-amber-400' : 'text-text-secondary'}`} data-testid={`char-counter-${index}`}>
            {charCount.toLocaleString()} / {charLimit.toLocaleString()}
          </span>
          {totalParts > 1 && (
            <button onClick={() => onRemove(index)} className="p-1 text-text-secondary hover:text-red-400 transition-colors" title="Remove part" data-testid={`remove-part-${index}`}>
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Part Body */}
      <div className="px-4 py-4 space-y-4">
        {/* Narration Text */}
        <div>
          <Label className="text-white text-sm mb-2 block">Narration Text</Label>
          <Textarea
            value={part.text}
            onChange={(e) => onUpdate(index, 'text', e.target.value)}
            className="bg-slate/50 border-white/5 text-white text-sm min-h-[160px] resize-y focus:border-neon-cyan/30"
            placeholder="Write your narration here..."
            disabled={isGenerating}
            data-testid={`narration-text-${index}`}
          />
        </div>

        {/* Director's Notes */}
        <div>
          <Label className="text-text-secondary text-xs mb-1.5 block">Director's Notes (optional)</Label>
          <Input
            value={part.director_notes || ''}
            onChange={(e) => onUpdate(index, 'director_notes', e.target.value)}
            className="bg-slate/30 border-white/5 text-white text-sm h-9"
            placeholder="e.g., read slowly and softly, pause after first paragraph..."
            disabled={isGenerating}
            data-testid={`narration-notes-${index}`}
          />
        </div>

        {/* Character limit progress bar */}
        <div className="h-1 bg-slate rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${isOverLimit ? 'bg-red-500' : isNearLimit ? 'bg-amber-500' : 'bg-neon-cyan/40'}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>

        {/* Warning messages */}
        {isNearLimit && !isOverLimit && (
          <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3" data-testid={`near-limit-warning-${index}`}>
            <p className="text-amber-300 text-xs leading-relaxed">
              Looks like your story is getting long. To keep audio smooth, try breaking it into smaller parts.
            </p>
            <p className="text-amber-300/70 text-xs mt-2 leading-relaxed">
              You can: Split into multiple parts &bull; Reduce some text &bull; Shorten Director's Notes
            </p>
            <p className="text-amber-300/50 text-xs mt-1">Tip: Smaller parts = faster and better audio</p>
          </div>
        )}

        {isOverLimit && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3" data-testid={`over-limit-error-${index}`}>
            <p className="text-red-300 text-xs leading-relaxed font-medium">
              This section is too long to generate audio right now.
            </p>
            <p className="text-red-300/70 text-xs mt-2 leading-relaxed">
              Please break it into smaller parts or reduce your text / Director's Notes. Each section supports up to {charLimit.toLocaleString()} characters (including notes).
            </p>
          </div>
        )}

        {/* ===== GENERATED VERSIONS ===== */}
        {versions.length > 0 && (
          <div className="border-t border-white/5 pt-4 mt-2">
            <button
              onClick={() => setExpandVersions(!expandVersions)}
              className="flex items-center gap-2 text-sm text-text-secondary hover:text-white transition-colors w-full"
              data-testid={`toggle-versions-${index}`}
            >
              <Sparkles className="w-3.5 h-3.5 text-neon-cyan" />
              <span className="font-medium">Generated Versions</span>
              <span className="text-xs bg-slate px-1.5 py-0.5 rounded font-mono">{versions.length}</span>
              {expandVersions ? <ChevronUp className="w-3.5 h-3.5 ml-auto" /> : <ChevronDown className="w-3.5 h-3.5 ml-auto" />}
            </button>

            {expandVersions && (
              <div className="mt-3 space-y-2" data-testid={`versions-list-${index}`}>
                {versions.map((v) => (
                  <VersionRow
                    key={v.clip_id}
                    version={v}
                    onSelect={() => onSelectVersion(v.clip_id)}
                    base={base}
                    authHeaders={authHeaders}
                  />
                ))}
                <p className="text-xs text-text-secondary/60 mt-2 italic">
                  Only your latest versions are kept. Older unused versions may be removed automatically.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}


// ===== DIALOGUE BLOCK COMPONENT (existing) =====

function DialogueBlock({ dialogue, index, characters, voices, onUpdate, onRemove, onAdd, onMove, onRegenerate, totalCount, isGenerating, regenLoading, needsRegeneration, audioDisabled }) {
  const [expanded, setExpanded] = useState(true);
  const selectedChar = characters.find(c => c.character_id === dialogue.character_id);

  const getVoiceName = (voiceId) => {
    if (!voiceId) return '';
    const v = (voices || []).find(x => x.voice_id === voiceId);
    return v ? v.name : voiceId;
  };

  return (
    <div
      className={`bg-charcoal rounded-lg border transition-all ${needsRegeneration ? 'border-amber-500/50' : dialogue.character_id && dialogue.text.trim() ? 'border-white/10' : 'border-amber-500/20'}`}
      data-testid={`dialogue-block-${index}`}
    >
      {needsRegeneration && (
        <div className="px-4 py-2 bg-amber-500/10 border-b border-amber-500/20 flex items-center gap-2" data-testid={`voice-changed-${index}`}>
          <AlertCircle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
          <span className="text-xs text-amber-300">Voice changed. Regenerate audio to apply the new voice.</span>
        </div>
      )}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
        <GripVertical className="w-4 h-4 text-text-secondary/50 cursor-grab" />
        <span className="text-xs font-mono text-text-secondary w-6">{String(index + 1).padStart(2, '0')}</span>
        <Select value={dialogue.character_id || 'none'} onValueChange={(val) => onUpdate(index, 'character_id', val === 'none' ? '' : val)}>
          <SelectTrigger className="w-48 h-8 bg-slate border-white/10 text-white text-sm" data-testid={`dialogue-character-select-${index}`}>
            <SelectValue placeholder="Select character">
              {selectedChar ? <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-neon-cyan" />{selectedChar.name}</span> : 'Select character'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent className="bg-charcoal border-white/10">
            {characters.length === 0 ? (
              <div className="px-3 py-2 text-text-secondary text-xs">No characters yet</div>
            ) : (
              characters.map(c => (
                <SelectItem key={c.character_id} value={c.character_id} className="text-white">
                  <span className="flex items-center gap-2">{c.name}{c.voice_id && <span className="text-xs text-text-secondary">({getVoiceName(c.voice_id)})</span>}</span>
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
        {selectedChar?.voice_id && <span className="text-xs px-2 py-0.5 bg-neon-purple/20 text-neon-purple rounded">{getVoiceName(selectedChar.voice_id)}</span>}
        <div className="flex-1" />
        <div className="flex items-center gap-1">
          <button onClick={() => onMove(index, -1)} disabled={index === 0} className="p-1 text-text-secondary hover:text-white disabled:opacity-30 transition-colors"><ChevronUp className="w-3.5 h-3.5" /></button>
          <button onClick={() => onMove(index, 1)} disabled={index === totalCount - 1} className="p-1 text-text-secondary hover:text-white disabled:opacity-30 transition-colors"><ChevronDown className="w-3.5 h-3.5" /></button>
          <button onClick={() => onAdd(index)} className="p-1 text-text-secondary hover:text-neon-cyan transition-colors"><Plus className="w-3.5 h-3.5" /></button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="p-1 text-text-secondary hover:text-white transition-colors" data-testid={`dialogue-menu-${index}`}>
                {regenLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin text-neon-cyan" /> : <MoreHorizontal className="w-3.5 h-3.5" />}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="bg-charcoal border-white/10 text-white text-sm min-w-[160px]">
              <DropdownMenuItem
                className="flex items-center gap-2 cursor-pointer hover:bg-white/5 focus:bg-white/5 text-white"
                disabled={audioDisabled || isGenerating || regenLoading || !dialogue.character_id || !dialogue.text?.trim()}
                onSelect={() => onRegenerate(index)}
                data-testid={`regenerate-dialogue-${index}`}
              >
                <RefreshCw className="w-3.5 h-3.5 text-neon-cyan" /> Regenerate Audio
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-white/10" />
              <DropdownMenuItem
                className="flex items-center gap-2 cursor-pointer hover:bg-red-500/10 focus:bg-red-500/10 text-red-400"
                onSelect={() => onRemove(index)}
                data-testid={`remove-dialogue-${index}`}
              >
                <Trash2 className="w-3.5 h-3.5" /> Delete Dialogue
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <div className="px-4 py-3 space-y-3">
        <Textarea
          value={dialogue.text}
          onChange={(e) => onUpdate(index, 'text', e.target.value)}
          className="bg-slate/50 border-white/5 text-white text-sm min-h-[60px] resize-none focus:border-neon-cyan/30"
          placeholder="Enter dialogue text..."
          disabled={isGenerating}
          data-testid={`dialogue-text-${index}`}
        />
        <div>
          <button onClick={() => setExpanded(!expanded)} className="text-xs text-text-secondary hover:text-white transition-colors flex items-center gap-1">
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />} Director Notes
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


// ===== VERSION ROW COMPONENT =====

function VersionRow({ version, onSelect, base, authHeaders }) {
  const [playing, setPlaying] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const audioRef = React.useRef(null);

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diff = now - d;
      if (diff < 60000) return 'Just now';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      if (diff < 604800000) return `${Math.floor(diff / 86400000)}d ago`;
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };

  const formatDuration = (s) => {
    if (!s) return '--:--';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const togglePlay = async () => {
    if (playing) {
      audioRef.current?.pause();
      setPlaying(false);
      return;
    }

    if (!audioRef.current) {
      setLoading(true);
      const audio = new Audio(`${base}/api/audio/stream-file/${version.audio_url}?t=${Date.now()}`);
      audio.onended = () => setPlaying(false);
      audio.onerror = () => { setPlaying(false); setLoading(false); };
      audio.oncanplay = () => setLoading(false);
      audioRef.current = audio;
    }

    try {
      await audioRef.current.play();
      setPlaying(true);
    } catch {
      setPlaying(false);
    }
  };

  // Clean up audio on unmount
  React.useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  const isSelected = version.is_selected;
  const label = version.label;

  return (
    <div
      className={`rounded-lg p-3 flex items-center gap-3 transition-all ${
        isSelected
          ? 'bg-signal-green/8 border border-signal-green/25'
          : 'bg-slate/40 border border-white/5 hover:border-white/15'
      }`}
      data-testid={`version-row-${version.clip_id}`}
    >
      {/* Play Button */}
      <button
        onClick={togglePlay}
        className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center transition-all ${
          playing ? 'bg-neon-cyan text-obsidian' : 'bg-white/10 text-white hover:bg-white/20'
        }`}
        data-testid={`play-version-${version.clip_id}`}
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : playing ? (
          <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
        ) : (
          <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current"><polygon points="5,3 19,12 5,21" /></svg>
        )}
      </button>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          {label === 'Selected for Episode' && (
            <span className="text-xs font-medium text-signal-green flex items-center gap-1">
              <svg viewBox="0 0 16 16" className="w-3 h-3 fill-current"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"/></svg>
              Selected for Episode
            </span>
          )}
          {label === 'Latest' && (
            <span className="text-xs font-medium text-neon-cyan">Latest</span>
          )}
          {label === 'Previous Version' && (
            <span className="text-xs text-text-secondary">Previous Version</span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          <span className="text-xs font-mono text-text-secondary">{formatDuration(version.duration_seconds)}</span>
          <span className="text-xs text-text-secondary/60">{formatDate(version.created_at)}</span>
        </div>
      </div>

      {/* Select Button */}
      {!isSelected && (
        <button
          onClick={onSelect}
          className="text-xs px-3 py-1.5 rounded bg-white/8 text-white hover:bg-neon-cyan/15 hover:text-neon-cyan border border-white/10 hover:border-neon-cyan/30 transition-all flex-shrink-0"
          data-testid={`select-version-${version.clip_id}`}
        >
          Use This Version
        </button>
      )}
    </div>
  );
}


export default ScriptEditor;
