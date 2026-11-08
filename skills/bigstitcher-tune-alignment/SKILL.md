---
name: bigstitcher-tune-alignment
description: Find good registration (alignment) settings for a BigStitcher / BigStitcher-Spark / multiview-reconstruction dataset by a coarse-to-fine grid search over interest-point detection (DoG and scale-space DoG, downsampling, threshold), pairwise matching (geometric descriptors and the learned translation-invariant descriptor) and the global solver (translation / rigid / affine, regularised), judged by correspondence counts, solver error and transform plausibility. Use it whenever someone asks which detection, matching or solver parameters to use, why an alignment is wrong or has too few correspondences, wants a parameter sweep or a reproducible recipe for a new tiled or multi-objective light-sheet dataset -- even if they only say "align this", "the stitching looks off" or "find the best settings". Covers translation-close alignments including a known manual rotation between view groups; not multi-view rotation registration.
---

# BigStitcher: tune the alignment by a coarse-to-fine grid search

Registration in BigStitcher is detect -> match -> solve, and the three stages hide each other's mistakes: a
solver error of 2 px can come from a perfect alignment of too few points or from a wrong link on one pair. This
skill makes the search systematic: a small grid at a coarse resolution, the winner carried to the next finer
level, every run recorded, and a verdict from the numbers (the `bigstitcher-judge-alignment` skill). It drives the
installed BigStitcher-Spark commands only; no Java source is needed. Pictures of the data are not available
headlessly yet (a `screenshot` command is being added) -- say so and ask the user to look at the flagged pairs in
BigStitcher when the numbers leave doubt.

Scope for now: differential alignments close to translations (tiles, cameras, objectives of one acquisition),
optionally after a known manual rotation of a view group. The learned matcher is NOT rotation tolerant: after a
manual rotation use the geometric matchers only, do not improvise around it.

Scripts live in `scripts/` of this skill (`SKILL_DIR`); the judge's scripts in the sibling skill
`bigstitcher-judge-alignment/scripts/`. The BigStitcher-Spark finder is `../bigstitcher-xml/scripts/find_bigstitcher_spark.sh`.
Read `references/parameters.md` for the flags and ranges, `references/ml-matching.md` for the learned arm.

## 0. Ground rules

- **Never run on the original project.** Every command here saves the XML and writes into `interestpoints.n5` /
  `.zarr`. Make a working copy first (step 1). Keep its `dataset.xml.orig`.
- **Absolute paths** for `-x` (a relative path fails with "Relative path in absolute URI").
- **One Spark job per working copy at a time**; long sweeps run as a background unit (`systemd-run --user ...`
  or `nohup`), never in a foreground shell that dies with the session.
- Keep the judge fixed while you compare: the same RANSAC settings (`-rme`, `-rmni 12`, `-rmir 0`), the same
  `--descriptorRatio 0.85`, the same solver flags across the configurations of one table.
- Record every run: `sweep.sh` writes `runs.jsonl`, the command lines and the logs; the report must let the user
  reproduce the pick in BigStitcher-Spark or the GUI.

## 1. Working copy and first look

