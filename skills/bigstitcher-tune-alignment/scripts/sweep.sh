#!/usr/bin/env bash
# sweep.sh -- ONE level of the coarse-to-fine alignment grid on a BigStitcher WORKING COPY (never the original project):
#   detect (DoG / scale-space at the noise floor) -> filter (response ladder, one plain label per matcher)
#   -> match (geometric descriptors / Java EMBEDDINGS / pcmatch) -> solver --dryRun per model -> runs.jsonl + report
#
#   sweep.sh XML OUTDIR                              run the grid of this level
#   sweep.sh --save XML OUTDIR LABEL SOLVER          run the chosen solver for real: the registration is written into XML
#
# Required environment:   BSS   directory with the BigStitcher-Spark launchers (find_bigstitcher_spark.sh)
#                         I0 I1 the dataset's (group's) intensity range for the detection
#                         DSXY DSZ  the downsampling of this level
# Optional (defaults):    DETECTORS="dog ss"   NF=2.5 (threshold = NF x noise floor)   SIGMA_DOG=1.8 SIGMA_SS=1.6   TYPE=MAX|MIN|BOTH
#                         FACTORS="2.5 5 10"   response ladder in multiples of the noise floor (<= NF = the unfiltered detection)
#                         OVERLAP="--overlappingOnly --onlyCompareOverlapTiles"   EXTRA_DETECT="" (both detectors, e.g. --maxSpots 50000)
#                         EXTRA_DOG="" (e.g. --anisotropy 2.55 = 0.8 x the z/x voxel ratio, the GUI's suggestion)   EXTRA_SS="" (default anisotropy = calibration)
#                         FLOOR=highest|median  how the per-view noise floors are pooled for the threshold: the tool's rule (highest view) or a
#                                               --dryRun probe + -t = NF x the MEDIAN floor (dim tiles next to a bright one; labels get the suffix m)
#                         MATCHERS="geo emb"   (geo = PRECISE_TRANSLATION, fastrot = FAST_ROTATION, emb = Java EMBEDDINGS, pcm = pcmatch)
#                         RME (default max(2, 2.5*DSXY) global px)   RMNI=12   RMIR=0   SR="" (geo search radius; empty = unlimited)
#                         RADIUS=100  (emb / pcm search radius = the registration's uncertainty in global px)   RATIO=0.85   MINSIM=0.3
#                         MODEL_ONNX=hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64 (emb; default = the Hugging Face hub model,
#                                    downloaded once into ~/.bigstitcher/models; a local .onnx with its .onnx.json next to it also works)
#                         PCMATCH=/path/to/pcmatch   DEVICE=cuda
#                         SOLVERS="tr rigid-tr affine-rigid affine-tr"   FIXED="" (e.g. 0,0; empty = the solver's default, the first view)
#                         VIEWS="" (Java view selection, e.g. "-vi 0,34 -vi 0,35" or "--channelId 2 --tileId 2,3,6,7")
#                         PCM_VIEWS="" (pcmatch view selection; default = the -vi entries of VIEWS)   SPARK="--localSparkBindAddress"
# Every command line and its log land in OUTDIR; a finished (label, matcher, solver) is skipped on re-runs.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-python3}
RANK=$HERE/rank_runs.py
for c in "$HERE/parse_logs.py" "$HERE/../../bigstitcher-judge-alignment/scripts/parse_logs.py" "${BIGSTITCHER_SKILLS:-/nonexistent}/bigstitcher-judge-alignment/scripts/parse_logs.py"; do
  [ -f "$c" ] && PARSE=$c && break
done
[ -n "${PARSE:-}" ] || { echo "parse_logs.py not found (install bigstitcher-judge-alignment next to this skill)" >&2; exit 2; }
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Duser.language=en -Duser.country=US"

