import { useEffect, useState } from 'react';
import { getMix } from '../api/client';
import type { Mix } from '../api/types';
import { formatTime } from '../lib/format';
import { ResultView } from './ResultView';
import { card } from './ui';

export function JobView({ id, pollMs = 2000 }: { id: string; pollMs?: number }) {
  const [mix, setMix] = useState<Mix | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setMix(null);
    setError(null);

    const tick = async () => {
      try {
        const m = await getMix(id);
        if (!live) return;
        setMix(m);
        setError(null);
        if (m.status === 'done' || m.status === 'failed') return;
      } catch (e) {
        if (!live) return;
        setError((e as Error).message);
      }
      timer = setTimeout(tick, pollMs);
    };
    tick();

    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [id, pollMs]);

  if (!mix) {
    return (
      <p className="text-mist" role="status">
        {error ? `Could not load the mix: ${error}` : 'Loading…'}
      </p>
    );
  }

  const pct = Math.round(mix.progress * 100);
  const running = mix.status !== 'done' && mix.status !== 'failed';

  return (
    <div className="space-y-4">
      <section className={`${card} space-y-2`} aria-label="Progress">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Mix {mix.id}</h2>
          <span data-testid="status" className="text-sm text-teal-glow">
            {mix.status}
          </span>
        </div>
        {running && <progress className="w-full" max={100} value={pct} aria-label="Mix progress" />}
        <p className="text-sm text-mist" role="status">
          {mix.message}
          {running && ` (${pct}%)`}
        </p>
        {error && <p className="text-sm text-amber-300">Connection trouble: {error}. Retrying…</p>}
        {mix.status === 'failed' && (
          <p role="alert" className="text-sm text-red-400">
            The mix failed. {mix.error ?? mix.message}
          </p>
        )}
      </section>

      {mix.plan && (
        <section className={`${card} space-y-2`} aria-label="Plan">
          <h3 className="text-base font-semibold">
            Plan{' '}
            <span className="text-sm font-normal text-mist">
              {Math.round(mix.plan.tempo_bpm)} BPM, {formatTime(mix.plan.duration_s)}
            </span>
          </h3>
          <ol className="space-y-1 text-sm">
            {mix.plan.tracks.map((t, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: a track can recur in a plan
              <li key={i} className="flex flex-wrap gap-x-3">
                <span className="w-14 text-mist">{formatTime(t.start_s)}</span>
                <span>
                  {t.artist} – {t.title}
                </span>
                <span className="text-mist">
                  {Math.round(t.bpm)} BPM · {t.camelot}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {mix.status === 'done' && <ResultView mix={mix} />}
    </div>
  );
}
