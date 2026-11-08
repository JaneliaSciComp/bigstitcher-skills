#!/usr/bin/env bash
# ladder.sh -- the coarse-to-fine loop: for every level run sweep.sh, pick the best unflagged configuration (most inliers,
# tripwires clean), save its registration into the working copy, and shrink the search radius for the next level.
#
#   ladder.sh XML OUTBASE "8,8 4,4 2,2"             levels as DSXY,DSZ pairs, coarse first (inspect_dataset.py proposes them)
#
# Takes the same environment as sweep.sh (BSS, I0, I1, VIEWS, MATCHERS, RADIUS, MODEL_ONNX, PCMATCH, ...). RADIUS given here is
# the FIRST level's search radius (the metadata uncertainty); later levels use max(RADIUS_MIN=20, 3 x the saved solve's max error).
# RME is recomputed per level unless you export it. PREFER_SOLVERS="tr,rigid-tr" prefers those solver models when unflagged.
# Each level's report: OUTBASE/ds<X>-<Z>/report_ds<X>-<Z>.md; the saved XML copies: OUTBASE/ds<X>-<Z>/solved_<label>_<solver>.xml.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
XML=$(readlink -f "${1:?XML}"); OUTBASE=$(readlink -f "${2:?OUTBASE}"); LEVELS=${3:?levels, e.g. "8,8 4,4 2,2"}
RADIUS_MIN=${RADIUS_MIN:-20}
RME_FIXED=${RME:-}
mkdir -p "$OUTBASE"
for lv in $LEVELS; do
  export DSXY=${lv%,*} DSZ=${lv#*,}
  if [ -n "$RME_FIXED" ]; then export RME=$RME_FIXED; else unset RME; fi
  L="ds${DSXY}-${DSZ}"; OUT="$OUTBASE/$L"
  echo "[$(date +%T)] ===== LADDER level $L (radius ${RADIUS:-default}, rme ${RME:-default})" | tee -a "$OUTBASE/ladder.log"
  bash "$HERE/sweep.sh" "$XML" "$OUT" || { echo "sweep failed at level $L" | tee -a "$OUTBASE/ladder.log"; exit 1; }
  read -r LAB SOL MAXERR < <(python3 "$HERE/rank_runs.py" best "$OUT/runs.jsonl" --level "$L" ${PREFER_SOLVERS:+--prefer $PREFER_SOLVERS} 2>>"$OUTBASE/ladder.log")
  [ -n "${LAB:-}" ] || { echo "no usable run at level $L -- stop (see $OUT/report_$L.md)" | tee -a "$OUTBASE/ladder.log"; exit 1; }
  echo "[$(date +%T)] level $L pick: $LAB / $SOL (max error $MAXERR px)" | tee -a "$OUTBASE/ladder.log"
  bash "$HERE/sweep.sh" --save "$XML" "$OUT" "$LAB" "$SOL" >> "$OUTBASE/ladder.log" 2>&1 || { echo "save failed" | tee -a "$OUTBASE/ladder.log"; exit 1; }
  export RADIUS=$(awk "BEGIN{r=3*$MAXERR; print (r<$RADIUS_MIN)?$RADIUS_MIN:r}")
  echo "[$(date +%T)] saved; next search radius $RADIUS" | tee -a "$OUTBASE/ladder.log"
done
echo "[$(date +%T)] ===== LADDER done: $XML holds the last pick; reports under $OUTBASE/ds*/report_*.md" | tee -a "$OUTBASE/ladder.log"