MODE=grid
if [ "${1:-}" = "--save" ]; then MODE=save; shift; fi
XML=$(readlink -f "${1:?XML}"); OUT=$(readlink -f "${2:?OUTDIR}"); mkdir -p "$OUT"
: "${BSS:?BSS (launcher directory) is required}"
SPARK=${SPARK-"--localSparkBindAddress"}
VIEWS=${VIEWS:-}
PCM_VIEWS=${PCM_VIEWS:-$(echo "$VIEWS" | tr ' ' '\n' | grep -A1 -x -- '-vi' | tr '\n' ' ' | sed 's/--//g')}
SOLVERS=${SOLVERS:-"tr rigid-tr affine-rigid affine-tr"}
FIXED=${FIXED:-}
MODEL_ONNX=${MODEL_ONNX:-hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64}
SECS=0

log() { echo "[$(date +%T)] $*" | tee -a "$OUT/sweep.log" >&2; }
run() { local name=$1; shift; local t0=$SECONDS
  log "RUN $name: $*"; echo "$*" > "$OUT/$name.cmd"
  "$@" > "$OUT/$name.log" 2>&1; local st=$?; SECS=$((SECONDS - t0))
  [ $st -ne 0 ] && log "  -> exit $st after ${SECS}s (see $OUT/$name.log)"; return $st; }
has_label() { grep -q "label=\"$1\"" "$XML"; }
solve_flags() { case $1 in
  tr) echo "-tm TRANSLATION -rm NONE";;  rigid) echo "-tm RIGID -rm NONE";;  affine) echo "-tm AFFINE -rm NONE";;
  rigid-tr) echo "-tm RIGID -rm TRANSLATION --lambda ${LAMBDA:-0.1}";;
  affine-rigid) echo "-tm AFFINE -rm RIGID --lambda ${LAMBDA:-0.1}";;
  affine-tr) echo "-tm AFFINE -rm TRANSLATION --lambda ${LAMBDA:-0.1}";;
  *) log "unknown solver '$1' (tr | rigid | affine | rigid-tr | affine-rigid | affine-tr)"; return 1;; esac; }

if [ $MODE = save ]; then
  LAB=${3:?LABEL}; S=${4:?SOLVER}; flags=$(solve_flags "$S") || exit 1
  run "save_${LAB}_$S" "$BSS/solver" -x "$XML" -s IP -l "$LAB" $VIEWS ${FIXED:+-fv $FIXED} $flags ${SOLVER_EXTRA:-} $SPARK || exit 1
  cp "$XML" "$OUT/solved_${LAB}_$S.xml"
  $PY "$PARSE" "$OUT/save_${LAB}_$S.log" | tee -a "$OUT/sweep.log"
  REP=$HERE/../../bigstitcher-judge-alignment/scripts/registration_report.py
  PYNP=$PY; $PYNP -c 'import numpy' 2>/dev/null || { [ -n "${PCMATCH:-}" ] && [ -x "$(dirname "$PCMATCH")/python" ] && PYNP=$(dirname "$PCMATCH")/python; }
  if [ -f "$REP" ] && $PYNP -c 'import numpy' 2>/dev/null; then
    SETUPS=$(echo "$VIEWS" | tr ' ' '\n' | grep -A1 -x -- '-vi' | grep -v -- '-vi\|--' | cut -d, -f2 | paste -sd, -)
    $PYNP "$REP" "$XML" ${SETUPS:+--setups "$SETUPS"} ${XML_ORIG:+--ref "$XML_ORIG"} $( [ -f "$XML.orig" ] && [ -z "${XML_ORIG:-}" ] && echo --ref "$XML.orig") | tee "$OUT/registration_after_${LAB}_$S.txt"
  else log "registration_report.py skipped (needs a python with numpy: set PY=/path/python)"; fi
  log "SAVED: $LAB / $S written into $XML (copy: $OUT/solved_${LAB}_$S.xml)"
  exit 0
fi

