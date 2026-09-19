---
name: bigstitcher-xml
description: Filter or modify BigStitcher / BigDataViewer SpimData XML datasets (dataset.xml) with a bundled stdlib-only Python script. Keep only selected channels, tiles, angles, illuminations, timepoints or view-setup IDs and write a new, internally consistent XML (view setups, attributes, registrations, interest points, PSFs, stitching results and intensity adjustments are all pruned together). Use this whenever the user wants to subset, split, drop or clean up views in a BigStitcher, BigStitcher-Spark or multiview-reconstruction XML, even if they only say "remove these tiles", "just channel 0", "make a small test dataset" or "the XML still lists views I deleted".
---

# BigStitcher XML: filter views

A BigStitcher / SpimData2 `dataset.xml` describes every view and everything derived from those views.
A view is one view setup at one timepoint; a view setup is one combination of channel, tile, angle and
illumination. Registrations, interest points, PSFs, pairwise stitching results and intensity adjustments
all reference views by ID. Deleting a `<ViewSetup>` by hand leaves dangling references in those sections
and BigStitcher will refuse to load the file or behave oddly. The bundled script prunes all sections
together so the output stays loadable.

## Script

`scripts/filter_bigstitcher_xml.py` is Python 3, standard library only, nothing to install.

```bash
python3 <this skill dir>/scripts/filter_bigstitcher_xml.py -i dataset.xml -o dataset_subset.xml [filters]
```

Filters (at least one required; the view-setup filters are combined with AND):

| Flag | Selects by | Example |
|---|---|---|
| `--channels` | channel ID | `--channels 0 2` |
| `--tiles` | tile ID | `--tiles 0-10 15` |
| `--angles` | angle ID | `--angles 0` |
| `--illuminations` | illumination ID | `--illuminations 0` |
| `--views` | view setup ID directly | `--views 0-99 200` |
| `--timepoints` | timepoint ID, applied independently | `--timepoints 0-5` |

Values are space-separated lists. Each value is a single ID or an inclusive range `a-b`. IDs are the
`<id>` elements in the XML, not names. The script exits with an error if the selection is empty.
Run it with `--help` for the full usage text and more examples.

## How to work

1. Map names to IDs first. Users say "the 488 channel" or "the second angle"; the script needs IDs.
   Read the `<Attributes name="channel">`, `tile`, `angle`, `illumination` blocks and `<ViewSetups>`
   before filtering, and confirm the mapping with the user if it is not obvious.
2. Write to a new file unless the user explicitly asks for in-place. Filtering is destructive to the
   view set and keeping the original is cheap.
3. Image data and interest-point directories on disk are not touched. Tell the user that orphaned
   interest points stay on disk and can be removed afterwards with BigStitcher-Spark's
   `clear-interestpoints --clearMode FIX_INTERESTPOINTS`.
4. After filtering, sanity-check the result: count `<ViewSetup>` elements and timepoints in the
   output and report them together with what was dropped.

## When to use BigStitcher-Spark's `filter-views` instead

BigStitcher-Spark ships a Java port of this script as the `filter-views` command. Prefer it when:

- the XML lives on S3 or another URI the Python script cannot open (`-x s3://bucket/dataset.xml`);
- the user wants in-place editing: `filter-views` overwrites the input by default and keeps a `~1`
  backup, `-xo` sets an explicit output path;
- the BigStitcher-Spark shims are already installed in the environment.

Syntax differs. `filter-views` takes comma-separated values (`--tiles 0-10,15`); the Python script takes
space-separated ones (`--tiles 0-10 15`). Range syntax `a-b` works in both.

## Scope

Only view filtering is implemented so far. Other XML edits (fixing image paths, dropping registrations
or interest-point labels, renaming attributes) are not yet covered. For those, edit carefully by hand
with the dangling-reference problem above in mind, or extend this skill with a new script.
