import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api/client';
import { RequestForm } from './RequestForm';

vi.mock('../api/client');

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getLibraries).mockResolvedValue([
    { key: '1', title: 'Music', kind: 'cc' },
    { key: '2', title: 'Purchased', kind: 'purchased' },
  ]);
  vi.mocked(api.getGenres).mockResolvedValue([
    { name: 'Trance', count: 412 },
    { name: 'House', count: 90 },
  ]);
  vi.mocked(api.createMix).mockResolvedValue({ id: 'abc', status: 'queued' });
});

describe('RequestForm', () => {
  it('loads libraries and genres, and labels licence kinds', async () => {
    render(<RequestForm onCreated={() => {}} />);
    expect(await screen.findByLabelText(/Trance/)).toBeInTheDocument();
    expect(screen.getByText('CC (publishable)')).toBeInTheDocument();
    expect(screen.getByText('Purchased (private)')).toBeInTheDocument();
    expect(screen.getByText('(412)')).toBeInTheDocument();
    expect(api.getGenres).toHaveBeenCalledWith(['Music', 'Purchased']);
  });

  it('posts the right body for split output', async () => {
    const onCreated = vi.fn();
    const user = userEvent.setup();
    render(<RequestForm onCreated={onCreated} />);
    await user.click(await screen.findByLabelText(/Trance/));
    await user.click(screen.getByRole('button', { name: '90' }));
    await user.click(
      screen
        .getByLabelText(/Purchased \(private\)/)
        .closest('label')
        ?.querySelector('input') as HTMLElement,
    );
    await user.click(screen.getByRole('button', { name: 'Make mix' }));
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('abc'));
    expect(api.createMix).toHaveBeenCalledWith({
      genres: ['Trance'],
      duration_min: 90,
      libraries: ['Music'],
      output: 'split',
    });
  });

  it('posts single output with a seed', async () => {
    const user = userEvent.setup();
    render(<RequestForm onCreated={() => {}} />);
    await user.click(await screen.findByLabelText(/House/));
    await user.click(screen.getByLabelText(/Single continuous file/));
    await user.type(screen.getByLabelText('Seed (optional)'), '42');
    await user.click(screen.getByRole('button', { name: 'Make mix' }));
    await waitFor(() => expect(api.createMix).toHaveBeenCalled());
    expect(api.createMix).toHaveBeenCalledWith({
      genres: ['House'],
      duration_min: 60,
      libraries: ['Music', 'Purchased'],
      output: 'single',
      seed: 42,
    });
  });

  it('reroll fills the seed and submit is disabled with no genre', async () => {
    const user = userEvent.setup();
    render(<RequestForm onCreated={() => {}} />);
    await screen.findByLabelText(/Trance/);
    expect(screen.getByRole('button', { name: 'Make mix' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Reroll' }));
    expect(screen.getByLabelText('Seed (optional)')).not.toHaveValue(null);
  });

  it('shows an error when the POST fails', async () => {
    vi.mocked(api.createMix).mockRejectedValue(new Error('500 boom'));
    const user = userEvent.setup();
    render(<RequestForm onCreated={() => {}} />);
    await user.click(await screen.findByLabelText(/Trance/));
    await user.click(screen.getByRole('button', { name: 'Make mix' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('500 boom');
  });
});