: "${I0:?I0 (min intensity) is required}"; : "${I1:?I1 (max intensity) is required}"; : "${DSXY:?DSXY is required}"; : "${DSZ:?DSZ is required}"
LEVEL="ds${DSXY}-${DSZ}"
DETECTORS=${DETECTORS:-"dog ss"}; NF=${NF:-2.5}; SIGMA_DOG=${SIGMA_DOG:-1.8}; SIGMA_SS=${SIGMA_SS:-1.6}; TYPE=${TYPE:-MAX}
FACTORS=${FACTORS:-"2.5 5 10"}; OVERLAP=${OVERLAP-"--overlappingOnly --onlyCompareOverlapTiles"}; EXTRA_DETECT=${EXTRA_DETECT:-}
MATCHERS=${MATCHERS:-"geo emb"}; RME=${RME:-$(awk "BEGIN{r=2.5*$DSXY; print (r<2)?2:r}")}; RMNI=${RMNI:-12}; RMIR=${RMIR:-0}; SR=${SR:-}
RADIUS=${RADIUS:-100}; RATIO=${RATIO:-0.85}; MINSIM=${MINSIM:-0.3}; DEVICE=${DEVICE:-cuda}
log "=== level $LEVEL on $XML -> $OUT | detectors [$DETECTORS] nf $NF type $TYPE factors [$FACTORS] | matchers [$MATCHERS] rme $RME rmni $RMNI radius $RADIUS sr '${SR}' | solvers [$SOLVERS] | views '${VIEWS}'"

