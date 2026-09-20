# Locating or installing BigStitcher-Spark

## Locate

`scripts/find_bigstitcher_spark.sh` checks `$BIGSTITCHER_SPARK_HOME`, the `PATH`, and common clone
locations (`~/workspace`, `~/git`, `~/src`, `~/code`, `~`, the current directory) for the generated command
shims and prints the directory that holds them.

| Exit code | Meaning |
|---|---|
| 0 | found; the directory is on stdout |
| 2 | a clone exists but was never built (message on stderr says where) |
| 1 | nothing found |

It also reports the Java version it sees, because the tools need Java 17 or 21.

## Install (only with the user's agreement)

There is no downloadable package yet: no release jars, no conda package, no Docker image. The tools are
built from source, which takes several minutes and downloads a large dependency tree on the first run.
Say so before starting, and let the user decide.

Prerequisites: **Java 21** (17 also works; Spark 4 dropped Java 8 and 11) and **Apache Maven**. Check
with `java -version` and `mvn -v`. `JAVA_HOME` must point at the JDK. If the project README still mentions
Java 8, that is outdated.

```bash
git clone https://github.com/PreibischLab/BigStitcher-Spark.git
cd BigStitcher-Spark
./install -t <threads> -m <memory in GB>      # e.g. ./install -t 8 -m 32
export BIGSTITCHER_SPARK_HOME="$PWD"          # optional; lets the finder script locate it later
```

`./install` runs `mvn clean install`, including the integration tests, and writes one shim per command into
the repository directory: `filter-views`, `clear-interestpoints`, `clear-registrations`, `resave`,
`detect-interestpoints`, `match-interestpoints`, `stitching`, `solver`, `create-fusion-container`, `fusion`,
and more. Each shim starts a local Spark with the given thread count and memory. The shims embed absolute
paths into `~/.m2`, so they only work on the machine that built them.

After `git pull`, rerun `./install`, or `mvn install -DskipTests` to refresh just the jar the shims use.

## Clusters and cloud

`mvn clean package -P fatjar` builds `target/BigStitcher-Spark-<version>.jar` for
`spark-submit --class net.preibisch.bigstitcher.spark.<Class>`. Spark itself is not bundled. The XML tools
covered by this skill are normally run locally through the shims, not via spark-submit.
