#!/usr/bin/env python3
"""Which view pairs to look at. From a match log (match-interestpoints) and optionally the solver log and the
registration report, name the pairs the numbers flag -- failed pairs, the fewest inliers, the largest error, the largest
change against the start -- plus one good pair as a reference, as the `--pairs 'A,B;C,D'` argument of BigStitcher-Spark
`screenshot` (render_pairs.sh).

  pick_pairs.py MATCH_LOG [MATCH_LOG...] [--solve SOLVER_LOG] [--report REPORT.json] [-n 6] [--all-up-to 12]
                [--setups 34,35,38,39] [--captions OUT.json] [--arg-only]

First line: the `--pairs` value -- 'overlapping' when the log has at most --all-up-to pairs (then look at all of them),
otherwise 'A,B;C,D' (setup ids; screenshot renders one timepoint per call). Then one line per picked pair with the reason.
--report takes `registration_report.py ... --json OUT`; --captions writes {"A,B": "1,234 inl, 1.2 px"} for every pair
of the log (contact_sheet.py --captions). Stdlib only; uses parse_logs.py next to this script.
"""
import argparse
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_logs import parse_log  # noqa: E402


def ids(key):
    """'0,34>0,35' -> ((0, 34), (0, 35))"""
    a, b = key.split(">")
    return tuple(int(x) for x in a.split(",")), tuple(int(x) for x in b.split(","))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("match_logs", nargs="+")
    ap.add_argument("--solve", help="solver log: pairs the solver dropped are flagged")
    ap.add_argument("--report", help="registration_report.py --json output: the largest change vs the start is flagged")
    ap.add_argument("-n", type=int, default=6, help="how many pairs to name (default 6)")
    ap.add_argument("--all-up-to", type=int, default=12, help="print 'overlapping' when the log has at most this many pairs (default 12)")
    ap.add_argument("--setups", help="only pairs within these setup ids, e.g. 34,35,38,39 or 0-5")
    ap.add_argument("--captions", metavar="OUT.json", help="write a caption per pair for contact_sheet.py")
    ap.add_argument("--arg-only", action="store_true", help="print only the --pairs value")
    a = ap.parse_args()

    sel = None
    if a.setups:
        sel = set()
        for part in a.setups.split(","):
            lo, _, hi = part.partition("-")
            sel.update(range(int(lo), int(hi or lo) + 1))

    pairs = {}
    for path in a.match_logs:
        r = parse_log(path)
        if r["kind"] != "match":
            sys.exit(f"{path} is a {r['kind']} log, not a match log")
        for key, p in r["pairs"].items():
            (ta, sa), (tb, sb) = ids(key)
            if sel is not None and (sa not in sel or sb not in sel):
                continue
            pairs[key] = dict(p)
    if not pairs:
        sys.exit("no pairs in the match log(s)" + (f" within setups {a.setups}" if a.setups else ""))

    tps = sorted({ids(k)[0][0] for k in pairs})
    if len(tps) > 1:
        print(f"# pairs span timepoints {tps}; using {tps[0]} (screenshot renders one timepoint per call)", file=sys.stderr)
        pairs = {k: v for k, v in pairs.items() if ids(k)[0][0] == tps[0]}

    dropped = set()
    if a.solve:
        s = parse_log(a.solve)
        if s["kind"] != "solver":
            sys.exit(f"{a.solve} is a {s['kind']} log, not a solver log")
        if s["pairs"]:
            dropped = {k for k in pairs if k not in s["pairs"] and ">".join(reversed(k.split(">"))) not in s["pairs"]}

    view_change, pair_change = {}, {}
    if a.report:
        rep = json.load(open(a.report))
        for v, row in rep.get("views", {}).items():
            if "change_vs_ref" in row:
                view_change[tuple(int(x) for x in v.split(","))] = row["change_vs_ref"]["corner_disp_max"]
        for p in rep.get("pairs", []):
            if "relative_change_max" in p:
                pair_change[(tuple(int(x) for x in p["a"].split(",")), tuple(int(x) for x in p["b"].split(",")))] = p["relative_change_max"]

    ok = {k: p for k, p in pairs.items() if p.get("status") == "ok" and p.get("inliers")}
    picked, reasons = [], {}

    def pick(key, why):
        if key not in reasons:
            picked.append(key)
            reasons[key] = why

    for k, p in pairs.items():
        if k not in ok:
            pick(k, f"FAILED: {p.get('status', 'no inliers')}" + (f" ({p.get('candidates', 0):,} candidates)" if p.get("candidates") else ""))
    for k in sorted(dropped):
        pick(k, "dropped by the solver (no correspondences used)")
    if ok:
        by_inl = sorted(ok, key=lambda k: ok[k]["inliers"])
        for k in by_inl[:2]:
            pick(k, f"fewest inliers: {ok[k]['inliers']:,}")
        errs = {k: p["avg_error"] for k, p in ok.items() if p.get("avg_error") is not None}
        if errs:
            kmax = max(errs, key=errs.get)
            med = statistics.median(errs.values())
            if errs[kmax] > 1.5 * med:
                pick(kmax, f"largest error: {errs[kmax]:.2f} px (median {med:.2f})")
    if pair_change:
        k2, v = max(pair_change.items(), key=lambda kv: kv[1])
        key = f"{k2[0][0]},{k2[0][1]}>{k2[1][0]},{k2[1][1]}"
        if key in pairs:
            pick(key, f"largest relative change vs the start: {v:.1f} px")
    if view_change:
        vmax = max(view_change, key=view_change.get)
        for k in pairs:
            if vmax in ids(k):
                pick(k, f"view {vmax[1]} moved most: {view_change[vmax]:.1f} px (corner displacement)")
                break
    if ok:
        best = max(ok, key=lambda k: ok[k]["inliers"])
        pick(best, f"reference, most inliers: {ok[best]['inliers']:,}")
    picked = picked[: a.n]

    if len(pairs) <= a.all_up_to:
        arg = "overlapping"
    else:
        arg = ";".join(f"{ids(k)[0][1]},{ids(k)[1][1]}" for k in picked)
    print(arg)
    if not a.arg_only:
        print(f"# {len(pairs)} pair(s) in the log, {len(ok)} with inliers, {len(pairs) - len(ok)} failed"
              + (f", {len(dropped)} dropped by the solver" if a.solve else "") + ("; look at all of them" if arg == "overlapping" else ""))
        for k in picked:
            (ta, sa), (tb, sb) = ids(k)
            p = pairs[k]
            inl = f"{p['inliers']:,} inl" if p.get("inliers") else "-"
            err = f", {p['avg_error']:.2f} px" if p.get("avg_error") is not None else ""
            print(f"#   s{sa}-s{sb}: {reasons[k]}  [{inl}{err}]")

    if a.captions:
        cap = {}
        for k, p in pairs.items():
            (ta, sa), (tb, sb) = ids(k)
            if p.get("status") == "ok" and p.get("inliers"):
                cap[f"{sa},{sb}"] = f"{p['inliers']:,} inl" + (f" of {p['candidates']:,}" if p.get("candidates") else "") \
                    + (f", {p['avg_error']:.2f} px" if p.get("avg_error") is not None else "")
            else:
                cap[f"{sa},{sb}"] = f"FAILED: {p.get('status', 'no inliers')}"
        with open(a.captions, "w") as f:
            json.dump(cap, f, indent=1)


if __name__ == "__main__":
    main()
