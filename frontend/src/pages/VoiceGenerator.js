import React, { useState, useEffect, useRef } from 'react';
import { useStudio } from '../contexts/StudioContext';
import { useParams, useOutletContext, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Slider } from '../components/ui/slider';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Badge } from '../components/ui/badge';
import { Switch } from '../components/ui/switch';
import { Play, Square, Loader2, Sparkles, Users, Mic, Settings, History, User, Trash2, Plus, Music, Wand2, ShieldCheck, ArrowRight, Check, Type, MessageSquare, Upload, Coins } from 'lucide-react';
import { toast } from 'sonner';

const AUDIO_TAGS = {
  emotions: ['cheerfully', 'sad', 'excited', 'angry', 'whispering', 'shouting', 'nervously', 'confidently', 'sarcastically'],
  actions: ['laughing', 'giggling', 'sighing', 'crying', 'gasping', 'coughing', 'clearing throat'],
  delivery: ['stuttering', 'slowly', 'quickly', 'dramatically', 'monotonously']
};

const STABILITY_MODES = [
  { value: 0.0, label: 'Creative', description: 'Most expressive' },
  { value: 0.5, label: 'Natural', description: 'Balanced (default)' },
  { value: 1.0, label: 'Robust', description: 'Most stable' }
];

const PIPELINE_STEPS = [
  { id: 'generate', label: 'Generating voice', icon: Mic },
  { id: 'isolate', label: 'Cleaning audio', icon: ShieldCheck },
  { id: 'studio', label: 'Adding to studio', icon: Music },
];

const STYLE_PRESET_LABELS = {
  storytelling: 'Storytelling',
  emotional: 'Emotional',
  dramatic: 'Dramatic',
  calm: 'Calm',
  horror: 'Horror',
  casual: 'Casual',
};

const MAX_HISTORY = 5;

