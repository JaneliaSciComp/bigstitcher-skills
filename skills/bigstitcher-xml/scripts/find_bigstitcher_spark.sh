#!/usr/bin/env bash
# Locate a BigStitcher-Spark installation. Never downloads, clones or builds anything.
#   exit 0: directory holding the command executables (filter-views, clear-interestpoints, ...) on stdout
#   exit 3: no executables, but a release jar (BigStitcher-Spark-<v>-local.jar) found; its path on stdout
#   exit 2: a source clone without executables (hint on stderr)
#   exit 1: nothing found (hint on stderr)
set -u

is_install_dir() { [ -x "$1/clear-interestpoints" ] && [ -x "$1/filter-views" ]; }
is_clone_dir()   { [ -f "$1/pom.xml" ] && [ -f "$1/install" ] && grep -q 'BigStitcher-Spark' "$1/pom.xml" 2>/dev/null; }
local_jar_in()   { ls -1t "$1"/BigStitcher-Spark-*-local.jar 2>/dev/null | head -1; }

candidates=()
[ -n "${BIGSTITCHER_SPARK_HOME:-}" ] && candidates+=("$BIGSTITCHER_SPARK_HOME")
if shim=$(command -v clear-interestpoints 2>/dev/null); then
    candidates+=("$(cd "$(dirname "$shim")" && pwd -P)")
fi
candidates+=("$HOME/bigstitcher-spark" "$HOME/.local/share/bigstitcher-spark" "/opt/bigstitcher-spark" "$HOME/BigStitcher-Spark")
for base in "$HOME/workspace" "$HOME/git" "$HOME/src" "$HOME/code"; do
    candidates+=("$base/BigStitcher-Spark" "$base/bigstitcher-spark")
done
candidates+=("$PWD")

report_java() {
    if command -v java >/dev/null 2>&1; then
        v=$(java -version 2>&1 | head -1)
        major=$(echo "$v" | sed -E 's/.*"([0-9]+)(\.[0-9]+)*.*/\1/')
        if [ "${major:-0}" -ge 17 ] 2>/dev/null; then
            echo "java: $v (ok)" >&2
        else
            echo "java: $v -- BigStitcher-Spark needs Java 17 or 21" >&2
        fi
    else
        echo "java: not found on PATH -- BigStitcher-Spark needs Java 17 or 21" >&2
    fi
}

# 1. executables
for d in "${candidates[@]}"; do
    if [ -d "$d" ] && is_install_dir "$d"; then
        echo "$d"
        report_java
        exit 0
    fi
done

# 2. a downloaded release jar without executables
jar=""
[ -n "${BIGSTITCHER_SPARK_JAR:-}" ] && [ -f "$BIGSTITCHER_SPARK_JAR" ] && jar="$BIGSTITCHER_SPARK_JAR"
if [ -z "$jar" ]; then
    for d in "${candidates[@]}"; do
        [ -d "$d" ] || continue
        jar=$(local_jar_in "$d")
        [ -n "$jar" ] && break
    done
fi
if [ -n "$jar" ]; then
    echo "$jar"
    echo "Release jar found but no command executables. Run commands as: java -Xmx<G>g -jar \"$jar\" <command> ..." >&2
    echo "or create executables with: cd \"$(dirname "$jar")\" && bash install-release -t <threads> -m <GB>  (see references/install-bigstitcher-spark.md)" >&2
    report_java
    exit 3
fi

# 3. a source clone that was never built
for d in "${candidates[@]}"; do
    if [ -d "$d" ] && is_clone_dir "$d"; then
        echo "BigStitcher-Spark source clone found at $d but no command executables." >&2
        echo "Easiest (no build): cd \"$d\" && bash install-release -t <threads> -m <GB>   -- downloads the latest release and creates the executables." >&2
        echo "From source (developers): cd \"$d\" && ./install -t <threads> -m <GB>   -- needs Maven, several minutes." >&2
        report_java
        exit 2
    fi
done

echo "BigStitcher-Spark not found. Install it (with the user's agreement) via install-release, see references/install-bigstitcher-spark.md:" >&2
echo "  mkdir -p ~/bigstitcher-spark && cd ~/bigstitcher-spark && curl -fsSLO https://raw.githubusercontent.com/JaneliaSciComp/BigStitcher-Spark/main/install-release && bash install-release -t <threads> -m <GB>" >&2
echo "Or set BIGSTITCHER_SPARK_HOME (executables) / BIGSTITCHER_SPARK_JAR (a downloaded BigStitcher-Spark-<v>-local.jar)." >&2
report_java
exit 1
