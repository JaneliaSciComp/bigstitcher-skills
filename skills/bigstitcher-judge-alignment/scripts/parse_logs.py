#!/usr/bin/env python3
"""
Turn BigStitcher-Spark logs into metrics. Stdlib only.

  python3 parse_logs.py detect.log match.log solve.log            # human-readable summary per log
  python3 parse_logs.py solve.log --json -                         # JSON to stdout (one object per log)
  python3 parse_logs.py match.log --pairs                          # plus the per-pair table

Recognised logs (the kind is detected from the content):
  detect   detect-interestpoints: points per view (the block after "Computed all interest points, statistics:"),
           noise floor per view / pooled, the derived threshold, min/max intensity, the argument list
  match    match-interestpoints: one result per view pair -- inliers, candidates, inlier %, average error, or the
           failure reason (too few candidates / no model / too few inliers); multi-consensus and ICP results;
           the EMBEDDINGS prefix (points with a vector, points within the radius)
  solver   solver: connected views, pairs with correspondences, the LAST Avg/Min/Max error block, removed links,
           disconnected groups, per-view transformation models (rotation, scaling, shear derived from the matrix)

Numbers are read with '.' as the decimal separator: run the Java tools with -Duser.language=en -Duser.country=US
(JAVA_OPTS) if your locale prints commas.
"""
import argparse
import json
import math
import os
import re
import statistics
import sys

RE_TS = re.compile(r"^\([A-Z][a-z]{2} [A-Z][a-z]{2} +\d+ [\d:]+ [A-Z]+ \d{4}\): ")
RE_PAIR = re.compile(r"\[TP=(\d+) ViewId=(\d+) Label=(\S+) >>> TP=(\d+) ViewId=(\d+) Label=(\S+)\]: (.*)$")
RE_OK = re.compile(r"Remaining inliers after RANSAC: (\d+) of (\d+) \((\d+)%\) with average error ([\d.]+)"
                   r"(?: \[removed (\d+) inconsistent inliers\])?")
RE_FEW_INL = re.compile(r"Model found but not enough remaining inliers \((\d+)/(\d+)\) after RANSAC of (\d+)")
RE_NO_MODEL = re.compile(r"NO Model found after RANSAC of (\d+)")
RE_FEW_CAND = re.compile(r"Not enough correspondences found (\d+), should be at least (\d+)")
RE_MC = re.compile(r"Found (\d+) set\(s\) containing (\d+)/(\d+) inliers \((\d+)%\) with min/avg/max set-error "
                   r"\(([\d.]+)/([\d.]+)/([\d.]+)\)")
RE_ICP = re.compile(r"Found (\d+) matches, avg error \[px\] ([\d.]+) after (\d+) iterations")
RE_EMB = re.compile(r"EMBEDDINGS (\d+) <-> (\d+) points(?:, (\d+) <-> (\d+) with a vector)?(?:, (\d+) <-> (\d+) within ([\d.]+) px)?: (.*)$")
RE_EMB_FEW = re.compile(r"(\d+) candidates, not enough \(need >= (\d+)\)")
RE_LOADED = re.compile(r"Loaded (\d+) corresponding interest points")
RE_VIEWPTS = re.compile(r"^tpId=(\d+) setupId=(\d+): (\d+)$")
RE_FLOOR = re.compile(r"noise floor of tpId=(\d+) setupId=(\d+): ([\d.Ee+-]+)")
RE_FLOOR_POOL = re.compile(r"noise floor .*?= ([\d.Ee+-]+) \[([\d.Ee+-]+) \.\. ([\d.Ee+-]+), median ([\d.Ee+-]+)\]")
RE_THR = re.compile(r"threshold = ([\d.Ee+-]+) x ([\d.Ee+-]+) = ([\d.Ee+-]+)")
RE_INT = re.compile(r"min intensity = ([\d.Ee+-]+), max intensity = ([\d.Ee+-]+)")
RE_SOLVE_PAIR = re.compile(r"tpId=(\d+) setupId=(\d+) <-> tpId=(\d+) setupId=(\d+): (\d+) correspondences added")
RE_CONNECT = re.compile(r"Connecting tpId=(\d+) setupId=(\d+) \((\S+)\) <-> tpId=(\d+) setupId=(\d+) \((\S+)\): (\d+) matches")
RE_ERR = re.compile(r"(Avg|Min|Max) Error: ([\d.Ee+-]+)px")
RE_CONN_VIEWS = re.compile(r"Total number of connected views: (\d+) \((\d+) missing")
RE_TOTAL_VIEWS = re.compile(r"Total number of views: (\d+)")
RE_TOTAL_PAIRS = re.compile(r"Total number of pairs of views that are connected: (\d+)")
RE_REMOVED = re.compile(r"Removed link from (.*?) to (.*?) \(error=([\d.Ee+-]+)\)")
RE_REMOVED_N = re.compile(r"Removed (\d+) inconsistent link\(s\) in (\d+) iteration\(s\)")
RE_GROUPS = re.compile(r"Identified (\d+) \(dis\)connected groups")
RE_GLOBOPT = re.compile(r"Global optimization of (\d+)(?: view-tiles \(Model=(\w+)\))?")
RE_MODEL = re.compile(r"^tpId=(\d+) setupId=(\d+): \(([^)]*)\), \(([^)]*)\), \(([^)]*)\)(.*)$")
RE_FIXED = re.compile(r"fixedViews: \[(.*?)\]")


