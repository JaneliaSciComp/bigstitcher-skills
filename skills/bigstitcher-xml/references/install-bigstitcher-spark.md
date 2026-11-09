# Locating or installing BigStitcher-Spark

## Locate first

`scripts/find_bigstitcher_spark.sh` checks `$BIGSTITCHER_SPARK_HOME`, the `PATH`, `$BIGSTITCHER_SPARK_JAR` and
common locations (`~/bigstitcher-spark`, `~/.local/share/bigstitcher-spark`, `/opt/bigstitcher-spark`,
`~/BigStitcher-Spark`, `~/workspace/…`, `~/git/…`, `~/src/…`, `~/code/…`, the current directory).

| Exit | Meaning | stdout |
|---|---|---|
| 0 | command executables found (`filter-views`, `clear-interestpoints`, … and usually `bigstitcher-spark`) | the directory |
| 3 | only a release jar found (`BigStitcher-Spark-<v>-local.jar`), no executables | the jar path; run `java -Xmx<G>g -jar <jar> <command> …`, or run `install-release` in that directory to get executables |
| 2 | a source clone without executables | hint on stderr |
| 1 | nothing found | hint on stderr |

It also reports the Java version; the tools need Java 17 or 21.

## Install with `install-release` (recommended, no build)

Prerequisite: **Java 21** (17 works), check with `java -version`. Nothing else. Takes about a minute.

```bash
mkdir -p ~/bigstitcher-spark && cd ~/bigstitcher-spark
curl -fsSLO https://raw.githubusercontent.com/JaneliaSciComp/BigStitcher-Spark/main/install-release
bash install-release -t <threads> -m <memory in GB>      # e.g. -t 8 -m 32; -v 0.2.0 pins a release; -f re-downloads
export BIGSTITCHER_SPARK_HOME="$PWD"                      # optional, lets the finder script locate it later
```

It resolves the latest GitHub release, downloads `BigStitcher-Spark-<v>-local.jar` (about 370 MB, Spark bundled),
verifies it, and writes one executable per command into the directory: `resave`, `detect-interestpoints`,
`match-interestpoints`, `stitching`, `solver`, `match-intensities`, `solve-intensities`, `create-fusion-container`,
`fusion`, `nonrigid-fusion`, `split-images`, `filter-views`, `downsample`, `clear-interestpoints`,
`clear-registrations`, `transform-points`, `overlay-landmarks`, `define-dataset`, `apply-transformation`,
`embed-interestpoints` (learned descriptors, 0.2.0+), `screenshot` (headless BDV pictures, 0.1.4+), plus `bigstitcher-spark`, which exposes all of them
as subcommands. Each executable runs `java -Xmx<mem>g -Dspark.master=local[<threads>] -jar <jar> <command>`;
`JAVA_OPTS` adds JVM options. Running it again in the same directory updates to the latest release.

Before running it, tell the user that it downloads a few hundred MB and where the files will go, and get their OK.
Never run it unasked.

## Manual alternative

Download `BigStitcher-Spark-<v>-local.jar` from https://github.com/JaneliaSciComp/BigStitcher-Spark/releases/latest
(stable link: https://github.com/JaneliaSciComp/BigStitcher-Spark/releases/latest/download/BigStitcher-Spark-local.jar) and run

```bash
java -Xmx32g -jar BigStitcher-Spark-local.jar <command> [options]    # all cores; -Dspark.master='local[8]' to limit
java -Xmx32g -jar BigStitcher-Spark-local.jar --help                 # lists the commands
```

## Versions

The alignment skills (`bigstitcher-tune-alignment`, `bigstitcher-judge-alignment`) need release **0.2.0 or later**:
`--method SCALE_SPACE`, `embed-interestpoints` with `hf://` hub models, `-m EMBEDDINGS` and `screenshot` all arrived
there (released 2026-11-09, bundling multiview-reconstruction 10.0.0).
View selection in `clear-interestpoints` and `clear-registrations` needs release **0.1.1 or later**; check with
`bigstitcher-spark --version` or `java -jar <jar> --version`. Releases: https://github.com/JaneliaSciComp/BigStitcher-Spark/releases

## Building from source (developers only)

Java 21 and Apache Maven, then `git clone https://github.com/JaneliaSciComp/BigStitcher-Spark.git`,
`cd BigStitcher-Spark`, `./install -t <threads> -m <GB>`. This runs `mvn clean install` including the tests
(several minutes, large dependency download) and writes the same executables into the clone, embedding absolute
`~/.m2` paths, so they only work on that machine. Only needed for unreleased changes; the finder says so when it
falls back to such a clone, and a release install in `~/bigstitcher-spark` always wins.

## Clusters and cloud

`BigStitcher-Spark-<v>-cluster.jar` from the same release page (Spark not bundled) is for
`spark-submit --class net.preibisch.bigstitcher.spark.<Class> … cluster.jar …` or `spark-submit … cluster.jar <command> …`.
The XML tools covered by this skill are normally run locally.
