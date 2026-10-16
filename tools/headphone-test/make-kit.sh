#!/usr/bin/env bash
# Builds the swimming-headphone test kit: gap, order and resume tests.
# Output: ./out/{gap,order,resume}/*.mp3, all CBR 192k MP3 (libmp3lame).
set -euo pipefail
cd "$(dirname "$0")"
OUT=out; TMP=tmp
rm -rf "$OUT" "$TMP"; mkdir -p "$OUT"/{gap,order,resume} "$TMP"
SR=44100
enc() { ffmpeg -v error -y -i "$1" -c:a libmp3lame -b:a 192k -ar $SR -ac 2 "${@:3}" "$2"; }

# ── 1. Gap test ─────────────────────────────────────────────────────────────
# 150 s of a steady 330 Hz tone plus a click on every beat at 128 BPM
# (0.46875 s/beat), split into 6 files. Odd cuts land on a beat, even cuts
# half-way between beats, so you can hear which kind of cut hides a gap.
ffmpeg -v error -y \
  -f lavfi -i "sine=frequency=330:sample_rate=$SR:duration=150" \
  -f lavfi -i "aevalsrc='0.9*sin(2*PI*1500*t)*exp(-60*mod(t\,0.46875))*lt(mod(t\,0.46875)\,0.05)':s=$SR:d=150" \
  -filter_complex "[0]volume=0.25[a];[1][a]amix=inputs=2:normalize=0[m]" -map "[m]" -ac 2 "$TMP/gap.wav"
cuts=(0 30.0 60.234375 90.0 120.234375 150)
for i in 1 2 3 4 5; do
  s=${cuts[$((i-1))]}; e=${cuts[$i]}
  ffmpeg -v error -y -i "$TMP/gap.wav" -ss "$s" -to "$e" "$TMP/gap$i.wav"
  enc "$TMP/gap$i.wav" "$OUT/gap/0$i - gap test.mp3" -metadata title="Gap test $i" -metadata track="$i/5" -metadata album="Headphone test kit"
done

# ── 2. Order test ───────────────────────────────────────────────────────────
# Five spoken files. Filename order, ID3 track order and copy order all
# differ, so the sequence you hear says which one the player uses:
#   by filename (1..5):  Charlie Echo Alpha Delta Bravo
#   by ID3 track:        Alpha Bravo Charlie Delta Echo
#   by copy order:       Delta Bravo Echo Charlie Alpha   (load-kit.sh copies in this order)
# word:filename:track
for spec in Alpha:3:1 Bravo:5:2 Charlie:1:3 Delta:4:4 Echo:2:5; do
  IFS=: read -r w file track <<<"$spec"
  say -o "$TMP/$w.aiff" "This is $w. $w."
  ffmpeg -v error -y -i "$TMP/$w.aiff" -af "apad=pad_dur=1.5" "$TMP/$w.wav"
  enc "$TMP/$w.wav" "$OUT/order/$file.mp3" -metadata title="$w" -metadata track="$track/5" -metadata album="Headphone test kit"
done

# ── 3. Resume test ──────────────────────────────────────────────────────────
# 30 minutes: a soft 330 Hz tone with "Minute N" spoken at the start of each
# minute. Switch off part-way through, switch on, and listen for the number.
: > "$TMP/resume.txt"
for n in $(seq 1 30); do
  say -o "$TMP/m$n.aiff" "Minute $n"
  ffmpeg -v error -y -i "$TMP/m$n.aiff" -f lavfi -i "sine=frequency=330:sample_rate=$SR:duration=60" \
    -filter_complex "[0]aresample=$SR,apad=whole_dur=60[v];[1]volume=0.08[t];[v][t]amix=inputs=2:normalize=0,atrim=0:60[m]" \
    -map "[m]" -ac 2 "$TMP/r$n.wav"
  echo "file 'r$n.wav'" >> "$TMP/resume.txt"
done
ffmpeg -v error -y -f concat -safe 0 -i "$TMP/resume.txt" -c copy "$TMP/resume.wav"
enc "$TMP/resume.wav" "$OUT/resume/30-minute resume test.mp3" -metadata title="Resume test" -metadata album="Headphone test kit"

rm -rf "$TMP"
du -sh "$OUT"/*
