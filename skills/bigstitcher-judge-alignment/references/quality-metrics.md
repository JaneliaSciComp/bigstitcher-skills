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

## 3. The pictures (BigStitcher-Spark `screenshot`, 0.1.4+)

`render_pairs.sh XML OUTDIR` runs `screenshot -x XML -o OUTDIR --pairs overlapping --planes xy,xz --json` (view selection
from `VIEWS`, one timepoint per call, the XML is never written, no DISPLAY needed): one PNG per overlapping pair and
plane, `pair_tp<T>_s<A>_s<B>_<plane>.png`, view A magenta and view B green, a maximum projection over the whole overlap
box, the box fitted into 1024 px wide at most 4 image px per global px (`--maxScale`; a thin overlap strip becomes a
small image, not a blown-up one), display ranges = the 0.1 / 99.9 percentiles of each view INSIDE the overlap box.
`screenshots.json` lists per image the box, the scale (image px per global px), the viewer transform, the depth and
the ranges; the wrapper prints one line per image from it. Other modes pass straight through: `--overview` (all
views, one colour each, a quarter-depth projection), `--single` (every view alone in grey: empty or saturated tiles),
`--pairs 'A,B;C,D'`, `--planes yz`, `--render slice`, `--depth D`, `--step`, `--level L`, `--width`, `--min/--max`,
`--range S=a:b`, `--dryRun`. `pick_pairs.py` names the pairs worth a picture when there are many; `contact_sheet.py`
tiles a run into one captioned image for the first pass (triage only -- fine doubles need the full-size PNG).

Read them in this order:

- **white = the two views agree** there. Magenta / green doubles = misaligned by the double's distance in image px
  divided by the image's `scale` (e.g. 8 px apart at scale 4 = 2 global px). A constant double over the whole overlap
  is a translation error; a double that grows along an axis is a rotation or scale error; doubles in xz / yz but not
  in xy are a z error the xy projection hides -- always look at both planes.
- **the seam**: continuous structure (vessels, tissue boundaries, a bead lattice) shows no step across the overlap.
- **repetitive structure** (nuclei lattices, bead grids) is the classic failure: an alignment shifted by one period
  looks locally perfect and shows up only as a step at the far end of the overlap or in the solver's residuals --
  compare the picture with the solver error, they must tell the same story.
- **dense tissue**: a projection over a deep overlap is a blur in which nothing can double; use `--render slice` or a
  thin `--depth 20` (global px) there, and the xz plane, where the projection depth is the short tile axis.
- **empty or saturated tiles**: black or noise-only in `--single`, no structure in their pair images; a view with no
  signal cannot be registered -- park it (fixed to the metadata) rather than let it drag the solve.
- **before vs after**: the same command on `dataset.xml.orig` into `OUTDIR_before`. The overlap boxes and scales
  differ once the registration moved, so compare by eye, not pixel by pixel; the start usually shows the metadata
  error as a double, the solve should turn it white.
- **calibrate your eye** once per dataset: `apply-transformation -x COPY.xml --translate 20,0,0 -vi 0,S` on a scratch
  copy, then the same pair pictures -- that is what a 20 px error looks like at this scale (BigStitcher-Spark's own
  test does exactly this).

Two things the pictures always show and that mean nothing: the margin around the overlap box is single-view
territory and therefore pure magenta on one side and pure green on the other; and camera noise differs between the
views, so at 4 image px per voxel a faint colour speckle covers the whole overlap -- misalignment is structure that
doubles, not speckle. A pair whose printed display range spans a few counts (`ranges s43 0..3, s46 0..3`) has no
signal in its overlap box: the picture is amplified noise (solid white or pink), and inliers reported for such a pair
are suspect (ds6-mouse-head test block, the diagonal pair of the empty tile).

Cost (this workstation, 2026-11-08; the block runs overlapped each other, so read them as ranges): a full-depth
projection reads the whole overlap column at the finest pyramid level, so the depth of the box decides. ds1-stitch,
six tiles, 11 pairs x 2 planes: 7 s. ds6-mouse-head 2x2 block (tiles 2000 x 1600 x 3600 px on a network share): 157 s
whole box (the default; `SHOT_BUDGET` 50 Gpx^3 leaves it alone at 21), 145 s with a quarter-depth slab and 112 s with a
400 px slab -- both lose the head's surface, the beads sit in a shell that a slab through the box centre misses -- 65 s
with `--min 0 --max 400` (the cap then reads pyramid level 1 at full depth; no percentile sampling, about a minute of
the total). ds5-fly-brain-3 2x2 block (overlap boxes 21,000 px deep, 120 Gpx^3 -> the cap projects the quarter slab): 505 s whole box, 248 s quarter slab, 79 s
400 px slab, 80 s as slices. ds9-mv-cardona-exm overview of 26 views (Zarr v3): 13 s. Fewer projection frames
(`--step`) or a smaller image do not help -- the voxels still have to be read; a pinned `--level` with automatic ranges
makes `--auto` sample that level and stalls for minutes on big data (use `--level` only with `--min/--max`).
`dataset.xml.orig` is a valid `-x`. Plan a minute or more per saved level on big blocks, seconds on small projects.

## 4. Verdict template

```
## Alignment verdict: <xml>  (label <l>, <tm>/<rm> lambda)
Connected: N of M views (missing: ...)           Pairs: P with >= rmni inliers, Q failed (worst 5 with reason)
Inliers: total T (per pair min/median/max)       Solver error: avg / min / max px (global frame; ~= physical um)
Transforms vs expectation (translation-close): max rotation deg, scale range, max shear -- OK / FLAG <views>
Change vs start: median / max corner displacement px per view
Pictures: N pairs in OUT/shots (xy, xz) -- clean | doubles on sA-sB (~D px) | z offset on ... | not rendered (<why>)
Verdict: GOOD | USABLE, CHECK pairs ... | BAD because ...      Next: <one concrete change>
```
