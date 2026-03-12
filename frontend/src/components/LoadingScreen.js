import React from 'react';

function LoadingScreen({ message = 'Preparing your studio...' }) {
  return (
    <div className="min-h-screen bg-obsidian flex flex-col items-center justify-center gap-8">
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-4xl font-space font-bold text-neon-cyan tracking-widest select-none">
          StoryFy
        </h1>

        <div className="flex items-end gap-[5px] h-10">
          {[0, 1, 2, 3, 4].map(i => (
            <div
              key={i}
              style={{
                width: 6,
                borderRadius: 4,
                backgroundColor: 'var(--color-neon-cyan, #00e5ff)',
                animation: `storyfy-wave 1.1s ease-in-out infinite`,
                animationDelay: `${i * 0.12}s`,
              }}
            />
          ))}
        </div>

        <p className="text-text-secondary font-space text-sm tracking-wide">
          {message}
        </p>
      </div>

      <style>{`
        @keyframes storyfy-wave {
          0%, 100% { height: 8px; opacity: 0.4; }
          50% { height: 36px; opacity: 1; }
        }
      `}</style>
    </div>
  );
}

export default LoadingScreen;