detect() { # detector -> LABEL_BASE NOISE_FLOOR
  local d=$1 flags lab="${1}_${LEVEL}_nf${NF}"; [ "$TYPE" != MAX ] && lab="${lab}_$(echo "$TYPE" | tr 'A-Z' 'a-z')"
  case $d in dog) flags="--method DOG -s $SIGMA_DOG ${EXTRA_DOG:-}";; ss) flags="--method SCALE_SPACE -s $SIGMA_SS --steps 4 --octaves -1 ${EXTRA_SS:-}";;
    *) log "unknown detector '$d' (dog | ss)"; return 1;; esac
  local thr_flags="--noiseFactor $NF"
  if [ "${FLOOR:-highest}" = median ]; then
    # the tool pools the per-view noise floors as the HIGHEST view; a bright / structure-rich tile then starves the dim ones.
    # FLOOR=median: probe the floors with a --dryRun pass, then detect with -t = NF x the MEDIAN floor (label suffix 'm').
    lab="${lab}m"
    if ! { has_label "$lab" && [ -s "$OUT/detect_$lab.log" ]; }; then
      run "probe_$lab" "$BSS/detect-interestpoints" -x "$XML" -l "$lab" $flags --noiseFactor "$NF" -dsxy "$DSXY" -dsz "$DSZ" -i0 "$I0" -i1 "$I1" \
          --type "$TYPE" $OVERLAP $EXTRA_DETECT $VIEWS $SPARK --dryRun || return 1
      MEDFLOOR=$($PY "$PARSE" "$OUT/probe_$lab.log" --json - | $PY -c 'import json,sys; r=json.load(sys.stdin); p=r.get("noise_floor_pooled") or {}; print(p.get("median", 0))')
      [ "$MEDFLOOR" != 0 ] || { log "no noise floor in the probe log"; return 1; }
      thr_flags="-t $(awk "BEGIN{printf \"%.6g\", $NF*$MEDFLOOR}")"
      log "probe $lab: median noise floor $MEDFLOOR (highest $($PY "$PARSE" "$OUT/probe_$lab.log" --json - | $PY -c 'import json,sys; print((json.load(sys.stdin).get("noise_floor_pooled") or {}).get("max", 0))')) -> $thr_flags"
    fi
  fi
  if has_label "$lab" && [ -s "$OUT/detect_$lab.log" ]; then log "label $lab exists, detection skipped"
  else run "detect_$lab" "$BSS/detect-interestpoints" -x "$XML" -l "$lab" $flags $thr_flags -dsxy "$DSXY" -dsz "$DSZ" -i0 "$I0" -i1 "$I1" \
           --type "$TYPE" $OVERLAP $EXTRA_DETECT $VIEWS $SPARK || return 1; fi
  LABEL_BASE=$lab
  read -r NOISE_FLOOR NPTS MINPTS SPREAD < <($PY "$PARSE" "$OUT/detect_$lab.log" --json - | $PY -c 'import json,sys; r=json.load(sys.stdin); t=r.get("threshold") or {}
p=r.get("noise_floor_pooled") or {}; fl=t.get("noise_floor") or (p.get("median", 0) if "'"${FLOOR:-highest}"'" == "median" else p.get("max", 0))
print(fl, r["totals"]["points"], r["totals"]["min"], (p.get("max", 0) / p["median"]) if p.get("median") else 0)')
  if [ "${FLOOR:-highest}" = median ]; then        # an explicit -t run prints no floors: take them from the probe log
    [ -n "${MEDFLOOR:-}" ] || MEDFLOOR=$($PY "$PARSE" "$OUT/probe_$lab.log" --json - | $PY -c 'import json,sys; print((json.load(sys.stdin).get("noise_floor_pooled") or {}).get("median", 0))')
    NOISE_FLOOR=$MEDFLOOR
    SPREAD=$($PY "$PARSE" "$OUT/probe_$lab.log" --json - | $PY -c 'import json,sys; p=json.load(sys.stdin).get("noise_floor_pooled") or {}; print((p.get("max", 0) / p["median"]) if p.get("median") else 0)')
  fi
  log "detected $lab: $NPTS points (min per view $MINPTS), noise floor $NOISE_FLOOR = ${FLOOR:-highest} view (spread highest/median ${SPREAD}x), threshold $(awk "BEGIN{print $NF*$NOISE_FLOOR}")"
  awk "BEGIN{exit !($SPREAD > 3)}" && log "  NOTE: the per-view noise floors differ by ${SPREAD}x -- the highest view is probably structure, not noise; consider -t NF x the median floor, or a finer level"
  [ "$MINPTS" -lt 100 ] && log "  NOTE: a view has only $MINPTS points -- too coarse a level or too high a threshold; expect failed pairs"
  return 0
}
make_label() { # base factor matcher -> echoes the FILTERED label of this (factor, matcher), created with filter-interestpoints.
  # One filtered label per matcher keeps the correspondence lists apart; filtered labels follow their base (the detector
  # parameters stay readable, one embedding of the base serves every filter). Factor <= NF = all points of the base.
  local base=$1 f=$2 m=$3 resp tag
  if awk "BEGIN{exit !($f <= $NF)}"; then resp=0; tag="${base}__${m}"
  else resp=$(awk "BEGIN{printf \"%.6g\", $f*$NOISE_FLOOR}"); tag="${base}_x${f}__${m}"; fi
  if ! has_label "$tag"; then
    run "filter_$tag" "$BSS/filter-interestpoints" -x "$XML" -l "$base" --response "$resp" --newLabel "$tag" $VIEWS $SPARK >&2 || return 1
  fi
  echo "$tag"
}
match() { local lab=$1 m=$2 base=${3:-$1}
  if [ -s "$OUT/match_$lab.log" ] && grep -q -E 'Done|RANSAC: [0-9]+ correspondences' "$OUT/match_$lab.log"; then log "match $lab exists, skipped"; return 0; fi
  case $m in
    geo) run "match_$lab" "$BSS/match-interestpoints" -x "$XML" -l "$lab" $VIEWS -m PRECISE_TRANSLATION -tm TRANSLATION -rm NONE \
            -rme "$RME" -rmni "$RMNI" -rmir "$RMIR" ${SR:+-sr $SR} --clearCorrespondences $SPARK;;
    fastrot) run "match_$lab" "$BSS/match-interestpoints" -x "$XML" -l "$lab" $VIEWS -m FAST_ROTATION -tm TRANSLATION -rm NONE \
            -rme "$RME" -rmni "$RMNI" -rmir "$RMIR" --clearCorrespondences $SPARK;;
    emb) if [ ! -f "$OUT/embed_$base.done" ]; then      # one embedding per BASE label serves every filtered label of it
           run "embed_$base" "$BSS/embed-interestpoints" -x "$XML" -l "$base" $VIEWS --model "$MODEL_ONNX" $SPARK && touch "$OUT/embed_$base.done" || return 1
         fi
         run "match_$lab" "$BSS/match-interestpoints" -x "$XML" -l "$lab" $VIEWS -m EMBEDDINGS -sr "$RADIUS" --descriptorRatio "$RATIO" --minSimilarity "$MINSIM" \
            -tm TRANSLATION -rm NONE -rme "$RME" -rmni "$RMNI" -rmir "$RMIR" --clearCorrespondences $SPARK;;
    pcm) [ -n "${PCMATCH:-}" ] || { log "matcher pcm needs PCMATCH (path to the pcmatch executable)"; return 1; }
         run "match_$lab" "$PCMATCH" match -x "$XML" -l "$lab" $PCM_VIEWS --radius "$RADIUS" --ratio "$RATIO" -tm translation -rme "$RME" -rmni "$RMNI" -rmir "$RMIR" \
            ${PCM_MODEL:+--model "$PCM_MODEL"} --write-correspondences --no-candidates --device "$DEVICE";;
    *) log "unknown matcher '$m' (geo | fastrot | emb | pcm)"; return 1;;
  esac
}
solve_dry() { local lab=$1 s=$2 flags; flags=$(solve_flags "$s") || return 1
  if [ -s "$OUT/solve_${lab}_$s.log" ] && grep -q 'Done' "$OUT/solve_${lab}_$s.log"; then log "solve $lab/$s exists, skipped"; return 0; fi
  run "solve_${lab}_$s" "$BSS/solver" -x "$XML" -s IP -l "$lab" $VIEWS ${FIXED:+-fv $FIXED} $flags --dryRun ${SOLVER_EXTRA:-} $SPARK; }
