import { useEffect, useState } from 'react';
import { JobView } from './components/JobView';
import { RecentMixes } from './components/RecentMixes';
import { RequestForm } from './components/RequestForm';
import { btn } from './components/ui';

function idFromHash(): string | null {
  const m = /^#mix=(.+)$/.exec(window.location.hash);
  return m?.[1] ? decodeURIComponent(m[1]) : null;
}

export function App() {
  const [id, setId] = useState<string | null>(idFromHash);

  useEffect(() => {
    const onHash = () => setId(idFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const open = (next: string | null) => {
    window.location.hash = next ? `mix=${encodeURIComponent(next)}` : '';
    setId(next);
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-teal-glow">Playlist</h1>
        {id && (
          <button type="button" className={btn} onClick={() => open(null)}>
            New mix
          </button>
        )}
      </header>
      <main className="space-y-6">
        {id ? <JobView id={id} /> : <RequestForm onCreated={open} />}
        <RecentMixes refreshKey={id} onOpen={open} />
      </main>
    </div>
  );
}
