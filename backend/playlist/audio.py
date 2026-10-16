"""Decoding, time-stretching and MP3 encoding, all through external tools.

ffmpeg does the decoding and encoding. Time-stretching prefers the Rubber Band
command-line tool (installed in the image) and falls back to librosa's phase
vocoder where it is missing, which is fine for tests but audibly smeared.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

SR = 44100


def decode(path: str | Path, sr: int = SR, channels: int = 2) -> np.ndarray:
    """Decode any audio file to float32, shape (samples, channels)."""
    out = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-f",
            "f32le",
            "-ac",
            str(channels),
            "-ar",
            str(sr),
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(out, dtype=np.float32).reshape(-1, channels).copy()


def have_rubberband() -> bool:
    return shutil.which("rubberband") is not None


def time_stretch(audio: np.ndarray, rate: float, sr: int = SR) -> np.ndarray:
    """Play `audio` `rate` times faster without changing its pitch."""
    if abs(rate - 1.0) < 1e-4:
        return audio
    if have_rubberband():
        return _rubberband(audio, rate, sr)
    import librosa

    chans = [
        librosa.effects.time_stretch(audio[:, c].copy(), rate=rate) for c in range(audio.shape[1])
    ]
    n = min(len(c) for c in chans)
    return np.stack([c[:n] for c in chans], axis=1).astype(np.float32)


def _rubberband(audio: np.ndarray, rate: float, sr: int) -> np.ndarray:
    import wave

    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
        _write_wav(src, audio, sr)
        # --tempo is a speed-up factor; -3 is the R3 (finer) engine.
        subprocess.run(
            ["rubberband", "-q", "-3", "--tempo", f"{rate:.6f}", str(src), str(dst)],
            check=True,
            capture_output=True,
        )
        with wave.open(str(dst)) as w:
            frames = w.readframes(w.getnframes())
            ch = w.getnchannels()
        pcm = np.frombuffer(frames, dtype=np.int16).reshape(-1, ch)
        return (pcm.astype(np.float32) / 32768.0).copy()


def _write_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    import wave

    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(audio.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def encode_mp3(
    audio: np.ndarray,
    path: Path,
    bitrate_kbps: int = 192,
    sr: int = SR,
    tags: dict[str, str] | None = None,
) -> None:
    """Encode float32 stereo to a constant-bitrate MP3 with ID3 tags.

    CBR, not VBR: cheap players' decoders cope with it best.
    """
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-f",
        "f32le",
        "-ac",
        str(audio.shape[1]),
        "-ar",
        str(sr),
        "-i",
        "-",
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate_kbps}k",
        "-id3v2_version",
        "3",
    ]
    for k, v in (tags or {}).items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(path))
    subprocess.run(
        cmd,
        input=np.ascontiguousarray(audio, dtype=np.float32).tobytes(),
        check=True,
        capture_output=True,
    )
