# The learned-descriptor (ML) matching arm

A small 3D network turns the image around every interest point into a 64-D vector (five concentric cubes at
5-30 x the point's sigma); corresponding points of two views get similar vectors. Matching is then a
nearest-neighbour search in vector space among the points within a SEARCH RADIUS of each other under the current
registration, followed by the usual RANSAC. It finds several times more correspondences than the geometric
descriptors on sparse or textured samples (mouse head 4x, Wang lab 2x, fly brain 1.5x in our tests) and is
translation-invariant but NOT rotation-invariant: views rotated against each other by more than a few degrees
(unknown manual rotation, another objective mounted at an angle) must go to the geometric matcher (`-m
FAST_ROTATION`) -- do not work around this, a rotation-tolerant model is a separate project.

## Driver A: all Java (BigStitcher-Spark >= 0.1.3-SNAPSHOT of 2026-10-30)

```
embed-interestpoints -x XML -l LABEL --model /path/model.onnx [view selection] --localSparkBindAddress
match-interestpoints -x XML -l LABEL [view selection] -m EMBEDDINGS -sr RADIUS --descriptorRatio 0.85 --minSimilarity 0.3 \
    -tm TRANSLATION -rm NONE -rme E -rmni 12 -rmir 0 --clearCorrespondences --localSparkBindAddress
```
- The `.onnx.json` sidecar must sit next to the `.onnx` (it carries the patch extents, normalisation and the model
  fingerprint). Models: `models/translation-stack_..._mv911_..._neg3r500.onnx` in a pcmatch checkout (the default
  translation model), the `..._mirror-xy.onnx` variant for cameras that mirror the image along x or y, the
  `rotinv-..._ft-allmv.onnx` rotation + mirror invariant model (weaker on tiles; out of scope here). On the Hugging
  Face hub: `JaneliaSciComp/bigstitcher-embedding-translation-stack64` (jars built after 2026-10-31 accept
  `--model hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64`; older ones need the downloaded files).
- Embedding runs once per label (the vectors are stored with the points); a filtered label is embedded through
  its base, a plain copy is its own base. Re-matching with other RANSAC settings needs no re-embedding.
- `-sr` is REQUIRED: the registration's uncertainty in global px. 20 for a dataset whose metadata is already good
  (ds1-stitch), 100 at a coarse level of the ladder, 300-500 for raw stage positions with large errors. Too small
  misses partners; too large costs time and adds wrong candidates (RANSAC copes up to ~500 on real data).
- `--descriptorRatio 0.85` (keep a candidate if `1 - best < 0.85 x (1 - second best)`), `--minSimilarity 0.3`:
  leave both alone while comparing other settings; they trade a few percent either way.
- No `-n / -r / -s` and no view grouping with EMBEDDINGS.

## Driver B: pcmatch (Python, GPU)

```
pcmatch match -x XML -l LABEL -vi 0,0 -vi 0,1 ... --radius RADIUS --ratio 0.85 -tm translation -rme E -rmni 12 -rmir 0 \
    [--model /path/model.pt] --write-correspondences --no-candidates --device cuda
```
- Same algorithm, same defaults (`--radius` = `-sr`, `--ratio` = `--descriptorRatio`); embeds live on the GPU (or
  uses stored vectors with `--embeddings stored|auto`), writes the correspondences as a STAGING file next to the
  store; the next XML save by a Java tool (the solver) commits it. Consequence: run the solver for that label
  right after the pcmatch match, before another Java command writes the same label.
- pcmatch also has the judges with ground truth (`pcmatch eval registration`) and `pcmatch inspect`.
- Needs the pcmatch checkout's venv (`.venv/bin/pcmatch`); set `PCMATCH=/path/.venv/bin/pcmatch` for the sweep.

## The two drivers are not bit-identical (observed 2026-11-08)

- pcmatch finds 5-20 % more inliers than `-m EMBEDDINGS` on the same points and radius (ds1-stitch full resolution:
  14,576 vs 12,363; mouse head coarse levels within 3 %); the solves agree to 0.01 px. Treat the gap as a property
  of the drivers, not of the settings.
- pcmatch's minimum-inlier rule is applied before its final consistency filter, so a pair can be kept with
  `rmni - 1` inliers where the Java matcher rejects it; at a coarse level this can decide whether a weak pair
  connects a view. Read `pairs ok / failed` with that in mind.
- pcmatch uses the vectors stored by `embed-interestpoints` when the label has them (`--embeddings auto`), and
  embeds live on the GPU otherwise; the order of the matchers in a sweep therefore changes what it reads, not
  the result.

## When to use which

| situation | arm |
|---|---|
| tiles of one acquisition, translation-close, any sample | geo AND emb (or pcm) -- compare; emb usually wins on sparse / textured samples, geo on dense bead fields |
| unknown rotation between view groups | geo only: `-m FAST_ROTATION`, then PRECISE_TRANSLATION on the next level |
| mirrored camera (left/right flipped) | emb with the `_mirror-xy` model, or geo (geometric descriptors do not care about mirroring) |
| multi-view (90 deg angles) | out of scope here; the rotation-invariant model exists but tiles are not its regime |
| no model file, no pcmatch | geo only; say so in the report |

## Failure modes

- Zero inliers everywhere with EMBEDDINGS but the geometric arm works: wrong `-sr` (too small for the metadata
  error) or the label has no vectors (embed step skipped / failed; the match log prints `a <-> b with a vector`).
- Far fewer inliers than geo on a dense bead field: expected on perfectly repetitive beads; keep geo.
- Vectors from another model on the label (`arrayName` clash): `embed-interestpoints` replaces them; the match
  refuses mixed fingerprints.