```bash
BSS=$(bash SKILL_DIR/../bigstitcher-xml/scripts/find_bigstitcher_spark.sh)      # launcher directory; exit != 0: see that skill
python3 SKILL_DIR/scripts/make_working_copy.py /data/run/dataset.xml /scratch/run_tune          # copies XML + points, links images
python3 SKILL_DIR/scripts/inspect_dataset.py /scratch/run_tune/dataset.xml --setups 0-5 --intensity
```
Restrict every step to the views you align (`--setups` here, `-vi` / `--channelId` for the Java tools): the other
channels of a tile overlap it 100 % and would swamp the pair list. `--intensity` needs a python with numpy and
tensorstore (a pcmatch venv's `.venv/bin/python` has both; `PY=/path/python` for the scripts); without it the
percentiles are skipped and you read min / max off BigStitcher.
`inspect_dataset.py` prints the views and the attributes that vary (tile, channel, angle, illumination), the
GROUPS of views sharing voxel size and image size, the transform stack with a RESET proposal, existing labels
with their detection parameters, the overlapping pairs under the current registration, a downsampling LADDER per
group and (with `--intensity`, needs tensorstore) percentiles of a coarse level for `-i0 / -i1`.

Decide with the user:
- **Which views.** One channel is enough for tiles (the others get the same transforms later). For a large
  mosaic cut TWO disjoint small blocks (2x2 tiles) with `../bigstitcher-xml/scripts/filter_bigstitcher_xml.py`:
  a TUNE block with real content (check the intensity percentiles -- an empty tile has p99.9 at background) and a
  TEST block elsewhere. Tune on the first, confirm on the second, then run the pick on everything.
- **Groups.** Two groups with different voxel sizes or intensity ranges = different objectives / cameras: each
  group gets its own `-i0 -i1` and its downsampling scaled by the voxel-size ratio, detected into the SAME label.
- **Start registration.** Translation-close data: reset to calibration + metadata placement,
  `clear-registrations -x XML --keep N --dryRun` with the proposed N AND the same view selection (other channels
  may carry a different stack), read what goes, then without `--dryRun`. If an existing registration is roughly
  right, keep it: the search radius can then be small. Quantify the metadata error right after the reset:
  `registration_report.py XML --ref XML.orig --setups ...` -- the "moved med/max" column is how far the previous
  registration sat from the metadata; the first level's `RADIUS` = max(20, 3 x that max). The other channels of a
  tile get the transforms afterwards in BigStitcher (Registration -> Duplicate Transformations); no Spark command
  does that yet.
- **Manual rotation.** A group known to be rotated (another objective, a camera at 90 deg):
  `python3 SKILL_DIR/scripts/add_rotation.py XML --setups 6-11 --axis y --degrees 90 --in-place` before anything
  else; afterwards `MATCHERS="geo fastrot"` only (no `emb`, no `pcm`).
- **Intensity range.** One `-i0 -i1` per group: `-i0` = the background level (p0.1 or the camera offset), `-i1`
  = p99.9 .. p99.99 of a bright view. The threshold is relative to `i1 - i0`: a too-high `-i1` (a hot pixel, the
  saturation value) lowers the effective threshold and floods the detection, a too-low one clips bright structure.

## 2. The ladder

Detection downsampling `dsXY` in 8, 4, 2, 1 while every view keeps >= 200 px per axis; `dsZ = round(dsXY * vx / vz)`,
at least 1 (a near-isotropic detection grid). Start at the COARSEST USEFUL level: if a level yields fewer than
~100-200 points per view or most pairs fail, that level is too coarse for the structures (beads vanish when the
DoG sigma spans them) -- move one level finer instead of lowering thresholds. On ds1-stitch (512 x 512 x 86)
downsampling 4 gave DoG + geometric matching 445 points and 2 pairs, scale space + learned matching 935 points and
270 inliers over all views -- usable but thin; downsampling 2 is the first solid level and the ladder proposal
starts there (>= 200 px rule).

Mind the image pyramid: BigStitcher reads the coarsest STORED level that does not exceed the requested
downsampling and downsamples the rest in memory. A request of 8/1 on a pyramid with levels (2,2,1), (4,4,2),
(8,8,4) reads the (2,2,1) level -- 8.6 Gvox per view on a 4096 x 2560 x 3300 tile, minutes per view from a file
server -- while 8/4 reads 0.14 Gvox directly. `inspect_dataset.py` prints the pyramid, what each level would read
and the cheaper `dsZ`; on anisotropic data prefer the cheap variant at the coarse levels (an anisotropic grid is
fine for finding the first registration) and the isotropic one once the registration is close.

Carry the winner's registration into the next level (`sweep.sh --save`), shrink the search radius to ~3x the
previous level's max error, and stop when the average error in physical units stops improving or full
resolution is reached. The detection sigma stays at the default (1.8 DoG / 1.6 scale space); the level is the
scale knob.

## 3. One level of the grid: `sweep.sh`

```bash
export BSS I0=16 I1=255 DSXY=2 DSZ=1 VIEWS="-vi 0,0 -vi 0,1 -vi 0,2 -vi 0,3 -vi 0,4 -vi 0,5" FIXED=0,0
export MATCHERS="geo emb pcm" RADIUS=100 MODEL_ONNX=/path/translation-stack_...neg3r500.onnx PCMATCH=/path/.venv/bin/pcmatch
export EXTRA_DOG="--anisotropy 2.55"            # DoG: 0.8 x the z/x voxel ratio (the GUI's suggestion); scale space defaults to the calibration
bash SKILL_DIR/scripts/sweep.sh /scratch/run_tune/dataset.xml /scratch/run_tune_results/ds2-1
```
What it does, per level: `detect-interestpoints` with `--method DOG -s 1.8` and `--method SCALE_SPACE -s 1.6
--steps 4 --octaves -1`, both `--noiseFactor 2.5 --overlappingOnly --onlyCompareOverlapTiles`; a response
ladder from that one detection (`filter-interestpoints --response` at 5x and 10x the noise floor, the base =
2.5x), one filtered label per (factor, matcher) so correspondence lists never mix; the matchers
`PRECISE_TRANSLATION` (geo), Java `EMBEDDINGS` after `embed-interestpoints` (emb), `pcmatch match` (pcm), all
with `-tm TRANSLATION -rm NONE -rme RME -rmni 12 -rmir 0 --clearCorrespondences`; four solver models with
`--dryRun` (`TRANSLATION`, `RIGID` regularised with `TRANSLATION`, `AFFINE` with `RIGID`, `AFFINE` with
`TRANSLATION`, lambda 0.1); one `runs.jsonl` row per (label, matcher, solver) and `report_<level>.md` ranked by
the judge. Defaults and every knob are in the script header (`DETECTORS`, `FACTORS`, `MATCHERS`, `SOLVERS`,
`RME`, `RADIUS`, `TYPE=BOTH`, `EXTRA_DETECT`, `FLOOR=median`, ...). Re-running skips finished steps. A JVM launch takes seconds;
the slow steps are `embed-interestpoints` on many points (160k points: ~2.5 min on the CPU) and detections that
read fine pyramid levels from a file server (see the ladder section).

Read the result with `rank_runs.py table OUT/runs.jsonl` (the console shows the top 40, `--top N` for more; the
markdown report holds every row) and judge it (step 4). Typical adaptations:
- too few points everywhere -> finer level (not a lower threshold); a single empty view -> drop it (`filter_bigstitcher_xml.py`)
- noise floors differing 3x or more between views (the sweep prints a NOTE; a view with 0 points is the extreme
  case) -> the tool pools the floors as the HIGHEST view, so a bright or structure-rich tile starves the dim ones:
  rerun the level with `FLOOR=median` (a `--dryRun` probe, then `-t` = 2.5 x the median floor; add `--maxSpots
  50000` via `EXTRA_DETECT` so the bright tile does not explode). ds6-mouse-head's test block: 40x spread, one tile
  with 0 points and 3 of 4 views connected with the default pooling
- millions of points on dense tissue -> keep the 10x-20x response filter, `--maxSpots 50000`
- sparse sample -> `TYPE=BOTH` (DoG minima nearly double the correspondences)
- pairs fail only for the learned matcher -> `RADIUS` too small for the metadata error; only for geo -> expected on
  textured samples, keep emb
- rotation > 1 deg or scale / shear flags on a translation-close dataset -> too few or wrong links on that view;
  prefer the regularised models, check the view's pairs

Persist the pick before the next level (the registration is written into the working copy's XML; a pcmatch label's
staged correspondences are committed at that save):
```bash
bash SKILL_DIR/scripts/sweep.sh --save /scratch/run_tune/dataset.xml /scratch/run_tune_results/ds2-1 ss_ds2-1_nf2.5__emb rigid-tr
```

**The whole ladder in one command** -- `ladder.sh` runs `sweep.sh` per level, picks the best UNFLAGGED run
(`rank_runs.py best`: tripwires clean = all views connected, solve error <= the RANSAC tolerance `RME`, rotation /
scale / shear within the translation-close rule; then the matching with the most inliers and the SIMPLEST solver
model whose average error is within 5 % of the lowest -- order `tr, rigid-tr, affine-rigid, affine-tr`,
`PREFER_SOLVERS` / `--err-slack` change it; a rigid or affine increment that buys 0.01 px is not worth stacking),
saves it, re-checks the COMPOSITE
registration against the translation-close rule (the solver only judges its own increment; `LADDER_STRICT=1` stops
on a flag) and shrinks the search radius to max(20, 3 x the saved solve's max error):
```bash
bash SKILL_DIR/scripts/ladder.sh /scratch/run_tune/dataset.xml /scratch/run_tune_results "8,8 4,4 2,2"    # levels DSXY,DSZ coarse first
```
Read every level's `report_<level>.md` anyway: the selector cannot see what the numbers hide (step 4).

**Confirm on the TEST block / apply to the whole dataset**: the same ladder with the grid pinned to the pick, e.g.
`DETECTORS=ss FACTORS=2.5 MATCHERS=emb SOLVERS=rigid-tr bash SKILL_DIR/scripts/ladder.sh TEST.xml TEST_results "4,4 2,2"`;
the TEST block should reach inliers, error and connectivity of the same order as the TUNE block.

## 4. Judge

Load `bigstitcher-judge-alignment` for the thresholds and the verdict template. The judge is the TOTAL number of
inliers (more true correspondences = a better constrained solve); the solver's average / max error, unconnected
views, failed pairs and the per-view transform plausibility (rotation <= 1 deg, |scale - 1| <= 1 %, shear <= 1 % on
translation-close data) are tripwires. `parse_logs.py` reads any log, `registration_report.py XML --ref
XML.orig` shows what the registration changed. Prefer the simplest solver model whose error is not clearly worse.

## 5. Report

Write `report.md` next to the results: the ranked table per level, the pick with the reasons (and what it beat),
the exact BigStitcher-Spark command lines to reproduce it (detect / filter / match / solve) plus the GUI-equivalent
settings, the open doubts (pairs to look at), and -- for large mosaics -- the confirmation on the TEST block.
Point the user at the working copy's XML as the deliverable; never copy anything back into the original project
without being asked. The grid leaves its labels behind (two detections plus one filtered label per factor and
matcher, per level): either apply the pick to a fresh working copy with the pinned ladder, or remove them with
`clear-interestpoints --clearMode REMOVE_LABEL --label <name>` (bigstitcher-xml skill).
