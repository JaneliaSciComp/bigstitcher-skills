# bigstitcher-skills

Claude Code skills for working with [BigStitcher](https://github.com/PreibischLab/BigStitcher),
[BigStitcher-Spark](https://github.com/PreibischLab/BigStitcher-Spark) and
[multiview-reconstruction](https://github.com/PreibischLab/multiview-reconstruction).

A skill is a `SKILL.md` instruction file plus optional scripts and reference docs. Claude Code keeps
every skill's name and description in context and loads the rest when a task matches. These skills
drive the installed CLI tools; they do not need the Java source trees.

## Skills

| Skill | What it does |
|---|---|
| `skills/bigstitcher-xml` | Edit SpimData XML projects safely: filter to selected channels / tiles / angles / illuminations / timepoints / views (bundled `filter_bigstitcher_xml.py`), clear or repair interest points and strip registrations via BigStitcher-Spark's `filter-views`, `clear-interestpoints`, `clear-registrations`. Locates an existing BigStitcher-Spark install (`BIGSTITCHER_SPARK_HOME`) and documents how to build one. |
| `skills/bigstitcher-tune-alignment` | Workflow for finding good interest-point detection, matching and solver parameters. Skeleton for now. |

All skills are prefixed `bigstitcher-` so they stay unambiguous when installed as bare user skills.

## Use locally (current setup)

Symlink each skill into your user skills directory. Claude Code loads user skills in every session,
regardless of working directory:

```bash
cd /path/to/bigstitcher-skills
ln -s "$PWD/skills/bigstitcher-xml"            ~/.claude/skills/bigstitcher-xml
ln -s "$PWD/skills/bigstitcher-tune-alignment" ~/.claude/skills/bigstitcher-tune-alignment
```

Edits in the repo are picked up at the next session start.

## Publishing as a plugin (not done yet, on purpose)

The `skills/` layout is already the one Claude Code plugins use. To let others install this repo:

1. Add `.claude-plugin/plugin.json` (name, version, description) and `.claude-plugin/marketplace.json`
   listing this plugin with source `./`.
2. Users run `/plugin marketplace add PreibischLab/bigstitcher-skills` followed by `/plugin install`.

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
