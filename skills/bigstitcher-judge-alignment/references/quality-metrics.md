# Reading an alignment: what the numbers mean, what is good, what is a red flag

Units: BigStitcher's global frame is calibrated pixels (x/y voxels; z multiplied by the calibration ratio).
Errors printed by the matcher and the solver are in that frame. Convert to physical units with the x voxel size.

## 1. Correspondences (the judge)

`match-interestpoints` prints one line per view pair: `Remaining inliers after RANSAC: I of C (P%) with average
error E`. The TOTAL of inliers over all pairs is the primary score of a configuration: more true correspondences
constrain the global solve better and make it robust to a few wrong ones. Read it with the detection count in
mind (inliers / detections per view = the yield).

| observation | reading |
|---|---|
| a pair with >= 50 inliers, inlier ratio >= 10 %, error well below `-rme` | solid |
| 12-30 inliers (the `-rmni` floor is 12) | usable but fragile: one wrong link can tilt a translation; prefer a configuration that gives more, or regularise the solver |
| `Model found but not enough remaining inliers (a/12)` | the descriptor found candidates but no consistent set: wrong scale of structure (change the level or sigma), too few points in the overlap, or the pair does not really overlap (check the overlap size in the registration report) |
| `Not enough correspondences found N` / `NO Model found` | too few detections in the overlap: lower the threshold (response ladder), detect `--type BOTH`, or the overlap estimate is wrong (metadata far off: no `--overlappingOnly`, large `-sr`) |
| inlier ratio < 2 % with a tiny error | suspicious: RANSAC fits a few coincidental points. Compare the pair's translation with its neighbours (the solver's residuals will show it) |
| the geometric and the learned matcher disagree by 10x on one pair | the pair has a problem the easier matcher hides (repetitive structure, mirrored content); look at it |
| inliers roughly equal across all four solver models | expected: the pairwise matching is the same, only the solve differs |

Purity (what fraction of the inliers is truly correct) is not observable without truth; RANSAC and the solver
absorb a few percent of wrong ones. Treat a collapse of the inlier count or an exploding solver error as the
tripwire, not a purity estimate.

## 2. The global solve (the tripwires)

`solver` prints `Total number of connected views: N (M missing ...)`, the error block `Avg / Min / Max Error`, and
`Transformation Models:` per view.

| quantity | expect | red flag |
|---|---|---|
| connected views | all selected views | any missing view: the final XML leaves it where the metadata put it; find its pairs in the match log |
| Avg Error | about the localisation error of the detections: ~0.5-1 voxel at the detection resolution, i.e. roughly 0.5-1 x dsXY global px (ds1-stitch full resolution: ~1 px; 4 um isotropic data at ds 1: ~2 px); RANSAC accepted every pair at residuals <= `-rme`, typically a third of it | avg ABOVE `-rme`: the pairs contradict each other (a wrong pair, a non-rigid sample, a wrong model) -- `rank_runs.py` flags it; max error >> avg: one bad pair -- iterative solving (`--method ONE_ROUND_ITERATIVE`, `TWO_ROUND_ITERATIVE`) drops it. ds6-mouse-head test block: 4 of 4 views "connected" with 286 inliers and avg 30 px at rme 20 = a wrong registration that looked connected |
| avg error that does NOT drop between coarse and fine levels | the limit is the sample (non-rigid, chromatic shift), not the parameters: stop refining |
| per-view transforms, translation-close problems | rotation <= 1 deg, scales within 1 %, shear <= 1 % (`registration_report.py` and `parse_logs.py` compute them) | an affine with scale 0.97 or shear 0.03 on one view = too few points or wrong links on that view; use `RIGID` regularised with `TRANSLATION`, or `AFFINE` regularised with `RIGID` (lambda 0.1-0.3), or fix more points |
| rigid rotation of several degrees where none is expected | the sample moved, or a view is flipped / rotated by acquisition; the learned matcher is not rotation tolerant: use FAST_ROTATION or a manual rotation first |
| change vs the start (`--ref`): corner displacement | a few px to tens of px for stage metadata; hundreds for a sloppy stage | a single view moving far more than the rest: its pairs are wrong |

The solver judges the INCREMENT it computed; a coarse-to-fine chain stacks several increments. Judge the composite
registration too (`registration_report.py` on the saved XML): three rigid increments of 0.3-0.7 deg each can sum
to a rotation no single level would have flagged.

Model choice on translation-close data: `TRANSLATION` is the safest with few points; `RIGID` regularised with
`TRANSLATION` absorbs small rotations; `AFFINE` regularised with `RIGID` or `TRANSLATION` absorbs chromatic / optical
scaling but needs many well-spread correspondences per view. Pick the simplest model whose residual is not
clearly worse than the next one.

## 3. The pictures (not available headlessly yet)

A headless `screenshot` command for BigStitcher-Spark is planned. Until it exists, ask the user to look in BigStitcher / BigDataViewer at the pairs the report flags (two views in
two colours, the overlap region, a maximum projection and an xz slice), and check:

- beads / nuclei appear once (white when the colours overlap), not as coloured doubles -> misalignment by the
  double's distance; a constant double over the whole overlap = a translation error, a double growing along an
  axis = a rotation / scale error
- the seam between tiles shows no step in continuous structure (vessels, tissue boundaries)
- repetitive structure (nuclei lattices, bead grids) is the classic failure: an alignment shifted by one period
  looks locally perfect and shows up only as a step at the far end of the overlap or in the solver's residuals
- empty or saturated tiles: a view with no signal cannot be registered; park it (fixed to the metadata) rather
  than let it drag the solve

## 4. Verdict template

```
## Alignment verdict: <xml>  (label <l>, <tm>/<rm> lambda)
Connected: N of M views (missing: ...)           Pairs: P with >= rmni inliers, Q failed (worst 5 with reason)
Inliers: total T (per pair min/median/max)       Solver error: avg / min / max px (global frame; ~= physical um)
Transforms vs expectation (translation-close): max rotation deg, scale range, max shear -- OK / FLAG <views>
Change vs start: median / max corner displacement px per view
Verdict: GOOD | USABLE, CHECK pairs ... | BAD because ...      Next: <one concrete change>
```
