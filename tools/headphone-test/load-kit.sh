#!/usr/bin/env bash
# Load one test onto the mounted headphones, removing any earlier kit files
# first (only files this kit created - nothing else on the device is touched).
#   load-kit.sh gap|order|resume /Volumes/<HEADPHONES>
set -euo pipefail
cd "$(dirname "$0")"
test=${1:?gap, order or resume}; vol=${2:?mount point, e.g. /Volumes/SWIM}
[ -d "$vol" ] || { echo "no such volume: $vol" >&2; exit 1; }

# Remove earlier kit files (and their ._ AppleDouble twins, if Finder made any).
for f in out/*/*.mp3; do
  b=$(basename "$f"); rm -f "$vol/$b" "$vol/._$b"
done

case $test in
  order) files=(4 5 2 1 3) ;;   # Delta Bravo Echo Charlie Alpha
  gap)   files=("01 - gap test" "02 - gap test" "03 - gap test" "04 - gap test" "05 - gap test") ;;
  resume) files=("30-minute resume test") ;;
  *) echo "unknown test: $test" >&2; exit 1 ;;
esac

for f in "${files[@]}"; do
  COPYFILE_DISABLE=1 cp -X "out/$test/$f.mp3" "$vol/"
  sync; sleep 1     # one at a time, so the FAT directory order is the copy order
  echo "copied $f.mp3"
done
diskutil eject "$vol" >/dev/null && echo "ejected $vol - unplug and listen"
