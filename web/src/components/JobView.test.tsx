import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/client';
import type { Mix } from '../api/types';
import { JobView } from './JobView';

vi.mock('../api/client', async (orig) => ({
  ...(await orig<typeof import('../api/client')>()),
  getMix: vi.fn(),
}));

const files = [
  { name: '01 - Trance mix.mp3', url: '/api/mixes/m1/files/01.mp3', size: 5 * 1024 * 1024 },
  { name: '02 - Trance mix.mp3', url: '/api/mixes/m1/files/02.mp3', size: 4 * 1024 * 1024 },
];
const plan = {
  tracks: [
    { title: 'Sunrise', artist: 'DJ A', library: 'Music', bpm: 138, camelot: '8A', start_s: 0 },
  ],
  duration_s: 3600,
  tempo_bpm: 138,
};
const done = (publishable: boolean): Mix => ({
  id: 'm1',
  status: 'done',
  progress: 1,
  message: 'Finished',
  plan,
  files,
  manifest: {
    publishable,
    attribution_text: 'Sunrise by DJ A (CC BY)',
    tracks: [
      { title: 'Sunrise', artist: 'DJ A', library: 'Music', licence: 'CC BY', attribution: 'x' },
    ],
  },
});

beforeEach(() => {
  vi.resetAllMocks();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('JobView', () => {
  it('polls until done, then shows files and the plan', async () => {
    vi.mocked(api.getMix)
      .mockResolvedValueOnce({
        id: 'm1',
        status: 'planning',
        progress: 0.2,
        message: 'Choosing tracks',
      })
      .mockResolvedValueOnce({
        id: 'm1',
        status: 'rendering',
        progress: 0.6,
        message: 'Mixing',
        plan,
      })
      .mockResolvedValue(done(true));
    render(<JobView id="m1" pollMs={5} />);
    expect(await screen.findByText(/Choosing tracks/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('done'));
    expect(screen.getByText('01 - Trance mix.mp3')).toBeInTheDocument();
    expect(screen.getByText('5.0 MiB')).toBeInTheDocument();
    expect(screen.getByText(/DJ A – Sunrise/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download zip' })).toHaveAttribute(
      'href',
      '/api/mixes/m1/zip',
    );
    const calls = vi.mocked(api.getMix).mock.calls.length;
    await new Promise((r) => setTimeout(r, 30));
    expect(vi.mocked(api.getMix).mock.calls.length).toBe(calls);
  });

  it('shows the publishable badge', async () => {
    vi.mocked(api.getMix).mockResolvedValue(done(true));
    render(<JobView id="m1" pollMs={5} />);
    expect(await screen.findByText('Publishable (all CC)')).toBeInTheDocument();
    expect(screen.queryByText(/Private: contains purchased music/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Attribution text')).toHaveValue('Sunrise by DJ A (CC BY)');
  });

  it('shows the private badge', async () => {
    vi.mocked(api.getMix).mockResolvedValue(done(false));
    render(<JobView id="m1" pollMs={5} />);
    expect(await screen.findByText('Private: contains purchased music')).toBeInTheDocument();
    expect(screen.queryByText('Publishable (all CC)')).not.toBeInTheDocument();
  });

  it('reports a failed mix', async () => {
    vi.mocked(api.getMix).mockResolvedValue({
      id: 'm1',
      status: 'failed',
      progress: 0.3,
      message: 'ffmpeg died',
    });
    render(<JobView id="m1" pollMs={5} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('ffmpeg died');
  });

  it('keeps polling after a transient error', async () => {
    vi.mocked(api.getMix).mockRejectedValueOnce(new Error('503')).mockResolvedValue(done(true));
    render(<JobView id="m1" pollMs={5} />);
    expect(await screen.findByText('Publishable (all CC)')).toBeInTheDocument();
  });
});
