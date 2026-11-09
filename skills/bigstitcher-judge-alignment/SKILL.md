---
name: bigstitcher-judge-alignment
description: Judge whether a BigStitcher / BigStitcher-Spark / multiview-reconstruction registration is good, from the numbers in the detect / match / solver logs and the XML itself -- inliers per view pair, failed pairs, connected views, solver residual error, and the plausibility of the solved transforms (rotation, scale, shear on data that should only translate) -- and say what to change next. Use it whenever someone asks "is this alignment good", "did the registration work", "why are there so few correspondences", "which of these two runs is better", wants a verdict on a solver log or an XML, or after any alignment run (also those driven by bigstitcher-tune-alignment). Renders headless BigDataViewer pictures of the view pairs with BigStitcher-Spark's `screenshot` command (0.1.4+) and reads them.
---

# BigStitcher: judge an alignment

An alignment is a chain of claims: the detector found real structure, the matcher linked the right points across
each overlapping pair, the solver found transforms consistent with all links, and the result looks right on the
data. Each claim has numbers, the last one has pictures; this skill reads them in that order and ends with a
verdict and ONE concrete next step. The scripts in `scripts/` do the parsing and the rendering;
`references/quality-metrics.md` holds the thresholds, the red flags, how to read the pictures and the verdict
template -- read it the first time.

## Inputs to collect