def fnum(s):
    return float(s.replace(",", "."))


def strip_ts(line):
    return RE_TS.sub("", line.rstrip("\n"))


def parse_args_line(lines):
    """The first line of a launcher log is the argument list '[-x, file.xml, -l, beads, ...]'."""
    for ln in lines[:5]:
        s = ln.strip()
        if s.startswith("[") and s.endswith("]") and ", " in s:
            toks = [t.strip() for t in s[1:-1].split(", ")]
            opts, i = {}, 0
            while i < len(toks):
                t = toks[i]
                if t.startswith("-"):
                    if "=" in t:
                        k, v = t.split("=", 1)
                        opts.setdefault(k, []).append(v)
                        i += 1
                    elif i + 1 < len(toks) and not toks[i + 1].startswith("-"):
                        opts.setdefault(t, []).append(toks[i + 1])
                        i += 2
                    else:
                        opts.setdefault(t, []).append(True)
                        i += 1
                else:
                    i += 1
            return {k: (v[0] if len(v) == 1 else v) for k, v in opts.items()}
    return {}


def detect_kind(lines):
    text = "\n".join(lines)
    if "Total number of connected views" in text or "Global optimization of" in text or "No views are connected" in text \
            or "Transformation Models:" in text:
        return "solver"
    if ">>>" in text and ("RANSAC" in text or "Not enough" in text or "matches, avg error" in text or "candidates, not enough" in text
                          or "set(s) containing" in text):
        return "match"
    if "Computed all interest points" in text or "noise floor of" in text or RE_VIEWPTS.search(text.replace("\r", "")):
        return "detect"
    return "unknown"


# ---------------------------------------------------------------- 3x3 decomposition, stdlib only
def jacobi_eigvals(S, sweeps=50):
    """Eigenvalues of a symmetric 3x3 (list of lists) by Jacobi rotations."""
    a = [row[:] for row in S]
    for _ in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(3) for j in range(3) if i != j)
        if off < 1e-22:
            break
        for p in range(3):
            for q in range(p + 1, 3):
                if abs(a[p][q]) < 1e-300:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1.0 if theta >= 0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(3):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(3):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
    return sorted(a[i][i] for i in range(3))


