import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';

const GenerationStatusContext = createContext(null);

const base = process.env.REACT_APP_BACKEND_URL;

export function GenerationStatusProvider({ children }) {
  const [jobs, setJobs] = useState([]);
  const [queueInfo, setQueueInfo] = useState({ total_queued: 0, total_processing: 0 });
  const [dismissed, setDismissed] = useState(new Set());
  const pollRef = useRef(null);
  const hasActiveRef = useRef(false);

  const getHeaders = () => ({
    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
  });

  const pollJobs = useCallback(async () => {
    try {
      const res = await fetch(`${base}/api/jobs/active`, { headers: getHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      setJobs(data.jobs || []);
      setQueueInfo(data.queue_info || { total_queued: 0, total_processing: 0 });
    } catch {
      // silent
    }
  }, []);

  // Start/stop polling based on active jobs
  useEffect(() => {
    const hasActive = jobs.some(j => j.status === 'queued' || j.status === 'processing');
    hasActiveRef.current = hasActive;

    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(pollJobs, 3000);
    } else if (!hasActive && pollRef.current) {
      // Keep polling for a few more seconds to catch completion
      setTimeout(() => {
        if (!hasActiveRef.current && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 10000);
    }
  }, [jobs, pollJobs]);

  // Initial poll + cleanup
  useEffect(() => {
    pollJobs();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollJobs]);

  // Called when user triggers generation — immediately start polling
  const trackNewJob = useCallback((jobData) => {
    setJobs(prev => [...prev, {
      job_id: jobData.queue_id || jobData.job_id,
      job_type: jobData.job_type || 'unknown',
      status: 'queued',
      position_in_queue: 0,
      queue_size: 0,
      script_job_id: jobData.job_id || '',
      script_progress: jobData.total_dialogues ? {
        completed_dialogues: 0,
        total_dialogues: jobData.total_dialogues,
        script_status: 'queued',
        error_message: '',
      } : null,
      episode_id: jobData.episode_id || '',
      error: '',
      created_at: new Date().toISOString(),
      completed_at: null,
    }]);
    // Start polling immediately
    if (!pollRef.current) {
      pollRef.current = setInterval(pollJobs, 3000);
    }
    // Also do an immediate poll after a short delay
    setTimeout(pollJobs, 1000);
  }, [pollJobs]);

  const dismissJob = useCallback((jobId) => {
    setDismissed(prev => new Set([...prev, jobId]));
  }, []);

  const visibleJobs = jobs.filter(j => !dismissed.has(j.job_id));
  const activeJobs = visibleJobs.filter(j => j.status === 'queued' || j.status === 'processing');
  const completedJobs = visibleJobs.filter(j => j.status === 'completed');
  const failedJobs = visibleJobs.filter(j => j.status === 'failed');

  return (
    <GenerationStatusContext.Provider value={{
      jobs: visibleJobs,
      activeJobs,
      completedJobs,
      failedJobs,
      queueInfo,
      trackNewJob,
      dismissJob,
      pollJobs,
    }}>
      {children}
    </GenerationStatusContext.Provider>
  );
}

export function useGenerationStatus() {
  const ctx = useContext(GenerationStatusContext);
  if (!ctx) throw new Error('useGenerationStatus must be used inside GenerationStatusProvider');
  return ctx;
}
