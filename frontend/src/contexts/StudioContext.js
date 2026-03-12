import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const StudioContext = createContext(null);

export function StudioProvider({ children, storyId }) {
  const [episodes, setEpisodes] = useState([]);
  const [characters, setCharacters] = useState([]);
  const [voices, setVoices] = useState([]);
  const [voiceCategories, setVoiceCategories] = useState({});
  const [ttsSettings, setTtsSettings] = useState(null);
  const [selectedEpisode, setSelectedEpisode] = useState(null);
  const [studioLoading, setStudioLoading] = useState(true);

  const base = process.env.REACT_APP_BACKEND_URL;

  const getHeaders = () => ({
    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
  });

  const fetchEpisodesData = useCallback(async () => {
    const res = await fetch(`${base}/api/episodes/story/${storyId}`, {
      credentials: 'include', headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch episodes');
    return res.json();
  }, [storyId, base]);

  const fetchCharactersData = useCallback(async () => {
    const res = await fetch(`${base}/api/characters/story/${storyId}`, {
      credentials: 'include', headers: getHeaders()
    });
    if (!res.ok) throw new Error('Failed to fetch characters');
    return res.json();
  }, [storyId, base]);

  const fetchTtsData = useCallback(async () => {
    try {
      const res = await fetch(`${base}/api/tts/settings`, {
        credentials: 'include', headers: getHeaders()
      });
      if (!res.ok) return null;
      return res.json();
    } catch {
      return null;
    }
  }, [base]);

  useEffect(() => {
    let cancelled = false;

    const loadAll = async () => {
      setStudioLoading(true);
      try {
        const [epData, charData, ttsData] = await Promise.all([
          fetchEpisodesData(),
          fetchCharactersData(),
          fetchTtsData(),
        ]);

        if (cancelled) return;

        setEpisodes(epData || []);
        setCharacters(charData || []);

        if (ttsData) {
          setTtsSettings(ttsData);
          setVoices(ttsData.voices || []);
          setVoiceCategories(ttsData.voiceCategories || {});
        }

        if (epData && epData.length > 0) {
          const savedId = localStorage.getItem(`current_episode_${storyId}`);
          const savedEp = savedId ? epData.find(e => e.episode_id === savedId) : null;
          setSelectedEpisode(savedEp || epData[0]);
        }
      } catch (err) {
        console.error('[StudioContext] Failed to load studio data:', err);
      } finally {
        if (!cancelled) setStudioLoading(false);
      }
    };

    loadAll();
    return () => { cancelled = true; };
  }, [storyId]);

  useEffect(() => {
    if (selectedEpisode?.episode_id && storyId) {
      localStorage.setItem(`current_episode_${storyId}`, selectedEpisode.episode_id);
    }
  }, [selectedEpisode?.episode_id, storyId]);

  const refreshEpisodes = useCallback(async () => {
    try {
      const data = await fetchEpisodesData();
      setEpisodes(data || []);
    } catch (err) {
      console.error('[StudioContext] Failed to refresh episodes:', err);
    }
  }, [fetchEpisodesData]);

  const refreshCharacters = useCallback(async () => {
    try {
      const data = await fetchCharactersData();
      setCharacters(data || []);
    } catch (err) {
      console.error('[StudioContext] Failed to refresh characters:', err);
    }
  }, [fetchCharactersData]);

  return (
    <StudioContext.Provider value={{
      episodes,
      setEpisodes,
      characters,
      setCharacters,
      voices,
      voiceCategories,
      ttsSettings,
      selectedEpisode,
      setSelectedEpisode,
      studioLoading,
      refreshEpisodes,
      refreshCharacters,
    }}>
      {children}
    </StudioContext.Provider>
  );
}

export function useStudio() {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error('useStudio must be used inside StudioProvider');
  return ctx;
}
