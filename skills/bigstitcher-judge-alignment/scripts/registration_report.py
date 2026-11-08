#!/usr/bin/env python3
"""
What a BigStitcher XML's registration looks like, in numbers. Needs numpy.

  python3 registration_report.py dataset.xml                      # per-view transforms + overlapping pairs
  python3 registration_report.py dataset.xml --ref dataset.xml.orig   # plus: how far every view / pair moved
  python3 registration_report.py dataset.xml --setups 34,35,37-42 --json report.json

Per view: the stack of <ViewTransform> layers (first listed = applied last), the REGISTRATION PART (the layers
above the calibration: tile placement + registration results) decomposed into rotation angle, scales and shear,
and the translation-close check (rotation <= --rot-tol deg, |scale-1| <= --scale-tol, shear <= --shear-tol; a view
that fails is flagged -- an affine that drifted into scale or shear usually means too few or wrong points).
Pairs: views whose registered bounding boxes intersect (the rule the matcher uses), overlap fraction, relative
rotation and scale between the two views. With --ref: the corner displacement of every view (median / max of
the 8 bounding-box corners, global px) and, per pair, how much B moved RELATIVE to A (a shift common to both
views does not count). Units: the global frame = calibrated pixels (x/y voxels; z scaled by the calibration).
"""
import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET

try:
    import numpy as np
except ImportError:
    sys.exit("registration_report.py needs numpy (pip install numpy)")


def parse_ids(spec):
    out = set()
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if "-" in tok:
            a, b = tok.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(tok))
    return out


def affine4(text):
    v = [float(x) for x in text.split()]
    M = np.eye(4)
    M[:3, :] = np.array(v).reshape(3, 4)
    return M


def load(xml_path):
    root = ET.parse(xml_path).getroot()
    setups = {}
    for vs in root.iter("ViewSetup"):
        sid = int(vs.findtext("id"))
        size = vs.findtext("size")
        vox = vs.find("voxelSize")
        setups[sid] = {"name": vs.findtext("name"), "size": [int(x) for x in size.split()] if size else None,
                       "voxel": [float(x) for x in vox.findtext("size").split()] if vox is not None else None,
                       "unit": vox.findtext("unit") if vox is not None else None,
                       "attrs": {a.tag: int(a.text) for a in (vs.find("attributes") if vs.find("attributes") is not None else [])}}
    missing = {(int(v.get("timepoint")), int(v.get("setup"))) for v in root.iter("DeletedView")}
    views = {}
    for vr in root.iter("ViewRegistration"):
        key = (int(vr.get("timepoint")), int(vr.get("setup")))
        layers = []
        for vt in vr.findall("ViewTransform"):
            aff = vt.find("affine")
            if aff is not None:
                layers.append((vt.findtext("Name") or "", affine4(aff.text)))
        M = np.eye(4)
        for _, L in layers:
            M = M @ L
        views[key] = {"layers": layers, "M": M}
    return setups, views, missing


def decompose(M):
    A = M[:3, :3]
    U, S, Vt = np.linalg.svd(A)
    R = U @ Vt
    mirrored = np.linalg.det(R) < 0
    if mirrored:
        U[:, -1] *= -1
        R = U @ Vt
    angle = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))
    AtA = A.T @ A
    d = np.sqrt(np.clip(np.diag(AtA), 1e-300, None))
    N = AtA / np.outer(d, d)
    shear = float(np.max(np.abs(N - np.diag(np.diag(N)))))
    axis = None
    if angle > 1e-6:
        w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
        n = np.linalg.norm(w)
        axis = (w / n).round(3).tolist() if n > 1e-12 else None
    return {"rotation_deg": float(angle), "axis": axis, "scales": sorted(S.tolist()), "shear": shear,
            "translation": M[:3, 3].tolist(), "mirrored": bool(mirrored)}


def classify(M, eps=1e-6):
    A = M[:3, :3]
    t = M[:3, 3]
    if np.allclose(A, np.eye(3), atol=eps):
        return "identity" if np.allclose(t, 0, atol=eps) else "translation"
    AtA = A.T @ A
    if np.allclose(AtA, np.eye(3), atol=1e-6):
        return "rigid"
    if np.allclose(AtA, AtA[0, 0] * np.eye(3), atol=1e-6):
        return "similarity"
    if np.allclose(A, np.diag(np.diag(A)), atol=eps):
        return "scaling"
    return "affine"


def corners(size):
    sx, sy, sz = size
    return np.array([[x, y, z, 1.0] for x in (0, sx) for y in (0, sy) for z in (0, sz)])


def aabb(M, size):
    c = (M @ corners(size).T).T[:, :3]
    return c.min(0), c.max(0)


