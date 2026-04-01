import React, { useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useGenerationStatus } from '../contexts/GenerationStatusContext';
import { Loader2, CheckCircle, AlertCircle, X, Music, Headphones } from 'lucide-react';

function GenerationStatusWidget() {
  const { jobs, activeJobs, completedJobs, failedJobs, dismissJob } = useGenerationStatus();
  const navigate = useNavigate();
  const location = useLocation();
  const autoDismissTimers = useRef({});

  // Auto-dismiss completed/failed jobs after 12 seconds
  useEffect(() => {
    [...completedJobs, ...failedJobs].forEach(job => {
      if (!autoDismissTimers.current[job.job_id]) {
        autoDismissTimers.current[job.job_id] = setTimeout(() => {
          dismissJob(job.job_id);
          delete autoDismissTimers.current[job.job_id];
        }, 12000);
      }
    });
    return () => {
      Object.values(autoDismissTimers.current).forEach(clearTimeout);
    };
  }, [completedJobs, failedJobs, dismissJob]);

  if (jobs.length === 0) return null;

  const goToAudioStudio = (episodeId) => {
    const storyPath = location.pathname.match(/\/studio\/[^/]+/)?.[0];
    if (storyPath) {
      navigate(`${storyPath}/audio`);
    }
  };

  const getJobLabel = (job) => {
    if (job.job_type === 'narration_batch') return 'Narration';
    if (job.job_type === 'dialogue_batch') return 'Script';
    if (job.job_type === 'regenerate') return 'Clip';
    return 'Audio';
  };

  const getProgress = (job) => {
    if (!job.script_progress) return null;
    const { completed_dialogues, total_dialogues } = job.script_progress;
    if (!total_dialogues) return null;
    return { completed: completed_dialogues, total: total_dialogues };
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm" data-testid="generation-status-widget">
      {jobs.map((job) => {
        const progress = getProgress(job);
        const label = getJobLabel(job);
        const pct = progress ? Math.round((progress.completed / progress.total) * 100) : 0;

        return (
          <div
            key={job.job_id}
            data-testid={`gen-job-${job.job_id}`}
            className={`rounded-lg border backdrop-blur-xl shadow-2xl px-4 py-3 transition-all animate-in slide-in-from-right-5 duration-300
              ${job.status === 'completed' ? 'bg-signal-green/10 border-signal-green/30' :
                job.status === 'failed' ? 'bg-red-500/10 border-red-500/30' :
                'bg-charcoal/95 border-white/10'}`}
          >
            <div className="flex items-start gap-3">
              {/* Icon */}
              <div className="flex-shrink-0 mt-0.5">
                {job.status === 'queued' && (
                  <div className="w-8 h-8 rounded-full bg-warm-gold/15 flex items-center justify-center">
                    <Headphones className="w-4 h-4 text-warm-gold" />
                  </div>
                )}
                {job.status === 'processing' && (
                  <div className="w-8 h-8 rounded-full bg-neon-cyan/15 flex items-center justify-center">
                    <Loader2 className="w-4 h-4 text-neon-cyan animate-spin" />
                  </div>
                )}
                {job.status === 'completed' && (
                  <div className="w-8 h-8 rounded-full bg-signal-green/15 flex items-center justify-center">
                    <CheckCircle className="w-4 h-4 text-signal-green" />
                  </div>
                )}
                {job.status === 'failed' && (
                  <div className="w-8 h-8 rounded-full bg-red-500/15 flex items-center justify-center">
                    <AlertCircle className="w-4 h-4 text-red-400" />
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                {job.status === 'queued' && (
                  <>
                    <p className="text-sm font-medium text-white">{label} generation queued</p>
                    <p className="text-xs text-text-secondary mt-0.5">
                      {job.position_in_queue > 0
                        ? `Position in queue: ${job.position_in_queue + 1}`
                        : "You're next in line"}
                    </p>
                  </>
                )}
                {job.status === 'processing' && (
                  <>
                    <p className="text-sm font-medium text-white">Generating {label.toLowerCase()} audio...</p>
                    {progress && (
                      <>
                        <div className="w-full bg-white/10 rounded-full h-1.5 mt-2">
                          <div
                            className="bg-neon-cyan h-1.5 rounded-full transition-all duration-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <p className="text-xs text-text-secondary mt-1">
                          {progress.completed}/{progress.total} clips &middot; {pct}%
                        </p>
                      </>
                    )}
                    {!progress && (
                      <p className="text-xs text-text-secondary mt-0.5">Processing your request...</p>
                    )}
                  </>
                )}
                {job.status === 'completed' && (
                  <>
                    <p className="text-sm font-medium text-signal-green">{label} audio is ready!</p>
                    <button
                      onClick={() => { goToAudioStudio(job.episode_id); dismissJob(job.job_id); }}
                      className="text-xs text-neon-cyan hover:text-neon-cyan/80 mt-1 flex items-center gap-1 transition-colors"
                      data-testid="go-to-audio-studio-btn"
                    >
                      <Music className="w-3 h-3" /> Go to Audio Studio
                    </button>
                  </>
                )}
                {job.status === 'failed' && (
                  <>
                    <p className="text-sm font-medium text-red-400">Generation failed</p>
                    <p className="text-xs text-text-secondary mt-0.5 truncate">
                      {job.error || 'Something went wrong. Please try again.'}
                    </p>
                  </>
                )}
              </div>

              {/* Dismiss */}
              <button
                onClick={() => dismissJob(job.job_id)}
                className="text-text-secondary hover:text-white transition-colors flex-shrink-0 p-0.5"
                data-testid={`dismiss-job-${job.job_id}`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default GenerationStatusWidget;
