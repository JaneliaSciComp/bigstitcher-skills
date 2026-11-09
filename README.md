# bigstitcher-skills

Claude Code skills for working with [BigStitcher](https://github.com/JaneliaSciComp/BigStitcher),
[BigStitcher-Spark](https://github.com/JaneliaSciComp/BigStitcher-Spark) and
[multiview-reconstruction](https://github.com/JaneliaSciComp/multiview-reconstruction).

A skill is a `SKILL.md` instruction file plus optional scripts and reference docs. Claude Code keeps
every skill's name and description in context and loads the rest when a task matches. These skills
drive the installed CLI tools; they do not need the Java source trees. They need a BigStitcher-Spark
**release 0.2.0 or later** (`install-release`, see `skills/bigstitcher-xml/references/install-bigstitcher-spark.md`);
the learned-descriptor step uses the Hugging Face hub model `hf://JaneliaSciComp/bigstitcher-embedding-translation-stack64`.

## Skills

| Skill | What it does |
|---|---|
| `skills/bigstitcher-xml` | Edit SpimData XML projects safely: filter to selected channels / tiles / angles / illuminations / timepoints / views (bundled `filter_bigstitcher_xml.py`), clear or repair interest points and strip registrations via BigStitcher-Spark's `filter-views`, `clear-interestpoints`, `clear-registrations`. Locates an existing BigStitcher-Spark install (`BIGSTITCHER_SPARK_HOME`, `BIGSTITCHER_SPARK_JAR`) and documents `install-release`, which downloads the latest release instead of building. |
| `skills/bigstitcher-tune-alignment` | Coarse-to-fine grid search for alignment settings: detection (DoG / scale-space DoG at the noise floor, downsampling ladder, response filters), pairwise matching (geometric descriptors, the learned translation-invariant descriptor via BigStitcher-Spark `embed-interestpoints` with the Hugging Face hub model and `-m EMBEDDINGS`), solver models (translation / rigid / affine, regularised), judged by inliers, error and transform plausibility. Scripts: `make_working_copy.py`, `inspect_dataset.py`, `add_rotation.py`, `sweep.sh` (one level), `ladder.sh` (all levels, pictures of every saved level), `rank_runs.py`. Translation-close alignments, optionally after a known manual rotation. |
| `skills/bigstitcher-judge-alignment` | Verdict on an alignment from the logs and the XML: inliers per pair, failed pairs, connected views, solver error, per-view transform decomposition (rotation / scale / shear) and the change against the start. Pictures: renders every overlapping pair (magenta / green, xy + xz) with BigStitcher-Spark's headless `screenshot` (0.1.4+) and reads them. Scripts: `parse_logs.py`, `registration_report.py`, `render_pairs.sh`, `pick_pairs.py`, `contact_sheet.py`. |

All skills are prefixed `bigstitcher-` so they stay unambiguous when installed as bare user skills.

## Use locally (current setup)

Symlink each skill into your user skills directory. Claude Code loads user skills in every session,
regardless of working directory:

```bash
cd /path/to/bigstitcher-skills
ln -s "$PWD/skills/bigstitcher-xml"            ~/.claude/skills/bigstitcher-xml
ln -s "$PWD/skills/bigstitcher-tune-alignment" ~/.claude/skills/bigstitcher-tune-alignment
ln -s "$PWD/skills/bigstitcher-judge-alignment" ~/.claude/skills/bigstitcher-judge-alignment
```

Edits in the repo are picked up at the next session start.

## Publishing as a plugin (not done yet, on purpose)

The `skills/` layout is already the one Claude Code plugins use. To let others install this repo:

1. Add `.claude-plugin/plugin.json` (name, version, description) and `.claude-plugin/marketplace.json`
   listing this plugin with source `./`.
2. Users run `/plugin marketplace add JaneliaSciComp/bigstitcher-skills` followed by `/plugin install`.

Nothing is distributed until that metadata exists and someone explicitly adds the marketplace. Once
installed, Claude Code pulls plugin updates at session start, so from that point on treat pushes to the
default branch as releases.

## Layout

```
skills/<name>/
├── SKILL.md        # frontmatter (name, description) + instructions
├── scripts/        # executable helpers (optional)
└── references/     # docs loaded on demand (optional)
```
