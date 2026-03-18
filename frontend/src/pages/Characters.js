import React, { useState, useEffect, useRef } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { useStudio } from '../contexts/StudioContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Plus, User, Mic, Play, Square, Trash2, Loader2, Volume2, Coins, Pencil } from 'lucide-react';
import { toast } from 'sonner';

function Characters() {
  const { storyId } = useParams();
  const { story } = useOutletContext();
  const { characters, setCharacters, voices, voiceCategories } = useStudio();

  const [credits, setCredits] = useState({ generation_credits: 0, audition_credits: 0 });
  const [sampleAvailability, setSampleAvailability] = useState({});
  const [generationStatus, setGenerationStatus] = useState({ can_generate: true, generations_remaining: 0, daily_limit: 0 });

  const [activeCategory, setActiveCategory] = useState('all');

  // Preview playback (FREE)
  const [playingVoiceId, setPlayingVoiceId] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(null);
  const previewAudioRef = useRef(null);
  const previewCacheRef = useRef({});

  // Custom audition (PAID)
  const [auditionVoice, setAuditionVoice] = useState('');
  const [auditionText, setAuditionText] = useState('');
  const [auditionLoading, setAuditionLoading] = useState(false);
  const [auditionAudio, setAuditionAudio] = useState(null);
  const [auditionPlaying, setAuditionPlaying] = useState(false);
  const auditionAudioRef = useRef(null);
  const auditionCacheRef = useRef({});

  // Character dialogs
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editingCharacter, setEditingCharacter] = useState(null);
  const [charForm, setCharForm] = useState({ name: '', voice_id: '' });

  const base = process.env.REACT_APP_BACKEND_URL;
  const token = localStorage.getItem('token') || '';
  const headers = { 'Authorization': `Bearer ${token}` };

  useEffect(() => {
    fetchCredits();
    fetchSampleStatus();
    fetchGenerationStatus();
  }, [storyId]);

  const fetchGenerationStatus = async () => {
    try {
      const res = await fetch(`${base}/api/generation/status`, { headers });
      if (res.ok) {
        const data = await res.json();
        setGenerationStatus(data);
      }
    } catch (e) {
      console.error('Failed to fetch generation status:', e);
    }
  };

  const fetchCredits = async () => {
    try {
      const res = await fetch(`${base}/api/credits`, { headers });
      if (res.ok) setCredits(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchSampleStatus = async () => {
    try {
      const res = await fetch(`${base}/api/voices/samples`, { headers });
      if (res.ok) {
        const data = await res.json();
        setSampleAvailability(data.samples || {});
      }
    } catch (e) { console.error(e); }
  };

  const getVoiceDisplay = (voiceId) => {
    const v = voices.find(x => x.voice_id === voiceId);
    return v ? `${v.name} — ${v.tone}` : voiceId;
  };

  // ===== FREE PREVIEW =====
  const handlePlayPreview = async (voiceId) => {
    if (playingVoiceId === voiceId) {
      if (previewAudioRef.current) previewAudioRef.current.pause();
      setPlayingVoiceId(null);
      return;
    }

    if (previewCacheRef.current[voiceId]) {
      playPreviewAudio(voiceId, previewCacheRef.current[voiceId]);
      return;
    }

    setLoadingPreview(voiceId);
    try {
      const res = await fetch(`${base}/api/voices/preview/${voiceId}`, { headers });
      if (!res.ok) throw new Error('Sample not available');
      const data = await res.json();
      previewCacheRef.current[voiceId] = data.audio_url;
      playPreviewAudio(voiceId, data.audio_url);
    } catch (e) {
      toast.error('Voice sample not available yet');
    } finally {
      setLoadingPreview(null);
    }
  };

  const playPreviewAudio = (voiceId, audioUrl) => {
    if (previewAudioRef.current) {
      previewAudioRef.current.src = audioUrl;
      previewAudioRef.current.onended = () => setPlayingVoiceId(null);
      previewAudioRef.current.play();
      setPlayingVoiceId(voiceId);
    }
  };

  // ===== PAID AUDITION =====
  const handleAudition = async () => {
    if (!auditionVoice) { toast.error('Select a voice'); return; }
    if (!auditionText.trim()) { toast.error('Enter dialogue text'); return; }

    const cacheKey = `${auditionVoice}:${auditionText.trim()}`;
    if (auditionCacheRef.current[cacheKey]) {
      setAuditionAudio(auditionCacheRef.current[cacheKey]);
      playAuditionAudio(auditionCacheRef.current[cacheKey]);
      return;
    }

    if (credits.audition_credits <= 0) { toast.error('You do not have enough audition credits.'); return; }
    if (!generationStatus.can_generate) { 
      toast.error(generationStatus.message || "You've reached today's generation limit. You can generate more audio tomorrow."); 
      return; 
    }

    setAuditionLoading(true);
    try {
      const res = await fetch(`${base}/api/tts/audition`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_id: auditionVoice, text: auditionText.trim() })
      });
      
      // Parse response ONCE
      const data = await res.json().catch(() => ({ detail: 'Failed to process response' }));
      
      if (!res.ok) {
        // Map technical errors to user-friendly messages
        let errorMsg = data.detail || 'Audition failed';
        if (errorMsg.toLowerCase().includes('credit')) {
          errorMsg = 'You do not have enough audition credits.';
        } else if (errorMsg.toLowerCase().includes('rate') || res.status === 429) {
          errorMsg = 'Too many requests. Please wait a moment and try again.';
        } else if (res.status >= 500) {
          errorMsg = 'Audio service is temporarily unavailable. Please try again shortly.';
        }
        throw new Error(errorMsg);
      }
      
      setAuditionAudio(data.audio_url);
      auditionCacheRef.current[cacheKey] = data.audio_url;
      playAuditionAudio(data.audio_url);
      if (!data.cached) {
        setCredits(prev => ({ ...prev, audition_credits: prev.audition_credits - 1 }));
      }
      toast.success(data.cached ? 'Playing cached sample' : 'Audition generated');
      // Refresh generation status after successful generation
      if (!data.cached) {
        fetchGenerationStatus();
      }
    } catch (e) { 
      // Show user-friendly error
      const friendlyMsg = e.message.includes('fetch') || e.message.includes('network') 
        ? 'Network issue. Please check your connection and try again.'
        : e.message;
      toast.error(friendlyMsg);
    }
    finally { setAuditionLoading(false); }
  };

  const playAuditionAudio = (url) => {
    if (auditionAudioRef.current) {
      auditionAudioRef.current.src = url;
      auditionAudioRef.current.onended = () => setAuditionPlaying(false);
      auditionAudioRef.current.play();
      setAuditionPlaying(true);
    }
  };

  // ===== CHARACTER CRUD =====
  const handleCreateCharacter = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${base}/api/characters`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ story_id: storyId, name: charForm.name, voice_id: charForm.voice_id })
      });
      if (!res.ok) throw new Error('Failed');
      const character = await res.json();
      setCharacters([...characters, character]);
      setShowCreateDialog(false);
      setCharForm({ name: '', voice_id: '' });
      toast.success('Character created!');
    } catch (e) { toast.error('Failed to create character'); }
  };

  const handleEditCharacter = async (e) => {
    e.preventDefault();
    if (!editingCharacter) return;
    try {
      const res = await fetch(`${base}/api/characters/${editingCharacter.character_id}`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ story_id: storyId, name: charForm.name, voice_id: charForm.voice_id })
      });
      if (!res.ok) throw new Error('Failed');
      const updated = await res.json();
      setCharacters(characters.map(c => c.character_id === updated.character_id ? updated : c));
      setShowEditDialog(false);
      setEditingCharacter(null);
      setCharForm({ name: '', voice_id: '' });
      toast.success('Character updated! Changes apply to future generations.');
    } catch (e) { toast.error('Failed to update character'); }
  };

  const handleDeleteCharacter = async (charId) => {
    try {
      const res = await fetch(`${base}/api/characters/${charId}`, { method: 'DELETE', headers });
      if (!res.ok) throw new Error('Failed');
      setCharacters(characters.filter(c => c.character_id !== charId));
      toast.success('Character deleted');
    } catch (e) { toast.error('Failed to delete character'); }
  };

  const openEditDialog = (char) => {
    setEditingCharacter(char);
    setCharForm({ name: char.name, voice_id: char.voice_id || '' });
    setShowEditDialog(true);
  };

  const openCreateDialog = () => {
    setCharForm({ name: '', voice_id: '' });
    setShowCreateDialog(true);
  };

  const filteredVoices = activeCategory === 'all'
    ? voices
    : voices.filter(v => v.category === activeCategory);

  const VoiceSelectDropdown = ({ value, onChange, testId }) => (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="mt-1.5 bg-slate border-white/10 text-white" data-testid={testId}>
        <SelectValue placeholder="Select a voice">
          {value ? getVoiceDisplay(value) : 'Select a voice'}
        </SelectValue>
      </SelectTrigger>
      <SelectContent className="bg-charcoal border-white/10 max-h-[280px]">
        {Object.entries(voiceCategories).map(([catKey, catLabel]) => {
          const catVoices = voices.filter(v => v.category === catKey);
          if (!catVoices.length) return null;
          return (
            <div key={catKey}>
              <div className="px-2 py-1.5 text-[10px] uppercase tracking-wider text-electric-purple/70 font-medium">{catLabel}</div>
              {catVoices.map(v => (
                <SelectItem key={v.voice_id} value={v.voice_id}>
                  <div className="flex items-center justify-between w-full gap-3">
                    <span className="text-white text-sm">{v.name}</span>
                    <span className="text-text-secondary text-xs">{v.tone}</span>
                  </div>
                </SelectItem>
              ))}
            </div>
          );
        })}
      </SelectContent>
    </Select>
  );

  return (
    <div className="p-6 max-w-7xl mx-auto" data-testid="characters-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-syne font-bold text-white mb-1">Characters & Voices</h2>
          <p className="text-text-secondary text-sm">Audition voices, then create characters for your story</p>
        </div>
        <div className="flex items-center gap-4">
          {/* Generation Status */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/10 text-xs" data-testid="generation-status-badge">
            <Mic className="w-3.5 h-3.5 text-neon-cyan" />
            <span className="text-text-secondary">Generations:</span>
            <span className="text-white font-mono">{generationStatus.generations_remaining}</span>
            <span className="text-text-secondary">/</span>
            <span className="text-text-secondary font-mono">{generationStatus.daily_limit}</span>
          </div>
          {/* Audition Credits */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/10 text-xs" data-testid="audition-credits-badge">
            <Coins className="w-3.5 h-3.5 text-electric-purple" />
            <span className="text-text-secondary">Audition:</span>
            <span className="text-white font-mono">{credits.audition_credits}</span>
          </div>
        </div>
      </div>

      {/* Generation Unavailable Warning */}
      {!generationStatus.can_generate && (
        <div className="mb-6 p-4 rounded-lg bg-amber-500/10 border border-amber-500/30">
          <p className="text-amber-400 text-sm flex items-center gap-2">
            <Volume2 className="w-4 h-4" />
            {generationStatus.message || "You've reached today's generation limit. You can generate more audio tomorrow."}
          </p>
        </div>
      )}

      {/* ========== AUDITION SECTION (TOP) ========== */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <Volume2 className="w-5 h-5 text-electric-purple" />
          <h3 className="text-lg font-syne font-bold text-white">Audition Voices</h3>
          <span className="text-text-secondary text-xs ml-2">Listen free, then create characters below</span>
        </div>

        {/* Category Filter */}
        <div className="flex gap-2 mb-4 flex-wrap">
          <Badge
            variant={activeCategory === 'all' ? 'default' : 'outline'}
            className={`cursor-pointer text-xs transition-colors ${activeCategory === 'all' ? 'bg-electric-purple text-white' : 'border-white/10 text-text-secondary hover:border-electric-purple/50'}`}
            onClick={() => setActiveCategory('all')}
            data-testid="filter-all"
          >All ({voices.length})</Badge>
          {Object.entries(voiceCategories).map(([key, label]) => {
            const count = voices.filter(v => v.category === key).length;
            return (
              <Badge
                key={key}
                variant={activeCategory === key ? 'default' : 'outline'}
                className={`cursor-pointer text-xs transition-colors ${activeCategory === key ? 'bg-electric-purple text-white' : 'border-white/10 text-text-secondary hover:border-electric-purple/50'}`}
                onClick={() => setActiveCategory(key)}
                data-testid={`filter-${key}`}
              >{label} ({count})</Badge>
            );
          })}
        </div>

        {/* Voice Grid — free previews */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3 mb-6">
          {filteredVoices.map(voice => {
            const hasSample = sampleAvailability[voice.voice_id];
            const isPlaying = playingVoiceId === voice.voice_id;
            const isLoading = loadingPreview === voice.voice_id;

            return (
              <div
                key={voice.voice_id}
                className={`p-3 rounded-sm border transition-all ${
                  isPlaying ? 'border-electric-purple bg-electric-purple/10' : 'border-white/10 bg-charcoal hover:border-white/20'
                }`}
                data-testid={`voice-card-${voice.voice_id}`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-white text-sm font-medium truncate">{voice.name}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-sm ${voice.gender === 'Female' ? 'text-pink-400 bg-pink-400/10' : 'text-blue-400 bg-blue-400/10'}`}>
                    {voice.gender === 'Female' ? 'F' : 'M'}
                  </span>
                </div>
                <p className="text-text-secondary text-xs mb-3 truncate">{voice.tone}</p>
                <Button
                  size="sm"
                  variant={isPlaying ? 'default' : 'outline'}
                  className={`w-full text-xs h-7 ${
                    isPlaying
                      ? 'bg-electric-purple text-white hover:bg-electric-purple/90'
                      : 'border-electric-purple/30 text-electric-purple hover:bg-electric-purple/10'
                  }`}
                  disabled={!hasSample && !isLoading}
                  onClick={() => handlePlayPreview(voice.voice_id)}
                  data-testid={`preview-${voice.voice_id}`}
                >
                  {isLoading ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : isPlaying ? (
                    <><Square className="w-3 h-3 mr-1" />Stop</>
                  ) : (
                    <><Play className="w-3 h-3 mr-1" />{hasSample ? 'Play Sample' : 'Generating...'}</>
                  )}
                </Button>
              </div>
            );
          })}
        </div>

        {/* Custom Audition (PAID) */}
        <Card className="bg-charcoal border-electric-purple/20" data-testid="custom-audition-panel">
          <CardHeader className="pb-3">
            <CardTitle className="text-white text-sm flex items-center gap-2">
              <Mic className="w-4 h-4 text-electric-purple" /> Custom Audition
            </CardTitle>
            <p className="text-text-secondary text-xs">Generate custom dialogue with any voice (costs 1 audition credit)</p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label className="text-white text-xs">Voice</Label>
                <VoiceSelectDropdown value={auditionVoice} onChange={setAuditionVoice} testId="audition-voice-select" />
              </div>
              <div>
                <Label className="text-white text-xs">Dialogue</Label>
                <Textarea
                  value={auditionText}
                  onChange={e => setAuditionText(e.target.value)}
                  className="mt-1.5 bg-slate border-white/10 text-white min-h-[70px] text-sm"
                  placeholder="अपना संवाद यहाँ लिखें..."
                  data-testid="audition-text-input"
                />
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Button
                onClick={handleAudition}
                disabled={auditionLoading || !auditionVoice || !auditionText.trim()}
                className="bg-electric-purple text-white hover:bg-electric-purple/90 text-sm"
                data-testid="audition-generate-button"
              >
                {auditionLoading ? (
                  <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />Generating...</>
                ) : (
                  <><Mic className="w-3.5 h-3.5 mr-1.5" />Generate Audition</>
                )}
              </Button>

              {auditionAudio && (
                <Button
                  size="sm"
                  onClick={() => {
                    if (auditionPlaying) {
                      auditionAudioRef.current?.pause();
                      setAuditionPlaying(false);
                    } else {
                      playAuditionAudio(auditionAudio);
                    }
                  }}
                  className="bg-electric-purple/20 text-electric-purple hover:bg-electric-purple/30"
                  data-testid="audition-playback-btn"
                >
                  {auditionPlaying ? <Square className="w-3.5 h-3.5 mr-1" /> : <Play className="w-3.5 h-3.5 mr-1" />}
                  {auditionPlaying ? 'Stop' : 'Replay'}
                </Button>
              )}

              <span className="text-text-secondary text-xs ml-auto">
                Cached replays are free
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ========== CHARACTERS SECTION (BOTTOM) ========== */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <User className="w-5 h-5 text-neon-cyan" />
            <h3 className="text-lg font-syne font-bold text-white">Your Characters</h3>
            <span className="text-text-secondary text-xs ml-1">({characters.length})</span>
          </div>
          <Button onClick={openCreateDialog} className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90" data-testid="create-character-button">
            <Plus className="w-4 h-4 mr-2" /> Add Character
          </Button>
        </div>

        {characters.length === 0 ? (
          <div className="text-center py-12 border border-dashed border-white/10 rounded-sm">
            <User className="w-12 h-12 text-neon-cyan/30 mx-auto mb-3" />
            <h3 className="text-base font-syne text-white mb-1">No characters yet</h3>
            <p className="text-text-secondary text-sm mb-4">Audition voices above, then create characters here</p>
            <Button onClick={openCreateDialog} className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90">
              <Plus className="w-4 h-4 mr-2" /> Add Character
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {characters.map(char => (
              <Card key={char.character_id} className="bg-charcoal border-white/10" data-testid={`character-${char.character_id}`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex items-start justify-between mb-1">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-neon-cyan/10 flex items-center justify-center">
                        <User className="w-5 h-5 text-neon-cyan" />
                      </div>
                      <div>
                        <h4 className="text-base font-syne font-bold text-white">{char.name}</h4>
                        <p className="text-xs text-text-secondary">{getVoiceDisplay(char.voice_id)}</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-3">
                    <Button
                      onClick={() => openEditDialog(char)}
                      variant="outline"
                      size="sm"
                      className="flex-1 border-neon-cyan/20 text-neon-cyan hover:bg-neon-cyan/10 text-xs"
                      data-testid={`edit-character-${char.character_id}`}
                    >
                      <Pencil className="w-3.5 h-3.5 mr-1.5" />Edit
                    </Button>
                    <Button
                      onClick={() => handleDeleteCharacter(char.character_id)}
                      variant="ghost"
                      size="sm"
                      className="text-text-secondary hover:text-red-400 h-8 w-8 p-0"
                      data-testid={`delete-character-${char.character_id}`}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* ===== CREATE CHARACTER DIALOG ===== */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="bg-charcoal border-white/10 text-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl font-syne">Create Character</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreateCharacter} className="space-y-5">
            <div>
              <Label className="text-white text-sm">Character Name</Label>
              <Input
                value={charForm.name}
                onChange={e => setCharForm({ ...charForm, name: e.target.value })}
                className="mt-1.5 bg-slate border-white/10 text-white"
                placeholder="e.g., Ravi, Priya"
                required
                data-testid="character-name-input"
              />
            </div>
            <div>
              <Label className="text-white text-sm">Voice</Label>
              <VoiceSelectDropdown value={charForm.voice_id} onChange={v => setCharForm({ ...charForm, voice_id: v })} testId="character-voice-select" />
              {charForm.voice_id && (() => {
                const v = voices.find(x => x.voice_id === charForm.voice_id);
                return v ? <p className="text-text-secondary text-xs mt-1">{v.gender} voice / {v.category_label}</p> : null;
              })()}
            </div>
            <Button
              type="submit"
              className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
              disabled={!charForm.name || !charForm.voice_id}
              data-testid="create-character-submit"
            >Create Character</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* ===== EDIT CHARACTER DIALOG ===== */}
      <Dialog open={showEditDialog} onOpenChange={(open) => { setShowEditDialog(open); if (!open) setEditingCharacter(null); }}>
        <DialogContent className="bg-charcoal border-white/10 text-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-xl font-syne">Edit Character</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleEditCharacter} className="space-y-5">
            <div>
              <Label className="text-white text-sm">Character Name</Label>
              <Input
                value={charForm.name}
                onChange={e => setCharForm({ ...charForm, name: e.target.value })}
                className="mt-1.5 bg-slate border-white/10 text-white"
                placeholder="e.g., Ravi, Priya"
                required
                data-testid="edit-character-name-input"
              />
            </div>
            <div>
              <Label className="text-white text-sm">Voice</Label>
              <VoiceSelectDropdown value={charForm.voice_id} onChange={v => setCharForm({ ...charForm, voice_id: v })} testId="edit-character-voice-select" />
              {charForm.voice_id && (() => {
                const v = voices.find(x => x.voice_id === charForm.voice_id);
                return v ? <p className="text-text-secondary text-xs mt-1">{v.gender} voice / {v.category_label}</p> : null;
              })()}
            </div>
            <p className="text-text-secondary text-xs">Changes will apply to future generations only.</p>
            <Button
              type="submit"
              className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
              disabled={!charForm.name || !charForm.voice_id}
              data-testid="edit-character-submit"
            >Save Changes</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Hidden audio elements */}
      <audio ref={previewAudioRef} className="hidden" />
      <audio ref={auditionAudioRef} onEnded={() => setAuditionPlaying(false)} className="hidden" />
    </div>
  );
}

export default Characters;
