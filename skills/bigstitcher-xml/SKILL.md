---
name: bigstitcher-xml
description: Edit BigStitcher / BigDataViewer SpimData XML projects (dataset.xml) without breaking them. Filter to selected channels, tiles, angles, illuminations, timepoints or views; clear, repair, add or remove interest-point labels and correspondences; strip registrations from views. Routes between a bundled stdlib-only Python script and the BigStitcher-Spark commands filter-views, clear-interestpoints and clear-registrations, and knows how to locate or install BigStitcher-Spark. Use whenever a user wants to subset, split or clean up a BigStitcher, BigStitcher-Spark or multiview-reconstruction project, even if they only say "remove these tiles", "just channel 0", "delete the beads label", "undo the last registration" or "the XML still lists views I deleted".
---

# BigStitcher XML: filter views, clear interest points, strip registrations

A BigStitcher / SpimData2 `dataset.xml` describes every view and everything derived from views. A view is
one view setup at one timepoint; a view setup is one channel, tile, angle and illumination combination.
Registrations, interest points, PSFs, pairwise stitching results and intensity adjustments all reference
views by ID. Interest points themselves live outside the XML, in `interestpoints.n5` next to it. Editing
the XML by hand leaves dangling references and BigStitcher refuses to load the file. The tools below keep
every section consistent.

## Which tool

| Task | Tool | Notes |
|---|---|---|
| Keep only some channels / tiles / angles / illuminations / timepoints / views; XML is a local file | `scripts/filter_bigstitcher_xml.py` | no install, never touches image data |
| Same, but the XML is on S3 / GCS, or in-place editing with a backup is wanted | `filter-views` (BigStitcher-Spark) | needs the image container reachable; `references/filter-views.md` |
| Remove or add an interest-point label, drop correspondences, wipe all interest points, repair after views were deleted | `clear-interestpoints` | `references/clear-interestpoints.md` |
| Remove the last N registrations, e.g. undo an affine solve | `clear-registrations` | `references/clear-registrations.md` |

Anything else, such as renaming attributes or fixing image paths, is not covered. Do it carefully with
the dangling-reference problem in mind, or extend this skill.

## Filtering with the Python script

```bash
python3 <skill dir>/scripts/filter_bigstitcher_xml.py -i dataset.xml -o dataset_subset.xml [filters] [--dry-run]
```

Filters: `--channels`, `--tiles`, `--angles`, `--illuminations`, `--views` (view-setup IDs) are combined
with AND; `--timepoints` is an independent dimension. Values are space-separated IDs or inclusive ranges
`a-b`. IDs are the `<id>` values in the XML, not names. `--help` prints all examples.

1. Map names to IDs first. Users say "the 488 channel" or "the second angle". Read the
   `<Attributes name="channel">`, `tile`, `angle`, `illumination` blocks and `<ViewSetups>`, and confirm
   the mapping with the user when it is not obvious.
2. Write to a new file unless the user explicitly asks for in-place. Use `--dry-run` to show what survives.
3. When the output goes to another directory, the script re-points `<BasePath>` at the original directory,
   so image data and `interestpoints.n5` still resolve. It prints a note when it does this; `--no-rebase`
   disables it for users who will copy the data next to the new XML.
4. Report the kept view setups and timepoints afterwards. Interest-point data of dropped views stays on
   disk; `clear-interestpoints --clearMode FIX_INTERESTPOINTS` removes it (needs BigStitcher-Spark).

## Using the BigStitcher-Spark commands

Locate an installation first. Never clone or build without asking.

```bash
bash <skill dir>/scripts/find_bigstitcher_spark.sh    # prints the directory holding the command shims
```

- Exit 0: run the executables from the printed directory or put it on `PATH`. Run each command with `--help`
  before proposing flags. The CLI evolves; the flags in the reference files were checked against release 0.2.0 (November 2026).
- Exit 3: a downloaded `BigStitcher-Spark-<v>-local.jar` but no executables. Run commands as
  `java -Xmx<G>g -jar <jar> <command> …`, or offer to create the executables with `install-release`.
- Exit 1 or 2: nothing installed. Read `references/install-bigstitcher-spark.md`. The normal path is
  `install-release`: Java 21 is the only prerequisite, it downloads the latest release (about 340 MB) and
  creates the executables in about a minute, no clone and no build. Tell the user what it downloads and where,
  and proceed only with their agreement. For filtering, use the Python script instead of blocking on this.

Safety rules for the Java tools:

- All three edit the XML in place. `filter-views` keeps a `~1` backup; the `clear-*` commands keep none.
  Run with `--dryRun` first, show the user the output, then run for real.
- `clear-interestpoints` also deletes data inside `interestpoints.n5`. There is no undo.
- View selection: `--tileId 0,3`, `--channelId 0`, `--angleId`, `--illuminationId`, `--timepointId`, or
  explicit `-vi '0,0' -vi '0,1'`. Comma-separated, unlike the Python script. No flags means every view.
- Keep outputs next to the input. Relocating an XML with the Java tools orphans `interestpoints.n5`.

Reference files: `references/filter-views.md`, `references/clear-interestpoints.md`,
`references/clear-registrations.md`, `references/install-bigstitcher-spark.md`.
