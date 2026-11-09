#!/usr/bin/env bash
# Headless BigDataViewer pictures of a BigStitcher project with BigStitcher-Spark's `screenshot` (0.1.4+): the selected
# views under their CURRENT registration -- by default every overlapping pair, view A magenta / view B green, maximum
# projection over the pair's overlap box, planes xy and xz, display ranges from the percentiles inside the overlap --
# plus the manifest screenshots.json and one summary line per image. Read-only: the XML is never written.
#
#   render_pairs.sh XML OUTDIR [screenshot flags...]
#     render_pairs.sh /abs/solved.xml /abs/results/shots                        # --pairs overlapping --planes xy,xz --json
#     render_pairs.sh solved.xml shots --pairs '34,35;38,39' --planes xy        # the pairs pick_pairs.py named
#     render_pairs.sh dataset.xml.orig shots_before                             # the start registration, same pairs
#     render_pairs.sh solved.xml shots_all --overview --single --planes xy,xz   # anything screenshot accepts
#   env  VIEWS       view selection passed through, e.g. "-vi 0,0 -vi 0,1" or "--channelId 0" (default: all views of the
#                    first timepoint; one timepoint per call)
#        SCREENSHOT  the screenshot launcher; else $BSS/screenshot, else the install find_bigstitcher_spark.sh returns,
#                    else the newest $HOME/bigstitcher-spark*/screenshot (where install-release -d puts a release)
#        SHOT_BUDGET cost cap as the data volume a run projects, in Gpx^3 of the global frame (box area x projection depth,
#                    summed over the images of a dry run; default 50 = roughly five minutes here; ds6-mouse-head's 2x2 block
#                    is 21, ds5-fly-brain-3's 120). Above it the projections cover a slab around the box
#                    centre -- a quarter of the deepest box, at least SHOT_SLAB (default 400) global px -- instead of the
#                    whole box (--depth); when the flags carry explicit display ranges (--min/--max or --range) the cap
#                    uses --level 1 instead (full depth from the next coarser pyramid level). A full-depth projection reads
#                    the whole overlap column at the finest level: ds5-fly-brain-3's test block (21,000 px deep) takes
#                    505 s, ds6-mouse-head's 157 s; fewer frames (--step) or a smaller image do not help, and a pinned
#                    --level with --auto ranges stalls for minutes (the percentiles are then sampled at that level).
#                    SHOT_BUDGET=0 disables the cap; explicit --depth, --level, --render or --dryRun are left alone.
#                    --render slice is the cheap choice for dense tissue, where a projection blurs anyway. A slab can
#                    miss structure that sits away from the box centre in depth (ds6-mouse-head's beads lie in a shell):
#                    rerun the suspicious pairs with SHOT_BUDGET=0 --pairs 'A,B'.
#   exit 3: no screenshot launcher (BigStitcher-Spark older than 0.1.4) -- say so and name the pairs to look at instead.
#   Note: screenshot reports argument errors with exit 0 and an 'ERROR:' line; this wrapper turns them into exit 1.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
XML=$(readlink -f "${1:?XML}") || exit 1
OUT=$(readlink -m "${2:?OUTDIR}"); shift 2

find_shot() {
  [ -n "${SCREENSHOT:-}" ] && [ -x "$SCREENSHOT" ] && { echo "$SCREENSHOT"; return; }
  [ -n "${BSS:-}" ] && [ -x "$BSS/screenshot" ] && { echo "$BSS/screenshot"; return; }
  local f="$HERE/../../bigstitcher-xml/scripts/find_bigstitcher_spark.sh" d
  [ -x "$f" ] && d=$("$f" 2>/dev/null) && [ -x "$d/screenshot" ] && { echo "$d/screenshot"; return; }
  ls -1d "$HOME"/bigstitcher-spark*/screenshot 2>/dev/null | sort -V | tail -1
}
SHOT=$(find_shot)
if [ -z "$SHOT" ] || [ ! -x "$SHOT" ]; then
  echo "no 'screenshot' launcher found (BigStitcher-Spark 0.1.4+). Set SCREENSHOT=/path/to/screenshot, or install a release:" >&2
  echo "  curl -fsSLO https://raw.githubusercontent.com/JaneliaSciComp/BigStitcher-Spark/main/install-release && bash install-release -d ~/bigstitcher-spark -t <threads> -m <GB>   (0.2.0 or later)" >&2
  echo "Without pictures: name the pairs to look at in BigDataViewer (quality-metrics.md section 3)." >&2
  exit 3
fi