def decompose3(A):
    """rotation angle (deg), singular values (scales), shear of a 3x3 matrix (list of 3 rows)."""
    AtA = [[sum(A[k][i] * A[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    ev = jacobi_eigvals(AtA)
    scales = [math.sqrt(max(e, 0.0)) for e in ev]
    # shear: off-diagonal of A^T A normalised by the diagonal (0 for pure rotation+anisotropic scale along the axes)
    shear = max(abs(AtA[i][j]) / math.sqrt(max(AtA[i][i] * AtA[j][j], 1e-300)) for i in range(3) for j in range(3) if i != j)
    # rotation: polar factor R = A (A^T A)^-1/2 -- approximate via normalising A by its scales when nearly axis-aligned;
    # for the angle use the trace of the orthogonalised matrix (Gram-Schmidt), good to << 0.1 deg for small shears
    cols = [[A[r][c] for r in range(3)] for c in range(3)]
    q = []
    for v in cols:
        for u in q:
            d = sum(x * y for x, y in zip(v, u))
            v = [x - d * y for x, y in zip(v, u)]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        q.append([x / n for x in v])
    det = (q[0][0] * (q[1][1] * q[2][2] - q[1][2] * q[2][1]) - q[0][1] * (q[1][0] * q[2][2] - q[1][2] * q[2][0])
           + q[0][2] * (q[1][0] * q[2][1] - q[1][1] * q[2][0]))
    tr = q[0][0] + q[1][1] + q[2][2]
    if det < 0:
        tr = -tr
    angle = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0))))
    return angle, scales, shear, det < 0


# ---------------------------------------------------------------- parsers
def parse_detect(lines):
    views, floors, pooled, thr, intensity = {}, {}, None, None, None
    in_stats = False
    for raw in lines:
        ln = strip_ts(raw)
        if ln.startswith("Computed all interest points"):
            in_stats, views = True, {}
            continue
        m = RE_VIEWPTS.match(ln)
        if m:
            views[f"{m.group(1)},{m.group(2)}"] = int(m.group(3))   # the stats block overwrites earlier per-view lines
            continue
        if in_stats and ln.strip() and not m:
            in_stats = False
        m = RE_FLOOR.search(ln)
        if m:
            floors[f"{m.group(1)},{m.group(2)}"] = fnum(m.group(3))
        m = RE_FLOOR_POOL.search(ln)
        if m:
            pooled = {"highest": fnum(m.group(1)), "min": fnum(m.group(2)), "max": fnum(m.group(3)), "median": fnum(m.group(4))}
        m = RE_THR.search(ln)
        if m:
            thr = {"noise_factor": fnum(m.group(1)), "noise_floor": fnum(m.group(2)), "threshold": fnum(m.group(3))}
        m = RE_INT.search(ln)
        if m and intensity is None:
            intensity = [fnum(m.group(1)), fnum(m.group(2))]
    counts = list(views.values())
    return {"views": views, "noise_floor": floors, "noise_floor_pooled": pooled, "threshold": thr, "intensity": intensity,
            "totals": {"n_views": len(counts), "points": sum(counts), "min": min(counts) if counts else 0,
                       "median": statistics.median(counts) if counts else 0, "max": max(counts) if counts else 0}}


def classify_result(text):
    r = {"status": "other", "text": text}
    m = RE_EMB.match(text)
    if m:
        r.update({"method": "EMBEDDINGS", "points_a": int(m.group(1)), "points_b": int(m.group(2))})
        if m.group(3):
            r.update({"with_vector_a": int(m.group(3)), "with_vector_b": int(m.group(4))})
        if m.group(5):
            r.update({"within_radius_a": int(m.group(5)), "within_radius_b": int(m.group(6)), "radius": fnum(m.group(7))})
        text = m.group(8)
        r["text"] = text
        m2 = RE_EMB_FEW.match(text)
        if m2:
            r.update({"status": "too_few_candidates", "candidates": int(m2.group(1)), "min_required": int(m2.group(2)), "inliers": 0})
            return r
    m = RE_OK.search(text)
    if m:
        r.update({"status": "ok", "inliers": int(m.group(1)), "candidates": int(m.group(2)), "inlier_pct": int(m.group(3)),
                  "avg_error": fnum(m.group(4)), "removed_inconsistent": int(m.group(5) or 0)})
        return r
    m = RE_MC.search(text)
    if m:
        r.update({"status": "ok", "multi_consensus": True, "sets": int(m.group(1)), "inliers": int(m.group(2)),
                  "candidates": int(m.group(3)), "inlier_pct": int(m.group(4)), "set_error_min": fnum(m.group(5)),
                  "avg_error": fnum(m.group(6)), "set_error_max": fnum(m.group(7))})
        return r
    m = RE_ICP.search(text)
    if m:
        r.update({"status": "ok", "method": "ICP", "inliers": int(m.group(1)), "avg_error": fnum(m.group(2)), "iterations": int(m.group(3))})
        return r
    m = RE_FEW_INL.search(text)
    if m:
        r.update({"status": "too_few_inliers", "inliers": int(m.group(1)), "min_required": int(m.group(2)), "candidates": int(m.group(3))})
        return r
    m = RE_NO_MODEL.search(text)
    if m:
        r.update({"status": "no_model", "inliers": 0, "candidates": int(m.group(1))})
        return r
    m = RE_FEW_CAND.search(text)
    if m:
        r.update({"status": "too_few_candidates", "inliers": 0, "candidates": int(m.group(1)), "min_required": int(m.group(2))})
        return r
    m = RE_LOADED.search(text)
    if m:
        r.update({"status": "loaded", "inliers": int(m.group(1))})
    return r


