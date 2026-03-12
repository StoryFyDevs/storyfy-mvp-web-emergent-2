import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Shield, LogOut, ArrowLeft, Volume2, VolumeX, Music, Mic2, Zap,
  ZoomIn, ZoomOut, Eye, Play, Pause, Square, SkipBack,
  AlertTriangle, RefreshCw, FileText, Layers
} from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Slider } from '../../components/ui/slider';

const PIXELS_PER_SECOND = 50;
const TRACK_HEIGHT = 80;

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 100);
  return `${m}:${String(s).padStart(2, '0')}.${String(ms).padStart(2, '0')}`;
}

const CHARACTER_COLORS = [
  'text-neon-cyan border-neon-cyan/40 bg-neon-cyan/10',
  'text-electric-purple border-electric-purple/40 bg-electric-purple/10',
  'text-warm-gold border-warm-gold/40 bg-warm-gold/10',
  'text-signal-green border-signal-green/40 bg-signal-green/10',
  'text-sunset-orange border-sunset-orange/40 bg-sunset-orange/10',
];

function AdminProjectViewer() {
  const { episodeId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [activeTab, setActiveTab] = useState('timeline');
  const [brokenClips, setBrokenClips] = useState(new Set());
  const [regenerating, setRegenerating] = useState(false);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [timelineTime, setTimelineTime] = useState(0);
  const [masterVolume, setMasterVolume] = useState(0.75);
  const [loadingAudio, setLoadingAudio] = useState(false);

  const audioContextRef = useRef(null);
  const audioBuffersRef = useRef({});
  const audioSourcesRef = useRef({});
  const gainNodesRef = useRef({});
  const playbackStartTimeRef = useRef(0);
  const playbackOffsetRef = useRef(0);
  const animationFrameRef = useRef(null);
  const isPlayingRef = useRef(false);
  const timelineViewportRef = useRef(null);

  const navigate = useNavigate();
  const token = localStorage.getItem('admin_token');

  useEffect(() => {
    if (!token) { navigate('/admin-access/login'); return; }
    fetchProject();
    return () => { if (isPlayingRef.current) stopPlayback(); };
  }, [episodeId]);

  const fetchProject = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin-9821/episodes/${episodeId}/project`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.status === 401 || res.status === 403) {
        localStorage.removeItem('admin_token');
        navigate('/admin-access/login');
        return;
      }
      if (!res.ok) throw new Error('Failed to load project');
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

  const handleRegenerate = async () => {
    if (!window.confirm('This will trigger a fresh audio generation for this episode using the saved script. Continue?')) return;
    setRegenerating(true);
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/admin-9821/episodes/${episodeId}/regenerate-audio`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Regeneration failed');
      toast.success(`Audio regeneration queued (job: ${body.job_id}). Refresh in a few minutes to see updated clips.`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRegenerating(false);
    }
  };

  const project = data?.project_state || {};
  const tracks = useMemo(() => (data?.project_state?.tracks || []), [data]);
  const dialogues = useMemo(() => data?.dialogues || [], [data]);
  const duration = project.duration || 60;
  const pps = PIXELS_PER_SECOND * zoom;
  const timelineWidth = duration * pps;
  const playheadPosition = timelineTime * pps;

  // Build character color map from dialogues
  const characterColorMap = useMemo(() => {
    const map = {};
    let idx = 0;
    dialogues.forEach(d => {
      const key = d.character_id || d.character || '';
      if (key && !map[key]) {
        map[key] = CHARACTER_COLORS[idx % CHARACTER_COLORS.length];
        idx++;
      }
    });
    return map;
  }, [dialogues]);

  const ensureAudioContext = useCallback(async () => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContextRef.current.state === 'suspended') {
      await audioContextRef.current.resume();
    }
    return audioContextRef.current;
  }, []);

  const resolveAudioUrl = useCallback((url) => {
    if (!url) return null;
    if (url.startsWith('data:')) return url;
    if (url.startsWith('nhost-file:')) {
      const fileId = url.replace('nhost-file:', '');
      return `${process.env.REACT_APP_BACKEND_URL}/api/audio/stream-file/${fileId}`;
    }
    return url;
  }, []);

  const loadAudioBuffer = useCallback(async (clip) => {
    if (!clip?.url) return null;
    if (audioBuffersRef.current[clip.id]) return audioBuffersRef.current[clip.id];
    const ctx = await ensureAudioContext();
    try {
      const resolvedUrl = resolveAudioUrl(clip.url);
      if (!resolvedUrl) return null;
      let arrayBuffer;
      if (resolvedUrl.startsWith('data:')) {
        const base64 = resolvedUrl.split(',')[1];
        const bin = atob(base64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        arrayBuffer = bytes.buffer;
      } else {
        const response = await fetch(resolvedUrl, { credentials: 'include' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        arrayBuffer = await response.arrayBuffer();
      }
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      audioBuffersRef.current[clip.id] = audioBuffer;
      return audioBuffer;
    } catch (err) {
      console.warn(`[Admin] Failed to load audio for ${clip.id}:`, err.message);
      setBrokenClips(prev => new Set([...prev, clip.id]));
      return null;
    }
  }, [ensureAudioContext, resolveAudioUrl]);

  const preloadAllClips = useCallback(async () => {
    setLoadingAudio(true);
    const allClips = tracks.flatMap(t => t.clips || []);
    await Promise.all(allClips.map(c => loadAudioBuffer(c)));
    setLoadingAudio(false);
  }, [tracks, loadAudioBuffer]);

  const scheduleClip = useCallback((ctx, track, clip, currentTime) => {
    const buffer = audioBuffersRef.current[clip.id];
    if (!buffer) return;
    const clipStart = clip.start || 0;
    const clipDuration = clip.duration || buffer.duration;
    const clipEnd = clipStart + clipDuration;
    const trimStart = clip.trimStart || 0;
    if (currentTime >= clipEnd) return;

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    const gainNode = ctx.createGain();
    gainNode.gain.value = (track.volume ?? 0.8) * masterVolume;
    source.connect(gainNode);
    gainNode.connect(ctx.destination);

    let when = ctx.currentTime;
    let offset = trimStart;
    let dur = clipDuration;

    if (currentTime < clipStart) {
      when = ctx.currentTime + (clipStart - currentTime);
      offset = trimStart;
      dur = clipDuration;
    } else {
      offset = trimStart + (currentTime - clipStart);
      dur = clipEnd - currentTime;
    }
    offset = Math.max(0, Math.min(offset, buffer.duration));
    dur = Math.min(dur, buffer.duration - offset);

    if (dur > 0) {
      source.start(when, offset, dur);
      const key = `${track.id}-${clip.id}`;
      audioSourcesRef.current[key] = source;
      gainNodesRef.current[key] = gainNode;
      source.onended = () => { delete audioSourcesRef.current[key]; delete gainNodesRef.current[key]; };
    }
  }, [masterVolume]);

  const startPlayback = useCallback(async () => {
    const ctx = await ensureAudioContext();
    if (!ctx) return;
    playbackStartTimeRef.current = ctx.currentTime;
    playbackOffsetRef.current = timelineTime;
    setIsPlaying(true);
    isPlayingRef.current = true;

    const hasSolo = tracks.some(t => t.solo);
    tracks.forEach(track => {
      if (track.muted || (hasSolo && !track.solo)) return;
      (track.clips || []).forEach(clip => scheduleClip(ctx, track, clip, timelineTime));
    });

    const updateLoop = () => {
      if (!isPlayingRef.current) return;
      const elapsed = audioContextRef.current.currentTime - playbackStartTimeRef.current;
      const newTime = playbackOffsetRef.current + elapsed;
      if (newTime >= duration) { stopPlayback(); setTimelineTime(0); return; }
      setTimelineTime(newTime);
      animationFrameRef.current = requestAnimationFrame(updateLoop);
    };
    animationFrameRef.current = requestAnimationFrame(updateLoop);
  }, [timelineTime, duration, tracks, ensureAudioContext, scheduleClip]);

  const stopPlayback = useCallback(() => {
    setIsPlaying(false);
    isPlayingRef.current = false;
    Object.values(audioSourcesRef.current).forEach(s => { try { s.stop(); } catch {} });
    audioSourcesRef.current = {};
    gainNodesRef.current = {};
    if (animationFrameRef.current) { cancelAnimationFrame(animationFrameRef.current); animationFrameRef.current = null; }
  }, []);

  const handlePlayPause = useCallback(async () => {
    if (isPlaying) {
      stopPlayback();
    } else {
      const hasClips = tracks.some(t => (t.clips || []).length > 0);
      if (!hasClips) { toast.error('No audio clips to play'); return; }
      await preloadAllClips();
      startPlayback();
    }
  }, [isPlaying, tracks, stopPlayback, startPlayback, preloadAllClips]);

  const handleStop = useCallback(() => { stopPlayback(); setTimelineTime(0); }, [stopPlayback]);

  const handleTimelineClick = useCallback(async (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const newTime = Math.max(0, Math.min(x / pps, duration));
    const wasPlaying = isPlaying;
    if (wasPlaying) stopPlayback();
    setTimelineTime(newTime);
    if (wasPlaying) {
      await new Promise(r => setTimeout(r, 10));
      playbackOffsetRef.current = newTime;
      startPlayback();
    }
  }, [pps, duration, isPlaying, stopPlayback, startPlayback]);

  const timeRulerMarkers = useMemo(() => {
    const markers = [];
    const step = zoom >= 2 ? 1 : zoom >= 1 ? 2 : 5;
    for (let t = 0; t <= duration; t += step) {
      markers.push({ time: t, position: t * pps, isMajor: t % 10 === 0, label: formatTime(t) });
    }
    return markers;
  }, [duration, pps, zoom]);

  const trackIcon = (type) => {
    if (type === 'music') return <Music className="w-3.5 h-3.5 text-warm-gold" />;
    if (type === 'sfx') return <Zap className="w-3.5 h-3.5 text-sunset-orange" />;
    return <Mic2 className="w-3.5 h-3.5 text-neon-cyan" />;
  };

  const clipColor = (type, broken) => {
    if (broken) return 'from-amber-500/30 to-amber-500/10 border-amber-500/50';
    if (type === 'music') return 'from-warm-gold/30 to-warm-gold/10 border-warm-gold/50';
    if (type === 'sfx') return 'from-sunset-orange/30 to-sunset-orange/10 border-sunset-orange/50';
    return 'from-neon-cyan/30 to-neon-cyan/10 border-neon-cyan/50';
  };

  const totalClips = tracks.reduce((sum, t) => sum + (t.clips?.length || 0), 0);
  const brokenCount = brokenClips.size;

  if (loading) {
    return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-neon-cyan font-space">Loading project...</div></div>;
  }
  if (!data) {
    return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-text-secondary">Project not found</div></div>;
  }

  const { episode, story, creator_name } = data;

  return (
    <div className="min-h-screen bg-obsidian flex flex-col" data-testid="admin-project-viewer">
      {/* Header */}
      <header className="border-b border-white/5 bg-charcoal/60 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-full mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="w-5 h-5 text-electric-purple" />
            <span className="font-syne font-bold text-white text-lg">StoryFy Admin</span>
          </div>
          <nav className="flex items-center gap-6">
            <Link to="/admin-access/dashboard" className="text-text-secondary hover:text-white text-sm">Dashboard</Link>
            <Link to="/admin-access/creators" className="text-text-secondary hover:text-white text-sm">Creators</Link>
            <Link to="/admin-access/stories" className="text-neon-cyan text-sm font-medium">Stories</Link>
            <Link to="/admin-access/usage" className="text-text-secondary hover:text-white text-sm">Usage</Link>
            <Button variant="ghost" size="sm" onClick={handleLogout} className="text-text-secondary hover:text-white">
              <LogOut className="w-4 h-4 mr-1" /> Logout
            </Button>
          </nav>
        </div>
      </header>

      {/* Toolbar */}
      <div className="border-b border-white/10 bg-charcoal px-6 py-3 shrink-0">
        <div className="flex items-center justify-between gap-4">
          {/* Left: back + title + tabs */}
          <div className="flex items-center gap-4 min-w-0">
            <Button variant="ghost" size="sm" className="text-text-secondary hover:text-white shrink-0" onClick={() => navigate(`/admin-access/stories/${story?.story_id}`)} data-testid="back-to-story">
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <div className="border-l border-white/10 pl-4 min-w-0">
              <h2 className="text-white font-medium text-sm truncate">{episode?.title}</h2>
              <p className="text-text-secondary text-xs truncate">{story?.title} by {creator_name}</p>
            </div>

            {/* Tab switcher */}
            <div className="flex items-center gap-1 ml-4 bg-slate/50 rounded-md p-0.5 shrink-0">
              <button
                onClick={() => setActiveTab('timeline')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${activeTab === 'timeline' ? 'bg-electric-purple/20 text-electric-purple' : 'text-text-secondary hover:text-white'}`}
                data-testid="tab-timeline"
              >
                <Layers className="w-3.5 h-3.5" /> Timeline
              </button>
              <button
                onClick={() => setActiveTab('script')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${activeTab === 'script' ? 'bg-electric-purple/20 text-electric-purple' : 'text-text-secondary hover:text-white'}`}
                data-testid="tab-script"
              >
                <FileText className="w-3.5 h-3.5" /> Script
                {dialogues.length > 0 && <span className="bg-white/10 rounded-full px-1.5 py-0.5 text-xs">{dialogues.length}</span>}
              </button>
            </div>
          </div>

          {/* Right: transport + controls */}
          <div className="flex items-center gap-3 shrink-0">
            {brokenCount > 0 && (
              <div className="flex items-center gap-1.5 text-amber-400 text-xs">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>{brokenCount} clip{brokenCount !== 1 ? 's' : ''} unavailable</span>
              </div>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={handleRegenerate}
              disabled={regenerating}
              className="text-xs border-electric-purple/40 text-electric-purple hover:bg-electric-purple/10 h-7"
              data-testid="regen-audio-btn"
            >
              <RefreshCw className={`w-3 h-3 mr-1 ${regenerating ? 'animate-spin' : ''}`} />
              {regenerating ? 'Queuing…' : 'Re-generate Audio'}
            </Button>

            <div className="flex items-center gap-1 bg-slate rounded-sm px-2 py-1">
              <Button variant="ghost" size="icon" className="h-7 w-7 text-text-secondary hover:text-white" onClick={handleStop} data-testid="stop-btn">
                <Square className="w-3.5 h-3.5" />
              </Button>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-text-secondary hover:text-white" onClick={() => { if (isPlaying) stopPlayback(); setTimelineTime(0); }} data-testid="rewind-btn">
                <SkipBack className="w-3.5 h-3.5" />
              </Button>
              <Button
                size="icon"
                className={`h-8 w-8 rounded-full ${isPlaying ? 'bg-sunset-orange hover:bg-sunset-orange/80' : 'bg-signal-green hover:bg-signal-green/80'} text-obsidian`}
                onClick={handlePlayPause}
                disabled={loadingAudio}
                data-testid="play-pause-btn"
              >
                {loadingAudio ? (
                  <div className="w-3.5 h-3.5 border-2 border-obsidian border-t-transparent rounded-full animate-spin" />
                ) : isPlaying ? (
                  <Pause className="w-3.5 h-3.5" />
                ) : (
                  <Play className="w-3.5 h-3.5 ml-0.5" />
                )}
              </Button>
            </div>

            <span className="text-white font-mono text-sm w-20 text-center" data-testid="time-display">{formatTime(timelineTime)}</span>

            <div className="flex items-center gap-2 w-28">
              <Volume2 className="w-3.5 h-3.5 text-text-secondary shrink-0" />
              <Slider value={[masterVolume]} onValueChange={([v]) => setMasterVolume(v)} min={0} max={1} step={0.01} className="w-full" data-testid="master-volume" />
            </div>

            <div className="flex items-center gap-1 bg-electric-purple/15 border border-electric-purple/30 rounded-full px-3 py-1">
              <Eye className="w-3.5 h-3.5 text-electric-purple" />
              <span className="text-electric-purple text-xs font-medium">Read-Only</span>
            </div>

            <div className="text-xs text-text-secondary font-mono">{tracks.length}T {totalClips}C</div>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" className="h-7 w-7 text-text-secondary hover:text-white" onClick={() => setZoom(z => Math.max(0.25, z - 0.25))} data-testid="zoom-out">
                <ZoomOut className="w-4 h-4" />
              </Button>
              <span className="text-xs text-white font-mono w-10 text-center">{zoom.toFixed(2)}x</span>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-text-secondary hover:text-white" onClick={() => setZoom(z => Math.min(4, z + 0.25))} data-testid="zoom-in">
                <ZoomIn className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-hidden">

        {/* ── TIMELINE TAB ── */}
        {activeTab === 'timeline' && (
          <div className="h-full flex overflow-hidden">
            {/* Track Controls */}
            <div className="w-48 shrink-0 bg-charcoal border-r border-white/10 overflow-y-auto">
              <div className="h-10 border-b border-white/10 flex items-center px-3">
                <span className="text-xs text-text-secondary uppercase tracking-wider">Tracks</span>
              </div>
              {tracks.map((track) => (
                <div key={track.id} className="px-3 py-2 border-b border-white/5" style={{ height: `${TRACK_HEIGHT}px` }}>
                  <div className="flex items-center gap-2 mb-1">
                    {trackIcon(track.type)}
                    <span className="text-white text-xs font-medium truncate">{track.name}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    {track.muted ? <VolumeX className="w-3 h-3 text-red-400" /> : <Volume2 className="w-3 h-3 text-text-secondary" />}
                    <div className="flex-1 h-1 bg-slate rounded-full overflow-hidden">
                      <div className="h-full bg-neon-cyan/50 rounded-full" style={{ width: `${(track.volume || 0) * 100}%` }} />
                    </div>
                    <span className="text-xs text-text-secondary font-mono">{Math.round((track.volume || 0) * 100)}%</span>
                  </div>
                  <div className="flex gap-1 mt-1.5">
                    <span className={`text-xs px-1.5 py-0.5 rounded ${track.muted ? 'bg-red-400/20 text-red-400' : 'text-text-secondary'}`}>M</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${track.solo ? 'bg-neon-cyan/20 text-neon-cyan' : 'text-text-secondary'}`}>S</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Scrollable Timeline */}
            <div ref={timelineViewportRef} className="flex-1 overflow-auto" data-testid="timeline-viewport">
              <div className="relative" style={{ width: `${timelineWidth}px`, minHeight: '100%' }}>
                {/* Playhead */}
                <div
                  className="absolute top-0 w-0.5 bg-neon-cyan pointer-events-none"
                  style={{ left: `${playheadPosition}px`, height: '100%', zIndex: 50, boxShadow: '0 0 20px rgba(0,240,255,0.9)', transition: isPlaying ? 'none' : 'left 0.05s linear' }}
                  data-testid="playhead"
                >
                  <div className="absolute top-0 left-1/2 -translate-x-1/2 -mt-1 z-50">
                    <div className="w-3 h-3 bg-neon-cyan rounded-full shadow-lg border-2 border-white" />
                  </div>
                </div>

                {/* Time Ruler */}
                <div className="h-10 bg-charcoal border-b border-white/10 relative sticky top-0 z-10 cursor-pointer" onClick={handleTimelineClick} data-testid="time-ruler">
                  {timeRulerMarkers.map((marker) => (
                    <div key={marker.time} className="absolute top-0 h-full pointer-events-none" style={{ left: `${marker.position}px` }}>
                      <div className={`h-full ${marker.isMajor ? 'border-l border-white/30' : 'border-l border-white/10'}`} />
                      {marker.isMajor && <span className="absolute top-1 left-1 text-xs text-text-secondary whitespace-nowrap">{marker.label}</span>}
                    </div>
                  ))}
                </div>

                {/* Tracks */}
                <div className="space-y-0.5 py-1">
                  {tracks.map((track) => (
                    <div key={track.id} className="bg-charcoal/50 border border-white/5 rounded-sm relative" style={{ height: `${TRACK_HEIGHT}px` }} data-testid={`viewer-track-${track.id}`}>
                      {(track.clips || []).map((clip) => {
                        const clipLeft = (clip.start || 0) * pps;
                        const clipWidth = Math.max((clip.duration || 0) * pps, 40);
                        const isBroken = brokenClips.has(clip.id);
                        return (
                          <div
                            key={clip.id}
                            className={`absolute top-2 h-16 bg-gradient-to-r ${clipColor(track.type, isBroken)} border rounded-sm px-2 py-1`}
                            style={{ left: `${clipLeft}px`, width: `${clipWidth}px` }}
                            title={isBroken ? `${clip.name}\n⚠ Audio unavailable (legacy data — use Re-generate Audio)` : `${clip.name}\nStart: ${formatTime(clip.start || 0)}\nDuration: ${formatTime(clip.duration || 0)}`}
                            data-testid={`viewer-clip-${clip.id}`}
                          >
                            <div className="flex items-center gap-1">
                              {isBroken && <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />}
                              <span className="text-xs text-white truncate font-medium">{clip.name}</span>
                            </div>
                            <span className="text-xs text-white/50 block">{formatTime(clip.duration || 0)}</span>
                            {isBroken && <span className="text-xs text-amber-400/80 block truncate">unavailable</span>}
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── SCRIPT TAB ── */}
        {activeTab === 'script' && (
          <div className="h-full overflow-y-auto px-6 py-6">
            {dialogues.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 gap-4">
                <FileText className="w-12 h-12 text-text-secondary/40" />
                <div className="text-center">
                  <p className="text-text-secondary font-medium">No script dialogues saved</p>
                  <p className="text-text-secondary/60 text-sm mt-1">The creator hasn't saved a structured script for this episode yet.</p>
                </div>
              </div>
            ) : (
              <div className="max-w-3xl mx-auto space-y-3">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-white font-syne font-semibold text-lg">{episode?.title}</h3>
                  <span className="text-text-secondary text-sm">{dialogues.length} line{dialogues.length !== 1 ? 's' : ''}</span>
                </div>

                {dialogues.map((d, i) => {
                  const charKey = d.character_id || d.character || '';
                  const colorClass = characterColorMap[charKey] || 'text-white border-white/20 bg-white/5';
                  const charName = d.character_name || d.character || 'Unknown';
                  const lineNum = d.index !== undefined ? d.index + 1 : i + 1;
                  return (
                    <div key={i} className="flex gap-4 group" data-testid={`dialogue-line-${i}`}>
                      {/* Line number */}
                      <div className="w-8 shrink-0 pt-3 text-right">
                        <span className="text-text-secondary/40 text-xs font-mono">{lineNum}</span>
                      </div>

                      {/* Card */}
                      <div className="flex-1 bg-charcoal/60 border border-white/5 rounded-lg p-4 hover:border-white/10 transition-colors">
                        <div className="flex items-center gap-3 mb-2">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${colorClass}`}>
                            {charName}
                          </span>
                          {d.voice_id && (
                            <span className="text-text-secondary/50 text-xs font-mono">{d.voice_id}</span>
                          )}
                          {d.director_notes && (
                            <span className="text-amber-400/70 text-xs italic truncate max-w-xs">[{d.director_notes}]</span>
                          )}
                        </div>
                        <p className="text-white/90 text-sm leading-relaxed">{d.text}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AdminProjectViewer;
