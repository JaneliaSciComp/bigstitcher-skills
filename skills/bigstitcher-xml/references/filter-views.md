# filter-views (BigStitcher-Spark)

Java port of `scripts/filter_bigstitcher_xml.py` (class `net.preibisch.bigstitcher.spark.Filter_Views`).
Same selection semantics: the attribute filters and `--views` are AND-combined to pick view setups,
`--timepoints` is an independent dimension, and all dependent sections (registrations, interest-point
entries, PSFs, stitching results, intensity adjustments, missing views) are pruned together.

```
filter-views -x <xml or URI> [-xo <output>] [--channels ..] [--tiles ..] [--angles ..] [--illuminations ..] [--views ..] [--timepoints ..] [--dryRun]
```

| Flag | Meaning |
|---|---|
| `-x, --xml` | input XML: local path, `file:`, `s3://bucket/...`, `gs://...` (add `--s3Region` if needed) |
| `-xo, --xmlout` | output XML. **Default: overwrite the input and keep a `~1` backup** |
| `--channels`, `--tiles`, `--angles`, `--illuminations` | attribute IDs, comma-separated, ranges allowed: `0,2` or `0-10,15` |
| `--views` | view-setup IDs directly |
| `--timepoints` | timepoint IDs |
| `--dryRun` | load and report, write nothing |

At least one filter is required. Exits with a message when nothing matches.

## Differences from the Python script

| | Python script | filter-views |
|---|---|---|
| Install | none (Python 3) | BigStitcher-Spark release via `install-release`, Java 21 |
| Input location | local file | local, S3, GCS |
| Image data must be reachable | never | yes for N5 and Zarr loaders (the container is opened while parsing the XML); HDF5 loads lazily |
| Output default | `-o` required | overwrite input with `~1` backup |
| Output in another directory | `<BasePath>` re-pointed, everything still resolves | image paths rebased, **interest points orphaned** |
| ID syntax | space-separated `--tiles 0-10 15` | comma-separated `--tiles 0-10,15` |
| Surviving contiguous timepoints written as | `pattern` | `range` |

Both produce the same view setups, attributes, timepoints, registrations, interest-point entries,
stitching results and intensity adjustments (compared section by section on real datasets, September 2026).

## Examples

```bash
filter-views -x dataset.xml -xo dataset_ch0.xml --channels 0
filter-views -x s3://bucket/run/dataset.xml --tiles 0-9 --timepoints 0-5 --dryRun
filter-views -x dataset.xml --views 0,1,5,10            # in place; dataset.xml~1 keeps the original
```

Afterwards, `clear-interestpoints -x dataset.xml --clearMode FIX_INTERESTPOINTS` removes interest-point
data of views that are no longer in the XML.
