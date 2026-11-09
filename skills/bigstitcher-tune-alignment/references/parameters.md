# BigStitcher-Spark parameters for the alignment grid search

Flags as of BigStitcher-Spark 0.2.0 (November 2026; the first release with `SCALE_SPACE`, `embed-interestpoints` and `screenshot`). They move between releases: run `<command> --help`
before building a command line, and prefer the long names in scripts. All commands take `-x <absolute path or URI>`
(a relative path fails with "Relative path in absolute URI"), the view selection `-vi 'tp,setup'` (repeatable) or
`--tileId / --channelId / --angleId / --illuminationId / --timepointId` (comma lists, ranges `0-5`), `--dryRun`, and
`--localSparkBindAddress` (needed on most workstations). Every command loads and SAVES the XML (except `--dryRun`
and the solver's dry run), so point them at a working copy.

## detect-interestpoints

| flag | meaning | typical |
|---|---|---|
| `-l LABEL` | name of the interest-point list; encode the settings (`ss_ds4-1_nf2.5`) | |
| `--method DOG` | Difference-of-Gaussian at ONE sigma (the classic) | `-s 1.8` |
| `--method SCALE_SPACE` | scale-space DoG: all structure sizes from `-s` upward, per-point sigma stored; `--steps 4 --octaves -1` (all octaves), `--finestLevel` (default on: keep every finest-level extremum, beads are no scale extrema) | `-s 1.6` |
| `-t T` or `--noiseFactor F` | threshold on the image normalised to [0,1], or F x the noise floor (robust std of the finest DoG level, pooled as the HIGHEST of the views -- a bright tile next to dim ones starves them; `sweep.sh FLOOR=median` probes the floors and passes `-t` = F x the median instead). 2.5 = the GUI's default. The log prints every view's floor and the derived threshold | `--noiseFactor 2.5` |
| `-dsxy D -dsz Z` | downsampling for the detection. Choose Z so the detection grid is near-isotropic: `Z = round(D * vx / vz)`, at least 1 | 8/2 for 0.157 x 1 um data, 4/4 for isotropic |
| `-i0 A -i1 B` | REQUIRED intensity range, one per dataset (or per view group); the threshold is relative to B - A. Use the bulk of the signal (p0.1 .. p99.9 of a coarse level), not a hot pixel | |
| `--anisotropy R` | z/x voxel ratio for the Gaussians (DOG default: isotropic in pixels; SCALE_SPACE default: the calibration). The GUI suggests 0.8 x the calibration ratio because the PSF blurs z more than the calibration says | |
| `--type MAX | MIN | BOTH` | DoG maxima (bright blobs), minima, or both. BOTH nearly doubles the correspondences on sparse samples; minima explode on dense tissue texture (25x) | MAX |
| `--overlappingOnly` | detect only inside regions overlapping other selected views (by the current registration) -- faster, fewer points off the seams. WARNING: other channels / illuminations of the same volume overlap it fully; add `--onlyCompareOverlapTiles` so only other tiles / angles count as partners | on for tiles |
| `--maxSpots N [--maxSpotsPerOverlap]` | keep the N brightest per view (per overlap region) | 50000 when a view explodes |
| `--medianFilter R` | divide by the median-filtered image before detection (uneven background) | |
| `--localization NONE | QUADRATIC` | subpixel refinement | QUADRATIC |
| `--blockSize`, `--maxPartitions`, `--prefetch` | Spark plumbing; on NFS full-resolution reads use FEW tasks (`-Dspark.master=local[16]`) -- 64 tasks thrashed a 2-day job that took 48 min with 16 | |

Log lines to read (parse_logs.py does): `noise floor of tpId=T setupId=S: F`, `threshold = F x FLOOR = T`, and after
`Computed all interest points, statistics:` one `tpId=T setupId=S: N` per view.

## filter-interestpoints (make the threshold ladder from ONE detection)

`-x XML -l BASE --response 'a' | 'a-b' | 'a,b,c'` keeps |DoG response| >= a (a..b; several entries = one label
each), `--sigma`, `--intensity` with the same grammar, `--keepPoints N --keepBy response|intensity|sigma
--keepMode highest|median|lowest`, `--newLabel NAME` (one filter only), `--copy` stores a PLAIN label (a copy
of the points) instead of a filtered label that follows its base. Detect once at the noise floor, then filter at
2x, 4x, 8x the floor: the registration decides which threshold is right (dense tissue wants ~16-20x the floor,
sparse beads the floor itself). The sweep script gives every (factor, matcher) its own FILTERED label (not a copy: a copy loses
the detector parameters pcmatch needs, and filtered labels share their base's embedding) so matchers never share correspondence lists.

## match-interestpoints

| flag | meaning | typical |
|---|---|---|
| `-m PRECISE_TRANSLATION` | geometric local descriptors (3 neighbours, `-n`, `-r` redundancy, `-s` significance 3), translation-invariant, no search radius needed (`-sr` optional) | the default geometric arm |
| `-m FAST_ROTATION` | rotation-invariant geometric hashing; use when the views may be rotated against each other (unknown manual rotation) | |
| `-m EMBEDDINGS` | the learned descriptors stored by `embed-interestpoints` (one 64-D vector per point); needs `-sr` (the registration's uncertainty in global px: 20 for a pre-registered set, 300-500 for raw stage metadata), `--descriptorRatio 0.85`, `--minSimilarity 0.3`; no `-n/-r/-s`, no grouping | the learned arm |
| `-m ICP` | iterative closest point, refinement only (`-ime`, `-iit`) | |
| `-m LOAD_CANDIDATES --candidatesPath X.n5` | RANSAC on candidates you computed elsewhere | |
| `-tm TRANSLATION | RIGID | AFFINE` + `-rm NONE | TRANSLATION | RIGID | AFFINE --lambda 0.1` | the PAIRWISE RANSAC model (and its regulariser). Translation-close problems: `-tm TRANSLATION -rm NONE` | |
| `-rme E` | RANSAC max error in global px: about the localisation error at the detection level, ~2.5 x dsXY at coarse levels, 2-2.5 at full resolution (sweep.sh: max(2, 2.5 x dsXY)) | |
| `-rmni N` | min inliers per pair (default 12); `-rmir 0` (min inlier ratio, 0.05 by default) | 12 / 0 |
| `-rit` | RANSAC iterations (10,000) | |
| `-rmc` | multi-consensus: several rigid pieces per pair (non-rigid / split samples; `-rmni` default 30 then) | off |
| `--clearCorrespondences` | drop the label's old links first -- ALWAYS in a grid search | on |
| `-ipfr OVERLAPPING_ONLY` | use only points inside the overlap for the pairwise registration | |
| `-vr OVERLAPPING_ONLY | ALL_AGAINST_ALL`, `--vsComparisonsFile` | which view pairs | |
| `--groupTiles / --groupChannels / --groupIllums`, `--interestPointMergeDistance` | treat several views as one (multi-angle alignment of stitched tiles) | |
| `--matchAcrossLabels`, `-l A -l B` | several labels at once | |

Per pair the log prints `[TP=.. ViewId=A Label=.. >>> TP=.. ViewId=B Label=..]: Remaining inliers after RANSAC: I of C
(P%) with average error E`, or the failure (`Not enough correspondences found`, `NO Model found`, `Model found
but not enough remaining inliers (a/b)`); EMBEDDINGS prefixes `EMBEDDINGS nA <-> nB points, a <-> b with a vector,
a <-> b within R px:`. There is no final total: parse_logs.py sums the pairs.

## embed-interestpoints (the learned descriptor, Java driver)

`-x XML -l LABEL --model hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64 [--arrayName embedding] [--blockSize 128] [view selection]`.
The hub model is the rule (a local `.onnx` needs its `.onnx.json` sidecar next to it). A filtered label is embedded through its base label; a plain
copy (`filter-interestpoints --copy`) is its own base. The vectors are stored with the points
(`interestpoints.zarr/<label>/tp<T>/arrays/embedding/setup<S>`), so matching can be repeated without re-embedding.
Hub models are downloaded once into `~/.bigstitcher/models` (`--modelCache DIR` moves the cache). See `ml-matching.md`.

## solver

| flag | meaning | typical |
|---|---|---|
| `-s IP -l LABEL` | solve from the label's correspondences (`-s STITCHING` for phase-correlation shifts) | |
| `-tm TRANSLATION | RIGID | AFFINE`, `-rm NONE | TRANSLATION | RIGID | AFFINE --lambda 0.1` | the global model and its regulariser. Grid: `TRANSLATION/NONE`, `RIGID/TRANSLATION 0.1`, `AFFINE/RIGID 0.1`, `AFFINE/TRANSLATION 0.1` | |
| `-fv tp,setup` | fixed view(s), one per connected group (default: the first view) | |
| `--method ONE_ROUND_SIMPLE | ONE_ROUND_ITERATIVE | TWO_ROUND_SIMPLE | TWO_ROUND_ITERATIVE` | two rounds handle unconnected tiles, iterative drops wrong links (`--relativeThreshold 3.5`, `--absoluteThreshold 7`) | ONE_ROUND_SIMPLE, TWO_ROUND_ITERATIVE when pairs failed |
| `--maxError 5 --maxIterations 10000 --maxPlateauwidth 200` | optimiser | |
| `-pa PREALIGN | NO_PREALIGN` | start from scratch or from the current transforms | NO_PREALIGN (coarse-to-fine) |
| `--disableFixedViews --enableMapbackViews --mapbackModel` | map the result back onto a view instead of fixing one | |
| `--dryRun` | prints everything (errors, per-view models) and saves NOTHING -- the grid-search judge | |

The log prints `Total number of connected views: N (M missing that are not connected)`, one `tpId=.. <-> tpId=..:
N correspondences added` per pair, the error block `Avg Error / Min Error / Max Error: ...px` (the LAST block
counts), `Removed link from ... (error=E)` for iterative solves, and `Transformation Models:` with one matrix per
view (parse_logs.py derives rotation, scales and shear from it).

## clear-registrations / clear-interestpoints

`clear-registrations -x XML --keep N | --remove N [view selection] [--dryRun]` -- N counts in order of application:
calibration first, then the metadata placement ("Translation to Regular Grid" / the first "Stitching Transform"),
then registration results. `inspect_dataset.py` proposes N. `clear-interestpoints --clearMode REMOVE_LABEL --label L`
removes a label (XML + store), `CLEAR_ALL_CORRESPONDENCES` keeps detections and drops every link. No undo; `--dryRun`
first. Details in the `bigstitcher-xml` skill.

## GUI equivalents (BigStitcher, Fiji)

| Spark | BigStitcher GUI |
|---|---|
| `detect-interestpoints --method DOG -s -t -dsxy -dsz -i0 -i1 --type` | Detect Interest Points: Difference-of-Gaussian; Sigma, Threshold, Downsample XY / Z, Min / Max intensity, Find maxima / minima / both; "Advanced" shows the interactive sigma / threshold preview |
| `--method SCALE_SPACE -s --steps --octaves` | Detect Interest Points: Scale-space Difference-of-Gaussian (multiview-reconstruction 10 with the scale-space branch); initial sigma, steps per octave |
| `--noiseFactor F` | the GUI's threshold preview suggests "F x noise"; otherwise type the derived threshold |
| `--overlappingOnly` | "Only in overlapping regions" |
| `filter-interestpoints --response` | Interest points > Filter (response range) / thinning |
| `match-interestpoints -m PRECISE_TRANSLATION / FAST_ROTATION / ICP` | Register using Interest Points: "Precise descriptor-based (translation invariant)" / "Fast descriptor-based (rotation invariant)" / "Iterative closest point" |
| `-m EMBEDDINGS` + `embed-interestpoints` | Interest points > Embed (learned descriptor) then "Learned descriptor matching" (recent BigStitcher builds only) |
| `-tm / -rm / --lambda`, `-rme -rmni -rmir -rit`, `-rmc` | the pairwise "Transformation model" + "Regularize with", RANSAC max error / min inliers / min inlier ratio / iterations, "Multi-consensus" |
| `solver -tm -rm --lambda -fv --method` | Register using Interest Points, global optimization: model + regularization, "Fix views", "Simple / Iterative / Two-round" |
| `clear-registrations --keep N` | Registration > Remove Transformations (keep the first N) |

## Typical starting points by sample

| sample | detection | notes |
|---|---|---|
| fluorescent beads in agarose (multi-view) | DOG `-s 1.8 --noiseFactor 2.5`, or SCALE_SPACE `-s 1.6`; `--type MAX` | beads are sub-resolution: SCALE_SPACE keeps them via `--finestLevel`; hundreds to a few thousand per view |
| nuclei (DAPI-like) | SCALE_SPACE `-s 1.6` (sizes vary), `--noiseFactor 2.5`, response ladder 2-4x | thousands per view; `--type BOTH` adds the dark gaps |
| dense tissue texture (cleared tissue, expansion) | SCALE_SPACE at the floor + response filter 8-20x the floor | the floor alone gives millions of noise points; `--maxSpots` as the cap |
| sparse vasculature / neurons | DOG or SCALE_SPACE, `--type BOTH`, coarse level first | few points: lower `-rmni` only as a last resort (12 is already lenient) |
| two objectives / cameras | detect per group with the group's `-i0/-i1` and `-dsxy` scaled by the voxel-size ratio, SAME label | the geometric matcher works in calibrated units; the learned descriptor uses the stored sigma |