def registration_part(layers):
    """Product of the layers above the first calibration-like layer (name contains 'calibration')."""
    M = np.eye(4)
    used = []
    for name, L in layers:
        if "calibration" in name.lower():
            break
        M = M @ L
        used.append(name)
    return M, used


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml")
    ap.add_argument("--ref", help="a second XML (e.g. dataset.xml.orig) to measure the change against")
    ap.add_argument("--tp", type=int, default=None, help="timepoint (default: all)")
    ap.add_argument("--setups", help="view setup ids, e.g. 0-5 or 34,35,37")
    ap.add_argument("--min-overlap", type=float, default=0.0, help="report pairs whose overlap fraction is above this (default 0 = any intersection)")
    ap.add_argument("--rot-tol", type=float, default=1.0, help="translation-close check: max rotation in degrees (default 1)")
    ap.add_argument("--scale-tol", type=float, default=0.01, help="max |scale - 1| (default 0.01)")
    ap.add_argument("--shear-tol", type=float, default=0.01, help="max shear (default 0.01)")
    ap.add_argument("--json", metavar="OUT", help="write everything as JSON ('-' = stdout only)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    setups, views, missing = load(a.xml)
    ref = load(a.ref)[1] if a.ref else None
    sel = parse_ids(a.setups) if a.setups else None
    keys = sorted(k for k in views if (a.tp is None or k[0] == a.tp) and (sel is None or k[1] in sel) and k not in missing
                  and setups.get(k[1], {}).get("size"))
    if not keys:
        sys.exit("no views selected")

    out_views, flags = {}, []
    for k in keys:
        v = views[k]
        layers = [{"name": n, "type": classify(L), **{kk: vv for kk, vv in decompose(L).items() if kk in ("rotation_deg", "scales", "shear")},
                   "translation_norm": float(np.linalg.norm(L[:3, 3]))} for n, L in v["layers"]]
        Mreg, used = registration_part(v["layers"])
        dec = decompose(Mreg)
        checks = {"rotation": dec["rotation_deg"] <= a.rot_tol,
                  "scale": max(abs(s - 1) for s in dec["scales"]) <= a.scale_tol,
                  "shear": dec["shear"] <= a.shear_tol}
        row = {"layers": layers, "registration_part": {"layers": used, **dec}, "translation_close": all(checks.values()), "checks": checks,
               "bbox": [x.tolist() for x in aabb(v["M"], setups[k[1]]["size"])], "attrs": setups[k[1]]["attrs"]}
        if not row["translation_close"]:
            flags.append(f"view {k}: " + ", ".join(f"{c} fails" for c, ok in checks.items() if not ok)
                         + f" (rot {dec['rotation_deg']:.3f} deg, scales {min(dec['scales']):.4f}..{max(dec['scales']):.4f}, shear {dec['shear']:.4f})")
        if ref is not None and k in ref:
            Ms, Mr = v["M"], ref[k]["M"]
            C = corners(setups[k[1]]["size"]).T
            d = np.linalg.norm(((Ms @ C) - (Mr @ C))[:3], axis=0)
            row["change_vs_ref"] = {"corner_disp_median": float(np.median(d)), "corner_disp_max": float(d.max()),
                                    **{kk: vv for kk, vv in decompose(Ms @ np.linalg.inv(Mr)).items() if kk in ("rotation_deg", "scales", "shear")}}
        out_views[f"{k[0]},{k[1]}"] = row

    pairs = []
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if ka[0] != kb[0]:
                continue
            (mina, maxa), (minb, maxb) = out_views[f"{ka[0]},{ka[1]}"]["bbox"], out_views[f"{kb[0]},{kb[1]}"]["bbox"]
            lo, hi = np.maximum(mina, minb), np.minimum(maxa, maxb)
            if np.any(hi <= lo):
                continue
            inter = float(np.prod(hi - lo))
            vol = min(float(np.prod(np.array(maxa) - np.array(mina))), float(np.prod(np.array(maxb) - np.array(minb))))
            frac = inter / vol if vol else 0.0
            if frac < a.min_overlap:
                continue
            Ma, Mb = views[ka]["M"], views[kb]["M"]
            rel = decompose(np.linalg.inv(Ma) @ Mb)
            p = {"a": f"{ka[0]},{ka[1]}", "b": f"{kb[0]},{kb[1]}", "overlap_frac": frac, "overlap_size": (hi - lo).tolist(),
                 "relative_rotation_deg": rel["rotation_deg"], "relative_scale": float(np.cbrt(abs(np.linalg.det(Mb[:3, :3])) / abs(np.linalg.det(Ma[:3, :3]))))}
            if ref is not None and ka in ref and kb in ref:
                Mar, Mbr = ref[ka]["M"], ref[kb]["M"]
                C = corners(setups[kb[1]]["size"]).T
                moved_with_a = (Ma @ np.linalg.inv(Mar)) @ (Mbr @ C)
                d = np.linalg.norm((moved_with_a - Mb @ C)[:3], axis=0)
                p["relative_change_max"] = float(d.max())
                p["relative_change_median"] = float(np.median(d))
            pairs.append(p)
    pairs.sort(key=lambda p: -p["overlap_frac"])

    summary = {"xml": a.xml, "ref": a.ref, "n_views": len(keys), "n_missing": len(missing), "n_pairs": len(pairs), "flags": flags,
               "max_rotation_deg": max(v["registration_part"]["rotation_deg"] for v in out_views.values()),
               "scale_range": [min(min(v["registration_part"]["scales"]) for v in out_views.values()),
                               max(max(v["registration_part"]["scales"]) for v in out_views.values())],
               "max_shear": max(v["registration_part"]["shear"] for v in out_views.values()),
               "units": "global frame = calibrated px", "voxel_sizes": sorted({tuple(setups[k[1]]["voxel"]) for k in keys if setups[k[1]]["voxel"]})}
    if ref is not None:
        ch = [v["change_vs_ref"] for v in out_views.values() if "change_vs_ref" in v]
        if ch:
            summary["corner_disp_median_over_views"] = float(np.median([c["corner_disp_median"] for c in ch]))
            summary["corner_disp_max_over_views"] = max(c["corner_disp_max"] for c in ch)
        if pairs and "relative_change_max" in pairs[0]:
            summary["pair_relative_change_max"] = max(p["relative_change_max"] for p in pairs)
    result = {"summary": summary, "views": out_views, "pairs": pairs}

    if a.json:
        txt = json.dumps(result, indent=1)
        if a.json == "-":
            print(txt)
        else:
            with open(a.json, "w") as f:
                f.write(txt)
    if not a.quiet and a.json != "-":
        s = summary
        print(f"== {a.xml}: {s['n_views']} views ({s['n_missing']} missing), {s['n_pairs']} overlapping pairs; voxel sizes {s['voxel_sizes']}")
        first = out_views[f"{keys[0][0]},{keys[0][1]}"]
        print("   layers (first = applied last): " + " | ".join(f"{l['name']} [{l['type']}]" for l in first["layers"]))
        print(f"   registration part = {first['registration_part']['layers']}")
        print(f"   translation-close check: max rotation {s['max_rotation_deg']:.4f} deg, scales {s['scale_range'][0]:.5f} .. {s['scale_range'][1]:.5f}, "
              f"max shear {s['max_shear']:.5f} -> {'OK' if not flags else 'FLAG ' + str(len(flags)) + ' view(s)'}")
        for fl in flags[:10]:
            print("     " + fl)
        hdr = f"   {'view':>8} {'rot deg':>8} {'scale min..max':>16} {'shear':>7} {'translation (global px)':>34}"
        if ref is not None:
            hdr += f" {'moved med/max':>16}"
        print(hdr)
        for k in keys:
            v = out_views[f"{k[0]},{k[1]}"]
            r = v["registration_part"]
            line = (f"   {k[0]},{k[1]:>5} {r['rotation_deg']:8.4f} {min(r['scales']):7.4f}..{max(r['scales']):7.4f} {r['shear']:7.4f} "
                    f"({r['translation'][0]:9.1f}, {r['translation'][1]:9.1f}, {r['translation'][2]:9.1f})")
            if "change_vs_ref" in v:
                c = v["change_vs_ref"]
                line += f" {c['corner_disp_median']:7.2f}/{c['corner_disp_max']:7.2f}"
            print(line)
        if pairs:
            print(f"   {'pair':>14} {'overlap':>8} {'overlap size (px)':>26} {'rel rot':>8} {'rel scale':>9}" + (f" {'rel change med/max':>20}" if ref else ""))
            for p in pairs:
                line = (f"   {p['a']:>6} - {p['b']:<6} {100 * p['overlap_frac']:7.1f}% ({p['overlap_size'][0]:7.0f} x {p['overlap_size'][1]:6.0f} x {p['overlap_size'][2]:6.0f})"
                        f" {p['relative_rotation_deg']:8.4f} {p['relative_scale']:9.5f}")
                if "relative_change_max" in p:
                    line += f" {p['relative_change_median']:9.2f}/{p['relative_change_max']:9.2f}"
                print(line)


if __name__ == "__main__":
    main()
