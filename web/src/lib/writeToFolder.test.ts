import { describe, expect, it, vi } from 'vitest';
import {
  type DirectoryHandleLike,
  findExisting,
  supportsFolderWrite,
  writeToFolder,
} from './writeToFolder';

function fakeDir(existing: string[] = []) {
  const log: string[] = [];
  const dir: DirectoryHandleLike = {
    async getFileHandle(name, opts) {
      if (!opts?.create && !existing.includes(name)) {
        throw Object.assign(new Error('nope'), { name: 'NotFoundError' });
      }
      return {
        async createWritable() {
          log.push(`open ${name}`);
          return {
            async write() {
              await new Promise((r) => setTimeout(r, 5));
              log.push(`write ${name}`);
            },
            async close() {
              log.push(`close ${name}`);
            },
          };
        },
      };
    },
  };
  return { dir, log };
}

const files = [
  { name: '01.mp3', url: '/a' },
  { name: '02.mp3', url: '/b' },
  { name: '03.mp3', url: '/c' },
];
const okFetch = async () => ({ ok: true, status: 200, blob: async () => new Blob(['x']) });

describe('writeToFolder', () => {
  it('writes sequentially, closing each file before opening the next', async () => {
    const { dir, log } = fakeDir();
    await writeToFolder(dir, files, okFetch);
    expect(log).toEqual([
      'open 01.mp3',
      'write 01.mp3',
      'close 01.mp3',
      'open 02.mp3',
      'write 02.mp3',
      'close 02.mp3',
      'open 03.mp3',
      'write 03.mp3',
      'close 03.mp3',
    ]);
  });

  it('reports progress for each file', async () => {
    const { dir } = fakeDir();
    const onProgress = vi.fn();
    await writeToFolder(dir, files.slice(0, 2), okFetch, onProgress);
    expect(onProgress.mock.calls.map((c) => [c[0].index, c[0].state])).toEqual([
      [0, 'writing'],
      [0, 'done'],
      [1, 'writing'],
      [1, 'done'],
    ]);
    expect(onProgress.mock.calls[0]?.[0].total).toBe(2);
  });

  it('stops on a failed fetch', async () => {
    const { dir, log } = fakeDir();
    const bad = async () => ({ ok: false, status: 500, blob: async () => new Blob() });
    await expect(writeToFolder(dir, files, bad)).rejects.toThrow(/01\.mp3.*500/);
    expect(log).toEqual([]);
  });

  it('detects existing names in play order', async () => {
    const { dir } = fakeDir(['03.mp3', '01.mp3']);
    expect(await findExisting(dir, files)).toEqual(['01.mp3', '03.mp3']);
  });

  it('rethrows unexpected errors when checking names', async () => {
    const dir: DirectoryHandleLike = {
      getFileHandle: async () => {
        throw new Error('boom');
      },
    };
    await expect(findExisting(dir, files)).rejects.toThrow('boom');
  });

  it('feature-detects showDirectoryPicker', () => {
    expect(supportsFolderWrite({})).toBe(false);
    expect(supportsFolderWrite({ showDirectoryPicker: () => {} })).toBe(true);
  });
});