def parse_match(lines):
    pairs, declared = {}, None
    for raw in lines:
        ln = strip_ts(raw)
        m = re.search(r"In total (\d+) pairs of views need to be aligned", ln)
        if m:
            declared = int(m.group(1))
        m = RE_PAIR.search(ln)
        if m:
            key = f"{m.group(1)},{m.group(2)}>{m.group(4)},{m.group(5)}"
            r = classify_result(m.group(7))
            if r["status"] == "loaded":
                continue
            r.update({"a": f"{m.group(1)},{m.group(2)}", "b": f"{m.group(4)},{m.group(5)}", "label_a": m.group(3), "label_b": m.group(6)})
            pairs[key] = r
    ok = [p for p in pairs.values() if p["status"] == "ok"]
    failed = [p for p in pairs.values() if p["status"] not in ("ok", "other")]
    inl = [p["inliers"] for p in ok]
    cand = [p.get("candidates", 0) for p in pairs.values()]
    err = [p["avg_error"] for p in ok if "avg_error" in p]
    tot = {"pairs_declared": declared, "pairs_reported": len(pairs), "pairs_ok": len(ok), "pairs_failed": len(failed),
           "inliers_total": sum(inl), "candidates_total": sum(cand),
           "inliers_min": min(inl) if inl else 0, "inliers_median": statistics.median(inl) if inl else 0, "inliers_max": max(inl) if inl else 0,
           "avg_error_mean": (sum(e * p["inliers"] for e, p in zip(err, [q for q in ok if "avg_error" in q])) / max(sum(inl), 1)) if err else None,
           "failures": sorted(set(p["status"] for p in failed))}
    return {"pairs": pairs, "totals": tot}


