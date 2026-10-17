import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DeliveryPanel } from './DeliveryPanel';

const files = [
  { name: '01.mp3', url: '/f/01', size: 1 },
  { name: '02.mp3', url: '/f/02', size: 1 },
];

afterEach(() => {
  delete (window as { showDirectoryPicker?: unknown }).showDirectoryPicker;
  vi.unstubAllGlobals();
});

describe('DeliveryPanel', () => {
  it('hides the folder button when the API is absent but keeps the zip', () => {
    render(<DeliveryPanel mixId="m1" files={files} />);
    expect(screen.queryByRole('button', { name: /Write to folder/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Use Chrome or Edge/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download zip' })).toBeInTheDocument();
  });

  it('writes files in order when the API is present', async () => {
    const order: string[] = [];
    const dir = {
      getFileHandle: async (name: string, opts?: { create?: boolean }) => {
        if (!opts?.create) throw Object.assign(new Error('x'), { name: 'NotFoundError' });
        return {
          createWritable: async () => ({
            write: async () => {},
            close: async () => {
              order.push(name);
            },
          }),
        };
      },
    };
    Object.assign(window, { showDirectoryPicker: vi.fn().mockResolvedValue(dir) });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(['x']) })),
    );
    const user = userEvent.setup();
    render(<DeliveryPanel mixId="m1" files={files} />);
    await user.click(screen.getByRole('button', { name: /Write to folder/ }));
    expect(await screen.findByText('Wrote 2 files.')).toBeInTheDocument();
    expect(order).toEqual(['01.mp3', '02.mp3']);
  });

  it('asks before overwriting', async () => {
    const written: string[] = [];
    const dir = {
      getFileHandle: async (name: string, opts?: { create?: boolean }) => {
        if (!opts?.create && name !== '02.mp3')
          throw Object.assign(new Error('x'), { name: 'NotFoundError' });
        return {
          createWritable: async () => ({
            write: async () => {},
            close: async () => {
              written.push(name);
            },
          }),
        };
      },
    };
    Object.assign(window, { showDirectoryPicker: vi.fn().mockResolvedValue(dir) });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, blob: async () => new Blob(['x']) })),
    );
    const user = userEvent.setup();
    render(<DeliveryPanel mixId="m1" files={files} />);
    await user.click(screen.getByRole('button', { name: /Write to folder/ }));
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('02.mp3');
    expect(written).toEqual([]);
    await user.click(screen.getByRole('button', { name: 'Overwrite' }));
    await waitFor(() => expect(written).toEqual(['01.mp3', '02.mp3']));
  });

  it('cancelling the overwrite writes nothing', async () => {
    const dir = { getFileHandle: vi.fn(async () => ({})) };
    Object.assign(window, { showDirectoryPicker: vi.fn().mockResolvedValue(dir) });
    const user = userEvent.setup();
    render(<DeliveryPanel mixId="m1" files={files} />);
    await user.click(screen.getByRole('button', { name: /Write to folder/ }));
    await user.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });
});
