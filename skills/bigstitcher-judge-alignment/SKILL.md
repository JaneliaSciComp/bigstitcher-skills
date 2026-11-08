---
name: bigstitcher-judge-alignment
description: Judge whether a BigStitcher / BigStitcher-Spark / multiview-reconstruction registration is good, from the numbers in the detect / match / solver logs and the XML itself -- inliers per view pair, failed pairs, connected views, solver residual error, and the plausibility of the solved transforms (rotation, scale, shear on data that should only translate) -- and say what to change next. Use it whenever someone asks "is this alignment good", "did the registration work", "why are there so few correspondences", "which of these two runs is better", wants a verdict on a solver log or an XML, or after any alignment run (also those driven by bigstitcher-tune-alignment). Headless pictures are not available yet; the skill says what to look at in BigDataViewer instead.
---

# BigStitcher: judge an alignment

An alignment is a chain of claims: the detector found real structure, the matcher linked the right points across
each overlapping pair, the solver found transforms consistent with all links, and the result looks right on the
data. Each claim has numbers; this skill reads them in that order and ends with a verdict and ONE concrete next
step. The scripts in `scripts/` do the parsing; `references/quality-metrics.md` holds the thresholds, the red
flags and the verdict template -- read it the first time.

## Inputs to collect

- the XML after the solve (and, if it exists, the start: `dataset.xml.orig` or the XML before the solve)
- the logs: `detect-interestpoints`, `match-interestpoints` (or `pcmatch match`), `solver` -- or, when the run
  was in the GUI, the numbers the user can read off (points per view, inliers per pair, the solver's errors)
- what the data should do: tiles that only translate? a known rotation? one or several objectives?

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
5. **Pictures.** Not possible headlessly yet (a `screenshot` command for BigStitcher-Spark is being added; see
   `~/BDV_SCREENSHOT_HANDOFF.md`). Until then, name the pairs to look at in BigStitcher / BigDataViewer -- the
   failed ones, the ones with the fewest inliers, the view with the largest change -- and what to look for:
   doubled beads or nuclei (a translation error of the double's distance), a step at a tile seam, a repetitive
   structure shifted by one period, empty tiles.
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
Verdict: GOOD | USABLE, CHECK pairs ... | BAD because ...      Next: <one concrete change>
```

## Scripts

- `scripts/parse_logs.py LOG... [--pairs] [--json OUT]` -- stdlib; recognises detect / match (incl. EMBEDDINGS,
  multi-consensus, ICP) / solver / pcmatch logs; sums the pairs, keeps the last error block, derives rotation,
  scales and shear from the printed models. Numbers must use '.' as decimal separator (`JAVA_TOOL_OPTIONS=
  "-Duser.language=en -Duser.country=US"`).
- `scripts/registration_report.py XML [--ref XML] [--setups 0-5] [--json OUT]` -- numpy; per-view transform
  decomposition and translation-close flags, overlapping pairs, change vs a reference XML.

Use absolute paths for the XML. Both scripts only read.
