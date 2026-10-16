import { useRef, useState } from 'react';
import type { MixFile } from '../api/types';
import { card } from './ui';

export function Preview({ files }: { files: MixFile[] }) {
  const [index, setIndex] = useState(0);
  const autoplay = useRef(false);
  const current = files[Math.min(index, files.length - 1)];

  if (!current) return null;

  return (
    <section className={`${card} space-y-2`} aria-label="Preview">
      <h3 className="text-base font-semibold">Preview</h3>
      <p className="text-sm text-mist">
        Now playing: {current.name} ({index + 1} of {files.length})
      </p>
      {/* biome-ignore lint/a11y/useMediaCaption: music has no captions */}
      <audio
        data-testid="preview-audio"
        controls
        className="w-full"
        src={current.url}
        autoPlay={autoplay.current}
        onEnded={() => {
          if (index < files.length - 1) {
            autoplay.current = true;
            setIndex(index + 1);
          }
        }}
      />
    </section>
  );
}
