# clear-registrations (BigStitcher-Spark)

Class `net.preibisch.bigstitcher.spark.ClearRegistrations`. Removes view transformations from the
`<ViewRegistrations>` of the selected views. XML only, in place, **no backup**. Run `--dryRun` first: it
prints every transformation that would be removed, per view.

```
clear-registrations -x <xml or URI> (--keep N | --remove N) [view selection] [--dryRun]
```

- `--remove N`: drop the last N transformations applied. `--remove 1` undoes the most recent
  registration result.
- `--keep N`: keep only the first N. `--keep 1` leaves the calibration; `--keep 2` leaves calibration
  plus the tile positions from metadata.

Exactly one of the two, N >= 0. "First" and "last" follow the order of application as BigStitcher lists
them: calibration, then metadata tile locations, then registration results.

View selection as in `clear-interestpoints`: `--tileId`, `--channelId`, `--angleId`, `--illuminationId`,
`--timepointId`, or `-vi '0,0'`. No flags means all views. Builds older than September 2026 accepted these
flags but silently applied the change to every view.

```bash
clear-registrations -x dataset.xml --remove 1 --dryRun                # show what would go
clear-registrations -x dataset.xml --remove 1 -vi '0,0' -vi '0,1'
```

Interest points and correspondences are untouched. Rerun the solver afterwards to recompute.