def parse_solver(lines):
    pairs, connect, errors, removed, models, info = {}, {}, [], [], {}, {}
    cur_err, in_models, groups = {}, False, None
    for raw in lines:
        ln = strip_ts(raw)
        m = RE_SOLVE_PAIR.search(ln)
        if m:
            pairs[f"{m.group(1)},{m.group(2)}>{m.group(3)},{m.group(4)}"] = int(m.group(5))
        m = RE_CONNECT.search(ln)
        if m:
            connect[f"{m.group(1)},{m.group(2)}>{m.group(4)},{m.group(5)}"] = int(m.group(7))
        m = RE_TOTAL_PAIRS.search(ln)
        if m:
            info["pairs_connected"] = int(m.group(1))
        m = RE_TOTAL_VIEWS.search(ln)
        if m:
            info["views"] = int(m.group(1))
        m = RE_CONN_VIEWS.search(ln)
        if m:
            info["views_connected"], info["views_missing"] = int(m.group(1)), int(m.group(2))
        m = RE_FIXED.search(ln)
        if m:
            info["fixed_views"] = m.group(1)
        m = RE_GLOBOPT.search(ln)
        if m:
            cur_err = {"n": int(m.group(1)), "model": m.group(2)}
        m = RE_ERR.search(ln)
        if m:
            cur_err[m.group(1).lower()] = fnum(m.group(2))
            if "max" in cur_err and "avg" in cur_err and "min" in cur_err:
                errors.append(cur_err)
                cur_err = {}
        m = RE_REMOVED.search(ln)
        if m:
            removed.append({"from": m.group(1), "to": m.group(2), "error": fnum(m.group(3))})
        m = RE_REMOVED_N.search(ln)
        if m:
            info["removed_links"], info["removal_iterations"] = int(m.group(1)), int(m.group(2))
        m = RE_GROUPS.search(ln)
        if m:
            groups = int(m.group(1))
        if "No views are connected" in ln or "No transformations could be found" in ln or "There are no connected tiles" in ln:
            info["failure"] = ln.strip()
        if "Transformation Models:" in ln:
            in_models = True
            continue
        if in_models:
            m = RE_MODEL.match(ln.strip())
            if m:
                rows = [[fnum(x) for x in m.group(i).split(",")] for i in (3, 4, 5)]
                A = [r[:3] for r in rows]
                t = [r[3] for r in rows]
                angle, scales, shear, mirrored = decompose3(A)
                models[f"{m.group(1)},{m.group(2)}"] = {"matrix": rows, "translation": t, "rotation_deg": round(angle, 4),
                                                         "scales": [round(s, 5) for s in scales], "shear": round(shear, 5),
                                                         "mirrored": mirrored, "tail": m.group(6).strip(" ,")}
            elif ln.strip() and not ln.startswith("tpId="):
                in_models = False
    last = errors[-1] if errors else None
    tot = dict(info)
    tot.update({"pairs_with_correspondences": len(pairs), "correspondences_total": sum(pairs.values()),
                "matches_total": sum(connect.values()) if connect else None,
                "avg_error": last["avg"] if last else None, "min_error": last["min"] if last else None,
                "max_error": last["max"] if last else None, "error_blocks": len(errors), "removed_links_list": removed,
                "disconnected_groups": groups})
    if models:
        tot["max_rotation_deg"] = max(v["rotation_deg"] for v in models.values())
        tot["scale_range"] = [min(min(v["scales"]) for v in models.values()), max(max(v["scales"]) for v in models.values())]
        tot["max_shear"] = max(v["shear"] for v in models.values())
    return {"pairs": pairs, "connections": connect, "errors": errors, "models": models, "totals": tot}



def parse_log(path):
    with open(path, errors="replace") as f:
        lines = f.read().splitlines()
    kind = detect_kind(lines)
    out = {"log": path, "kind": kind, "args": parse_args_line(lines)}
    if kind == "detect":
        out.update(parse_detect(lines))
    elif kind == "match":
        out.update(parse_match(lines))
    elif kind == "solver":
        out.update(parse_solver(lines))
    out["exceptions"] = sum(1 for ln in lines if "Exception" in ln and "SLF4J" not in ln)
    out["done"] = any(ln.strip().startswith("Done") for ln in lines[-30:])
    return out


