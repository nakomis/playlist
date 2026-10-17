import { useState } from 'react';
import type { Manifest } from '../api/types';
import { btn, card } from './ui';

export function LicencePanel({ manifest }: { manifest: Manifest }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(manifest.attribution_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className={`${card} space-y-3`} aria-label="Licence">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-base font-semibold">Licence</h3>
        {manifest.publishable ? (
          <span className="rounded-full bg-teal-glow/20 px-3 py-1 text-sm font-medium text-teal-glow">
            Publishable (all CC)
          </span>
        ) : (
          <span className="rounded-full bg-amber-400/20 px-3 py-1 text-sm font-medium text-amber-300">
            Private: contains purchased music
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-mist">
            <tr>
              <th className="py-1 pr-3">Track</th>
              <th className="py-1 pr-3">Artist</th>
              <th className="py-1 pr-3">Library</th>
              <th className="py-1">Licence</th>
            </tr>
          </thead>
          <tbody>
            {manifest.tracks.map((t, i) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: tracks can repeat titles
              <tr key={i} className="border-t border-line">
                <td className="py-1 pr-3">{t.title}</td>
                <td className="py-1 pr-3">{t.artist}</td>
                <td className="py-1 pr-3">{t.library}</td>
                <td className="py-1">{t.licence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-1">
        <label htmlFor="attribution" className="block text-sm font-medium text-mist">
          Attribution text
        </label>
        <textarea
          id="attribution"
          readOnly
          rows={6}
          className="w-full rounded-lg border border-line bg-abyss p-2 font-mono text-xs"
          value={manifest.attribution_text}
        />
        <button type="button" className={btn} onClick={copy}>
          {copied ? 'Copied' : 'Copy attribution'}
        </button>
      </div>
    </section>
  );
}