- the XML after the solve (and, if it exists, the start: `dataset.xml.orig` or the XML before the solve)
- the logs: `detect-interestpoints`, `match-interestpoints` (or `pcmatch match`), `solver` -- or, when the run
  was in the GUI, the numbers the user can read off (points per view, inliers per pair, the solver's errors)
- what the data should do: tiles that only translate? a known rotation? one or several objectives?
- a BigStitcher-Spark install with `screenshot` (0.1.4+) for the pictures; `render_pairs.sh` finds it (`SCREENSHOT=`,
  `BSS=`, the xml skill's finder, `~/bigstitcher-spark*/`) and exits 3 when there is none

Without the logs the XML alone still gives the transform plausibility and the overlap geometry; say which parts
of the verdict are missing.

## Procedure

1. **Detections.** `python3 SKILL_DIR/scripts/parse_logs.py detect.log --pairs`: points per view, the noise floor
   and the threshold. A view with far fewer points than its neighbours is empty, dark or saturated (check the
   intensity range); hundreds to tens of thousands per view is the usual band.
2. **Pairwise matching.** `parse_logs.py match.log --pairs`: inliers / candidates / error per pair, the failed
   pairs with their reason. The TOTAL of inliers is the score of a configuration; the failed pairs are the first
   place to look (`Not enough correspondences` = too few detections in the overlap; `not enough remaining
   inliers (a/12)` = candidates without a consistent set: wrong scale of structure, a pair that barely overlaps,
   or a rotation the matcher cannot absorb).
3. **Global solve.** `parse_logs.py solve.log --pairs`: connected views (all? which are missing?), the last
   `Avg / Min / Max Error` block, removed links, and the per-view models with their rotation / scales / shear.
   Expect the average error near the localisation precision of the detections (about 0.5-1 voxel at the
   detection resolution, in global px); a max error far above the average points at one bad pair.
4. **Transforms.** `python3 SKILL_DIR/scripts/registration_report.py solved.xml --ref start.xml`: the registration
   part of every view decomposed (rotation deg, scales, shear; translation-close rule: rotation <= 1 deg,
   |scale - 1| <= 1 %, shear <= 1 %), the overlapping pairs with their relative rotation and scale, and the change
   against the start (corner displacement per view, relative change per pair). A view that moved far more than
   the others, or an affine that drifted into scale / shear, means wrong or too few links on that view.
5. **Pictures.** `bash SKILL_DIR/scripts/render_pairs.sh /abs/solved.xml OUT/shots` renders every overlapping pair
   of the selected views (env `VIEWS="-vi 0,0 -vi 0,1"` or `VIEWS="--channelId 0"`; one timepoint per call) under the
   current registration: view A magenta, view B green, a maximum projection over the pair's overlap box in the xy
   and xz planes, display ranges from the percentiles inside the overlap; `OUT/shots/screenshots.json` records the
   camera of every image, the summary prints the scale (image px per global px). Which pairs: all of them up to
   about a dozen; beyond that `python3 SKILL_DIR/scripts/pick_pairs.py match.log --solve solve.log --report
   report.json` names the failed pairs, the fewest inliers, the largest error and change, and one good pair as the
   reference, as the `--pairs 'A,B;C,D'` argument for `render_pairs.sh`. Then LOOK at them (the Read tool shows
   PNGs): `contact_sheet.py OUT/shots --plane xy --captions captions.json` tiles them for a first pass, the suspicious
   pairs at full size afterwards. White = the views agree; magenta / green doubles = misaligned by the double's
   distance divided by the scale; a double only in xz is a z error the xy projection hides; a tile that stays black
   in `--single` is empty. The same command on `dataset.xml.orig` into `OUT/shots_before` shows what the solve
   changed. The reading rules, the caveats (dense tissue wants `--render slice`) and the cost are in
   quality-metrics.md section 3. No `screenshot` launcher (exit 3): say so and name the pairs to look at in
   BigDataViewer -- the failed ones, the fewest inliers, the view with the largest change.
6. **Verdict.** Use the template below; rank GOOD / USABLE-CHECK / BAD by the tripwires, not by taste. When two
   runs are compared, same numbers side by side, the configuration with more inliers wins unless a tripwire
   (unconnected view, error far above the detection precision, implausible transform) fires.

## Verdict template

```
## Alignment verdict: <xml>  (label <l>, <tm>/<rm> lambda)
Connected: N of M views (missing: ...)           Pairs: P with >= rmni inliers, Q failed (worst 5 with reason)
Inliers: total T (per pair min/median/max)       Solver error: avg / min / max px (global frame)
Transforms vs expectation (translation-close): max rotation deg, scale range, max shear -- OK / FLAG <views>
Change vs start: median / max corner displacement px per view
Pictures: N pairs in OUT/shots (xy, xz) -- clean | doubles on sA-sB (~D px) | z offset on ... | not rendered (<why>)
Verdict: GOOD | USABLE, CHECK pairs ... | BAD because ...      Next: <one concrete change>
```

## Scripts

- `scripts/parse_logs.py LOG... [--pairs] [--json OUT]` -- stdlib; recognises detect / match (incl. EMBEDDINGS,
  multi-consensus, ICP) / solver / pcmatch logs; sums the pairs, keeps the last error block, derives rotation,
  scales and shear from the printed models. Numbers must use '.' as decimal separator (`JAVA_TOOL_OPTIONS=
  "-Duser.language=en -Duser.country=US"`).
- `scripts/registration_report.py XML [--ref XML] [--setups 0-5] [--json OUT]` -- numpy; per-view transform
  decomposition and translation-close flags, overlapping pairs, change vs a reference XML.
- `scripts/render_pairs.sh XML OUTDIR [screenshot flags]` -- BigStitcher-Spark `screenshot` with the judge's defaults
  (`--pairs overlapping --planes xy,xz --json`), any flag of the command passes through (`--pairs 'A,B'`, `--overview`,
  `--single`, `--render slice`, `--depth`, `--level`, `--width`, `--min/--max`, `--dryRun`); prints one line per image
  with the scale and the display ranges. A dry run first estimates the data volume the projections read (box area
  x depth) and, above `SHOT_BUDGET` (50 Gpx^3, about five minutes), projects a slab of a quarter of the deepest box (at least `SHOT_SLAB`
  = 400 px) around the box centre instead of the whole box -- or, when `--min/--max` are given, the full depth from
  pyramid level 1. A full-depth projection of a 21,000 px deep overlap reads the whole column at full resolution
  (8 min for the ds5-fly-brain-3 block); a slab can miss structure away from the box centre, so rerun doubtful
  pairs with `SHOT_BUDGET=0 ... --pairs 'A,B'`. `--render slice` is the cheap choice for dense tissue. Never pin
  `--level` with automatic ranges on big data: the percentiles are then sampled at that level, for minutes.
- `scripts/pick_pairs.py MATCH_LOG [--solve LOG] [--report JSON] [--captions OUT.json]` -- stdlib; the pairs worth a
  picture and why, as the `--pairs` value; captions (inliers, error) per pair for the sheet.
- `scripts/contact_sheet.py SHOTS_DIR [--plane xy] [--captions JSON]` -- Pillow; one captioned sheet of a run's images.

Use absolute paths for the XML. All scripts only read; `screenshot` never writes the XML.