def summarize(r, show_pairs=False):
    t = r.get("totals", {})
    print(f"== {r['log']}  [{r['kind']}]" + ("" if r["done"] else "  (no 'Done' line: incomplete?)") +
          (f"  exceptions: {r['exceptions']}" if r["exceptions"] else ""))
    a = r.get("args", {})
    if a:
        keys = [k for k in ("-l", "--label", "--method", "-m", "-s", "-t", "--noiseFactor", "-dsxy", "-dsz", "-i0", "-i1", "--anisotropy",
                            "-tm", "-rm", "--lambda", "-rme", "-rmni", "-rmir", "-sr", "--descriptorRatio", "--minSimilarity", "-fv", "--dryRun") if k in a]
        print("   args: " + " ".join(f"{k} {a[k]}" if a[k] is not True else k for k in keys))
    if r["kind"] == "detect":
        print(f"   points: {t['points']:,} over {t['n_views']} views (min {t['min']:,} / median {t['median']:,.0f} / max {t['max']:,})")
        if r.get("threshold"):
            th = r["threshold"]
            print(f"   threshold {th['threshold']:.6g} = {th['noise_factor']:g} x noise floor {th['noise_floor']:.6g}", end="")
            pool = r.get("noise_floor_pooled")
            print(f"  (per-view floors {pool['min']:.3g} .. {pool['max']:.3g}, median {pool['median']:.3g})" if pool else "")
        if r.get("intensity"):
            print(f"   intensity range {r['intensity'][0]:g} .. {r['intensity'][1]:g}")
        if show_pairs:
            for k, v in sorted(r["views"].items(), key=lambda kv: tuple(int(x) for x in kv[0].split(","))):
                print(f"     view {k:>8}: {v:>9,}" + (f"   floor {r['noise_floor'][k]:.3g}" if k in r.get("noise_floor", {}) else ""))
    elif r["kind"] == "match":
        line = (f"   inliers: {t['inliers_total']:,} total over {t.get('pairs_ok', t.get('pairs_reported', 0))} pairs with a model"
                + (f" (min {t['inliers_min']:,} / median {t['inliers_median']:,.0f} / max {t['inliers_max']:,})" if t.get("inliers_max") else "")
                + f"; candidates {t.get('candidates_total', 0):,}; failed pairs {t.get('pairs_failed', 0)}"
                + (f" of {t['pairs_declared']} declared" if t.get("pairs_declared") else "")
                + (f"; avg error {t['avg_error_mean']:.2f}" if t.get("avg_error_mean") else "")
                + (f"; failures: {', '.join(t['failures'])}" if t.get("failures") else ""))
        print(line)
        if show_pairs:
            for k, p in sorted(r["pairs"].items(), key=lambda kv: -kv[1].get("inliers", 0)):
                extra = f"  err {p['avg_error']:.2f}" if "avg_error" in p else ""
                extra += f"  [{p['status']}]" if p["status"] != "ok" else ""
                extra += f"  radius {p['radius']:g}: {p.get('within_radius_a')}/{p.get('within_radius_b')} pts" if p.get("radius") else ""
                print(f"     {k:>16}: {p.get('inliers', 0):>7,} of {p.get('candidates', 0):>7,}{extra}")
    elif r["kind"] == "solver":
        print(f"   views: {t.get('views_connected', '?')} connected of {t.get('views', '?')} ({t.get('views_missing', '?')} missing)"
              f"; pairs with correspondences {t['pairs_with_correspondences']} ({t['correspondences_total']:,} correspondences)"
              + (f"; fixed {t['fixed_views']}" if t.get("fixed_views") else ""))
        if t.get("avg_error") is not None:
            print(f"   error: avg {t['avg_error']:.3f} / min {t['min_error']:.3f} / max {t['max_error']:.3f} px"
                  f" ({t['error_blocks']} optimisation block(s) logged)")
        if t.get("removed_links_list") or t.get("removed_links"):
            print(f"   removed links: {t.get('removed_links', len(t['removed_links_list']))}")
        if t.get("disconnected_groups"):
            print(f"   disconnected groups: {t['disconnected_groups']}")
        if t.get("failure"):
            print(f"   FAILURE: {t['failure']}")
        if r.get("models"):
            print(f"   transforms: max rotation {t['max_rotation_deg']:.3f} deg, scales {t['scale_range'][0]:.4f} .. {t['scale_range'][1]:.4f},"
                  f" max shear {t['max_shear']:.4f}")
            if show_pairs:
                for k, v in sorted(r["models"].items(), key=lambda kv: tuple(int(x) for x in kv[0].split(","))):
                    print(f"     view {k:>8}: rot {v['rotation_deg']:7.3f} deg  scales {v['scales'][0]:.4f}/{v['scales'][1]:.4f}/{v['scales'][2]:.4f}"
                          f"  shear {v['shear']:.4f}  t ({v['translation'][0]:.1f}, {v['translation'][1]:.1f}, {v['translation'][2]:.1f})")
        if show_pairs and r.get("pairs"):
            for k, n in sorted(r["pairs"].items(), key=lambda kv: -kv[1]):
                print(f"     {k:>16}: {n:>7,} correspondences")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--json", metavar="OUT", help="write the parsed metrics as JSON ('-' = stdout)")
    ap.add_argument("--pairs", action="store_true", help="also print the per-pair / per-view tables")
    a = ap.parse_args()
    results = [parse_log(p) for p in a.logs]
    if a.json:
        txt = json.dumps(results if len(results) > 1 else results[0], indent=1)
        if a.json == "-":
            print(txt)
        else:
            with open(a.json, "w") as f:
                f.write(txt)
    if not a.json or a.json != "-":
        for r in results:
            summarize(r, a.pairs)


if __name__ == "__main__":
    main()
