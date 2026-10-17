import { useEffect, useState } from 'react';
import { createMix, getGenres, getLibraries } from '../api/client';
import type { Genre, Library, MixRequest, OutputMode } from '../api/types';
import { btn, btnPrimary, card, input } from './ui';

const QUICK_DURATIONS = [30, 45, 60, 90, 120];

export function RequestForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [chosenLibs, setChosenLibs] = useState<string[]>([]);
  const [genres, setGenres] = useState<Genre[]>([]);
  const [chosenGenres, setChosenGenres] = useState<string[]>([]);
  const [duration, setDuration] = useState(60);
  const [output, setOutput] = useState<OutputMode>('split');
  const [seed, setSeed] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let live = true;
    getLibraries()
      .then((libs) => {
        if (!live) return;
        setLibraries(libs);
        setChosenLibs(libs.map((l) => l.title));
      })
      .catch((e: Error) => live && setError(`Could not load libraries: ${e.message}`));
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (chosenLibs.length === 0) {
      setGenres([]);
      return;
    }
    let live = true;
    getGenres(chosenLibs)
      .then((g) => {
        if (!live) return;
        setGenres(g);
        setChosenGenres((prev) => prev.filter((n) => g.some((x) => x.name === n)));
      })
      .catch((e: Error) => live && setError(`Could not load genres: ${e.message}`));
    return () => {
      live = false;
    };
  }, [chosenLibs]);

  const toggle = (list: string[], v: string) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  const seedValid = seed.trim() === '' || Number.isInteger(Number(seed));
  const canSubmit =
    !submitting && chosenLibs.length > 0 && chosenGenres.length > 0 && duration > 0 && seedValid;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    const body: MixRequest = {
      genres: chosenGenres,
      duration_min: duration,
      libraries: chosenLibs,
      output,
    };
    if (seed.trim() !== '') body.seed = Number(seed);
    setSubmitting(true);
    setError(null);
    try {
      const { id } = await createMix(body);
      onCreated(id);
    } catch (err) {
      setError(`Could not start the mix: ${(err as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className={`${card} space-y-5`} aria-label="New mix">
      <h2 className="text-lg font-semibold">New mix</h2>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium text-mist">Libraries</legend>
        {libraries.map((l) => (
          <label key={l.key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={chosenLibs.includes(l.title)}
              onChange={() => setChosenLibs((p) => toggle(p, l.title))}
            />
            <span>{l.title}</span>
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${
                l.kind === 'cc'
                  ? 'bg-teal-glow/20 text-teal-glow'
                  : 'bg-amber-400/20 text-amber-300'
              }`}
            >
              {l.kind === 'cc' ? 'CC (publishable)' : 'Purchased (private)'}
            </span>
          </label>
        ))}
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium text-mist">Genres</legend>
        {genres.length === 0 && <p className="text-sm text-mist">No genres to show.</p>}
        <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
          {genres.map((g) => (
            <label key={g.name} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={chosenGenres.includes(g.name)}
                onChange={() => setChosenGenres((p) => toggle(p, g.name))}
              />
              <span>{g.name}</span>
              <span className="text-xs text-mist">({g.count})</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="space-y-2">
        <label htmlFor="duration" className="block text-sm font-medium text-mist">
          Duration (minutes)
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <input
            id="duration"
            type="number"
            min={1}
            className={`${input} w-24`}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
          {QUICK_DURATIONS.map((d) => (
            <button key={d} type="button" className={btn} onClick={() => setDuration(d)}>
              {d}
            </button>
          ))}
        </div>
      </div>

      <fieldset className="space-y-2">
        <legend className="mb-1 text-sm font-medium text-mist">Output</legend>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="output"
            checked={output === 'split'}
            onChange={() => setOutput('split')}
          />
          Split into ~5-minute files (skip-friendly)
        </label>
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="output"
            checked={output === 'single'}
            onChange={() => setOutput('single')}
          />
          Single continuous file (no gaps; no skipping)
        </label>
      </fieldset>

      <div className="space-y-2">
        <label htmlFor="seed" className="block text-sm font-medium text-mist">
          Seed (optional)
        </label>
        <div className="flex items-center gap-2">
          <input
            id="seed"
            type="number"
            className={`${input} w-40`}
            value={seed}
            placeholder="random"
            onChange={(e) => setSeed(e.target.value)}
          />
          <button
            type="button"
            className={btn}
            onClick={() => setSeed(String(Math.floor(Math.random() * 1_000_000)))}
          >
            Reroll
          </button>
        </div>
        {!seedValid && <p className="text-sm text-red-400">The seed must be a whole number.</p>}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}

      <button type="submit" className={btnPrimary} disabled={!canSubmit}>
        {submitting ? 'Starting…' : 'Make mix'}
      </button>
    </form>
  );
}