record() { # detector base factor label matcher solver seconds
  grep -q "\"label\": \"$4\", \"matcher\": \"$5\", \"solver\": \"$6\"" "$OUT/runs.jsonl" 2>/dev/null && return 0
  $PY "$RANK" add "$OUT/runs.jsonl" --meta level="$LEVEL" detector="$1" base="$2" factor="$3" label="$4" matcher="$5" solver="$6" dsxy="$DSXY" dsz="$DSZ" \
      nf="$NF" type="$TYPE" rme="$RME" rmni="$RMNI" radius="$RADIUS" sr="$SR" xml="$XML" \
      --detect "$OUT/detect_$2.log" --match "$OUT/match_$4.log" --solve "$OUT/solve_$4_$6.log" --seconds "$7" | tee -a "$OUT/sweep.log"; }

for d in $DETECTORS; do
  detect "$d" || continue
  for f in $FACTORS; do
    for m in $MATCHERS; do
      lab=$(make_label "$LABEL_BASE" "$f" "$m") || continue
      t0=$SECONDS
      match "$lab" "$m" "$LABEL_BASE" || continue
      tm=$((SECONDS - t0))
      for s in $SOLVERS; do
        solve_dry "$lab" "$s" && record "$d" "$LABEL_BASE" "$f" "$lab" "$m" "$s" "$((tm + SECONDS - t0 - tm))"
      done
    done
  done
done
$PY "$RANK" table "$OUT/runs.jsonl" --level "$LEVEL" --md "$OUT/report_$LEVEL.md" | tee -a "$OUT/sweep.log"
log "=== level $LEVEL done; report: $OUT/report_$LEVEL.md"
