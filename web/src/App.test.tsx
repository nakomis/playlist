import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { App } from './App';
import * as api from './api/client';

vi.mock('./api/client');

describe('App', () => {
  it('shows the form and recent mixes', async () => {
    vi.mocked(api.getLibraries).mockResolvedValue([]);
    vi.mocked(api.getGenres).mockResolvedValue([]);
    vi.mocked(api.listMixes).mockResolvedValue([
      { id: 'old1', status: 'done', progress: 1, message: '' },
    ]);
    render(<App />);
    expect(screen.getByRole('heading', { name: 'Playlist' })).toBeInTheDocument();
    expect(await screen.findByText('old1')).toBeInTheDocument();
    expect(screen.getByRole('form', { name: 'New mix' })).toBeInTheDocument();
  });
});
