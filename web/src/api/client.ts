import type { Genre, Library, Mix, MixRequest } from './types';

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = '';
    try {
      detail = (await res.text()).slice(0, 200);
    } catch {
      // ignore: the status line is enough
    }
    throw new Error(`${res.status} ${res.statusText}${detail ? `: ${detail}` : ''}`.trim());
  }
  return (await res.json()) as T;
}

export const getLibraries = () => request<Library[]>('/api/libraries');

export const getGenres = (libraries: string[]) =>
  request<Genre[]>(`/api/genres?libraries=${encodeURIComponent(libraries.join(','))}`);

export const createMix = (body: MixRequest) =>
  request<{ id: string; status: string }>('/api/mixes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const getMix = (id: string) => request<Mix>(`/api/mixes/${encodeURIComponent(id)}`);

export const listMixes = () => request<Mix[]>('/api/mixes');

export const zipUrl = (id: string) => `/api/mixes/${encodeURIComponent(id)}/zip`;
