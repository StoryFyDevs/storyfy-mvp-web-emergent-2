import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Shield, LogOut, ArrowLeft, Volume2, VolumeX, Music, Mic2, Zap, ZoomIn, ZoomOut, Eye, Play, Pause, Square, SkipBack } from 'lucide-react';
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

function AdminProjectViewer() {
  const { episodeId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [timelineTime, setTimelineTime] = useState(0);
  const [masterVolume, setMasterVolume] = useState(0.75);
  const [loadingAudio, setLoadingAudio] = useState(false);

  // Refs for Web Audio API
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
    return () => {
      if (isPlayingRef.current) stopPlayback();
    };
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

  const project = data?.project_state || {};
  const tracks = project.tracks || [];
  const duration = project.duration || 60;
  const pps = PIXELS_PER_SECOND * zoom;
  const timelineWidth = duration * pps;
  const playheadPosition = timelineTime * pps;

  // Audio context
  const ensureAudioContext = useCallback(async () => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioContextRef.current.state === 'suspended') {
      await audioContextRef.current.resume();
    }
    return audioContextRef.current;
  }, []);

  // Load audio buffer for a clip
  const loadAudioBuffer = useCallback(async (clip) => {
    if (!clip?.url) return null;
    if (audioBuffersRef.current[clip.id]) return audioBuffersRef.current[clip.id];
    const ctx = await ensureAudioContext();
    try {
      let arrayBuffer;
      if (clip.url.startsWith('data:')) {
        const base64 = clip.url.split(',')[1];
        const bin = atob(base64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        arrayBuffer = bytes.buffer;
      } else {
        const response = await fetch(clip.url);
        arrayBuffer = await response.arrayBuffer();
      }
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      audioBuffersRef.current[clip.id] = audioBuffer;
      return audioBuffer;
    } catch (err) {
      console.error(`Failed to load audio for ${clip.id}:`, err);
      return null;
    }
  }, [ensureAudioContext]);

  // Preload all clips
  const preloadAllClips = useCallback(async () => {
    setLoadingAudio(true);
    const allClips = tracks.flatMap(t => t.clips || []);
    await Promise.all(allClips.map(c => loadAudioBuffer(c)));
    setLoadingAudio(false);
  }, [tracks, loadAudioBuffer]);

  // Schedule a clip for playback
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

  // Start playback
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

  // Stop playback
  const stopPlayback = useCallback(() => {
    setIsPlaying(false);
    isPlayingRef.current = false;
    Object.values(audioSourcesRef.current).forEach(s => { try { s.stop(); } catch {} });
    audioSourcesRef.current = {};
    gainNodesRef.current = {};
    if (animationFrameRef.current) { cancelAnimationFrame(animationFrameRef.current); animationFrameRef.current = null; }
  }, []);

  // Play/Pause toggle
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

  // Seek on timeline click
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

  // Time ruler markers
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

  const clipColor = (type) => {
    if (type === 'music') return 'from-warm-gold/30 to-warm-gold/10 border-warm-gold/50';
    if (type === 'sfx') return 'from-sunset-orange/30 to-sunset-orange/10 border-sunset-orange/50';
    return 'from-neon-cyan/30 to-neon-cyan/10 border-neon-cyan/50';
  };

  if (loading) {
    return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-neon-cyan font-space">Loading project...</div></div>;
  }
  if (!data) {
    return <div className="min-h-screen bg-obsidian flex items-center justify-center"><div className="text-text-secondary">Project not found</div></div>;
  }

  const { episode, story, creator_name } = data;
  const totalClips = tracks.reduce((sum, t) => sum + (t.clips?.length || 0), 0);

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
      <div className="border-b border-white/10 bg-charcoal px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" className="text-text-secondary hover:text-white" onClick={() => navigate(`/admin-access/stories/${story?.story_id}`)} data-testid="back-to-story">
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <div className="border-l border-white/10 pl-4">
              <h2 className="text-white font-medium text-sm">{episode?.title}</h2>
              <p className="text-text-secondary text-xs">{story?.title} by {creator_name}</p>
            </div>
          </div>

          {/* Transport Controls */}
          <div className="flex items-center gap-3">
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

            {/* Volume */}
            <div className="flex items-center gap-2 w-28">
              <Volume2 className="w-3.5 h-3.5 text-text-secondary shrink-0" />
              <Slider
                value={[masterVolume]}
                onValueChange={([v]) => setMasterVolume(v)}
                min={0} max={1} step={0.01}
                className="w-full"
                data-testid="master-volume"
              />
            </div>

            <div className="flex items-center gap-1 bg-electric-purple/15 border border-electric-purple/30 rounded-full px-3 py-1">
              <Eye className="w-3.5 h-3.5 text-electric-purple" />
              <span className="text-electric-purple text-xs font-medium">Read-Only</span>
            </div>
            <div className="text-xs text-text-secondary font-mono">v{project.version || 0} | {tracks.length}T {totalClips}C</div>
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

      {/* Timeline */}
      <div className="flex-1 flex overflow-hidden">
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
              style={{
                left: `${playheadPosition}px`,
                height: '100%',
                zIndex: 50,
                boxShadow: '0 0 20px rgba(0, 240, 255, 0.9), 0 0 8px rgba(0, 240, 255, 1)',
                transition: isPlaying ? 'none' : 'left 0.05s linear'
              }}
              data-testid="playhead"
            >
              <div className="absolute top-0 left-1/2 -translate-x-1/2 flex flex-col items-center -mt-1 z-50">
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
                    return (
                      <div
                        key={clip.id}
                        className={`absolute top-2 h-16 bg-gradient-to-r ${clipColor(track.type)} border rounded-sm px-2 py-1`}
                        style={{ left: `${clipLeft}px`, width: `${clipWidth}px` }}
                        title={`${clip.name}\nStart: ${formatTime(clip.start || 0)}\nDuration: ${formatTime(clip.duration || 0)}`}
                        data-testid={`viewer-clip-${clip.id}`}
                      >
                        <span className="text-xs text-white truncate block font-medium">{clip.name}</span>
                        <span className="text-xs text-white/50 block">{formatTime(clip.duration || 0)}</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdminProjectViewer;
