import { useState } from 'react';
import { zipUrl } from '../api/client';
import type { MixFile } from '../api/types';
import {
  type DirectoryHandleLike,
  findExisting,
  supportsFolderWrite,
  type WriteProgress,
  writeToFolder,
} from '../lib/writeToFolder';
import { btn, btnPrimary, card } from './ui';

type PickerWindow = Window & {
  showDirectoryPicker?: (opts?: { mode?: 'read' | 'readwrite' }) => Promise<DirectoryHandleLike>;
};

export function DeliveryPanel({ mixId, files }: { mixId: string; files: MixFile[] }) {
  const canWrite = supportsFolderWrite();
  const [dir, setDir] = useState<DirectoryHandleLike | null>(null);
  const [clashes, setClashes] = useState<string[]>([]);
  const [progress, setProgress] = useState<WriteProgress | null>(null);
  const [doneCount, setDoneCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(handle: DirectoryHandleLike) {
    setBusy(true);
    setClashes([]);
    setDoneCount(0);
    setError(null);
    setMessage(null);
    try {
      await writeToFolder(
        handle,
        files,
        (u) => fetch(u),
        (p) => {
          setProgress(p);
          if (p.state === 'done') setDoneCount(p.index + 1);
        },
      );
      setMessage(`Wrote ${files.length} file${files.length === 1 ? '' : 's'}.`);
    } catch (e) {
      setError(`Writing stopped: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      setDir(null);
    }
  }

  async function pick() {
    setError(null);
    setMessage(null);
    let handle: DirectoryHandleLike;
    try {
      const picker = (window as PickerWindow).showDirectoryPicker;
      if (!picker) return;
      handle = await picker.call(window, { mode: 'readwrite' });
    } catch (e) {
      if ((e as Error).name !== 'AbortError')
        setError(`Could not open the folder: ${(e as Error).message}`);
      return;
    }
    try {
      const existing = await findExisting(handle, files);
      if (existing.length > 0) {
        setDir(handle);
        setClashes(existing);
        return;
      }
    } catch (e) {
      setError(`Could not check the folder: ${(e as Error).message}`);
      return;
    }
    await run(handle);
  }

  return (
    <section className={`${card} space-y-3`} aria-label="Delivery">
      <h3 className="text-base font-semibold">Delivery</h3>
      <div className="flex flex-wrap items-center gap-3">
        {canWrite && (
          <button type="button" className={btnPrimary} onClick={pick} disabled={busy}>
            Write to folder…
          </button>
        )}
        <a className={btn} href={zipUrl(mixId)} download>
          Download zip
        </a>
      </div>
      {!canWrite && (
        <p className="text-sm text-mist">
          This browser cannot write to a folder. Use Chrome or Edge to write straight to the
          headphones, or download the zip and copy the files across in order.
        </p>
      )}

      {clashes.length > 0 && dir && (
        <div
          role="alertdialog"
          aria-label="Overwrite files"
          className="rounded-lg border border-amber-400/50 p-3 text-sm"
        >
          <p>
            {clashes.length} file{clashes.length === 1 ? '' : 's'} already exist in that folder (
            {clashes.join(', ')}). Overwrite {clashes.length === 1 ? 'it' : 'them'}?
          </p>
          <div className="mt-2 flex gap-2">
            <button type="button" className={btnPrimary} onClick={() => run(dir)}>
              Overwrite
            </button>
            <button
              type="button"
              className={btn}
              onClick={() => {
                setClashes([]);
                setDir(null);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {(busy || doneCount > 0) && (
        <div aria-live="polite" className="space-y-1 text-sm">
          <progress
            className="w-full"
            max={files.length}
            value={doneCount}
            aria-label="Files written"
          />
          <p>
            {busy && progress
              ? `Writing ${progress.index + 1} of ${progress.total}: ${progress.name}`
              : `${doneCount} of ${files.length} written`}
          </p>
        </div>
      )}
      {message && <p className="text-sm text-teal-glow">{message}</p>}
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
    </section>
  );
}
