import type { Mix } from '../api/types';
import { formatBytes } from '../lib/format';
import { DeliveryPanel } from './DeliveryPanel';
import { LicencePanel } from './LicencePanel';
import { Preview } from './Preview';
import { card } from './ui';

export function ResultView({ mix }: { mix: Mix }) {
  const files = mix.files ?? [];
  return (
    <div className="space-y-4">
      <section className={`${card} space-y-2`} aria-label="Files">
        <h3 className="text-base font-semibold">Files</h3>
        <ol className="space-y-1 text-sm">
          {files.map((f) => (
            <li key={f.name} className="flex justify-between gap-3">
              <span>{f.name}</span>
              <span className="text-mist">{formatBytes(f.size)}</span>
            </li>
          ))}
        </ol>
      </section>
      <Preview files={files} />
      {mix.manifest && <LicencePanel manifest={mix.manifest} />}
      <DeliveryPanel mixId={mix.id} files={files} />
    </div>
  );
}
