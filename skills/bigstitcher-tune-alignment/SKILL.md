---
name: bigstitcher-tune-alignment
description: Find good registration (alignment) parameters for BigStitcher / BigStitcher-Spark multi-view or tiled light-sheet datasets. Covers interest-point detection (DoG sigma, threshold, downsampling), pairwise matching (descriptor and RANSAC settings) and global solver settings, judged by correspondence counts and registration error. Use this whenever a user asks why an alignment looks wrong, which detection or matching parameters to use, wants a parameter sweep, or wants a checklist for registering a new dataset with detect-interestpoints / match-interestpoints / solver, even if they never say "tune".
---

# BigStitcher: tune alignment parameters

> **Status: skeleton.** The outline below is the intended shape of this skill. Parameter tables,
> quality thresholds and sweep scripts are still TODO. Until they exist, reason from this outline and
> from each command's `--help`, and tell the user the guidance is provisional.

## Purpose

Registration in BigStitcher is a three-stage pipeline whose parameters interact. "The alignment is
bad" almost always traces back to one of three things: too few or too many interest points, matching
that finds correspondences between the wrong pairs, or a solver asked to fit a model the data does not
support. This skill makes that diagnosis systematic instead of guesswork.

## The loop

1. **Detect interest points** with `detect-interestpoints`.
   Knobs: DoG sigma and threshold, downsampling per axis, min/max intensity, interest-point label.
   Judge by: number of points per view, whether points sit on beads / nuclei / real structure rather
   than noise, runtime per view.
2. **Match pairwise** with `match-interestpoints`.
   Knobs: matching method (geometric descriptor, ICP), RANSAC iterations / max error / min inliers,
   which view pairs to consider (overlapping only vs all), transformation model used for matching.
   Judge by: candidates vs inliers per pair, pairs with zero correspondences, agreement of the found
   correspondences with the known overlap geometry.
3. **Solve globally** with `solver`.
   Knobs: transformation model (translation / rigid / affine), regularization, fixed views,
   iterations, max allowed error.
   Judge by: reported average and max registration error, views dropped as disconnected, plausibility
   of the resulting transforms (no extreme scaling or shear).
4. **Evaluate and adjust.** Change one stage at a time, re-run the downstream stages, compare metrics.
   Record every run (parameters plus metrics) so the sweep is reproducible.

For tiled acquisitions without beads, `stitching` (phase-correlation pairwise shifts) is the
alternative to steps 1 and 2 and feeds the same solver.

Always run each command with `--help` before proposing flags. The CLI changes between
BigStitcher-Spark versions; the knob names above are descriptive, not authoritative.

## TODO

- [ ] `references/parameters.md`: per-command parameter table with typical ranges per sample type
      (beads, nuclei, sparse structure), downsampling guidance, model choice.
- [ ] `references/quality-metrics.md`: how to read the transformation summary and error output of
      `solver`, thresholds for "good enough", red flags.
- [ ] `scripts/`: parse XML / log output of a run into a compact metrics table; drive a parameter
      sweep and collect results.
- [ ] Worked examples on small, shareable datasets.
