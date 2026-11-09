# The learned-descriptor (ML) matching arm

A small 3D network turns the image around every interest point into a 64-D vector (five concentric cubes at
5-30 x the point's sigma); corresponding points of two views get similar vectors. Matching is then a
nearest-neighbour search in vector space among the points within a SEARCH RADIUS of each other under the current
registration, followed by the usual RANSAC. It finds several times more correspondences than the geometric
descriptors on sparse or textured samples (mouse head 4x, Wang lab 2x, fly brain 1.5x in our tests) and is
translation-invariant but NOT rotation-invariant: views rotated against each other by more than a few degrees
(unknown manual rotation, another objective mounted at an angle) must go to the geometric matcher (`-m
FAST_ROTATION`) -- do not work around this, a rotation-tolerant model is a separate project.

## The commands (BigStitcher-Spark release 0.2.0 or later)

```
embed-interestpoints -x XML -l LABEL --model hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64 [view selection] --localSparkBindAddress
match-interestpoints -x XML -l LABEL [view selection] -m EMBEDDINGS -sr RADIUS --descriptorRatio 0.85 --minSimilarity 0.3 \
    -tm TRANSLATION -rm NONE -rme E -rmni 12 -rmir 0 --clearCorrespondences --localSparkBindAddress
```
- The model is ALWAYS the Hugging Face hub model `hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64` (the sweep's
  default `MODEL_ONNX`). The driver pins the hub revision, downloads the `.onnx` and its `.onnx.json` sidecar once
  into `~/.bigstitcher/models` (`--modelCache DIR` moves the cache) and records the pinned URI with the stored
  vectors. The maintainers replace the hub model when a better one is released, so the skill never has to change.
  More models (mirror-tolerant, rotation-invariant) will appear on the hub under the same namespace; a local file
  (`--model /path/model.onnx` with its `.onnx.json` next to it) is only for a user who asks for one.
- Embedding runs once per label (the vectors are stored with the points); a filtered label is embedded through
  its base, a plain copy is its own base. Re-matching with other RANSAC settings needs no re-embedding.
- `-sr` is REQUIRED: the registration's uncertainty in global px. 20 for a dataset whose metadata is already good
  (ds1-stitch), 100 at a coarse level of the ladder, 300-500 for raw stage positions with large errors. Too small
  misses partners; too large costs time and adds wrong candidates (RANSAC copes up to ~500 on real data).
- `--descriptorRatio 0.85` (keep a candidate if `1 - best < 0.85 x (1 - second best)`), `--minSimilarity 0.3`:
  leave both alone while comparing other settings; they trade a few percent either way.
- No `-n / -r / -s` and no view grouping with EMBEDDINGS.

## When to use which

| situation | arm |
|---|---|
| tiles of one acquisition, translation-close, any sample | geo AND emb -- compare; emb usually wins on sparse / textured samples, geo on dense bead fields |
| unknown rotation between view groups | geo only: `-m FAST_ROTATION`, then PRECISE_TRANSLATION on the next level |
| mirrored camera (left/right flipped) | emb with the local `_mirror-xy` model (user-supplied file), or geo (geometric descriptors do not care about mirroring) |
| multi-view (90 deg angles) | out of scope here; the rotation-invariant model exists but tiles are not its regime |
| no access to the hub and no local model file | geo only; say so in the report |

## Failure modes

- Zero inliers everywhere with EMBEDDINGS but the geometric arm works: wrong `-sr` (too small for the metadata
  error) or the label has no vectors (embed step skipped / failed; the match log prints `a <-> b with a vector`).
- Far fewer inliers than geo on a dense bead field: expected on perfectly repetitive beads; keep geo.
- Vectors from another model on the label (`arrayName` clash): `embed-interestpoints` replaces them; the match
  refuses mixed fingerprints.
