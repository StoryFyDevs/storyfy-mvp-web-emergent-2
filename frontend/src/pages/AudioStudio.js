import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import { useStudio } from '../contexts/StudioContext';
import { Button } from '../components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Slider } from '../components/ui/slider';
import { Plus, Upload, Play, Pause, Square, Volume2, Mic2, Music, X, Trash2, SkipBack, Scissors, Copy, ZoomIn, ZoomOut, Save, Bug, Edit3, AlertCircle, Check, Lock, Download } from 'lucide-react';
import { toast } from 'sonner';

// ============================================================================
// PROFESSIONAL DAW TIMELINE ENGINE
// Single Source of Truth: TIME IN SECONDS (floating point precision)
// ============================================================================

// Constants for timeline configuration
const DEFAULT_PIXELS_PER_SECOND = 50; // Base pixels per second at zoom 1.0
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4.0;
const TIMELINE_PADDING = 192; // Track controls width in pixels
const SNAP_THRESHOLD = 0.1; // Snap to grid threshold in seconds

function AudioStudio() {
  const { storyId } = useParams();
  const { story } = useOutletContext();
  const {
    episodes, setEpisodes, refreshEpisodes,
    characters,
    selectedEpisode, setSelectedEpisode,
    setIsLoadingEpisode,
    setIsProjectDirty,
    requestEpisodeSwitch,
    registerSaveCallback,
  } = useStudio();

  // ========== CORE STATE ==========
  const [audioAssets, setAudioAssets] = useState([]);
  
  // Track state
  const [tracks, setTracks] = useState([
    { id: 'voice-1', name: 'Voice Track 1', type: 'voice', clips: [], volume: 0.8, muted: false, solo: false },
    { id: 'music-1', name: 'Background Music', type: 'music', clips: [], volume: 0.5, muted: false, solo: false },
    { id: 'sfx-1', name: 'Sound Effects', type: 'sfx', clips: [], volume: 0.7, muted: false, solo: false }
  ]);
  
  // ========== TIMELINE STATE - SINGLE SOURCE OF TRUTH ==========
  const [timelineTime, setTimelineTime] = useState(0); // Current time in seconds (THE source of truth)
  const [timelineDuration, setTimelineDuration] = useState(60); // Total duration in seconds
  const [zoom, setZoom] = useState(1); // Zoom multiplier
  const [isPlaying, setIsPlaying] = useState(false);
  const [masterVolume, setMasterVolume] = useState(0.75);
  
  // UI State
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showAddTrackDialog, setShowAddTrackDialog] = useState(false);
  const [showDebugOverlay, setShowDebugOverlay] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [newTrackName, setNewTrackName] = useState('');
  const [newTrackType, setNewTrackType] = useState('voice');
  const [selectedClip, setSelectedClip] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);
  
  // Render & Lock state
  const [isRendering, setIsRendering] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  
  // ========== PROJECT VERSIONING STATE (Critical for persistence) ==========
  const [projectVersion, setProjectVersion] = useState(0);
  const [isDirty, setIsDirty] = useState(false); // Track unsaved changes
  const [scrollLeft, setScrollLeft] = useState(0); // For horizontal scroll tracking
  
  // Drag state - Enhanced for cross-track dragging
  const [isDraggingClip, setIsDraggingClip] = useState(false);
  const [draggedClip, setDraggedClip] = useState(null);
  const [dragStartX, setDragStartX] = useState(0);
  const [dragStartY, setDragStartY] = useState(0);
  const [dragStartTime, setDragStartTime] = useState(0);
  const [dragTargetTrackId, setDragTargetTrackId] = useState(null);
  const [dragGhostPosition, setDragGhostPosition] = useState({ x: 0, y: 0 });
  
  // Clip renaming state
  const [editingClipId, setEditingClipId] = useState(null);
  const [editingClipName, setEditingClipName] = useState('');
  const clipNameInputRef = useRef(null);
  
  // Debug state
  const [debugInfo, setDebugInfo] = useState({
    timelineTime: 0,
    playheadPx: 0,
    lastClickTime: 0,
    activeClips: [],
    audioContextState: 'suspended',
    scrollLeft: 0,
    projectVersion: 0,
    isDirty: false
  });
  
  // ========== REFS FOR HIGH-PRECISION TIMING ==========
  const audioContextRef = useRef(null);
  const audioBuffersRef = useRef({}); // Decoded audio buffers for Web Audio API
  const audioSourcesRef = useRef({}); // Active audio source nodes
  const gainNodesRef = useRef({}); // Gain nodes for volume control
  const playbackStartTimeRef = useRef(0); // AudioContext time when playback started
  const playbackOffsetRef = useRef(0); // Timeline offset when playback started
  const animationFrameRef = useRef(null);
  const isPlayingRef = useRef(false);
  const timelineContainerRef = useRef(null);
  const tracksContainerRef = useRef(null);
  const trackRefs = useRef({}); // Store refs to track elements for cross-track drag
  const dragAnimationRef = useRef(null); // requestAnimationFrame for drag updates
  const timelineViewportRef = useRef(null); // For horizontal scrolling
  const saveTimeoutRef = useRef(null); // For debounced auto-save
  const lastSavedStateRef = useRef(null); // Track last saved state to prevent duplicate saves
  
  // Loading state
  const loadingRef = useRef(false);
  const prevEpisodeIdRef = useRef(null);
  
  // Track height constant for cross-track dragging
  const TRACK_HEIGHT = 100; // pixels - must match min-h-[100px] on track lanes
  
  // ========== LOCK STATE (Published episodes are immutable) ==========
  const isLocked = selectedEpisode?.isPublished === true;
  
  // ========== COMPUTED VALUES ==========
  // Pixels per second - THE key value for all positioning
  const pixelsPerSecond = useMemo(() => DEFAULT_PIXELS_PER_SECOND * zoom, [zoom]);
  
  // Timeline width in pixels
  const timelineWidth = useMemo(() => timelineDuration * pixelsPerSecond, [timelineDuration, pixelsPerSecond]);
  
  // ========== TIME <-> PIXEL CONVERSIONS ==========
  const timeToPixels = useCallback((timeInSeconds) => {
    return timeInSeconds * pixelsPerSecond;
  }, [pixelsPerSecond]);
  
  const pixelsToTime = useCallback((pixels) => {
    return pixels / pixelsPerSecond;
  }, [pixelsPerSecond]);
  
  // Playhead position in pixels
  const playheadPosition = useMemo(() => {
    return timeToPixels(timelineTime);
  }, [timelineTime, timeToPixels]);
  
  // ========== AUDIO CONTEXT INITIALIZATION ==========
  useEffect(() => {
    // Create AudioContext on mount
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    // Don't close AudioContext on unmount - let it persist for remounting
    // The browser will manage context lifecycle
    return () => {
      // Only stop playback, don't close context
      if (isPlayingRef.current) {
        isPlayingRef.current = false;
        if (animationFrameRef.current) {
          cancelAnimationFrame(animationFrameRef.current);
        }
      }
    };
  }, []);
  
  // Resume or recreate AudioContext on user interaction (required by browsers)
  const ensureAudioContext = useCallback(async () => {
    // Check if context doesn't exist or is closed - create new one
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      console.log('[Audio] Creating new AudioContext');
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    
    // Resume if suspended (browser autoplay policy)
    if (audioContextRef.current.state === 'suspended') {
      console.log('[Audio] Resuming suspended AudioContext');
      await audioContextRef.current.resume();
    }
    
    return audioContextRef.current;
  }, []);
  
  // ========== AUDIO URL RESOLVER ==========
  const resolveAudioUrl = useCallback((url) => {
    if (!url) return null;
    // base64 data URLs — use directly
    if (url.startsWith('data:')) return url;
    // Supabase storage format: storage-file:{file_id}
    if (url.startsWith('nhost-file:')) {
      const fileId = url.replace('nhost-file:', '');
      return `/api/audio/stream-file/${fileId}`;
    }
    // Any other URL — use as-is
    return url;
  }, []);

  // ========== AUDIO BUFFER LOADING (Web Audio API) ==========
  const loadAudioBuffer = useCallback(async (clip) => {
    if (!clip || !clip.url) return null;
    
    // Return cached buffer if exists and clip hasn't changed
    if (audioBuffersRef.current[clip.id]) {
      return audioBuffersRef.current[clip.id];
    }
    
    const ctx = await ensureAudioContext();
    if (!ctx) return null;
    
    const resolvedUrl = resolveAudioUrl(clip.url);
    if (!resolvedUrl) return null;
    
    try {
      let arrayBuffer;
      
      if (resolvedUrl.startsWith('data:')) {
        // Handle base64 data URL
        const base64 = resolvedUrl.split(',')[1];
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        arrayBuffer = bytes.buffer;
      } else {
        // Fetch from URL (backend streaming endpoint or external)
        const response = await fetch(resolvedUrl);
        if (!response.ok) {
          console.warn(`[Audio] Failed to fetch ${clip.id}: HTTP ${response.status}`);
          return null;
        }
        arrayBuffer = await response.arrayBuffer();
        if (!arrayBuffer || arrayBuffer.byteLength === 0) {
          console.warn(`[Audio] Empty response for ${clip.id}`);
          return null;
        }
      }
      
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      audioBuffersRef.current[clip.id] = audioBuffer;
      
      // Update clip duration with actual audio duration
      if (audioBuffer.duration && audioBuffer.duration > 0) {
        clip.originalDuration = audioBuffer.duration;
        if (!clip.duration || clip.duration === 5) {
          clip.duration = audioBuffer.duration;
        }
      }
      
      console.log(`[Audio] Loaded buffer for ${clip.id}: ${audioBuffer.duration.toFixed(3)}s`);
      return audioBuffer;
    } catch (err) {
      console.error(`[Audio] Failed to load buffer for ${clip.id}:`, err);
      // Clear any stale buffer reference
      delete audioBuffersRef.current[clip.id];
      return null;
    }
  }, [ensureAudioContext, resolveAudioUrl]);
  
  // Preload all clip buffers (forces reload for any missing buffers)
  const preloadAllClips = useCallback(async () => {
    const allClips = tracks.flatMap(track => track.clips);
    const results = await Promise.all(allClips.map(async (clip) => {
      // Clear stale buffer if URL changed
      if (audioBuffersRef.current[clip.id] && clip._urlChanged) {
        delete audioBuffersRef.current[clip.id];
        delete clip._urlChanged;
      }
      return loadAudioBuffer(clip);
    }));
    const loaded = results.filter(Boolean).length;
    console.log(`[Audio] Preloaded ${loaded}/${allClips.length} clips`);
  }, [tracks, loadAudioBuffer]);
  
  // ========== HIGH-PRECISION PLAYBACK ENGINE ==========
  const startPlayback = useCallback(async () => {
    const ctx = await ensureAudioContext();
    if (!ctx) return;
    
    // Store the AudioContext time when playback started
    playbackStartTimeRef.current = ctx.currentTime;
    playbackOffsetRef.current = timelineTime;
    
    setIsPlaying(true);
    isPlayingRef.current = true;
    
    // Determine which tracks are active
    const hasSolo = tracks.some(t => t.solo);
    
    // Schedule all clips that should be playing
    tracks.forEach(track => {
      if (track.muted || (hasSolo && !track.solo)) return;
      
      track.clips.forEach(clip => {
        scheduleClipPlayback(ctx, track, clip, timelineTime);
      });
    });
    
    // Start the animation frame loop for UI updates
    const updateLoop = () => {
      if (!isPlayingRef.current) return;
      
      const ctx = audioContextRef.current;
      if (!ctx) return;
      
      // Calculate current timeline time from AudioContext (HIGH PRECISION)
      const elapsed = ctx.currentTime - playbackStartTimeRef.current;
      const newTime = playbackOffsetRef.current + elapsed;
      
      if (newTime >= timelineDuration) {
        stopPlayback();
        setTimelineTime(0);
        return;
      }
      
      setTimelineTime(newTime);
      
      // Update debug info
      if (showDebugOverlay) {
        updateDebugInfo(newTime);
      }
      
      animationFrameRef.current = requestAnimationFrame(updateLoop);
    };
    
    animationFrameRef.current = requestAnimationFrame(updateLoop);
  }, [timelineTime, timelineDuration, tracks, showDebugOverlay, ensureAudioContext]);
  
  // Schedule a single clip for playback using Web Audio API
  const scheduleClipPlayback = useCallback((ctx, track, clip, currentTime) => {
    const buffer = audioBuffersRef.current[clip.id];
    if (!buffer) return;
    
    const clipStart = clip.start || 0;
    const clipDuration = clip.duration || buffer.duration;
    const clipEnd = clipStart + clipDuration;
    const trimStart = clip.trimStart || 0;
    
    // Check if this clip is relevant to current playback position
    if (currentTime >= clipEnd) return; // Already passed
    
    // Create audio source
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    
    // Create gain node for volume control
    const gainNode = ctx.createGain();
    gainNode.gain.value = track.volume * masterVolume;
    
    // Connect: source -> gain -> destination
    source.connect(gainNode);
    gainNode.connect(ctx.destination);
    
    // Calculate when to start this source in AudioContext time
    let when = ctx.currentTime; // When to start (AudioContext time)
    let offset = trimStart; // Where in the buffer to start
    let duration = clipDuration; // How long to play
    
    if (currentTime < clipStart) {
      // Clip hasn't started yet - schedule for future
      const delay = clipStart - currentTime;
      when = ctx.currentTime + delay;
      offset = trimStart;
      duration = clipDuration;
    } else if (currentTime >= clipStart && currentTime < clipEnd) {
      // Currently within clip - start immediately from offset
      when = ctx.currentTime;
      offset = trimStart + (currentTime - clipStart);
      duration = clipEnd - currentTime;
    }
    
    // Ensure we don't exceed buffer bounds
    offset = Math.max(0, Math.min(offset, buffer.duration));
    duration = Math.min(duration, buffer.duration - offset);
    
    if (duration > 0) {
      source.start(when, offset, duration);
      
      // Store references for later control
      const key = `${track.id}-${clip.id}`;
      audioSourcesRef.current[key] = source;
      gainNodesRef.current[key] = gainNode;
      
      // Clean up when done
      source.onended = () => {
        delete audioSourcesRef.current[key];
        delete gainNodesRef.current[key];
      };
      
      console.log(`[Audio] Scheduled ${clip.id}: when=${when.toFixed(3)}, offset=${offset.toFixed(3)}, duration=${duration.toFixed(3)}`);
    }
  }, [masterVolume]);
  
  // Stop all playback
  const stopPlayback = useCallback(() => {
    setIsPlaying(false);
    isPlayingRef.current = false;
    
    // Stop all active sources
    Object.values(audioSourcesRef.current).forEach(source => {
      try {
        source.stop();
      } catch (e) {
        // Source may have already stopped
      }
    });
    
    // Clear references
    audioSourcesRef.current = {};
    gainNodesRef.current = {};
    
    // Cancel animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  }, []);
  
  // Handle play/pause toggle
  const handlePlayPause = useCallback(async () => {
    if (isPlaying) {
      stopPlayback();
    } else {
      const hasClips = tracks.some(track => track.clips.length > 0);
      if (!hasClips) {
        toast.error('No audio clips to play');
        return;
      }
      
      // Preload buffers before playing
      await preloadAllClips();
      startPlayback();
    }
  }, [isPlaying, tracks, stopPlayback, startPlayback, preloadAllClips]);
  
  // Handle stop (reset to beginning)
  const handleStop = useCallback(() => {
    stopPlayback();
    setTimelineTime(0);
    // Update debug info
    setDebugInfo(prev => ({
      ...prev,
      timelineTime: 0,
      playheadPx: 0
    }));
  }, [stopPlayback]);
  
  // ========== SEEK FUNCTIONALITY (CRITICAL FOR SYNC) ==========
  const seekToTime = useCallback(async (newTime) => {
    // Clamp time to valid range
    const clampedTime = Math.max(0, Math.min(newTime, timelineDuration));
    
    const wasPlaying = isPlaying;
    
    // Always stop current playback first
    if (wasPlaying) {
      stopPlayback();
    }
    
    // Update timeline time immediately
    setTimelineTime(clampedTime);
    
    // Update debug info immediately for responsive feedback
    setDebugInfo(prev => ({
      ...prev,
      timelineTime: clampedTime,
      playheadPx: clampedTime * pixelsPerSecond
    }));
    
    // Restart playback from new position if was playing
    if (wasPlaying) {
      // Small delay to ensure state is updated
      await new Promise(resolve => setTimeout(resolve, 10));
      startPlayback();
    }
  }, [isPlaying, timelineDuration, stopPlayback, startPlayback, pixelsPerSecond]);
  
  // Handle timeline click for seeking - FIXED with scroll offset
  const handleTimelineClick = useCallback((e) => {
    const container = timelineContainerRef.current;
    const viewport = timelineViewportRef.current;
    if (!container) return;
    
    const rect = container.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    // Add scrollLeft offset for accurate time calculation
    const currentScrollLeft = viewport?.scrollLeft || 0;
    const clickTime = pixelsToTime(clickX + currentScrollLeft);
    
    // Update debug info
    setDebugInfo(prev => ({
      ...prev,
      lastClickTime: clickTime,
      lastClickX: clickX,
      scrollLeft: currentScrollLeft
    }));
    
    seekToTime(clickTime);
  }, [pixelsToTime, seekToTime]);
  
  // ========== HORIZONTAL SCROLL HANDLING ==========
  const handleTimelineScroll = useCallback((e) => {
    const newScrollLeft = e.target.scrollLeft;
    setScrollLeft(newScrollLeft);
    
    // Update debug info
    setDebugInfo(prev => ({
      ...prev,
      scrollLeft: newScrollLeft
    }));
  }, []);
  
  // Auto-scroll when playhead approaches edge during playback
  useEffect(() => {
    if (!isPlaying || !timelineViewportRef.current) return;
    
    const viewport = timelineViewportRef.current;
    const viewportWidth = viewport.clientWidth;
    const playheadScreenPos = playheadPosition - viewport.scrollLeft;
    
    // Auto-scroll when playhead is within 100px of right edge
    if (playheadScreenPos > viewportWidth - 100) {
      viewport.scrollLeft = playheadPosition - viewportWidth + 200;
    }
  }, [isPlaying, playheadPosition]);
  
  // ========== VOLUME CONTROL ==========
  // Update gain nodes in real-time when volume changes
  useEffect(() => {
    const hasSolo = tracks.some(t => t.solo);
    
    tracks.forEach(track => {
      track.clips.forEach(clip => {
        const key = `${track.id}-${clip.id}`;
        const gainNode = gainNodesRef.current[key];
        if (gainNode) {
          const shouldMute = track.muted || (hasSolo && !track.solo);
          gainNode.gain.value = shouldMute ? 0 : track.volume * masterVolume;
        }
      });
    });
  }, [tracks, masterVolume]);
  
  // ========== DEBUG OVERLAY ==========
  const updateDebugInfo = useCallback((time) => {
    const ctx = audioContextRef.current;
    setDebugInfo({
      timelineTime: time,
      playheadPx: timeToPixels(time),
      lastClickTime: debugInfo.lastClickTime,
      activeClips: Object.keys(audioSourcesRef.current),
      audioContextState: ctx?.state || 'none',
      audioContextTime: ctx?.currentTime || 0,
      pixelsPerSecond: pixelsPerSecond,
      scrollLeft: scrollLeft,
      projectVersion: projectVersion,
      isDirty: isDirty
    });
  }, [timeToPixels, debugInfo.lastClickTime, pixelsPerSecond, scrollLeft, projectVersion, isDirty]);
  
  // ========== TIME FORMATTING ==========
  const formatTime = useCallback((seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    const ms = Math.floor((seconds % 1) * 1000);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
  }, []);
  
  const formatTimeShort = useCallback((seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }, []);
  
  // ========== ZOOM CONTROL ==========
  const handleZoomIn = useCallback(() => {
    setZoom(prev => Math.min(prev + 0.25, MAX_ZOOM));
    setIsDirty(true);
  }, []);
  
  const handleZoomOut = useCallback(() => {
    setZoom(prev => Math.max(prev - 0.25, MIN_ZOOM));
    setIsDirty(true);
  }, []);
  
  // ========== CLIP MANAGEMENT ==========
  const addClipToTrack = useCallback((trackId, clip) => {
    setTracks(prev => prev.map(track => 
      track.id === trackId 
        ? { ...track, clips: [...track.clips, clip] }
        : track
    ));
    setIsDirty(true);
  }, []);
  
  const removeClipFromTrack = useCallback((trackId, clipId) => {
    // Clean up audio resources
    delete audioBuffersRef.current[clipId];
    const key = `${trackId}-${clipId}`;
    if (audioSourcesRef.current[key]) {
      try {
        audioSourcesRef.current[key].stop();
      } catch (e) {}
      delete audioSourcesRef.current[key];
    }
    delete gainNodesRef.current[key];
    
    setTracks(prev => prev.map(track => 
      track.id === trackId 
        ? { ...track, clips: track.clips.filter(c => c.id !== clipId) }
        : track
    ));
    
    if (selectedClip?.id === clipId) {
      setSelectedClip(null);
    }
    setIsDirty(true);
  }, [selectedClip]);
  
  const updateClip = useCallback((trackId, clipId, updates) => {
    setTracks(prev => prev.map(track => 
      track.id === trackId
        ? {
            ...track,
            clips: track.clips.map(clip =>
              clip.id === clipId ? { ...clip, ...updates } : clip
            )
          }
        : track
    ));
    
    if (selectedClip?.id === clipId) {
      setSelectedClip(prev => ({ ...prev, ...updates }));
    }
    setIsDirty(true);
  }, [selectedClip]);
  
  // ========== CLIP RENAMING SYSTEM ==========
  const startRenamingClip = useCallback((clipId, currentName) => {
    setEditingClipId(clipId);
    setEditingClipName(currentName);
    // Focus input on next render
    setTimeout(() => {
      if (clipNameInputRef.current) {
        clipNameInputRef.current.focus();
        clipNameInputRef.current.select();
      }
    }, 10);
  }, []);
  
  const finishRenamingClip = useCallback((trackId, clipId) => {
    const trimmedName = editingClipName.trim();
    
    // Validation
    if (!trimmedName) {
      toast.error('Clip name cannot be empty');
      setEditingClipId(null);
      return;
    }
    
    // Max length validation
    const finalName = trimmedName.substring(0, 50);
    
    // Update the clip name
    updateClip(trackId, clipId, { name: finalName });
    
    setEditingClipId(null);
    setEditingClipName('');
    toast.success('Clip renamed');
  }, [editingClipName, updateClip]);
  
  const cancelRenamingClip = useCallback(() => {
    setEditingClipId(null);
    setEditingClipName('');
  }, []);
  
  const handleClipNameKeyDown = useCallback((e, trackId, clipId) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      finishRenamingClip(trackId, clipId);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelRenamingClip();
    }
  }, [finishRenamingClip, cancelRenamingClip]);
  
  const handleClipDoubleClick = useCallback((e, clip) => {
    e.stopPropagation();
    startRenamingClip(clip.id, clip.name);
  }, [startRenamingClip]);
  
  // ========== CROSS-TRACK CLIP MOVEMENT ==========
  const moveClipToTrack = useCallback((sourceTrackId, targetTrackId, clipId, newStartTime) => {
    if (sourceTrackId === targetTrackId) {
      // Same track - just update start time
      updateClip(sourceTrackId, clipId, { start: Math.max(0, newStartTime) });
      return;
    }
    
    // Find the clip in source track
    const sourceTrack = tracks.find(t => t.id === sourceTrackId);
    const clip = sourceTrack?.clips.find(c => c.id === clipId);
    
    if (!clip) return;
    
    // Create new clip for target track
    const movedClip = {
      ...clip,
      start: Math.max(0, newStartTime)
    };
    
    // Remove from source and add to target
    setTracks(prev => prev.map(track => {
      if (track.id === sourceTrackId) {
        return { ...track, clips: track.clips.filter(c => c.id !== clipId) };
      }
      if (track.id === targetTrackId) {
        return { ...track, clips: [...track.clips, movedClip] };
      }
      return track;
    }));
    
    // Update selected clip reference if needed
    if (selectedClip?.id === clipId) {
      setSelectedClip({ ...movedClip, trackId: targetTrackId });
    }
    
    setIsDirty(true);
    toast.success(`Moved clip to ${tracks.find(t => t.id === targetTrackId)?.name || 'track'}`);
  }, [tracks, selectedClip, updateClip]);
  
  const duplicateClip = useCallback((trackId, clip) => {
    const newClip = {
      ...clip,
      id: `clip-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      start: clip.start + clip.duration + 0.5
    };
    addClipToTrack(trackId, newClip);
    toast.success('Clip duplicated');
  }, [addClipToTrack]);
  
  const splitClip = useCallback((trackId, clip) => {
    const splitPoint = timelineTime - clip.start;
    
    if (splitPoint <= 0 || splitPoint >= clip.duration) {
      toast.error('Position playhead within clip to split');
      return;
    }
    
    const clip1 = {
      ...clip,
      id: `clip-${Date.now()}-1`,
      duration: splitPoint,
      trimEnd: (clip.trimStart || 0) + splitPoint
    };
    
    const clip2 = {
      ...clip,
      id: `clip-${Date.now()}-2`,
      start: clip.start + splitPoint,
      duration: clip.duration - splitPoint,
      trimStart: (clip.trimStart || 0) + splitPoint
    };
    
    setTracks(prev => prev.map(track =>
      track.id === trackId
        ? {
            ...track,
            clips: track.clips.filter(c => c.id !== clip.id).concat([clip1, clip2])
          }
        : track
    ));
    
    setIsDirty(true);
    toast.success('Clip split at playhead');
  }, [timelineTime]);
  
  // ========== TRACK MANAGEMENT ==========
  const updateTrackVolume = useCallback((trackId, volume) => {
    setTracks(prev => prev.map(track => 
      track.id === trackId ? { ...track, volume } : track
    ));
    setIsDirty(true);
  }, []);
  
  const toggleTrackMute = useCallback((trackId) => {
    setTracks(prev => prev.map(track => 
      track.id === trackId ? { ...track, muted: !track.muted } : track
    ));
    setIsDirty(true);
  }, []);
  
  const toggleTrackSolo = useCallback((trackId) => {
    setTracks(prev => prev.map(track => 
      track.id === trackId ? { ...track, solo: !track.solo } : track
    ));
  }, []);
  
  const addNewTrack = useCallback(() => {
    if (!newTrackName) {
      toast.error('Please enter a track name');
      return;
    }
    
    const newTrack = {
      id: `track-${Date.now()}`,
      name: newTrackName,
      type: newTrackType,
      clips: [],
      volume: 0.8,
      muted: false,
      solo: false
    };
    
    setTracks(prev => [...prev, newTrack]);
    setShowAddTrackDialog(false);
    setNewTrackName('');
    toast.success('Track added');
  }, [newTrackName, newTrackType]);
  
  const deleteTrack = useCallback((trackId) => {
    if (tracks.length <= 1) {
      toast.error('Cannot delete the last track');
      return;
    }
    
    // Clean up audio resources for all clips in this track
    const track = tracks.find(t => t.id === trackId);
    if (track) {
      track.clips.forEach(clip => {
        delete audioBuffersRef.current[clip.id];
        const key = `${trackId}-${clip.id}`;
        if (audioSourcesRef.current[key]) {
          try {
            audioSourcesRef.current[key].stop();
          } catch (e) {}
          delete audioSourcesRef.current[key];
        }
        delete gainNodesRef.current[key];
      });
    }
    
    setTracks(prev => prev.filter(t => t.id !== trackId));
    toast.success('Track deleted');
  }, [tracks]);
  
  // ========== CROSS-TRACK CLIP DRAGGING SYSTEM ==========
  // Detect which track is under the cursor based on Y position
  const getTrackAtPosition = useCallback((clientY) => {
    const container = tracksContainerRef.current;
    if (!container) return null;
    
    const containerRect = container.getBoundingClientRect();
    const relativeY = clientY - containerRect.top;
    
    // Find track based on Y position
    for (let i = 0; i < tracks.length; i++) {
      const trackElement = trackRefs.current[tracks[i].id];
      if (trackElement) {
        const trackRect = trackElement.getBoundingClientRect();
        const trackTop = trackRect.top - containerRect.top;
        const trackBottom = trackTop + trackRect.height;
        
        if (relativeY >= trackTop && relativeY < trackBottom) {
          return tracks[i].id;
        }
      }
    }
    
    // Fallback: calculate based on index
    const trackIndex = Math.floor(relativeY / (TRACK_HEIGHT + 8)); // 8px is the gap
    if (trackIndex >= 0 && trackIndex < tracks.length) {
      return tracks[trackIndex].id;
    }
    
    return null;
  }, [tracks]);
  
  const handleClipMouseDown = useCallback((e, trackId, clip) => {
    // Don't start drag if we're renaming
    if (editingClipId === clip.id) return;
    
    e.stopPropagation();
    e.preventDefault();
    
    setIsDraggingClip(true);
    setDraggedClip({ trackId, clip });
    setDragStartX(e.clientX);
    setDragStartY(e.clientY);
    setDragStartTime(clip.start);
    setDragTargetTrackId(trackId);
    setDragGhostPosition({ x: e.clientX, y: e.clientY });
    setSelectedClip({ ...clip, trackId });
    
    // Add grabbing cursor to body
    document.body.style.cursor = 'grabbing';
  }, [editingClipId]);
  
  const handleClipMouseMove = useCallback((e) => {
    if (!isDraggingClip || !draggedClip) return;
    
    // Use requestAnimationFrame for smooth updates
    if (dragAnimationRef.current) {
      cancelAnimationFrame(dragAnimationRef.current);
    }
    
    dragAnimationRef.current = requestAnimationFrame(() => {
      // Calculate new start time from X movement
      const deltaX = e.clientX - dragStartX;
      const deltaTime = pixelsToTime(deltaX);
      let newStart = Math.max(0, dragStartTime + deltaTime);
      
      // Clamp to timeline duration
      newStart = Math.min(newStart, timelineDuration - draggedClip.clip.duration);
      
      // Detect target track from Y position
      const targetTrackId = getTrackAtPosition(e.clientY);
      
      // Update ghost position for visual feedback
      setDragGhostPosition({ x: e.clientX, y: e.clientY });
      
      // Update target track highlight
      if (targetTrackId && targetTrackId !== dragTargetTrackId) {
        setDragTargetTrackId(targetTrackId);
      }
      
      // Update clip position in current track (visual preview)
      updateClip(draggedClip.trackId, draggedClip.clip.id, { start: newStart });
    });
  }, [isDraggingClip, draggedClip, dragStartX, dragStartTime, pixelsToTime, timelineDuration, getTrackAtPosition, dragTargetTrackId, updateClip]);
  
  const handleClipMouseUp = useCallback((e) => {
    if (!isDraggingClip || !draggedClip) {
      setIsDraggingClip(false);
      setDraggedClip(null);
      return;
    }
    
    // Cancel any pending animation frame
    if (dragAnimationRef.current) {
      cancelAnimationFrame(dragAnimationRef.current);
    }
    
    // Restore cursor
    document.body.style.cursor = '';
    
    // Calculate final position
    const deltaX = e.clientX - dragStartX;
    const deltaTime = pixelsToTime(deltaX);
    let newStart = Math.max(0, dragStartTime + deltaTime);
    newStart = Math.min(newStart, timelineDuration - draggedClip.clip.duration);
    
    // Detect final target track
    const targetTrackId = getTrackAtPosition(e.clientY) || draggedClip.trackId;
    
    // Move clip to new position/track
    if (targetTrackId !== draggedClip.trackId) {
      // Cross-track move
      moveClipToTrack(draggedClip.trackId, targetTrackId, draggedClip.clip.id, newStart);
    } else {
      // Same track, just update time
      updateClip(draggedClip.trackId, draggedClip.clip.id, { start: newStart });
      toast.success('Clip repositioned');
    }
    
    // Reset drag state
    setIsDraggingClip(false);
    setDraggedClip(null);
    setDragTargetTrackId(null);
    setDragGhostPosition({ x: 0, y: 0 });
  }, [isDraggingClip, draggedClip, dragStartX, dragStartTime, pixelsToTime, timelineDuration, getTrackAtPosition, moveClipToTrack, updateClip]);
  
  // Global mouse move/up handlers for dragging
  useEffect(() => {
    if (isDraggingClip) {
      document.addEventListener('mousemove', handleClipMouseMove);
      document.addEventListener('mouseup', handleClipMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleClipMouseMove);
        document.removeEventListener('mouseup', handleClipMouseUp);
        document.body.style.cursor = '';
      };
    }
  }, [isDraggingClip, handleClipMouseMove, handleClipMouseUp]);
  
  // ========== DATA FETCHING ==========
  const fetchAudioAssets = useCallback(async () => {
    if (!selectedEpisode) return;
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/audio/assets/${storyId}`, {
        credentials: 'include',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` }
      });
      if (!response.ok) throw new Error('Failed to fetch assets');
      const data = await response.json();
      setAudioAssets(data);
    } catch (error) {
      console.error('Failed to load audio assets');
    }
  }, [storyId, selectedEpisode]);
  
  const createEpisode = useCallback(async (title = 'Episode 1') => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/episodes`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
        },
        body: JSON.stringify({
          title,
          story_id: storyId,
          order: episodes.length + 1,
          script: ''
        })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create episode');
      }
      
      const newEpisode = await response.json();
      await refreshEpisodes();
      setSelectedEpisode(newEpisode);
      toast.success('Episode created!');
      return newEpisode;
    } catch (error) {
      toast.error(error.message || 'Failed to create episode');
      return null;
    }
  }, [storyId, episodes.length]);
  
  // ========== PROJECT SAVE/LOAD ==========
  const loadProjectStateAndPendingClips = useCallback(async () => {
    if (!selectedEpisode) return;

    const defaultTracks = [
      { id: 'voice-1', name: 'Voice Track 1', type: 'voice', clips: [], volume: 0.8, muted: false, solo: false },
      { id: 'music-1', name: 'Background Music', type: 'music', clips: [], volume: 0.5, muted: false, solo: false },
      { id: 'sfx-1', name: 'Sound Effects', type: 'sfx', clips: [], volume: 0.7, muted: false, solo: false }
    ];

    try {
      const response = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/episodes/${selectedEpisode.episode_id}/project-state`,
        {
          credentials: 'include',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
          }
        }
      );

      let loadedTracks = [...defaultTracks];
      let projectLoaded = false;
      let serverVersion = 0;

      if (response.ok) {
        const projectState = await response.json();
        console.log('[Project] Loaded state:', projectState ? 'Found' : 'Empty');
        
        // Extract version from server
        serverVersion = projectState?.version || 0;
        console.log(`[Project] Server version: ${serverVersion}`);

        if (projectState && projectState.tracks && projectState.tracks.length > 0) {
          const loadedClipCount = projectState.tracks.reduce((sum, t) => sum + (t.clips?.length || 0), 0);
          console.log(`[Project] Found ${loadedClipCount} saved clips at v${serverVersion}`);
          
          // Log clip positions for debugging
          projectState.tracks.forEach(track => {
            (track.clips || []).forEach(clip => {
              console.log(`[Project] Loaded clip ${clip.id}: track=${track.id}, start=${clip.start}s`);
            });
          });

          // Merge saved tracks with default tracks - ensure all default tracks exist
          // This prevents losing Background Music and Sound Effects tracks
          loadedTracks = defaultTracks.map((defaultTrack, idx) => {
            // Find matching saved track by ID or fallback by index
            const savedTrack = projectState.tracks.find(t => t.id === defaultTrack.id) 
              || projectState.tracks[idx];
            
            if (savedTrack) {
              return {
                ...defaultTrack,
                ...savedTrack,
                type: savedTrack.type || defaultTrack.type,
                clips: (savedTrack.clips || []).filter(clip => clip && clip.url).map(clip => ({
                  ...clip,
                  url: clip.url
                }))
              };
            }
            // No saved data for this default track - keep defaults
            return { ...defaultTrack };
          });
          
          // Also include any additional tracks from saved state that aren't in defaults
          const additionalTracks = projectState.tracks.filter(savedTrack => 
            !defaultTracks.some(def => def.id === savedTrack.id)
          ).map(track => ({
            ...track,
            clips: (track.clips || []).filter(clip => clip && clip.url).map(clip => ({
              ...clip,
              url: clip.url
            }))
          }));
          
          loadedTracks = [...loadedTracks, ...additionalTracks];

          if (projectState.duration) setTimelineDuration(projectState.duration);
          if (projectState.zoom) setZoom(projectState.zoom);
          if (projectState.masterVolume !== undefined) setMasterVolume(projectState.masterVolume);
          if (projectState.currentTime !== undefined) setTimelineTime(projectState.currentTime);
          setLastSaved(projectState.savedAt ? new Date(projectState.savedAt) : null);
          setProjectVersion(serverVersion);
          projectLoaded = true;
        }
      }

      // Check for removed clips from Script Compiler (deleted dialogues) — scoped to episode
      const removedKey = `removed_clips_${storyId}_${selectedEpisode.episode_id}`;
      const removedRaw = localStorage.getItem(removedKey);
      const removedClipNames = JSON.parse(removedRaw || '[]');
      if (removedClipNames.length > 0) {
        console.log(`[Project] Removing ${removedClipNames.length} deleted dialogue clips`);
        loadedTracks = loadedTracks.map(track => ({
          ...track,
          clips: (track.clips || []).filter(clip => !removedClipNames.includes(clip.name))
        }));
        localStorage.removeItem(removedKey);
      }

      // Check for pending clips from Script Compiler / Voice Generator — scoped to episode
      const pendingClipsKey = `pending_clips_${storyId}_${selectedEpisode.episode_id}`;
      const pendingClipsRaw = localStorage.getItem(pendingClipsKey);
      const pendingData = JSON.parse(pendingClipsRaw || '[]');

      if (pendingData.length > 0) {
        // Determine format: new per-character track format or legacy flat array
        const isPerCharacterFormat = pendingData[0]?.characterName && pendingData[0]?.clips;

        if (isPerCharacterFormat) {
          // New format: array of { characterName, clips: [...] }
          // First, clear any existing script-generated clips (scrclip-*) from all tracks
          // to avoid duplicates on regeneration
          loadedTracks = loadedTracks.map(track => ({
            ...track,
            clips: (track.clips || []).filter(clip => !clip.id?.startsWith('scrclip-'))
          }));

          let totalNewClips = 0;
          const charColors = ['#00F0FF', '#FF6B6B', '#4ECDC4', '#FFE66D', '#A78BFA', '#F97316'];
          let colorIndex = 0;

          // Collect ALL clips across all characters, sorted by dialogueIndex
          const allPendingClips = [];
          for (const trackData of pendingData) {
            for (const clipData of (trackData.clips || [])) {
              allPendingClips.push({
                ...clipData,
                characterName: trackData.characterName || clipData.characterName || 'Unknown',
              });
            }
          }
          // Sort by dialogueIndex for correct script order
          allPendingClips.sort((a, b) => (a.dialogueIndex || 0) - (b.dialogueIndex || 0));

          // Re-calculate sequential timing based on sorted order
          let globalOffset = 0;
          const charColorMap = {};

          for (const clipData of allPendingClips) {
            const charName = clipData.characterName;
            if (!charColorMap[charName]) {
              charColorMap[charName] = charColors[colorIndex % charColors.length];
              colorIndex++;
            }

            // Find or create a track for this character
            let trackIdx = loadedTracks.findIndex(t =>
              t.name === charName || t.name === `${charName} Voice`
            );
            if (trackIdx === -1) {
              loadedTracks.push({
                id: `voice-${charName.toLowerCase().replace(/\s/g, '-')}-${Date.now()}`,
                name: `${charName} Voice`,
                type: 'voice',
                clips: [],
                volume: 0.8,
                muted: false,
                solo: false,
              });
              trackIdx = loadedTracks.length - 1;
            }

            const newClip = {
              id: clipData.id || `scrclip-${Date.now()}-${clipData.dialogueIndex || totalNewClips}`,
              name: clipData.name || `${charName}_${String((clipData.dialogueIndex || 0) + 1).padStart(2, '0')}`,
              url: clipData.url,
              start: clipData.start !== undefined ? clipData.start : globalOffset,
              duration: clipData.duration || 5,
              originalDuration: clipData.duration || 5,
              color: charColorMap[charName],
              characterName: charName,
              text: clipData.text || '',
              type: 'voice',
              trimStart: 0,
              dialogueIndex: clipData.dialogueIndex,
            };

            loadedTracks[trackIdx] = {
              ...loadedTracks[trackIdx],
              clips: [...(loadedTracks[trackIdx].clips || []), newClip],
            };

            globalOffset = newClip.start + newClip.duration + 0.3;
            totalNewClips++;
          }

          localStorage.removeItem(pendingClipsKey);
          setIsDirty(true);
          toast.success(`Added ${totalNewClips} clip(s) across ${Object.keys(charColorMap).length} character track(s)`);
        } else {
          // Legacy flat format: array of clip objects
          console.log(`[Project] Processing ${pendingData.length} pending clips (legacy format)`);

          let voiceTrackIndex = loadedTracks.findIndex(t => 
            t.type === 'voice' || t.name?.toLowerCase().includes('voice')
          );
          if (voiceTrackIndex === -1) voiceTrackIndex = 0;

          const existingClips = loadedTracks[voiceTrackIndex]?.clips || [];
          let maxEndTime = 0;
          existingClips.forEach(clip => {
            const endTime = (clip.start || 0) + (clip.duration || 5);
            if (endTime > maxEndTime) maxEndTime = endTime;
          });

          const newClips = pendingData.map((clipData, index) => ({
            id: clipData.id || `clip-${Date.now()}-${index}`,
            name: clipData.name || `Voice Clip ${index + 1}`,
            url: clipData.url,
            start: maxEndTime + (index * 5),
            duration: clipData.duration || 5,
            originalDuration: clipData.duration || 5,
            color: '#00F0FF',
            characterName: clipData.characterName,
            text: clipData.text,
            type: clipData.type || 'voice',
            trimStart: 0
          }));

          loadedTracks = loadedTracks.map((track, index) => {
            if (index === voiceTrackIndex) {
              return {
                ...track,
                clips: [...(track.clips || []), ...newClips]
              };
            }
            return track;
          });

          localStorage.removeItem(pendingClipsKey);
          setIsDirty(true);
          toast.success(`Added ${pendingData.length} clip(s) from Voice Generator`);
        }
      } else if (projectLoaded) {
        const totalClips = loadedTracks.reduce((sum, t) => sum + t.clips.length, 0);
        toast.success(`Project loaded v${serverVersion} (${totalClips} clips)`);
      }

      // Check for a single-dialogue regeneration replacement
      const replaceKey = `pending_clip_replace_${storyId}_${selectedEpisode.episode_id}`;
      const replaceRaw = localStorage.getItem(replaceKey);
      if (replaceRaw) {
        try {
          const rd = JSON.parse(replaceRaw);
          const { dialogueIndex, url, duration, name, characterName, text } = rd;
          const charColors = ['#00F0FF', '#FF6B6B', '#4ECDC4', '#FFE66D', '#A78BFA', '#F97316'];

          let replaced = false;
          // Find and replace the matching clip by dialogueIndex across all tracks
          loadedTracks = loadedTracks.map(track => {
            const matchIdx = track.clips.findIndex(c => c.dialogueIndex === dialogueIndex);
            if (matchIdx === -1) return track;
            replaced = true;
            const oldClip = track.clips[matchIdx];
            const updatedClip = {
              ...oldClip,
              id: `scrclip-${Date.now()}-${dialogueIndex}`,
              url,
              duration: duration || oldClip.duration,
              originalDuration: duration || oldClip.duration,
              name: name || oldClip.name,
              characterName: characterName || oldClip.characterName,
              text: text || oldClip.text,
            };
            const updatedClips = [...track.clips];
            updatedClips[matchIdx] = updatedClip;
            return { ...track, clips: updatedClips };
          });

          // If no existing clip with that dialogueIndex, append to the right character track
          if (!replaced) {
            const charName = characterName || 'Unknown';
            let trackIdx = loadedTracks.findIndex(t =>
              t.name === charName || t.name === `${charName} Voice`
            );
            if (trackIdx === -1) {
              loadedTracks.push({
                id: `voice-${charName.toLowerCase().replace(/\s/g, '-')}-${Date.now()}`,
                name: `${charName} Voice`,
                type: 'voice',
                clips: [],
                volume: 0.8,
                muted: false,
                solo: false,
              });
              trackIdx = loadedTracks.length - 1;
            }
            const maxEnd = loadedTracks[trackIdx].clips.reduce(
              (m, c) => Math.max(m, (c.start || 0) + (c.duration || 0)), 0
            );
            loadedTracks[trackIdx] = {
              ...loadedTracks[trackIdx],
              clips: [...loadedTracks[trackIdx].clips, {
                id: `scrclip-${Date.now()}-${dialogueIndex}`,
                url,
                duration: duration || 3,
                originalDuration: duration || 3,
                start: maxEnd + 0.3,
                name: name || `${charName}_${String(dialogueIndex + 1).padStart(2, '0')}`,
                characterName: charName,
                text: text || '',
                color: charColors[0],
                type: 'voice',
                trimStart: 0,
                dialogueIndex,
              }],
            };
          }

          localStorage.removeItem(replaceKey);
          setIsDirty(true);
          toast.success(`Dialogue ${dialogueIndex + 1} clip updated in timeline`);
        } catch (e) {
          console.warn('[Project] pending_clip_replace parse error:', e);
          localStorage.removeItem(replaceKey);
        }
      }

      setTracks(loadedTracks);
      setIsDirty(false); // Reset dirty state after load

      // Preload audio buffers for all clips
      const allClips = loadedTracks.flatMap(track => track.clips);
      for (const clip of allClips) {
        if (clip.url) {
          await loadAudioBuffer(clip);
        }
      }

    } catch (error) {
      console.error('[Project] Load error:', error);
    }
  }, [selectedEpisode, storyId, loadAudioBuffer]);
  
  const saveProjectState = useCallback(async (force = false) => {
    if (!selectedEpisode) {
      toast.error('No episode selected');
      return false;
    }
    
    // Skip if not dirty and not forced
    if (!isDirty && !force) {
      console.log('[Project] Skipping save - no changes');
      return true;
    }

    setIsSaving(true);

    try {
      // Increment version for this save
      const newVersion = projectVersion + 1;
      const savedAt = new Date().toISOString();
      
      const projectState = {
        version: newVersion,
        tracks: tracks.map(track => ({
          id: track.id,
          name: track.name,
          type: track.type,
          volume: track.volume,
          muted: track.muted,
          solo: track.solo,
          clips: track.clips.map(clip => ({
            id: clip.id,
            name: clip.name,
            url: clip.url,
            start: clip.start,
            duration: clip.duration,
            originalDuration: clip.originalDuration,
            trimStart: clip.trimStart,
            trimEnd: clip.trimEnd,
            fadeIn: clip.fadeIn,
            fadeOut: clip.fadeOut,
            color: clip.color,
            characterName: clip.characterName,
            text: clip.text,
            type: clip.type
          }))
        })),
        duration: timelineDuration,
        zoom,
        masterVolume,
        currentTime: timelineTime,
        savedAt
      };

      const totalClips = projectState.tracks.reduce((sum, t) => sum + t.clips.length, 0);
      console.log(`[Project] Saving v${newVersion} with ${totalClips} clips`);
      
      // Log clip positions for debugging
      projectState.tracks.forEach(track => {
        track.clips.forEach(clip => {
          console.log(`[Project] Clip ${clip.id}: track=${track.id}, start=${clip.start.toFixed(3)}s`);
        });
      });

      const response = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/episodes/${selectedEpisode.episode_id}/save-project`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
          },
          body: JSON.stringify(projectState)
        }
      );

      // Parse response ONCE
      const responseData = await response.json().catch(() => ({ detail: 'Failed to process response' }));
      
      if (!response.ok) {
        throw new Error(responseData.detail || 'Failed to save project');
      }
      
      // Update version from server response
      setProjectVersion(newVersion);
      setIsDirty(false);
      setLastSaved(new Date(savedAt));
      
      // Store last saved state for comparison
      lastSavedStateRef.current = JSON.stringify(projectState);
      
      console.log(`[Project] Saved successfully v${newVersion}`);
      toast.success(`Project saved v${newVersion} (${totalClips} clips)`);
      return true;
    } catch (error) {
      console.error('[Project] Save error:', error);
      toast.error('Failed to save project');
      return false;
    } finally {
      setIsSaving(false);
    }
  }, [selectedEpisode, tracks, timelineDuration, zoom, masterVolume, timelineTime, projectVersion, isDirty]);
  
  // ========== DEBOUNCED AUTO-SAVE ==========
  useEffect(() => {
    if (!selectedEpisode || !isDirty) return;
    
    // Clear any existing timeout
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    
    // Set new debounced save (2 seconds after last change)
    saveTimeoutRef.current = setTimeout(() => {
      console.log('[Project] Auto-saving...');
      saveProjectState();
    }, 2000);
    
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, [isDirty, selectedEpisode, tracks]); // Only trigger on dirty or track changes
  
  // ========== FILE UPLOAD ==========
  const handleFileUpload = useCallback(async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!selectedEpisode) {
      toast.error('Please select an episode first');
      return;
    }
    
    setUploading(true);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('story_id', storyId);
      formData.append('episode_id', selectedEpisode.episode_id);
      formData.append('asset_type', newTrackType);
      formData.append('name', file.name);
      
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/audio/upload`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
        },
        body: formData
      });
      
      if (!response.ok) throw new Error('Upload failed');
      
      const asset = await response.json();
      setAudioAssets(prev => [...prev, asset]);
      
      // Create audio URL and decode buffer
      const audioUrl = URL.createObjectURL(file);
      
      // Decode to get duration
      const ctx = await ensureAudioContext();
      const arrayBuffer = await file.arrayBuffer();
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      
      const targetTrack = tracks.find(t => t.type === newTrackType);
      if (targetTrack) {
        const lastClipEnd = targetTrack.clips.reduce((max, clip) => {
          const clipEnd = clip.start + clip.duration;
          return clipEnd > max ? clipEnd : max;
        }, 0);
        
        const startPosition = Math.max(lastClipEnd, timelineTime);
        
        const newClip = {
          id: `clip-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          assetId: asset.asset_id,
          name: file.name,
          start: startPosition,
          duration: audioBuffer.duration,
          originalDuration: audioBuffer.duration,
          trimStart: 0,
          trimEnd: audioBuffer.duration,
          fadeIn: 0,
          fadeOut: 0,
          url: audioUrl,
          type: 'uploaded'
        };
        
        // Store buffer for playback
        audioBuffersRef.current[newClip.id] = audioBuffer;
        
        addClipToTrack(targetTrack.id, newClip);
        
        toast.success(`Audio added at ${formatTimeShort(startPosition)}`);
        
        if (audioBuffer.duration + startPosition > timelineDuration) {
          setTimelineDuration(Math.ceil(audioBuffer.duration + startPosition) + 10);
        }
      }
      
      setShowUploadDialog(false);
    } catch (error) {
      console.error('[Upload] Error:', error);
      toast.error('Failed to upload audio');
    } finally {
      setUploading(false);
    }
  }, [selectedEpisode, storyId, newTrackType, tracks, timelineTime, timelineDuration, addClipToTrack, ensureAudioContext, formatTimeShort]);
  
  // ========== EFFECTS ==========

  // Sync isDirty to global project dirty state so StudioContext can intercept navigation
  useEffect(() => {
    setIsProjectDirty(isDirty);
  }, [isDirty, setIsProjectDirty]);

  // Register saveProjectState as the save callback for the unsaved changes modal
  useEffect(() => {
    registerSaveCallback(saveProjectState);
    return () => registerSaveCallback(null);
  }, [registerSaveCallback, saveProjectState]);

  // Browser refresh/close guard
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  // Episode switching — triggers when selectedEpisode changes
  useEffect(() => {
    const currentEpisodeId = selectedEpisode?.episode_id;
    
    if (currentEpisodeId && currentEpisodeId !== prevEpisodeIdRef.current && !loadingRef.current) {
      loadingRef.current = true;
      prevEpisodeIdRef.current = currentEpisodeId;
      
      fetchAudioAssets();
      loadProjectStateAndPendingClips().finally(() => {
        loadingRef.current = false;
        setIsLoadingEpisode(false);
      });
    }
  }, [selectedEpisode?.episode_id, fetchAudioAssets, loadProjectStateAndPendingClips, setIsLoadingEpisode]);
  
  // Auto-save every 30 seconds
  useEffect(() => {
    if (!selectedEpisode) return;

    const autoSaveInterval = setInterval(() => {
      if (tracks.some(t => t.clips.length > 0)) {
        saveProjectState();
      }
    }, 30000);

    return () => clearInterval(autoSaveInterval);
  }, [selectedEpisode, tracks, saveProjectState]);

  // ========== WAV ENCODER ==========
  const audioBufferToWav = useCallback((buffer) => {
    const numChannels = 1; // Mono output
    const sampleRate = buffer.sampleRate;
    const bitDepth = 16;

    // Mix all channels to mono
    const length = buffer.length;
    const mono = new Float32Array(length);
    for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
      const channelData = buffer.getChannelData(ch);
      for (let i = 0; i < length; i++) {
        mono[i] += channelData[i] / buffer.numberOfChannels;
      }
    }

    const dataLength = mono.length * (bitDepth / 8);
    const arrayBuffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(arrayBuffer);

    const writeStr = (offset, str) => {
      for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
    };

    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * (bitDepth / 8), true);
    view.setUint16(32, numChannels * (bitDepth / 8), true);
    view.setUint16(34, bitDepth, true);
    writeStr(36, 'data');
    view.setUint32(40, dataLength, true);

    let offset = 44;
    for (let i = 0; i < mono.length; i++) {
      const s = Math.max(-1, Math.min(1, mono[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      offset += 2;
    }

    return new Blob([arrayBuffer], { type: 'audio/wav' });
  }, []);

  // ========== RENDER & EXPORT FINAL AUDIO ==========
  const renderFinalAudio = useCallback(async () => {
    if (!selectedEpisode || isLocked) return;

    const allClips = tracks.flatMap(t => t.clips.map(c => ({ ...c, trackId: t.id })));
    if (allClips.length === 0) {
      toast.error('No audio clips on the timeline to render');
      return;
    }

    setIsRendering(true);
    setRenderProgress(5);
    toast.info('Rendering final audio...');

    try {
      // 1. Calculate total duration
      let maxEnd = 0;
      for (const clip of allClips) {
        const end = (clip.start || 0) + (clip.duration || 0);
        if (end > maxEnd) maxEnd = end;
      }
      const renderDuration = Math.ceil(maxEnd) + 1;

      // 2. Create OfflineAudioContext
      const sampleRate = 44100;
      const offlineCtx = new OfflineAudioContext(1, sampleRate * renderDuration, sampleRate);
      setRenderProgress(15);

      // 3. Schedule all clips (mirroring the playback engine)
      const hasSolo = tracks.some(t => t.solo);

      for (const track of tracks) {
        if (track.muted || (hasSolo && !track.solo)) continue;

        for (const clip of track.clips) {
          const buffer = audioBuffersRef.current[clip.id];
          if (!buffer) continue;

          const source = offlineCtx.createBufferSource();
          source.buffer = buffer;

          const gainNode = offlineCtx.createGain();
          gainNode.gain.value = track.volume * masterVolume;

          source.connect(gainNode);
          gainNode.connect(offlineCtx.destination);

          const clipStart = clip.start || 0;
          const trimStart = clip.trimStart || 0;
          const clipDuration = Math.min(clip.duration || buffer.duration, buffer.duration - trimStart);

          if (clipDuration > 0) {
            source.start(clipStart, trimStart, clipDuration);
          }
        }
      }

      setRenderProgress(30);

      // 4. Render
      const renderedBuffer = await offlineCtx.startRendering();
      setRenderProgress(60);

      // 5. Encode to WAV
      const wavBlob = audioBufferToWav(renderedBuffer);
      setRenderProgress(70);

      // 6. Chunked upload (512KB chunks)
      const CHUNK_SIZE = 512 * 1024;
      const totalChunks = Math.ceil(wavBlob.size / CHUNK_SIZE);

      for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, wavBlob.size);
        const chunk = wavBlob.slice(start, end);

        const formData = new FormData();
        formData.append('chunk', chunk, `chunk_${i}`);
        formData.append('chunk_index', String(i));
        formData.append('total_chunks', String(totalChunks));

        const res = await fetch(
          `${process.env.REACT_APP_BACKEND_URL}/api/episodes/${selectedEpisode.episode_id}/render/chunk`,
          { method: 'POST', headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` }, body: formData, credentials: 'include' }
        );
        if (!res.ok) throw new Error(`Chunk upload failed at ${i + 1}/${totalChunks}`);

        setRenderProgress(70 + Math.round((i + 1) / totalChunks * 20));
      }

      // 7. Finalize
      const finalRes = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/episodes/${selectedEpisode.episode_id}/render/finalize`,
        {
          method: 'POST', credentials: 'include',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` },
          body: JSON.stringify({ total_chunks: totalChunks, duration: maxEnd })
        }
      );
      // Parse response ONCE
      const result = await finalRes.json().catch(() => ({ detail: 'Failed to process response' }));
      
      if (!finalRes.ok) {
        throw new Error(result.detail || 'Finalize failed');
      }
      setRenderProgress(100);

      // Update local episode state
      setSelectedEpisode(prev => prev ? { ...prev, finalAudioUrl: result.finalAudioUrl, duration: result.duration } : prev);
      setEpisodes(prev => prev.map(ep =>
        ep.episode_id === selectedEpisode.episode_id
          ? { ...ep, finalAudioUrl: result.finalAudioUrl, duration: result.duration }
          : ep
      ));

      toast.success(`Final audio rendered! (${(wavBlob.size / (1024 * 1024)).toFixed(1)} MB, ${maxEnd.toFixed(1)}s)`);
    } catch (error) {
      console.error('[Render] Error:', error);
      toast.error(`Render failed: ${error.message}`);
    } finally {
      setIsRendering(false);
      setRenderProgress(0);
    }
  }, [selectedEpisode, isLocked, tracks, masterVolume, audioBufferToWav]);

  // ========== UNPUBLISH HANDLER ==========
  const handleUnpublishEpisode = useCallback(async () => {
    if (!selectedEpisode) return;
    try {
      const res = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/creator/episodes/${selectedEpisode.episode_id}/unpublish`,
        { method: 'POST', credentials: 'include', headers: { 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` } }
      );
      if (!res.ok) throw new Error('Failed to unpublish');
      const data = await res.json();
      setSelectedEpisode(prev => prev ? { ...prev, isPublished: data.isPublished } : prev);
      setEpisodes(prev => prev.map(ep =>
        ep.episode_id === selectedEpisode.episode_id ? { ...ep, isPublished: data.isPublished } : ep
      ));
      toast.success('Episode unpublished. You can now edit the audio.');
    } catch (error) {
      toast.error('Failed to unpublish episode');
    }
  }, [selectedEpisode]);

  // ========== RENDER UI HELPERS ==========
  // Generate time ruler markers
  const timeRulerMarkers = useMemo(() => {
    const markers = [];
    const interval = zoom >= 2 ? 1 : zoom >= 1 ? 2 : 5; // Adjust interval based on zoom
    
    for (let time = 0; time <= timelineDuration; time += interval) {
      markers.push({
        time,
        position: timeToPixels(time),
        label: formatTimeShort(time),
        isMajor: time % 5 === 0
      });
    }
    return markers;
  }, [timelineDuration, zoom, timeToPixels, formatTimeShort]);
  
  return (
    <div className="h-full flex flex-col bg-obsidian" data-testid="audio-studio">
      {/* Lock Banner */}
      {isLocked && selectedEpisode && (
        <div className="bg-amber-500/10 border-b border-amber-500/30 px-6 py-3 flex items-center justify-between" data-testid="lock-banner">
          <div className="flex items-center gap-3">
            <Lock className="w-5 h-5 text-amber-400" />
            <span className="text-amber-300 font-medium text-sm">
              This episode is published and locked. Unpublish to make changes.
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="border-amber-500/50 text-amber-400 hover:bg-amber-500/10"
            onClick={handleUnpublishEpisode}
            data-testid="lock-banner-unpublish"
          >
            Unpublish Episode
          </Button>
        </div>
      )}

      {/* Render Progress Bar */}
      {isRendering && (
        <div className="bg-charcoal border-b border-neon-cyan/30 px-6 py-2" data-testid="render-progress">
          <div className="flex items-center gap-3">
            <Download className="w-4 h-4 text-neon-cyan animate-pulse" />
            <span className="text-neon-cyan text-sm font-medium">Rendering final audio... {renderProgress}%</span>
            <div className="flex-1 h-2 bg-slate rounded-full overflow-hidden">
              <div className="h-full bg-neon-cyan rounded-full transition-all duration-300" style={{ width: `${renderProgress}%` }} />
            </div>
          </div>
        </div>
      )}

      {/* Debug Overlay */}
      {showDebugOverlay && (
        <div className="fixed top-20 right-4 z-50 bg-black/90 border border-neon-cyan/50 rounded-lg p-4 font-mono text-xs text-white min-w-[320px]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-neon-cyan font-bold">DEBUG MODE</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowDebugOverlay(false)}
              className="h-6 w-6 p-0 text-white/50 hover:text-white"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
          <div className="space-y-1">
            <div>Timeline Time: <span className="text-neon-cyan">{debugInfo.timelineTime?.toFixed(3)}s</span></div>
            <div>Playhead Px: <span className="text-signal-green">{debugInfo.playheadPx?.toFixed(1)}px</span></div>
            <div>Scroll Left: <span className="text-warm-gold">{scrollLeft.toFixed(0)}px</span></div>
            <div>Pixels/Sec: <span className="text-white/70">{pixelsPerSecond.toFixed(1)}</span></div>
            <div>Last Click: <span className="text-neon-purple">{debugInfo.lastClickTime?.toFixed(3)}s</span></div>
            <div>AudioContext: <span className={debugInfo.audioContextState === 'running' ? 'text-signal-green' : 'text-red-400'}>{debugInfo.audioContextState}</span></div>
            <div>Active Clips: <span className="text-neon-cyan">{debugInfo.activeClips?.length || 0}</span></div>
            <div className="pt-2 border-t border-white/10 mt-2">
              <div>Project Version: <span className="text-signal-green">v{projectVersion}</span></div>
              <div>Dirty State: <span className={isDirty ? 'text-warm-gold' : 'text-signal-green'}>{isDirty ? 'UNSAVED' : 'Saved'}</span></div>
              <div className="text-text-secondary">Zoom: {zoom}x</div>
              <div className="text-text-secondary">Duration: {timelineDuration}s</div>
              <div className="text-text-secondary">Width: {timelineWidth.toFixed(0)}px</div>
            </div>
          </div>
        </div>
      )}
      
      {/* Top Toolbar */}
      <div className="border-b border-white/10 bg-charcoal px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Select value={selectedEpisode?.episode_id || ''} onValueChange={async (value) => {
              if (value === 'create-new') {
                await createEpisode(`Episode ${episodes.length + 1}`);
              } else {
                const ep = episodes.find(e => e.episode_id === value);
                if (ep) requestEpisodeSwitch(ep);
              }
            }}>
              <SelectTrigger className="w-64 bg-slate border-white/10 text-white" data-testid="episode-select">
                <SelectValue placeholder="Select Episode" />
              </SelectTrigger>
              <SelectContent className="bg-charcoal border-white/10">
                {episodes.length === 0 ? (
                  <SelectItem value="create-new" className="text-neon-cyan">
                    + Create New Episode
                  </SelectItem>
                ) : (
                  <>
                    {episodes.map((ep) => (
                      <SelectItem key={ep.episode_id} value={ep.episode_id}>
                        {ep.title}
                      </SelectItem>
                    ))}
                    <SelectItem value="create-new" className="text-neon-cyan border-t border-white/10 mt-1 pt-1">
                      + Create New Episode
                    </SelectItem>
                  </>
                )}
              </SelectContent>
            </Select>
            
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-text-secondary hover:text-white"
                onClick={handleZoomOut}
                disabled={zoom <= MIN_ZOOM}
              >
                <ZoomOut className="w-4 h-4" />
              </Button>
              <span className="text-xs text-white font-mono w-12 text-center">{zoom.toFixed(2)}x</span>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-text-secondary hover:text-white"
                onClick={handleZoomIn}
                disabled={zoom >= MAX_ZOOM}
              >
                <ZoomIn className="w-4 h-4" />
              </Button>
            </div>
            
            <Button
              variant="ghost"
              size="icon"
              className={`h-8 w-8 ${showDebugOverlay ? 'text-neon-cyan' : 'text-text-secondary hover:text-white'}`}
              onClick={() => setShowDebugOverlay(!showDebugOverlay)}
              title="Toggle Debug Mode"
            >
              <Bug className="w-4 h-4" />
            </Button>
          </div>
          
          <div className="flex items-center gap-2">
            {/* Dirty state indicator */}
            {isDirty && (
              <div className="flex items-center gap-1 text-warm-gold text-xs">
                <AlertCircle className="w-3 h-3" />
                <span>Unsaved</span>
              </div>
            )}
            
            <Dialog open={showUploadDialog} onOpenChange={setShowUploadDialog}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  className="border-white/10 text-white hover:bg-slate"
                  disabled={!selectedEpisode || isLocked}
                  data-testid="upload-audio-button"
                >
                  <Upload className="w-4 h-4 mr-2" />
                  Upload Audio
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-charcoal border-white/10 text-white">
                <DialogHeader>
                  <DialogTitle className="text-xl font-space">Upload Audio File</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label>Track Type</Label>
                    <Select value={newTrackType} onValueChange={setNewTrackType}>
                      <SelectTrigger className="mt-2 bg-slate border-white/10 text-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-charcoal border-white/10">
                        <SelectItem value="voice">Voice</SelectItem>
                        <SelectItem value="music">Music</SelectItem>
                        <SelectItem value="sfx">Sound Effects</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <Label>Audio File</Label>
                    <Input
                      type="file"
                      accept="audio/*"
                      onChange={handleFileUpload}
                      className="mt-2 bg-slate border-white/10 text-white"
                      disabled={uploading}
                    />
                    <p className="text-xs text-text-secondary mt-2">
                      Supported: MP3, WAV, M4A, OGG, FLAC
                    </p>
                  </div>
                  
                  {uploading && (
                    <div className="text-center text-neon-cyan">
                      Uploading...
                    </div>
                  )}
                </div>
              </DialogContent>
            </Dialog>
            
            <Dialog open={showAddTrackDialog} onOpenChange={setShowAddTrackDialog}>
              <DialogTrigger asChild>
                <Button
                  variant="outline"
                  className="border-white/10 text-white hover:bg-slate"
                  disabled={isLocked}
                  data-testid="add-track-button"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Add Track
                </Button>
              </DialogTrigger>
              <DialogContent className="bg-charcoal border-white/10 text-white">
                <DialogHeader>
                  <DialogTitle className="text-xl font-space">Add New Track</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <Label>Track Name</Label>
                    <Input
                      value={newTrackName}
                      onChange={(e) => setNewTrackName(e.target.value)}
                      className="mt-2 bg-slate border-white/10 text-white"
                      placeholder="e.g., Narration, Ambient Sound"
                    />
                  </div>
                  
                  <div>
                    <Label>Track Type</Label>
                    <Select value={newTrackType} onValueChange={setNewTrackType}>
                      <SelectTrigger className="mt-2 bg-slate border-white/10 text-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-charcoal border-white/10">
                        <SelectItem value="voice">Voice</SelectItem>
                        <SelectItem value="music">Music</SelectItem>
                        <SelectItem value="sfx">Sound Effects</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <Button
                    onClick={addNewTrack}
                    className="w-full bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
                  >
                    Add Track
                  </Button>
                </div>
              </DialogContent>
            </Dialog>

            <Button
              onClick={() => saveProjectState(true)}
              className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
              disabled={!selectedEpisode || isSaving || isLocked}
              data-testid="save-project-button"
            >
              <Save className="w-4 h-4 mr-2" />
              {isSaving ? 'Saving...' : (isDirty ? 'Save*' : 'Save')}
            </Button>

            {/* Render Final Audio Button */}
            <Button
              onClick={renderFinalAudio}
              disabled={!selectedEpisode || isRendering || isLocked}
              className="bg-signal-green text-obsidian hover:bg-signal-green/90"
              data-testid="render-audio-button"
            >
              <Download className="w-4 h-4 mr-2" />
              {isRendering ? `Rendering ${renderProgress}%` : (selectedEpisode?.finalAudioUrl ? 'Re-render Audio' : 'Render Final Audio')}
            </Button>

            {lastSaved && (
              <span className="text-xs text-text-secondary">
                v{projectVersion} • {lastSaved.toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main Timeline Area - Proper horizontal scroll implementation */}
      <div className="flex-1 flex overflow-hidden">
        {selectedEpisode ? (
          <>
            {/* Timeline Wrapper - Fixed structure for sync scrolling */}
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="p-4 flex-1 flex flex-col">
                {/* Fixed Track Controls + Scrollable Timeline */}
                <div className="flex flex-1 overflow-hidden">
                  {/* Fixed Track Controls Column */}
                  <div className="shrink-0" style={{ width: `${TIMELINE_PADDING}px` }}>
                    {/* Spacer for time ruler */}
                    <div className="h-10 mb-4" />
                    {/* Track Controls */}
                    <div className="space-y-2">
                      {tracks.map((track) => (
                        <div 
                          key={`control-${track.id}`}
                          className="bg-charcoal border border-white/10 rounded-sm p-3 flex flex-col gap-2"
                          style={{ height: `${TRACK_HEIGHT}px` }}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              {track.type === 'voice' && <Mic2 className="w-4 h-4 text-neon-cyan" />}
                              {track.type === 'music' && <Music className="w-4 h-4 text-signal-green" />}
                              {track.type === 'sfx' && <Volume2 className="w-4 h-4 text-warm-gold" />}
                              <span className="text-sm font-space font-bold text-white truncate max-w-[100px]">
                                {track.name}
                              </span>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-text-secondary hover:text-red-400"
                              onClick={() => deleteTrack(track.id)}
                              disabled={isLocked}
                            >
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          </div>
                          
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className={`h-6 text-xs flex-1 ${track.muted ? 'text-red-400 bg-red-400/10' : 'text-text-secondary'}`}
                              onClick={() => toggleTrackMute(track.id)}
                              disabled={isLocked}
                            >
                              M
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className={`h-6 text-xs flex-1 ${track.solo ? 'text-neon-cyan bg-neon-cyan/10' : 'text-text-secondary'}`}
                              onClick={() => toggleTrackSolo(track.id)}
                              disabled={isLocked}
                            >
                              S
                            </Button>
                          </div>
                          
                          <div className="mt-auto">
                            <Slider
                              value={[track.volume]}
                              onValueChange={([value]) => { if (!isLocked) updateTrackVolume(track.id, value); }}
                              min={0}
                              max={1}
                              step={0.01}
                              className="w-full"
                              disabled={isLocked}
                            />
                            <span className="text-xs text-text-secondary">{Math.round(track.volume * 100)}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                  
                  {/* Scrollable Timeline Viewport */}
                  <div 
                    ref={timelineViewportRef}
                    className="flex-1 overflow-x-auto overflow-y-hidden ml-2"
                    onScroll={handleTimelineScroll}
                  >
                    {/* Timeline Content - All elements share this container for sync */}
                    <div 
                      className="relative"
                      style={{ width: `${timelineWidth}px`, minHeight: '100%' }}
                    >
                      {/* PLAYHEAD - Positioned relative to timeline content */}
                      <div
                        className="absolute top-0 w-0.5 bg-neon-cyan pointer-events-none"
                        style={{ 
                          left: `${playheadPosition}px`,
                          height: '100%',
                          zIndex: 50,
                          boxShadow: '0 0 20px rgba(0, 240, 255, 0.9), 0 0 8px rgba(0, 240, 255, 1)',
                          transition: isPlaying ? 'none' : 'left 0.05s linear'
                        }}
                      >
                        {/* Playhead Top Indicator */}
                        <div className="absolute top-0 left-1/2 transform -translate-x-1/2 flex flex-col items-center -mt-1 z-50">
                          <div className="w-4 h-4 bg-neon-cyan rounded-full shadow-lg border-2 border-white mb-1" />
                          <div className="text-xs font-mono font-bold text-neon-cyan whitespace-nowrap bg-obsidian/90 px-2 py-0.5 rounded border border-neon-cyan/30">
                            {formatTime(timelineTime)}
                          </div>
                        </div>
                      </div>
                      
                      {/* Time Ruler */}
                      <div 
                        ref={timelineContainerRef}
                        className="mb-4 h-10 bg-charcoal border border-white/10 rounded-sm relative cursor-pointer"
                        onClick={handleTimelineClick}
                      >
                        {timeRulerMarkers.map((marker) => (
                          <div
                            key={marker.time}
                            className="absolute top-0 h-full pointer-events-none"
                            style={{ left: `${marker.position}px` }}
                          >
                            <div className={`h-full ${marker.isMajor ? 'border-l border-white/30' : 'border-l border-white/10'}`} />
                            {marker.isMajor && (
                              <span className="absolute top-1 left-1 text-xs text-text-secondary whitespace-nowrap">
                                {marker.label}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Tracks Container */}
                      <div ref={tracksContainerRef} className="space-y-2">
                        {tracks.map((track) => (
                          <div
                            key={track.id}
                            ref={el => trackRefs.current[track.id] = el}
                            className={`bg-charcoal border rounded-sm relative transition-colors ${
                              isDraggingClip && dragTargetTrackId === track.id && draggedClip?.trackId !== track.id
                                ? 'border-signal-green border-2 bg-signal-green/5'
                                : 'border-white/10'
                            }`}
                            style={{ height: `${TRACK_HEIGHT}px` }}
                            data-testid={`track-${track.id}`}
                            data-track-id={track.id}
                          >
                            {/* Drop zone indicator when dragging */}
                            {isDraggingClip && dragTargetTrackId === track.id && draggedClip?.trackId !== track.id && (
                              <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-5">
                                <span className="text-signal-green text-sm font-medium bg-obsidian/80 px-3 py-1 rounded">
                                  Drop here
                                </span>
                              </div>
                            )}
                            
                            {track.clips.map((clip) => {
                              const clipLeft = timeToPixels(clip.start);
                              const clipWidth = timeToPixels(clip.duration);
                              const isBeingDragged = isDraggingClip && draggedClip?.clip.id === clip.id;
                              const isEditing = editingClipId === clip.id;
                              
                              return (
                                <div
                                  key={clip.id}
                                  className={`absolute top-2 h-16 bg-gradient-to-r from-neon-cyan/30 to-neon-cyan/10 border-2 rounded-sm px-2 py-1 transition-all ${
                                    isEditing ? 'cursor-text' : 'cursor-grab active:cursor-grabbing'
                                  } hover:border-neon-cyan ${
                                    selectedClip?.id === clip.id ? 'border-neon-cyan shadow-lg shadow-neon-cyan/50' : 'border-neon-cyan/50'
                                  } ${isBeingDragged ? 'opacity-60 scale-105 shadow-xl' : ''}`}
                                  style={{
                                    left: `${clipLeft}px`,
                                    width: `${Math.max(clipWidth, 60)}px`,
                                    zIndex: isBeingDragged ? 100 : (selectedClip?.id === clip.id ? 20 : 10),
                                    transform: isBeingDragged ? 'translateY(-2px)' : 'none'
                                  }}
                                  onMouseDown={(e) => !isEditing && !isLocked && handleClipMouseDown(e, track.id, clip)}
                                  onClick={(e) => {
                                    if (!isEditing) {
                                      setSelectedClip({ ...clip, trackId: track.id });
                                    }
                                  }}
                                  onDoubleClick={(e) => handleClipDoubleClick(e, clip)}
                                  title={clip.name}
                                >
                                  <div className="flex items-center justify-between h-full relative z-10 gap-1">
                                    {/* Clip Name - Inline editable */}
                                    {isEditing ? (
                                      <input
                                        ref={clipNameInputRef}
                                        type="text"
                                        value={editingClipName}
                                        onChange={(e) => setEditingClipName(e.target.value.substring(0, 50))}
                                        onKeyDown={(e) => handleClipNameKeyDown(e, track.id, clip.id)}
                                        onBlur={() => finishRenamingClip(track.id, clip.id)}
                                        className="text-xs text-white bg-obsidian/80 border border-neon-cyan rounded px-1 py-0.5 outline-none flex-1 min-w-0"
                                        onClick={(e) => e.stopPropagation()}
                                        onMouseDown={(e) => e.stopPropagation()}
                                        autoFocus
                                      />
                                    ) : (
                                      <span 
                                        className="text-xs text-white truncate font-medium flex-1 min-w-0 select-none"
                                        title={`Double-click to rename: ${clip.name}`}
                                      >
                                        {clip.name}
                                      </span>
                                    )}
                                    
                                    {/* Clip action buttons */}
                                    <div className="flex items-center gap-0.5 shrink-0">
                                      {!isLocked && (<>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-5 w-5 text-white/70 hover:text-neon-cyan hover:bg-neon-cyan/20"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          startRenamingClip(clip.id, clip.name);
                                        }}
                                        title="Rename"
                                      >
                                        <Edit3 className="w-3 h-3" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-5 w-5 text-white/70 hover:text-neon-cyan hover:bg-neon-cyan/20"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          duplicateClip(track.id, clip);
                                        }}
                                        title="Duplicate"
                                      >
                                        <Copy className="w-3 h-3" />
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-5 w-5 text-white/70 hover:text-red-400 hover:bg-red-400/20"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          removeClipFromTrack(track.id, clip.id);
                                        }}
                                        title="Delete"
                                      >
                                        <X className="w-3 h-3" />
                                      </Button>
                                      </>)}
                                    </div>
                                  </div>
                                  {/* Waveform Placeholder */}
                                  <div className="absolute bottom-1 left-2 right-2 h-4 flex items-end gap-px overflow-hidden pointer-events-none">
                                    {Array.from({ length: Math.max(10, Math.floor(clipWidth / 4)) }).map((_, i) => (
                                      <div
                                        key={i}
                                        className="flex-1 bg-neon-cyan/40 rounded-t min-w-[1px]"
                                        style={{ height: `${20 + Math.sin(i * 0.5) * 30 + Math.random() * 50}%` }}
                                      />
                                    ))}
                                  </div>
                                </div>
                              );
                            })}
                            {track.clips.length === 0 && !isDraggingClip && (
                              <div className="absolute inset-0 flex items-center justify-center text-text-secondary text-sm">
                                Drag clips here or generate audio
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Clip Inspector Panel */}
            {selectedClip && (
              <div className="w-80 border-l border-white/10 bg-charcoal p-4 overflow-y-auto">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-space font-bold text-white">Clip Editor</h3>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-text-secondary hover:text-white"
                    onClick={() => setSelectedClip(null)}
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
                
                <div className="space-y-4">
                  {/* Editable Clip Name */}
                  <div className="space-y-2">
                    <Label className="text-sm text-text-secondary">Clip Name</Label>
                    <div className="flex gap-2">
                      <Input
                        value={selectedClip.name}
                        onChange={(e) => {
                          if (isLocked) return;
                          const newName = e.target.value.substring(0, 50);
                          updateClip(selectedClip.trackId, selectedClip.id, { name: newName });
                        }}
                        className="bg-slate border-white/10 text-white flex-1"
                        placeholder="Enter clip name"
                        disabled={isLocked}
                      />
                    </div>
                    <p className="text-xs text-text-secondary">Max 50 characters</p>
                  </div>
                  
                  {/* Move to Track selector */}
                  <div className="space-y-2">
                    <Label>Move to Track</Label>
                    <Select 
                      value={selectedClip.trackId} 
                      onValueChange={(newTrackId) => {
                        if (newTrackId !== selectedClip.trackId) {
                          moveClipToTrack(selectedClip.trackId, newTrackId, selectedClip.id, selectedClip.start);
                        }
                      }}
                    >
                      <SelectTrigger className="bg-slate border-white/10 text-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-charcoal border-white/10">
                          {tracks.map((track) => (
                            <SelectItem key={track.id} value={track.id}>
                              {track.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Start Position (seconds)</Label>
                      <Input
                        type="number"
                        value={selectedClip.start.toFixed(3)}
                        onChange={(e) => {
                          const newStart = Math.max(0, parseFloat(e.target.value) || 0);
                          updateClip(selectedClip.trackId, selectedClip.id, { start: newStart });
                        }}
                        className="bg-slate border-white/10 text-white"
                        step="0.1"
                        disabled={isLocked}
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Duration (seconds)</Label>
                      <Input
                        type="number"
                        value={selectedClip.duration.toFixed(3)}
                        onChange={(e) => {
                          const newDuration = Math.max(0.1, parseFloat(e.target.value) || 0.1);
                          updateClip(selectedClip.trackId, selectedClip.id, { duration: newDuration });
                        }}
                        className="bg-slate border-white/10 text-white"
                        step="0.1"
                        disabled={isLocked}
                      />
                    </div>
                    
                    <div className="space-y-2">
                      <Label>Trim Start (seconds)</Label>
                      <Slider
                        value={[selectedClip.trimStart || 0]}
                        onValueChange={([value]) => {
                          if (!isLocked) updateClip(selectedClip.trackId, selectedClip.id, { trimStart: value });
                        }}
                        min={0}
                        max={selectedClip.originalDuration || selectedClip.duration}
                        step={0.01}
                        className="w-full"
                        disabled={isLocked}
                      />
                      <span className="text-xs text-text-secondary">
                        {(selectedClip.trimStart || 0).toFixed(3)}s
                      </span>
                    </div>
                    
                    <div className="pt-4 space-y-2">
                      <Button
                        onClick={() => duplicateClip(selectedClip.trackId, selectedClip)}
                        className="w-full bg-slate hover:bg-slate/80 text-white"
                        disabled={isLocked}
                      >
                        <Copy className="w-4 h-4 mr-2" />
                        Duplicate Clip
                      </Button>
                      
                      <Button
                        onClick={() => splitClip(selectedClip.trackId, selectedClip)}
                        className="w-full bg-slate hover:bg-slate/80 text-white"
                        disabled={isLocked}
                      >
                        <Scissors className="w-4 h-4 mr-2" />
                        Split at Playhead
                      </Button>
                      
                      <Button
                        onClick={() => {
                          removeClipFromTrack(selectedClip.trackId, selectedClip.id);
                          setSelectedClip(null);
                        }}
                        className="w-full bg-red-500/20 hover:bg-red-500/30 text-red-400"
                        disabled={isLocked}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete Clip
                      </Button>
                    </div>
                  </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Music className="w-16 h-16 text-neon-cyan/50 mx-auto mb-4" />
              <p className="text-text-secondary mb-4">Select an episode to start producing audio</p>
              <Button
                onClick={() => createEpisode(`Episode ${episodes.length + 1}`)}
                className="bg-neon-cyan text-obsidian hover:bg-neon-cyan/90"
              >
                <Plus className="w-4 h-4 mr-2" />
                Create Episode
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Transport Controls */}
      <div className="border-t border-white/10 bg-charcoal px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              size="icon"
              variant="outline"
              className="border-white/10 text-white hover:bg-slate h-10 w-10"
              onClick={handleStop}
              data-testid="stop-button"
            >
              <Square className="w-5 h-5" fill="currentColor" />
            </Button>
            
            <Button
              size="icon"
              variant="outline"
              className="border-neon-cyan/50 text-neon-cyan hover:bg-neon-cyan/10 h-12 w-12"
              onClick={handlePlayPause}
              data-testid="play-pause-button"
            >
              {isPlaying ? (
                <Pause className="w-6 h-6" />
              ) : (
                <Play className="w-6 h-6 ml-0.5" />
              )}
            </Button>
            
            <Button
              size="icon"
              variant="outline"
              className="border-white/10 text-white hover:bg-slate h-10 w-10"
              onClick={() => seekToTime(0)}
              data-testid="rewind-button"
            >
              <SkipBack className="w-5 h-5" />
            </Button>
            
            <span className="text-neon-cyan text-base font-mono font-bold min-w-[100px]">
              {formatTime(timelineTime)}
            </span>
            <span className="text-text-secondary text-sm">/</span>
            <span className="text-white text-sm font-mono">
              {formatTimeShort(timelineDuration)}
            </span>
          </div>
          
          <div className="flex-1 mx-8">
            <Slider
              value={[timelineTime]}
              onValueChange={([value]) => seekToTime(value)}
              min={0}
              max={timelineDuration}
              step={0.001}
              className="w-full"
            />
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-secondary">Master</span>
            <Volume2 className="w-5 h-5 text-text-secondary" />
            <Slider
              value={[masterVolume]}
              onValueChange={([value]) => setMasterVolume(value)}
              min={0}
              max={1}
              step={0.01}
              className="w-24"
            />
            <span className="text-xs text-white font-mono w-10">
              {Math.round(masterVolume * 100)}%
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AudioStudio;
