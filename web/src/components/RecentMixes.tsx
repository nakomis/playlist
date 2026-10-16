import { useEffect, useState } from 'react';
import { listMixes } from '../api/client';
import type { Mix } from '../api/types';
import { card } from './ui';

export function RecentMixes({
  refreshKey,
  onOpen,
}: {
  refreshKey: string | null;
  onOpen: (id: string) => void;
}) {
  const [mixes, setMixes] = useState<Mix[]>([]);
  const [error, setError] = useState<string | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: refreshKey re-fetches the list
  useEffect(() => {
    let live = true;
    listMixes()
      .then((m) => live && setMixes(m))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [refreshKey]);

  return (
    <section className={`${card} space-y-2`} aria-label="Recent mixes">
      <h2 className="text-lg font-semibold">Recent mixes</h2>
      {error && <p className="text-sm text-red-400">Could not load recent mixes: {error}</p>}
      {!error && mixes.length === 0 && <p className="text-sm text-mist">No mixes yet.</p>}
      <ul className="space-y-1 text-sm">
        {mixes.map((m) => (
          <li key={m.id}>
            <button
              type="button"
              className="flex w-full justify-between gap-3 rounded px-2 py-1 text-left hover:bg-shelf"
              onClick={() => onOpen(m.id)}
            >
              <span>
                {m.title ?? m.id}
                {m.created_at && (
                  <span className="ml-2 text-mist">
                    {new Date(m.created_at * 1000).toLocaleString('en-GB', {
                      dateStyle: 'short',
                      timeStyle: 'short',
                    })}
                  </span>
                )}
              </span>
              <span className="text-mist">{m.status}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