what=0; json=0; planes=0
for a in "$@"; do case $a in --pairs|--overview|--single|--transform) what=1;; --json) json=1;; --planes) planes=1;; esac; done
args=()
[ $what = 1 ] || { args+=(--pairs overlapping); [ $planes = 1 ] || args+=(--planes xy,xz); }
[ $json = 1 ] || args+=(--json)
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Duser.language=en -Duser.country=US"
mkdir -p "$OUT"

# cost cap: a dry run lists every planned image as "<w> x <h>, scale <s>, mip over <D> px in steps of <S> px";
# the data a projection reads is about (w / s) x (h / s) x D global px^3 at the finest level (scale >= 1), s^3 of that
# from the coarser level the renderer picks when the scale is below 1; summed over the run
BUDGET=${SHOT_BUDGET:-50}
case " $* " in *" --depth "*|*" --level "*|*" --render "*|*" --dryRun "*) BUDGET=0;; esac
if awk "BEGIN{exit !($BUDGET > 0)}"; then
  # shellcheck disable=SC2086
  "$SHOT" -x "$XML" -o "$OUT" ${VIEWS:-} "${args[@]}" "$@" --dryRun > "$OUT/screenshot_dryrun.log" 2>&1
  read -r VOL DMAX < <(grep -E ', [0-9]+ x [0-9]+, scale' "$OUT/screenshot_dryrun.log" \
        | sed -E 's/.*, ([0-9]+) x ([0-9]+), scale ([0-9.]+)(, mip over ([0-9.]+) px in steps of ([0-9.]+) px)?.*/\1 \2 \3 \5/' \
        | awk '{d = ($4 != "") ? $4 : 1; f = ($3 < 1) ? $3 * $3 * $3 : 1; t += ($1 / $3) * ($2 / $3) * d * f; if (d > m) m = d} END {printf "%.2f %d", t / 1e9, m}')
  if [ -n "${VOL:-}" ] && awk "BEGIN{exit !($VOL > $BUDGET)}"; then
    case " $* " in
      *" --min "*|*" --range "*)
        echo "planned data volume $VOL Gpx^3 > SHOT_BUDGET $BUDGET: rendering from pyramid level 1 (--level 1; display ranges are explicit)" >&2
        args+=(--level 1);;
      *)
        SLAB=$(awk "BEGIN{q = int($DMAX / 4); m = ${SHOT_SLAB:-400}; print (q > m) ? q : m}")
        echo "planned data volume $VOL Gpx^3 > SHOT_BUDGET $BUDGET: projecting a $SLAB px slab around the box centre (--depth $SLAB; deepest box $DMAX px) instead of the whole box" >&2
        args+=(--depth "$SLAB");;
    esac
  fi
fi
echo "$SHOT -x $XML -o $OUT ${VIEWS:-} ${args[*]} $*" > "$OUT/screenshot.cmd"
t0=$SECONDS
# shellcheck disable=SC2086
"$SHOT" -x "$XML" -o "$OUT" ${VIEWS:-} "${args[@]}" "$@" > "$OUT/screenshot.log" 2>&1; st=$?
grep -E "^ERROR|overlapping pair|skipping pair|Dry run|image\(s\) to render" "$OUT/screenshot.log" >&2
if [ $st -ne 0 ] || grep -q '^ERROR' "$OUT/screenshot.log"; then
  echo "screenshot failed (exit $st, see $OUT/screenshot.log)" >&2; grep -v '^\[' "$OUT/screenshot.log" | tail -5 >&2; exit 1
fi
grep -q 'Dry run' "$OUT/screenshot.log" && exit 0
M=$OUT/screenshots.json
[ -f "$M" ] || { echo "no manifest $M written (see $OUT/screenshot.log)" >&2; exit 1; }
python3 - "$M" "$((SECONDS - t0))" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"{len(m['images'])} image(s) in {sys.argv[2]} s ({m['render']}); manifest {sys.argv[1]}")
for e in m["images"]:
    box = ""
    if e.get("boxMin"):
        box = " box " + "x".join(str(int(round(hi - lo))) for lo, hi in zip(e["boxMin"], e["boxMax"])) + " px"
    rng = ", ".join(f"s{k} {v[0]:.0f}..{v[1]:.0f}" for k, v in e["ranges"].items())
    mip = f" over {e['depth']:.0f} px/{e['frames']} frames" if e.get("depth") else ""
    print(f"  {e['file']:<32} {e['kind']:<8} setups {str(e['setups']):<10} {e.get('plane') or '-':<3} {e['width']}x{e['height']}"
          f"  1 global px = {e['scale']:.3f} image px{box}  {e['render']}{mip}  ranges {rng}  {e['renderMillis']} ms")
PY
