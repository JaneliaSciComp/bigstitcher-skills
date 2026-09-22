# clear-interestpoints (BigStitcher-Spark)

Class `net.preibisch.bigstitcher.spark.ClearInterestPoints`. Edits the XML **and** the `interestpoints.n5`
container at the project's base path (local, S3 or GCS). In place, **no backup**. Always run with `--dryRun`
first and show the user what it reports.

```
clear-interestpoints -x <xml or URI> --clearMode <MODE> [--label <name>] [view selection] [--silent] [--dryRun]
```

## Modes (`--clearMode`)

| Mode | Effect on the selected views | Also |
|---|---|---|
| `CLEAR_EVERYTHING` (default) | removes all interest points and correspondences: XML entries and the per-view N5 groups | without view selection: deletes the whole `interestpoints.n5` |
| `CLEAR_ALL_CORRESPONDENCES` | keeps detections, empties every correspondence list | |
| `ADD_LABEL` | adds an empty interest-point list `--label` to views that lack it | materialised in N5 as well |
| `REMOVE_LABEL` | removes `--label` (XML entry and N5 group) | |
| `FIX_INTERESTPOINTS` | repair: drops entries, N5 groups and correspondences belonging to views no longer in the XML | **ignores view selection**, always covers the whole dataset |

Consistency rule: whenever data is removed from selected views, correspondences in *unselected* views that
point into the selection are removed too. The project stays loadable after a single run.

## View selection

`--tileId 0,3`, `--channelId 0`, `--angleId 1`, `--illuminationId 0`, `--timepointId 0-5` (comma-separated,
ranges allowed), or explicit view IDs `-vi '0,0' -vi '0,1'` as (timepoint, view setup). `-vi` cannot be
combined with the attribute flags. No flags means all present views. Missing views are always skipped.

## Other flags

- `--silent`: skip the per-view listing that loads every selected view's points and correspondences just
  to print counts. Use on large or cloud-hosted datasets.
- `--dryRun`: prints the selection, the listing and, for FIX, the orphan count; writes nothing.
- `--s3Region`: for S3 inputs when the region is not discoverable.

## Typical uses

```bash
# a detection went wrong on two tiles: remove just that label there, keep everything else
clear-interestpoints -x dataset.xml --clearMode REMOVE_LABEL --label beads --tileId 3,4 --dryRun
clear-interestpoints -x dataset.xml --clearMode REMOVE_LABEL --label beads --tileId 3,4

# rerun matching from scratch: keep detections, drop every link
clear-interestpoints -x dataset.xml --clearMode CLEAR_ALL_CORRESPONDENCES --silent

# after filter-views or manual view removal: clean up orphaned interest-point data
clear-interestpoints -x dataset.xml --clearMode FIX_INTERESTPOINTS
```

View selection requires BigStitcher-Spark release 0.1.1 or later (`bigstitcher-spark --version`). Older
versions always process the whole dataset and reject the selection flags as unknown options.
