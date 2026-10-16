export type LibraryKind = 'cc' | 'purchased';

export interface Library {
  key: string;
  title: string;
  kind: LibraryKind;
}

export interface Genre {
  name: string;
  count: number;
}

export type OutputMode = 'split' | 'single';

export interface MixRequest {
  genres: string[];
  duration_min: number;
  libraries: string[];
  output: OutputMode;
  seed?: number;
}

export type MixStatus = 'queued' | 'planning' | 'rendering' | 'done' | 'failed';

export interface PlanTrack {
  title: string;
  artist: string;
  library: string;
  bpm: number;
  camelot: string;
  start_s: number;
}

export interface MixPlan {
  tracks: PlanTrack[];
  duration_s: number;
  tempo_bpm: number;
}

export interface MixFile {
  name: string;
  url: string;
  size: number;
  start_s?: number;
  duration_s?: number;
}

export interface ManifestTrack {
  title: string;
  artist: string;
  library: string;
  licence: string;
  attribution: string;
}

export interface Manifest {
  publishable: boolean;
  tracks: ManifestTrack[];
  attribution_text: string;
}

export interface Mix {
  id: string;
  status: MixStatus;
  progress: number;
  message: string;
  title?: string;
  created_at?: number;
  genres?: string[];
  error?: string | null;
  plan?: MixPlan;
  files?: MixFile[];
  manifest?: Manifest;
}
