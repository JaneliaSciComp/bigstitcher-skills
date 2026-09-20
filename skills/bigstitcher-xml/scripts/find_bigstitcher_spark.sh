#!/usr/bin/env bash
# Locate a BigStitcher-Spark installation, i.e. the directory holding the generated command shims
# (filter-views, clear-interestpoints, ...). Prints that directory and exits 0.
# Exit 2: a clone was found but never built. Exit 1: nothing found.
# This script never downloads, clones or builds anything.
set -u

is_install_dir() { [ -x "$1/clear-interestpoints" ] && [ -x "$1/filter-views" ]; }
is_clone_dir()   { [ -f "$1/pom.xml" ] && [ -f "$1/install" ] && grep -q 'BigStitcher-Spark' "$1/pom.xml" 2>/dev/null; }

candidates=()
[ -n "${BIGSTITCHER_SPARK_HOME:-}" ] && candidates+=("$BIGSTITCHER_SPARK_HOME")
if shim=$(command -v clear-interestpoints 2>/dev/null); then
    candidates+=("$(cd "$(dirname "$shim")" && pwd -P)")
fi
for base in "$HOME/workspace" "$HOME/git" "$HOME/src" "$HOME/code" "$HOME" "$PWD"; do
    candidates+=("$base/BigStitcher-Spark")
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

for d in "${candidates[@]}"; do
    if [ -d "$d" ] && is_install_dir "$d"; then
        echo "$d"
        report_java
        exit 0
    fi
done

for d in "${candidates[@]}"; do
    if [ -d "$d" ] && is_clone_dir "$d"; then
        echo "BigStitcher-Spark clone found at $d but the command shims are missing." >&2
        echo "Build it (with the user's agreement) with: cd \"$d\" && ./install -t <threads> -m <memGB>" >&2
        report_java
        exit 2
    fi
done

echo "BigStitcher-Spark not found. Set BIGSTITCHER_SPARK_HOME to an installed clone, or see references/install-bigstitcher-spark.md" >&2
report_java
exit 1
