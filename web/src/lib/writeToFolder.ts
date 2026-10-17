// Writes mix files into a user-chosen directory via the File System Access API.
// Strictly sequential: some MP3 players play in directory write order.

export interface WritableLike {
  write(data: Blob): Promise<void>;
  close(): Promise<void>;
}

export interface FileHandleLike {
  createWritable(): Promise<WritableLike>;
}

export interface DirectoryHandleLike {
  getFileHandle(name: string, options?: { create?: boolean }): Promise<FileHandleLike>;
}

export interface FileToWrite {
  name: string;
  url: string;
}

export type FetchFn = (url: string) => Promise<Pick<Response, 'ok' | 'status' | 'blob'>>;

export type WriteState = 'writing' | 'done';

export interface WriteProgress {
  index: number;
  total: number;
  name: string;
  state: WriteState;
}

/** True when this browser can write straight to a folder (Chrome, Edge). */
export function supportsFolderWrite(target: object = window): boolean {
  return typeof (target as { showDirectoryPicker?: unknown }).showDirectoryPicker === 'function';
}

/** Names from `files` that already exist in the directory, in play order. */
export async function findExisting(
  dir: DirectoryHandleLike,
  files: readonly FileToWrite[],
): Promise<string[]> {
  const existing: string[] = [];
  for (const f of files) {
    try {
      await dir.getFileHandle(f.name);
      existing.push(f.name);
    } catch (e) {
      if (!(e instanceof Error) || e.name !== 'NotFoundError') throw e;
    }
  }
  return existing;
}

/**
 * Fetch and write each file in order, finishing one (including close) before
 * starting the next.
 */
export async function writeToFolder(
  dir: DirectoryHandleLike,
  files: readonly FileToWrite[],
  fetchFn: FetchFn,
  onProgress?: (p: WriteProgress) => void,
): Promise<void> {
  const total = files.length;
  for (const [index, file] of files.entries()) {
    onProgress?.({ index, total, name: file.name, state: 'writing' });
    const res = await fetchFn(file.url);
    if (!res.ok) throw new Error(`Could not fetch ${file.name} (HTTP ${res.status})`);
    const blob = await res.blob();
    const handle = await dir.getFileHandle(file.name, { create: true });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    onProgress?.({ index, total, name: file.name, state: 'done' });
  }
}
