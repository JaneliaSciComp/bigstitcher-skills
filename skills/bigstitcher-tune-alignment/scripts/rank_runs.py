#!/usr/bin/env python3
"""
Collect and rank the runs of an alignment grid search. Stdlib only.

  rank_runs.py add RUNS.jsonl --meta level=ds2-1 detector=ss label=ss_ds2-1_nf2.5_x5__geo matcher=geo solver=affine-tr \
               --detect detect.log --match match.log --solve solve.log [--seconds 42]
  rank_runs.py table RUNS.jsonl [--top 20] [--level ds2-1] [--md report.md]

The JUDGE is the total number of RANSAC inliers of the pairwise matching (more true correspondences = a better
constrained, more robust solve); the solver's average error, missing views, failed pairs and the transform
plausibility (rotation / scale / shear of the solved models) are TRIPWIRES printed next to it, not the score.
Rows are ranked by inliers, then by lower solver error. 'parse_logs.py' (bigstitcher-judge-alignment) does the
log reading; this script expects it next to itself or in the sibling skill directory.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, "parse_logs.py"),
              os.path.join(HERE, "..", "..", "bigstitcher-judge-alignment", "scripts", "parse_logs.py"),
              os.path.join(os.environ.get("BIGSTITCHER_SKILLS", "/nonexistent"), "bigstitcher-judge-alignment", "scripts", "parse_logs.py")]


def parse(log):
    if not log or not os.path.exists(log):
        return None
    for c in CANDIDATES:
        if os.path.exists(c):
            out = subprocess.run([sys.executable, c, log, "--json", "-"], capture_output=True, text=True, check=True).stdout
            return json.loads(out)
    sys.exit("parse_logs.py not found (install bigstitcher-judge-alignment next to this skill or set BIGSTITCHER_SKILLS)")


def cmd_add(a):
    row = {"meta": dict(kv.split("=", 1) for kv in a.meta or [])}
    for kind, log in (("detect", a.detect), ("match", a.match), ("solve", a.solve)):
        r = parse(log)
        if r is not None:
            row[kind] = {"log": log, "kind": r["kind"], "totals": r.get("totals", {}), "args": r.get("args", {}),
                         "done": r.get("done"), "exceptions": r.get("exceptions")}
            if kind == "match" and r.get("pairs"):
                row[kind]["failed_pairs"] = [k for k, p in r["pairs"].items() if p["status"] not in ("ok", "other")]
    if a.seconds is not None:
        row["seconds"] = a.seconds
    with open(a.runs, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(short(row))


def short(row):
    m, s = row.get("match", {}).get("totals", {}), row.get("solve", {}).get("totals", {})
    d = row.get("detect", {}).get("totals", {})
    meta = row["meta"]
    parts = [f"{meta.get('label', '?')} / {meta.get('matcher', '?')} / {meta.get('solver', '?')}"]
    if d:
        parts.append(f"points {d.get('points', 0):,}")
    if m:
        parts.append(f"inliers {m.get('inliers_total', 0):,} ({m.get('pairs_ok', '?')} pairs ok, {m.get('pairs_failed', 0)} failed)")
    if s and s.get("avg_error") is not None:
        parts.append(f"solve avg {s['avg_error']:.2f} max {s['max_error']:.2f} px, "
                     f"{s.get('views_connected', '?')}/{s.get('views', '?')} views" + (f", rot {s['max_rotation_deg']:.2f} deg" if "max_rotation_deg" in s else ""))
    elif s:
        parts.append("solve FAILED (" + (s.get("failure") or "no error block") + ")")
    return "; ".join(parts)


def fmt(v, f="{:,}"):
    try:
        return f.format(v)
    except (TypeError, ValueError):
        return "-" if v is None else str(v)


def cmd_table(a):
    rows = [json.loads(l) for l in open(a.runs) if l.strip()]
    if a.level:
        rows = [r for r in rows if r["meta"].get("level") == a.level]
    def key(r):
        m, s = r.get("match", {}).get("totals", {}), r.get("solve", {}).get("totals", {})
        return (-(m.get("inliers_total") or 0), s.get("avg_error") if s.get("avg_error") is not None else 1e9)
    rows.sort(key=key)
    hdr = ["#", "level", "label", "matcher", "solver", "points", "inliers", "pairs ok/failed", "cand", "solve avg/max px", "views", "rot deg", "scale", "shear", "flags"]
    lines = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for i, r in enumerate(rows, 1):
        meta, d, m, s = r["meta"], r.get("detect", {}).get("totals", {}), r.get("match", {}).get("totals", {}), r.get("solve", {}).get("totals", {})
        flags = []
        if s:
            if s.get("views_missing"):
                flags.append(f"{s['views_missing']} view(s) unconnected")
            if s.get("max_rotation_deg", 0) > a.rot_tol:
                flags.append("rotation")
            if s.get("scale_range") and max(abs(s["scale_range"][0] - 1), abs(s["scale_range"][1] - 1)) > a.scale_tol:
                flags.append("scale")
            if s.get("max_shear", 0) > a.shear_tol:
                flags.append("shear")
            if s.get("failure"):
                flags.append("SOLVE FAILED")
            if s.get("avg_error") is not None and a.err_tol and s["avg_error"] > a.err_tol:
                flags.append("error")
        if m.get("pairs_failed"):
            flags.append(f"{m['pairs_failed']} pair(s) failed")
        if r.get("match", {}).get("exceptions") or r.get("solve", {}).get("exceptions"):
            flags.append("exceptions in log")
        lines.append("| " + " | ".join([
            str(i), meta.get("level", "-"), meta.get("label", "-"), meta.get("matcher", "-"), meta.get("solver", "-"),
            fmt(d.get("points")), fmt(m.get("inliers_total")), f"{m.get('pairs_ok', '-')}/{m.get('pairs_failed', '-')}", fmt(m.get("candidates_total")),
            (f"{s['avg_error']:.2f}/{s['max_error']:.2f}" if s.get("avg_error") is not None else "-"),
            (f"{s.get('views_connected', '-')}/{s.get('views', '-')}" if s else "-"),
            (f"{s['max_rotation_deg']:.3f}" if "max_rotation_deg" in s else "-"),
            (f"{s['scale_range'][0]:.4f}..{s['scale_range'][1]:.4f}" if s.get("scale_range") else "-"),
            (f"{s['max_shear']:.4f}" if "max_shear" in s else "-"),
            ", ".join(flags) or "ok"]) + " |")
    full = "\n".join(lines)
    if a.md:
        with open(a.md, "w") as f:
            f.write(f"# Alignment grid search: {a.runs}\n\n{len(rows)} runs. Judge = total RANSAC inliers; the other columns are tripwires "
                    f"(rotation > {a.rot_tol} deg, |scale-1| > {a.scale_tol}, shear > {a.shear_tol}, unconnected views, failed pairs).\n\n" + full + "\n")
    print("\n".join(lines[: a.top + 2]))
    if len(rows) > a.top:
        print(f"... {len(rows) - a.top} more rows (--top N; the markdown report has all {len(rows)})")
    if rows:
        print(f"\nmost inliers: {short(rows[0])}")
        print("pick = the simplest adequate solver of that matching: see `rank_runs.py best`")


def flags_of(r, rot_tol, scale_tol, shear_tol):
    s, m = r.get("solve", {}).get("totals", {}), r.get("match", {}).get("totals", {})
    f = []
    if not s or s.get("avg_error") is None or s.get("failure"):
        f.append("solve failed")
    if s.get("views_missing"):
        f.append("unconnected views")
    if s.get("max_rotation_deg", 0) > rot_tol:
        f.append("rotation")
    if s.get("scale_range") and max(abs(s["scale_range"][0] - 1), abs(s["scale_range"][1] - 1)) > scale_tol:
        f.append("scale")
    if s.get("max_shear", 0) > shear_tol:
        f.append("shear")
    return f


def cmd_best(a):
    """Print 'LABEL SOLVER MAX_ERROR' of the best unflagged run of a level (most inliers, then lowest error)."""
    rows = [json.loads(l) for l in open(a.runs) if l.strip()]
    if a.level:
        rows = [r for r in rows if r["meta"].get("level") == a.level]
    rows.sort(key=lambda r: (-(r.get("match", {}).get("totals", {}).get("inliers_total") or 0),
                             r.get("solve", {}).get("totals", {}).get("avg_error") if r.get("solve", {}).get("totals", {}).get("avg_error") is not None else 1e9))
    ok = [r for r in rows if not flags_of(r, a.rot_tol, a.scale_tol, a.shear_tol)]
    if not ok:
        print("no unflagged run; the best flagged one is: " + (short(rows[0]) if rows else "none"), file=sys.stderr)
        if not rows or a.strict:
            sys.exit(1)
        ok = rows
    # the simplest adequate model: among the unflagged runs of the best (label, matcher) -- they share the matching, so the
    # inliers are equal -- take the first solver in the preference order whose avg error is within --err-slack of the lowest
    top = ok[0]
    group = [r for r in ok if (r["meta"].get("label"), r["meta"].get("matcher")) == (top["meta"].get("label"), top["meta"].get("matcher"))]
    errs = [r.get("solve", {}).get("totals", {}).get("avg_error") for r in group]
    emin = min(e for e in errs if e is not None) if any(e is not None for e in errs) else None
    order = [t for t in a.prefer.split(",") if t]
    b = None
    for tag in order:
        for r in group:
            e = r.get("solve", {}).get("totals", {}).get("avg_error")
            if r["meta"].get("solver") == tag and (emin is None or e is None or e <= emin * (1 + a.err_slack)):
                b = r
                break
        if b is not None:
            break
    if b is None:
        b = top
    print(b["meta"]["label"], b["meta"]["solver"], b.get("solve", {}).get("totals", {}).get("max_error") or 0)
    print("best: " + short(b), file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    p.add_argument("runs")
    p.add_argument("--meta", nargs="*", help="key=value pairs: level, detector, label, matcher, solver, ...")
    p.add_argument("--detect")
    p.add_argument("--match")
    p.add_argument("--solve")
    p.add_argument("--seconds", type=float)
    p.set_defaults(func=cmd_add)
    p = sub.add_parser("table")
    p.add_argument("runs")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--level")
    p.add_argument("--md", help="also write a markdown report")
    p.add_argument("--rot-tol", type=float, default=1.0)
    p.add_argument("--scale-tol", type=float, default=0.01)
    p.add_argument("--shear-tol", type=float, default=0.01)
    p.add_argument("--err-tol", type=float, default=None, help="flag solves whose avg error exceeds this (global px)")
    p.set_defaults(func=cmd_table)
    p = sub.add_parser("best", help="print 'LABEL SOLVER MAX_ERROR' of the best unflagged run (for ladder.sh)")
    p.add_argument("runs")
    p.add_argument("--level")
    p.add_argument("--prefer", default="tr,rigid-tr,affine-rigid,affine-tr",
                   help="ORDERED solver preference, simplest first; the first one whose error is within --err-slack of the best wins (default tr,rigid-tr,affine-rigid,affine-tr)")
    p.add_argument("--err-slack", type=float, default=0.05, help="relative avg-error slack for preferring a simpler model (default 0.05 = 5 %%)")
    p.add_argument("--strict", action="store_true", help="exit 1 when every run is flagged")
    p.add_argument("--rot-tol", type=float, default=1.0)
    p.add_argument("--scale-tol", type=float, default=0.01)
    p.add_argument("--shear-tol", type=float, default=0.01)
    p.set_defaults(func=cmd_best)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