function ProgressBar({ step, steps, active }) {
  const currentIdx = steps.findIndex(s => s.id === step);
  return (
    <div className="space-y-2" data-testid="generation-progress-bar">
      <div className="flex gap-1">
        {steps.map((s, i) => (
          <div key={s.id} className="flex-1">
            <div className={`h-1.5 rounded-full transition-all duration-500 ${
              i < currentIdx ? 'bg-signal-green' : i === currentIdx && active ? 'bg-neon-cyan animate-pulse' : 'bg-white/10'
            }`} />
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2">
        {steps.map((s, i) => {
          const Icon = s.icon;
          const isDone = i < currentIdx;
          const isCurrent = i === currentIdx && active;
          return (
            <div key={s.id} className={`flex items-center gap-1.5 text-xs ${isDone ? 'text-signal-green' : isCurrent ? 'text-neon-cyan' : 'text-text-secondary/40'}`}>
              {isDone ? <Check className="w-3 h-3" /> : <Icon className="w-3 h-3" />}
              <span>{s.label}{isCurrent ? '...' : ''}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VoiceGenerator() {
  const { storyId } = useParams();
  const { story } = useOutletContext();
  const navigate = useNavigate();
  const {
    characters,
    ttsSettings,
    episodes,
    selectedEpisode, setSelectedEpisode,
    studioLoading: loading,
  } = useStudio();

  const [generating, setGenerating] = useState(false);
  const [pipelineStep, setPipelineStep] = useState(null);
  const [generatedAudio, setGeneratedAudio] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playingHistoryIndex, setPlayingHistoryIndex] = useState(null);
  const audioRef = useRef(null);
  const historyAudioRef = useRef(null);
  const [history, setHistory] = useState([]);
  const [credits, setCredits] = useState({ generation_credits: 0, audition_credits: 0 });

  // Engine settings from shared context
  const engineSettings = ttsSettings;
  const isAlternateEngine = engineSettings?.engineType === 'alternate';

  // Character & text
  const [selectedCharacterId, setSelectedCharacterId] = useState('');
  const [selectedCharacter, setSelectedCharacter] = useState(null);
  const [text, setText] = useState('');

  // ElevenLabs settings
  const [stability, setStability] = useState(0.5);
  const [similarityBoost, setSimilarityBoost] = useState(0.75);
  const [style, setStyle] = useState(0.0);
  const [speed, setSpeed] = useState(1.0);
  const [useSpeakerBoost, setUseSpeakerBoost] = useState(true);
  const [languageCode, setLanguageCode] = useState('');

  // Gemini settings
  const [stylePreset, setStylePreset] = useState('storytelling');
  const [directorNotes, setDirectorNotes] = useState('');

  // Toggles
  const [enhanceVoice, setEnhanceVoice] = useState(true);
  const [cleanAudio, setCleanAudio] = useState(false);
  const [addToStudio, setAddToStudio] = useState(true);

  // Dialogue
  const [dialogueInputs, setDialogueInputs] = useState([
    { text: '', character_id: '' },
    { text: '', character_id: '' }
  ]);

  const base = process.env.REACT_APP_BACKEND_URL;
  const token = localStorage.getItem('token') || '';
  const headers = { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };

  useEffect(() => {
    fetchCredits();
    loadHistory();
  }, [storyId]);

  useEffect(() => {
    if (characters.length > 0 && !selectedCharacterId) {
      setSelectedCharacterId(characters[0].character_id);
    }
  }, [characters]);

  useEffect(() => {
    if (selectedCharacterId && characters.length > 0) {
      const char = characters.find(c => c.character_id === selectedCharacterId);
      if (char) {
        setSelectedCharacter(char);
        if (!isAlternateEngine && char.voice_settings && !enhanceVoice) {
          setStability(char.voice_settings.stability ?? 0.5);
          setSimilarityBoost(char.voice_settings.similarity_boost ?? 0.75);
          setStyle(char.voice_settings.style ?? 0.0);
        }
      }
    } else { setSelectedCharacter(null); }
  }, [selectedCharacterId, characters, isAlternateEngine]);

  useEffect(() => {
    if (!isAlternateEngine && enhanceVoice) { setStability(0.0); setStyle(0.45); setSimilarityBoost(0.85); }
  }, [enhanceVoice, isAlternateEngine]);

  const fetchCredits = async () => {
    try {
      const res = await fetch(`${base}/api/credits`, { headers: { 'Authorization': `Bearer ${token}` } });
      if (res.ok) setCredits(await res.json());
    } catch (e) { console.error(e); }
  };

  const loadHistory = () => { try { const s = localStorage.getItem(`voice_history_${storyId}`); if (s) setHistory(JSON.parse(s)); } catch (e) {} };
  const saveToHistory = (item) => { const h = [item, ...history].slice(0, MAX_HISTORY); setHistory(h); localStorage.setItem(`voice_history_${storyId}`, JSON.stringify(h)); };
  const clearHistory = () => { setHistory([]); localStorage.removeItem(`voice_history_${storyId}`); toast.success('History cleared'); };

  const insertAudioTag = (tag) => setText(prev => `${prev} [${tag}]`);

  // ===== MAIN PIPELINE =====
  const handleGenerateAndPush = async () => {
    if (!text.trim()) { toast.error('Please enter dialogue text'); return; }
    if (!selectedCharacter) { toast.error('Select a character first'); return; }
    if (!selectedCharacter.voice_id) { toast.error('Character has no voice assigned'); return; }

    setGenerating(true);
    setGeneratedAudio(null);
    setPipelineStep('generate');

    let audioUrl = null;
    let durationSec = null;

    try {
      const body = {
        text,
        voice_id: selectedCharacter.voice_id,
        language_code: languageCode || undefined
      };

      if (isAlternateEngine) {
        body.style_preset = stylePreset;
        body.style_instructions = directorNotes || undefined;
      } else {
        body.stability = stability;
        body.similarity_boost = similarityBoost;
        body.style = style;
        body.speed = speed;
        body.use_speaker_boost = useSpeakerBoost;
        body.output_format = 'mp3_44100_128';
      }

      const genRes = await fetch(`${base}/api/tts/generate`, { method: 'POST', headers, body: JSON.stringify(body) });
      
      // Parse response ONCE
      const genData = await genRes.json().catch(() => ({ detail: 'Failed to process response' }));
      
      if (!genRes.ok) { 
        // Map technical errors to user-friendly messages
        let errorMsg = genData.detail || 'Generation failed';
        if (errorMsg.toLowerCase().includes('credit')) {
          errorMsg = 'You do not have enough credits for this generation.';
        } else if (errorMsg.toLowerCase().includes('rate') || genRes.status === 429) {
          errorMsg = 'Too many requests. Please wait a moment and try again.';
        } else if (genRes.status >= 500) {
          errorMsg = 'Voice generation service is temporarily unavailable. Please try again shortly.';
        }
        throw new Error(errorMsg); 
      }
      
      audioUrl = genData.audio_url;
      durationSec = genData.duration_seconds;

      if (cleanAudio) {
        setPipelineStep('isolate');
        try {
          const isoRes = await fetch(`${base}/api/tts/isolate`, { method: 'POST', headers, body: JSON.stringify({ audio_base64: audioUrl }) });
          if (isoRes.ok) { const isoData = await isoRes.json(); audioUrl = isoData.audio_url; durationSec = isoData.duration_seconds || durationSec; }
          else toast.warning('Isolation failed — using original audio');
        } catch (isoErr) { toast.warning('Isolation unavailable — using original audio'); }
      }

      setGeneratedAudio({ audio_url: audioUrl, settings_used: genData.settings_used, duration_seconds: durationSec });

      if (addToStudio) {
        setPipelineStep('studio');
        pushClipToStudio(audioUrl, selectedCharacter.name, text, durationSec);
      }

      saveToHistory({
        id: Date.now(),
        character_name: selectedCharacter.name,
        character_id: selectedCharacter.character_id,
        text: text.substring(0, 100) + (text.length > 100 ? '...' : ''),
        full_text: text, audio_url: audioUrl,
        settings: genData.settings_used,
        enhanced: enhanceVoice, isolated: cleanAudio,
        timestamp: new Date().toISOString()
      });

      fetchCredits();
      toast.success(addToStudio ? 'Audio generated and added to studio!' : 'Voice generated successfully!');
    } catch (error) { 
      // Show user-friendly error
      const friendlyMsg = error.message.includes('fetch') || error.message.includes('network') 
        ? 'Network issue. Please check your connection and try again.'
        : error.message;
      toast.error(friendlyMsg);
    }
    finally { setGenerating(false); setPipelineStep(null); }
  };

  // Dialogue generation
  const handleGenerateDialogue = async () => {
    const validInputs = dialogueInputs.filter(i => i.text.trim() && i.character_id);
    if (validInputs.length < 2) { toast.error('Add at least 2 dialogue turns with characters'); return; }
    const inputs = validInputs.map(input => {
      const char = characters.find(c => c.character_id === input.character_id);
      return { text: input.text, voice_id: char?.voice_id || '' };
    }).filter(i => i.voice_id);
    if (inputs.length < 2) { toast.error('Characters must have voices assigned'); return; }

    setGenerating(true);
    setGeneratedAudio(null);
    setPipelineStep('generate');

    try {
      const res = await fetch(`${base}/api/tts/dialogue`, {
        method: 'POST', headers,
        body: JSON.stringify({ inputs, stability, similarity_boost: similarityBoost, style, speed, output_format: 'mp3_44100_128' })
      });
      
      // Parse response ONCE
      const data = await res.json().catch(() => ({ detail: 'Failed to process response' }));
      
      if (!res.ok) { 
        // Map technical errors to user-friendly messages
        let errorMsg = data.detail || 'Dialogue generation failed';
        if (errorMsg.toLowerCase().includes('credit')) {
          errorMsg = 'You do not have enough credits for this generation.';
        } else if (errorMsg.toLowerCase().includes('rate') || res.status === 429) {
          errorMsg = 'Too many requests. Please wait a moment and try again.';
        } else if (res.status >= 500) {
          errorMsg = 'Voice generation service is temporarily unavailable. Please try again shortly.';
        }
        throw new Error(errorMsg); 
      }
      
      let audioUrl = data.audio_url;

      if (cleanAudio) {
        setPipelineStep('isolate');
        try {
          const isoRes = await fetch(`${base}/api/tts/isolate`, { method: 'POST', headers, body: JSON.stringify({ audio_base64: audioUrl }) });
          if (isoRes.ok) { const isoData = await isoRes.json(); audioUrl = isoData.audio_url; }
        } catch (e) { toast.warning('Isolation unavailable — using original'); }
      }

      setGeneratedAudio({ ...data, audio_url: audioUrl });

      if (addToStudio) {
        setPipelineStep('studio');
        const charNames = validInputs.map(i => characters.find(c => c.character_id === i.character_id)?.name || '?').join(' & ');
        pushClipToStudio(audioUrl, charNames, `Dialogue: ${data.total_turns} turns`, data.duration_seconds);
        toast.success('Dialogue generated and added to studio!');
      } else { toast.success(`Dialogue generated with ${data.speakers_count} speakers!`); }

      fetchCredits();
    } catch (error) { 
      // Show user-friendly error
      const friendlyMsg = error.message.includes('fetch') || error.message.includes('network') 
        ? 'Network issue. Please check your connection and try again.'
        : error.message;
      toast.error(friendlyMsg);
    }
    finally { setGenerating(false); setPipelineStep(null); }
  };

  const pushClipToStudio = (audioUrl, characterName, textContent, duration) => {
    const clipData = {
      id: `generated-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name: `${characterName} - ${textContent?.substring(0, 30) || 'Voice'}...`,
      url: audioUrl, characterName, text: textContent,
      duration: duration || 5, start: 0, type: 'voice',
      generatedAt: new Date().toISOString()
    };
    const episodeId = selectedEpisode?.episode_id;
    const key = episodeId ? `pending_clips_${storyId}_${episodeId}` : `pending_clips_${storyId}`;
    const existing = JSON.parse(localStorage.getItem(key) || '[]');
    existing.push(clipData);
    localStorage.setItem(key, JSON.stringify(existing));
  };

  const handlePlayPause = () => {
    if (!audioRef.current) return;
    if (isPlaying) audioRef.current.pause(); else audioRef.current.play();
    setIsPlaying(!isPlaying);
  };

  const playHistoryItem = (index) => {
    if (playingHistoryIndex === index) { historyAudioRef.current?.pause(); setPlayingHistoryIndex(null); }
    else { if (historyAudioRef.current) { historyAudioRef.current.src = history[index].audio_url; historyAudioRef.current.play(); setPlayingHistoryIndex(index); } }
  };

  const addDialogueTurn = () => setDialogueInputs([...dialogueInputs, { text: '', character_id: '' }]);
  const updateDialogueTurn = (index, field, value) => { const u = [...dialogueInputs]; u[index][field] = value; setDialogueInputs(u); };
  const removeDialogueTurn = (index) => { if (dialogueInputs.length <= 2) return; setDialogueInputs(dialogueInputs.filter((_, i) => i !== index)); };

  if (!loading && characters.length === 0) {
    return (
      <div className="p-6 max-w-4xl mx-auto" data-testid="voice-generator-page">
        <div className="text-center py-20">
          <User className="w-16 h-16 text-neon-cyan/50 mx-auto mb-4" />
          <h3 className="text-xl font-syne text-white mb-2">No characters yet</h3>
          <p className="text-text-secondary mb-6">Create characters in the Characters tab first, then come back to generate voices.</p>
          <Button onClick={() => navigate(`/studio/${storyId}/characters`)} className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90">
            <Plus className="w-4 h-4 mr-2" /> Go to Characters
          </Button>
        </div>
      </div>
    );
  }

  const activePipelineSteps = [
    PIPELINE_STEPS[0],
    ...(cleanAudio ? [PIPELINE_STEPS[1]] : []),
    ...(addToStudio ? [PIPELINE_STEPS[2]] : []),
  ];

  return (
    <div className="p-6 max-w-7xl mx-auto" data-testid="voice-generator-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-syne font-bold text-white mb-1">Voice Generator</h2>
          <p className="text-text-secondary text-sm">Select a character and generate dialogue for your story</p>
        </div>
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/10 text-xs" data-testid="generation-credits-badge">
          <Coins className="w-3.5 h-3.5 text-neon-cyan" />
          <span className="text-text-secondary">Credits:</span>
          <span className="text-white font-mono">{credits.generation_credits}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Panel */}
        <div className="lg:col-span-2 space-y-4">
          <Tabs defaultValue="single" className="w-full">
            <TabsList className="bg-charcoal border border-white/10">
              <TabsTrigger value="single" className="data-[state=active]:bg-neon-cyan data-[state=active]:text-obsidian" data-testid="tab-single-voice"><Mic className="w-4 h-4 mr-1.5" />Single Voice</TabsTrigger>
              {!isAlternateEngine && (
                <TabsTrigger value="dialogue" className="data-[state=active]:bg-neon-cyan data-[state=active]:text-obsidian" data-testid="tab-dialogue"><Users className="w-4 h-4 mr-1.5" />Dialogue</TabsTrigger>
              )}
            </TabsList>

            {/* Single Voice Tab */}
            <TabsContent value="single" className="mt-4">
              <Card className="bg-charcoal border-white/10">
                <CardContent className="pt-6 space-y-4">
                  {/* Character Selection — MANDATORY */}
                  <div>
                    <Label className="text-white text-sm">Character</Label>
                    <Select value={selectedCharacterId} onValueChange={setSelectedCharacterId}>
                      <SelectTrigger className="mt-1.5 bg-slate border-white/10 text-white" data-testid="character-select"><SelectValue placeholder="Select character" /></SelectTrigger>
                      <SelectContent className="bg-charcoal border-white/10">
                        {characters.map(c => (
                          <SelectItem key={c.character_id} value={c.character_id}>
                            <div className="flex items-center gap-2"><User className="w-3.5 h-3.5 text-neon-cyan" />{c.name}</div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {selectedCharacter && (
                      <p className="text-text-secondary text-xs mt-1">Voice assigned to this character will be used for generation</p>
                    )}
                  </div>

                  {/* Script Input */}
                  <div>
                    <Label className="text-white text-sm">Dialogue</Label>
                    <Textarea value={text} onChange={e => setText(e.target.value)}
                      className="mt-1.5 bg-slate border-white/10 text-white min-h-[100px]"
                      placeholder="Write dialogue for this character. Use [tags] for emotion like [excited], [whispering]..."
                      data-testid="text-input" />
                    <p className="text-text-secondary text-xs mt-1">{text.length} characters = {text.length} credits</p>
                  </div>

                  {/* Quick Tags */}
                  <div className="flex flex-wrap gap-1.5">
                    {AUDIO_TAGS.emotions.slice(0, 5).map(tag =>
                      <Badge key={tag} variant="outline" className="cursor-pointer border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/10 text-xs" onClick={() => insertAudioTag(tag)} data-testid={`tag-${tag}`}>[{tag}]</Badge>
                    )}
                    {AUDIO_TAGS.actions.slice(0, 3).map(tag =>
                      <Badge key={tag} variant="outline" className="cursor-pointer border-electric-purple/30 text-electric-purple hover:bg-electric-purple/10 text-xs" onClick={() => insertAudioTag(tag)}>[{tag}]</Badge>
                    )}
                  </div>

                  {/* Enhancement toggles (default engine only) */}
                  {!isAlternateEngine && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                      <div className={`flex items-center justify-between p-3 rounded-sm border transition-colors ${enhanceVoice ? 'border-neon-cyan/30 bg-neon-cyan/5' : 'border-white/10'}`}>
                        <div className="flex items-center gap-2.5">
                          <Wand2 className={`w-4 h-4 ${enhanceVoice ? 'text-neon-cyan' : 'text-text-secondary'}`} />
                          <div><p className="text-white text-sm font-medium">Enhance Voice</p><p className="text-text-secondary text-xs">Expressive tone & emotion</p></div>
                        </div>
                        <Switch checked={enhanceVoice} onCheckedChange={setEnhanceVoice} data-testid="enhance-toggle" />
                      </div>
                      <div className={`flex items-center justify-between p-3 rounded-sm border transition-colors ${cleanAudio ? 'border-signal-green/30 bg-signal-green/5' : 'border-white/10'}`}>
                        <div className="flex items-center gap-2.5">
                          <ShieldCheck className={`w-4 h-4 ${cleanAudio ? 'text-signal-green' : 'text-text-secondary'}`} />
                          <div><p className="text-white text-sm font-medium">Clean Audio</p><p className="text-text-secondary text-xs">Remove noise via isolation</p></div>
                        </div>
                        <Switch checked={cleanAudio} onCheckedChange={setCleanAudio} data-testid="clean-toggle" />
                      </div>
                    </div>
                  )}

                  {/* Push to studio toggle */}
                  <div className={`flex items-center justify-between p-3 rounded-sm border transition-colors ${addToStudio ? 'border-electric-purple/30 bg-electric-purple/5' : 'border-white/10'}`}>
                    <div className="flex items-center gap-2.5">
                      <Music className={`w-4 h-4 ${addToStudio ? 'text-electric-purple' : 'text-text-secondary'}`} />
                      <div><p className="text-white text-sm font-medium">Auto-Push to Studio</p><p className="text-text-secondary text-xs">Clip appears on voice track instantly</p></div>
                    </div>
                    <Switch checked={addToStudio} onCheckedChange={setAddToStudio} data-testid="studio-toggle" />
                  </div>

                  {generating && pipelineStep && <ProgressBar step={pipelineStep} steps={activePipelineSteps} active={true} />}

                  <Button onClick={handleGenerateAndPush}
                    disabled={generating || !text.trim() || !selectedCharacter}
                    className="w-full h-12 bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 font-semibold text-base"
                    data-testid="generate-studio-button">
                    {generating ? (
                      <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{
                        pipelineStep === 'generate' ? 'Generating voice...' :
                        pipelineStep === 'isolate' ? 'Cleaning audio...' :
                        pipelineStep === 'studio' ? 'Adding to studio...' : 'Processing...'
                      }</>
                    ) : (
                      <><Sparkles className="w-4 h-4 mr-2" />{addToStudio ? 'Generate & Push to Studio' : 'Generate Voice'}<ArrowRight className="w-4 h-4 ml-2" /></>
                    )}
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Dialogue Mode (default engine only) */}
            {!isAlternateEngine && (
              <TabsContent value="dialogue" className="mt-4">
                <Card className="bg-charcoal border-white/10">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-white text-lg">Multi-Speaker Dialogue</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {dialogueInputs.map((input, index) => (
                      <div key={index} className="p-3 bg-slate/50 rounded-sm border border-white/5">
                        <div className="flex items-center justify-between mb-2">
                          <Label className="text-white text-xs">Turn {index + 1}</Label>
                          {dialogueInputs.length > 2 && <Button variant="ghost" size="sm" onClick={() => removeDialogueTurn(index)} className="text-red-400 hover:text-red-300 h-6 text-xs">Remove</Button>}
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                          <Select value={input.character_id} onValueChange={v => updateDialogueTurn(index, 'character_id', v)}>
                            <SelectTrigger className="bg-slate border-white/10 text-white text-xs"><SelectValue placeholder="Character" /></SelectTrigger>
                            <SelectContent className="bg-charcoal border-white/10">{characters.map(c => <SelectItem key={c.character_id} value={c.character_id}>{c.name}</SelectItem>)}</SelectContent>
                          </Select>
                          <Textarea value={input.text} onChange={e => updateDialogueTurn(index, 'text', e.target.value)} className="md:col-span-2 bg-slate border-white/10 text-white min-h-[50px] text-sm" placeholder="Write dialogue..." />
                        </div>
                      </div>
                    ))}
                    <Button variant="outline" onClick={addDialogueTurn} className="w-full border-white/10 text-white hover:bg-white/5 text-sm">+ Add Turn</Button>

                    <div className="grid grid-cols-2 gap-3">
                      <div className={`flex items-center justify-between p-3 rounded-sm border ${cleanAudio ? 'border-signal-green/30 bg-signal-green/5' : 'border-white/10'}`}>
                        <div className="flex items-center gap-2"><ShieldCheck className={`w-3.5 h-3.5 ${cleanAudio ? 'text-signal-green' : 'text-text-secondary'}`} /><span className="text-white text-xs">Clean Audio</span></div>
                        <Switch checked={cleanAudio} onCheckedChange={setCleanAudio} />
                      </div>
                      <div className={`flex items-center justify-between p-3 rounded-sm border ${addToStudio ? 'border-electric-purple/30 bg-electric-purple/5' : 'border-white/10'}`}>
                        <div className="flex items-center gap-2"><Music className={`w-3.5 h-3.5 ${addToStudio ? 'text-electric-purple' : 'text-text-secondary'}`} /><span className="text-white text-xs">Push to Studio</span></div>
                        <Switch checked={addToStudio} onCheckedChange={setAddToStudio} />
                      </div>
                    </div>

                    {generating && pipelineStep && <ProgressBar step={pipelineStep} steps={activePipelineSteps} active={true} />}

                    <Button onClick={handleGenerateDialogue} disabled={generating}
                      className="w-full h-11 bg-electric-purple text-white hover:bg-electric-purple/90 font-semibold" data-testid="generate-dialogue-button">
                      {generating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Processing...</> : <><Users className="w-4 h-4 mr-2" />{addToStudio ? 'Generate & Push to Studio' : 'Generate Dialogue'}</>}
                    </Button>
                  </CardContent>
                </Card>
              </TabsContent>
            )}
          </Tabs>

          {/* Audio Player */}
          {generatedAudio && (
            <Card className="bg-charcoal border-neon-cyan/20">
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Button onClick={handlePlayPause} size="sm" className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90 h-9 w-9 p-0" data-testid="play-button">
                      {isPlaying ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                    </Button>
                    <div>
                      <p className="text-white text-sm font-medium">Generated Audio</p>
                      <p className="text-text-secondary text-xs">
                        {generatedAudio.duration_seconds ? `${generatedAudio.duration_seconds}s` : ''}
                        {generatedAudio.settings_used?.stability_mode ? ` / ${generatedAudio.settings_used.stability_mode}` : ''}
                        {generatedAudio.settings_used?.style_preset ? ` / ${STYLE_PRESET_LABELS[generatedAudio.settings_used.style_preset] || ''}` : ''}
                      </p>
                    </div>
                  </div>
                  {!addToStudio && (
                    <Button size="sm" onClick={() => {
                      pushClipToStudio(generatedAudio.audio_url, selectedCharacter?.name || 'Voice', text, generatedAudio.duration_seconds);
                      navigate(`/studio/${storyId}/audio`);
                      toast.success('Pushed to studio!');
                    }}
                      className="bg-signal-green text-obsidian hover:bg-signal-green/90 text-xs" data-testid="push-to-studio-button">
                      <Upload className="w-3.5 h-3.5 mr-1" />Push to Studio
                    </Button>
                  )}
                </div>
                <audio ref={audioRef} src={generatedAudio.audio_url} onEnded={() => setIsPlaying(false)} className="hidden" />
              </CardContent>
            </Card>
          )}

          {/* History */}
          {history.length > 0 && (
            <Card className="bg-charcoal border-white/10">
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-white text-sm flex items-center gap-2"><History className="w-4 h-4" />Recent ({history.length}/{MAX_HISTORY})</CardTitle>
                  <Button variant="ghost" size="sm" onClick={clearHistory} className="text-text-secondary hover:text-red-400 h-6"><Trash2 className="w-3.5 h-3.5" /></Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {history.map((item, index) => (
                  <div key={item.id} className="flex items-center justify-between p-2.5 bg-slate/50 rounded-sm border border-white/5">
                    <div className="flex items-center gap-2.5 flex-1 min-w-0">
                      <Button size="sm" variant="ghost" onClick={() => playHistoryItem(index)} className="text-neon-cyan hover:bg-neon-cyan/10 shrink-0 h-7 w-7 p-0">
                        {playingHistoryIndex === index ? <Square className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                      </Button>
                      <div className="min-w-0 flex-1">
                        <p className="text-white text-xs font-medium truncate">{item.character_name}</p>
                        <p className="text-text-secondary text-xs truncate">{item.text}</p>
                      </div>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => { pushClipToStudio(item.audio_url, item.character_name, item.full_text || item.text); navigate(`/studio/${storyId}/audio`); toast.success('Pushed to studio!'); }}
                      className="text-signal-green hover:bg-signal-green/10 h-7 w-7 p-0 shrink-0 ml-2" title="Push to studio"><Upload className="w-3.5 h-3.5" /></Button>
                  </div>
                ))}
                <audio ref={historyAudioRef} onEnded={() => setPlayingHistoryIndex(null)} className="hidden" />
              </CardContent>
            </Card>
          )}
        </div>

        {/* Settings Sidebar */}
        <div className="space-y-4">
          {/* Default engine settings */}
          {!isAlternateEngine && (
            <Card className="bg-charcoal border-white/10">
              <CardHeader className="pb-3">
                <CardTitle className="text-white text-sm flex items-center gap-2"><Settings className="w-4 h-4" />Voice Settings</CardTitle>
                {enhanceVoice && <p className="text-neon-cyan text-xs">Enhanced mode — optimal settings applied</p>}
              </CardHeader>
              <CardContent className="space-y-5">
                <div>
                  <Label className="text-white text-sm mb-2 block">Stability Mode</Label>
                  <div className="space-y-1.5">
                    {STABILITY_MODES.map(mode => (
                      <div key={mode.value} onClick={() => { setStability(mode.value); if (enhanceVoice && mode.value !== 0.0) setEnhanceVoice(false); }}
                        className={`p-2.5 rounded-sm border cursor-pointer transition-colors ${stability === mode.value ? 'border-neon-cyan bg-neon-cyan/10' : 'border-white/10 hover:border-white/20'}`}
                        data-testid={`stability-${mode.label.toLowerCase()}`}>
                        <div className="flex items-center justify-between"><span className="text-white text-sm font-medium">{mode.label}</span><span className="text-text-secondary text-xs">{mode.value}</span></div>
                        <p className="text-xs text-text-secondary">{mode.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-1.5"><Label className="text-white text-sm">Similarity</Label><span className="text-neon-cyan font-mono text-xs">{similarityBoost.toFixed(2)}</span></div>
                  <Slider value={[similarityBoost]} onValueChange={([v]) => setSimilarityBoost(v)} min={0} max={1} step={0.05} data-testid="similarity-slider" />
                </div>
                <div>
                  <div className="flex justify-between mb-1.5"><Label className="text-white text-sm">Style</Label><span className="text-neon-cyan font-mono text-xs">{style.toFixed(2)}</span></div>
                  <Slider value={[style]} onValueChange={([v]) => setStyle(v)} min={0} max={1} step={0.05} data-testid="style-slider" />
                </div>
                <div>
                  <div className="flex justify-between mb-1.5"><Label className="text-white text-sm">Speed</Label><span className="text-neon-cyan font-mono text-xs">{speed.toFixed(2)}x</span></div>
                  <Slider value={[speed]} onValueChange={([v]) => setSpeed(v)} min={0.7} max={1.2} step={0.05} data-testid="speed-slider" />
                </div>
                <div className="flex items-center justify-between">
                  <div><Label className="text-white text-sm">Speaker Boost</Label><p className="text-xs text-text-secondary">Enhanced similarity</p></div>
                  <Switch checked={useSpeakerBoost} onCheckedChange={setUseSpeakerBoost} data-testid="speaker-boost-toggle" />
                </div>
                <div>
                  <Label className="text-white text-sm mb-1.5 block">Language</Label>
                  <Select value={languageCode || "auto"} onValueChange={v => setLanguageCode(v === "auto" ? "" : v)}>
                    <SelectTrigger className="bg-slate border-white/10 text-white text-xs" data-testid="language-select"><SelectValue placeholder="Auto" /></SelectTrigger>
                    <SelectContent className="bg-charcoal border-white/10">
                      <SelectItem value="auto">Auto-detect</SelectItem>
                      <SelectItem value="en">English</SelectItem><SelectItem value="hi">Hindi</SelectItem>
                      <SelectItem value="es">Spanish</SelectItem><SelectItem value="fr">French</SelectItem>
                      <SelectItem value="de">German</SelectItem><SelectItem value="ja">Japanese</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Alternate engine settings */}
          {isAlternateEngine && (
            <Card className="bg-charcoal border-white/10">
              <CardHeader className="pb-3">
                <CardTitle className="text-white text-sm flex items-center gap-2"><Settings className="w-4 h-4" />Voice Settings</CardTitle>
                <p className="text-electric-purple text-xs">Style-based voice generation</p>
              </CardHeader>
              <CardContent className="space-y-5">
                <div>
                  <Label className="text-white text-sm mb-1.5 block">Style Preset</Label>
                  <Select value={stylePreset} onValueChange={setStylePreset}>
                    <SelectTrigger className="bg-slate border-white/10 text-white" data-testid="style-preset-select"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-charcoal border-white/10">
                      {(engineSettings?.stylePresets || []).map(p => (
                        <SelectItem key={p} value={p}><div className="flex items-center gap-2"><Type className="w-3.5 h-3.5 text-electric-purple" />{STYLE_PRESET_LABELS[p] || p}</div></SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-white text-sm mb-1.5 block">Director's Notes</Label>
                  <Textarea value={directorNotes} onChange={e => setDirectorNotes(e.target.value)}
                    className="bg-slate border-white/10 text-white min-h-[80px] text-sm"
                    placeholder="e.g., Speak in a dramatic Hindi storytelling tone with natural pauses and expressive delivery."
                    data-testid="director-notes-input" />
                  <p className="text-text-secondary text-xs mt-1">Fine-tune delivery alongside the style preset.</p>
                </div>
                <div>
                  <Label className="text-white text-sm mb-1.5 block">Language</Label>
                  <Select value={languageCode || "auto"} onValueChange={v => setLanguageCode(v === "auto" ? "" : v)}>
                    <SelectTrigger className="bg-slate border-white/10 text-white text-xs" data-testid="language-select"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-charcoal border-white/10">
                      <SelectItem value="auto">Auto-detect</SelectItem>
                      <SelectItem value="en">English</SelectItem><SelectItem value="hi">Hindi</SelectItem>
                      <SelectItem value="es">Spanish</SelectItem><SelectItem value="fr">French</SelectItem>
                      <SelectItem value="de">German</SelectItem><SelectItem value="ja">Japanese</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="p-3 rounded-sm border border-electric-purple/20 bg-electric-purple/5">
                  <div className="flex items-center gap-2 mb-1.5"><MessageSquare className="w-3.5 h-3.5 text-electric-purple" /><span className="text-white text-xs font-medium">Audio Tags Supported</span></div>
                  <p className="text-text-secondary text-xs">Use [whispering], [angry], [sad] directly in dialogue text.</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Audio Tags Reference */}
          <Card className="bg-charcoal border-white/10">
            <CardHeader className="pb-2"><CardTitle className="text-white text-sm">Audio Tags</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <div><p className="text-xs text-neon-cyan mb-1">Emotions</p><div className="flex flex-wrap gap-1">{AUDIO_TAGS.emotions.map(t => <Badge key={t} variant="outline" className="text-[10px] border-white/10 text-text-secondary cursor-pointer hover:border-neon-cyan/50" onClick={() => insertAudioTag(t)}>[{t}]</Badge>)}</div></div>
              <div><p className="text-xs text-electric-purple mb-1">Actions</p><div className="flex flex-wrap gap-1">{AUDIO_TAGS.actions.map(t => <Badge key={t} variant="outline" className="text-[10px] border-white/10 text-text-secondary cursor-pointer hover:border-electric-purple/50" onClick={() => insertAudioTag(t)}>[{t}]</Badge>)}</div></div>
              <div><p className="text-xs text-warm-gold mb-1">Delivery</p><div className="flex flex-wrap gap-1">{AUDIO_TAGS.delivery.map(t => <Badge key={t} variant="outline" className="text-[10px] border-white/10 text-text-secondary cursor-pointer hover:border-warm-gold/50" onClick={() => insertAudioTag(t)}>[{t}]</Badge>)}</div></div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default VoiceGenerator;
