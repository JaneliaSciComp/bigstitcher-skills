#!/usr/bin/env python3
"""
First look at a BigStitcher XML before tuning the alignment. Stdlib only (the optional --intensity sampling uses
tensorstore when importable).

  python3 inspect_dataset.py dataset.xml                 # views, groups, transform stacks, labels, pairs, ladder
  python3 inspect_dataset.py dataset.xml --intensity     # + sampled intensity percentiles per group (for -i0/-i1)
  python3 inspect_dataset.py dataset.xml --setups 32-47 --json inspect.json

It reports
  * the views (timepoints, setups, attributes), image sizes, voxel sizes, anisotropy
  * GROUPS of views that share voxel size and image size -- a second group usually means another objective or
    camera and needs its own detection settings (intensity range, downsampling)
  * the <ViewTransform> stack per distinct stack and a RESET proposal: `clear-registrations --keep N` keeps the
    calibration and the metadata placement (large pure translations), drops registration results
  * existing interest-point labels with their detection parameters
  * the pairs of views whose registered bounding boxes overlap (what the matcher will try)
  * a coarse-to-fine downsampling LADDER per group: dsXY in 8,4,2,1 while every view keeps >= 200 px per axis,
    dsZ chosen so the detection grid is near-isotropic, the stored pyramid level each choice reads (and a cheaper dsZ
    that hits a stored level directly), with the RANSAC max error to start from at each level
"""
import argparse
import json
import math
import os
import sys
import xml.etree.ElementTree as ET


def parse_ids(spec):
    out = set()
    for tok in spec.split(","):
        tok = tok.strip()
        if "-" in tok:
            a, b = tok.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif tok:
            out.add(int(tok))
    return out


def mat_mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def affine(text):
    v = [float(x) for x in text.split()]
    return [v[0:4], v[4:8], v[8:12], [0.0, 0.0, 0.0, 1.0]]


def apply(M, p):
    return [M[i][0] * p[0] + M[i][1] * p[1] + M[i][2] * p[2] + M[i][3] for i in range(3)]


def layer_type(L, eps=1e-6):
    A = [row[:3] for row in L[:3]]
    ident = all(abs(A[i][j] - (1.0 if i == j else 0.0)) < eps for i in range(3) for j in range(3))
    t = [L[i][3] for i in range(3)]
    tnorm = math.sqrt(sum(x * x for x in t))
    if ident:
        return ("identity" if tnorm < eps else "translation"), tnorm
    diag = all(abs(A[i][j]) < eps for i in range(3) for j in range(3) if i != j)
    if diag:
        return "scaling", tnorm
    AtA = [[sum(A[k][i] * A[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    if all(abs(AtA[i][j] - (1.0 if i == j else 0.0)) < 1e-6 for i in range(3) for j in range(3)):
        return "rigid", tnorm
    return "affine", tnorm


def parse_params(s):
    out = {}
    if not s:
        return out
    head, _, rest = s.partition(" ")
    out["kind"] = head if "=" not in head else ""
    for tok in (s if "=" in head else rest).split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def bbox(M, size):
    pts = [apply(M, [x, y, z]) for x in (0, size[0]) for y in (0, size[1]) for z in (0, size[2])]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def ladder(vox, size, factors=None, min_px=200, min_z=32):
    """Coarse-to-fine levels. dsz = the near-isotropic choice; when the image pyramid has no level with that z factor the
    detection reads a finer stored level and downsamples in memory -- 'read_level' / 'read_gvox' show the cost per view and
    'dsz_cheap' the z factor of the stored level that would be read directly (anisotropic grid, much cheaper on NFS)."""
    vx, vz = vox[0], vox[2]
    out = []
    for ds in (8, 4, 2, 1):
        if min(size[0], size[1]) / ds < min_px and ds != 1:
            continue
        dsz = max(1, int(round(ds * vx / vz)))
        while dsz > 1 and size[2] / dsz < min_z:
            dsz //= 2
        row = {"dsxy": ds, "dsz": dsz, "grid_vox_xy": ds * vx, "grid_vox_z": dsz * vz, "rme_start": max(2.0, 2.5 * ds) if ds > 1 else 2.0}
        if factors:
            lvl = stored_level_for(factors, ds, dsz)
            row["read_level"] = lvl
            row["read_gvox"] = size[0] * size[1] * size[2] / (lvl[0] * lvl[1] * lvl[2]) / 1e9
            stored_z = sorted({f[2] for f in factors if f[0] <= ds})
            cheap = max((z for z in stored_z if z <= max(dsz, 1) * 4), default=dsz)
            if cheap != dsz:
                lvl2 = stored_level_for(factors, ds, cheap)
                row["dsz_cheap"] = cheap
                row["read_gvox_cheap"] = size[0] * size[1] * size[2] / (lvl2[0] * lvl2[1] * lvl2[2]) / 1e9
        out.append(row)
    return out


def pyramid_factors(il_fmt, img_base, zgroup, setup, tp):
    """The stored downsampling factors [[fx, fy, fz], ...] of one view's image pyramid (BDV N5 or OME-Zarr), or None."""
    try:
        if il_fmt == "bdv.n5":
            a = json.load(open(os.path.join(img_base, f"setup{setup}", "attributes.json")))
            if "downsamplingFactors" in a:
                return [list(map(int, f)) for f in a["downsamplingFactors"]]
            cont = os.path.join(img_base, f"setup{setup}", f"timepoint{tp}")
            out = []
            for L in sorted(int(d[1:]) for d in os.listdir(cont) if d.startswith("s") and d[1:].isdigit()):
                la = json.load(open(os.path.join(cont, f"s{L}", "attributes.json")))
                out.append(list(map(int, la.get("downsamplingFactors", [2 ** L] * 3))))
            return out or None
        if il_fmt == "bdv.multimg.zarr":
            cont = os.path.join(img_base, zgroup)
            if os.path.exists(os.path.join(cont, "zarr.json")):
                attrs = json.load(open(os.path.join(cont, "zarr.json")))["attributes"]
                meta = attrs.get("ome", attrs)["multiscales"][0]
            else:
                meta = json.load(open(os.path.join(cont, ".zattrs")))["multiscales"][0]
            scales = [next(t["scale"] for t in d["coordinateTransformations"] if t["type"] == "scale")[-3:] for d in meta["datasets"]]
            s0 = scales[0]
            return [[int(round(sc[2] / s0[2])), int(round(sc[1] / s0[1])), int(round(sc[0] / s0[0]))] for sc in scales]
    except Exception:  # noqa: BLE001
        return None
    return None


def stored_level_for(factors, dsxy, dsz):
    """The stored level BigStitcher reads for a requested (dsxy, dsxy, dsz): the coarsest whose factors do not exceed the request."""
    best = None
    for f in factors or [[1, 1, 1]]:
        if f[0] <= dsxy and f[1] <= dsxy and f[2] <= dsz and (best is None or f[0] * f[1] * f[2] > best[0] * best[1] * best[2]):
            best = f
    return best or [1, 1, 1]


def sample_intensity(il_fmt, img_base, rel_path, zgroup, setup, tp, max_vox=40_000_000):
    """Percentiles of the coarsest pyramid level of one view (tensorstore). Returns None when unsupported."""
    try:
        import tensorstore as ts
    except ImportError:
        return None
    try:
        if il_fmt == "bdv.n5":
            setup_dir = os.path.join(img_base, f"setup{setup}")
            cont = os.path.join(setup_dir, f"timepoint{tp}")
            levels = sorted(int(d[1:]) for d in os.listdir(cont) if d.startswith("s") and d[1:].isdigit())
            arr = ts.open({"driver": "n5", "kvstore": {"driver": "file", "path": os.path.join(cont, f"s{levels[-1]}")}}).result()
        elif il_fmt == "bdv.multimg.zarr":
            cont = os.path.join(img_base, zgroup)
            v3 = os.path.exists(os.path.join(cont, "zarr.json"))
            if v3:
                attrs = json.load(open(os.path.join(cont, "zarr.json")))["attributes"]
                meta = attrs.get("ome", attrs)["multiscales"][0]
            else:
                meta = json.load(open(os.path.join(cont, ".zattrs")))["multiscales"][0]
            path = meta["datasets"][-1]["path"]
            arr = ts.open({"driver": "zarr3" if v3 else "zarr", "kvstore": {"driver": "file", "path": os.path.join(cont, path)}}).result()
            while arr.ndim > 3:
                arr = arr[0]
        else:
            return None
        n = 1
        for s in arr.shape:
            n *= s
        if n > max_vox:          # central sub-block
            sl = []
            f = (n / max_vox) ** (1 / 3)
            for s in arr.shape:
                w = max(1, int(s / f))
                a0 = (s - w) // 2
                sl.append(slice(a0, a0 + w))
            arr = arr[tuple(sl)]
        import numpy as np
        data = np.asarray(arr.read().result()).ravel()
        data = data[np.isfinite(data)]
        nz = data[data > 0]
        q = np.percentile(nz if nz.size else data, [0.1, 1, 50, 99, 99.9, 99.99]) if data.size else [0] * 6
        return {"level_shape": list(arr.shape), "min": float(data.min()), "max": float(data.max()),
                "p0.1": float(q[0]), "p1": float(q[1]), "p50": float(q[2]), "p99": float(q[3]), "p99.9": float(q[4]), "p99.99": float(q[5]),
                "zero_fraction": float(1 - nz.size / max(data.size, 1))}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml")
    ap.add_argument("--setups", help="restrict to these view setup ids (e.g. 32-47)")
    ap.add_argument("--tp", type=int, help="restrict to this timepoint")
    ap.add_argument("--intensity", action="store_true", help="sample intensity percentiles of the views (tensorstore): every view of a group up to --intensity-max, else that many spread over the group; flags EMPTY tiles")
    ap.add_argument("--intensity-max", type=int, default=8, help="max views sampled per group (default 8)")
    ap.add_argument("--json", metavar="OUT")
    a = ap.parse_args()

    root = ET.parse(a.xml).getroot()
    xml_dir = os.path.dirname(os.path.abspath(a.xml))
    bp = root.find("BasePath")
    base = os.path.normpath(os.path.join(xml_dir, (bp.text or ".").strip())) if bp is None or bp.get("type", "relative") == "relative" \
        else (bp.text or "").replace("file:", "")
    il = root.find("SequenceDescription/ImageLoader")
    il_fmt = il.get("format") if il is not None else None
    img_el = il.find("n5") if il is not None and il.find("n5") is not None else (il.find("zarr") if il is not None else None)
    img_base = None
    if img_el is not None and img_el.text:
        p = img_el.text.strip()
        img_base = os.path.normpath(os.path.join(base, p)) if img_el.get("type", "relative") == "relative" else p.replace("file:", "")
    zgroups = {(int(z.get("tp")), int(z.get("setup"))): z.get("path") for z in il.iter("zgroup")} if il is not None else {}

    attr_names = {}
    for at in root.iter("Attributes"):
        attr_names[at.get("name")] = {int(e.findtext("id")): (e.findtext("name") or "") for e in at}
    setups = {}
    for vs in root.iter("ViewSetup"):
        sid = int(vs.findtext("id"))
        vox = vs.find("voxelSize")
        setups[sid] = {"name": vs.findtext("name"), "size": [int(x) for x in vs.findtext("size").split()] if vs.findtext("size") else None,
                       "voxel": [float(x) for x in vox.findtext("size").split()] if vox is not None else None,
                       "unit": vox.findtext("unit") if vox is not None else None,
                       "attrs": {e.tag: int(e.text) for e in (vs.find("attributes") if vs.find("attributes") is not None else [])}}
    missing = {(int(v.get("timepoint")), int(v.get("setup"))) for v in root.iter("DeletedView")}
    sel = parse_ids(a.setups) if a.setups else None
    views = {}
    for vr in root.iter("ViewRegistration"):
        key = (int(vr.get("timepoint")), int(vr.get("setup")))
        if key in missing or (sel and key[1] not in sel) or (a.tp is not None and key[0] != a.tp) or key[1] not in setups or not setups[key[1]]["size"]:
            continue
        layers = [(vt.findtext("Name") or "", affine(vt.find("affine").text)) for vt in vr.findall("ViewTransform") if vt.find("affine") is not None]
        M = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        for _, L in layers:
            M = mat_mul(M, L)
        views[key] = {"layers": layers, "M": M}
    if not views:
        sys.exit("no views selected")
    keys = sorted(views)
    tps = sorted({k[0] for k in keys})

    # groups by (voxel, size)
    groups = {}
    for k in keys:
        s = setups[k[1]]
        g = (tuple(s["voxel"] or []), tuple(s["size"]))
        groups.setdefault(g, []).append(k)
    # attribute dimensions with more than one value
    dims = {}
    for name in ("channel", "tile", "angle", "illumination"):
        vals = sorted({setups[k[1]]["attrs"].get(name) for k in keys if name in setups[k[1]]["attrs"]})
        if len(vals) > 1:
            dims[name] = vals

    # transform stacks + reset proposal
    stacks, stack_types = {}, {}
    for k in keys:
        sig = tuple(n for n, L in views[k]["layers"])
        stacks.setdefault(sig, []).append(k)
        for i, (n, L) in enumerate(views[k]["layers"]):      # the least trivial type seen per layer position
            t = layer_type(L)[0]
            rank = {"identity": 0, "translation": 1, "scaling": 2, "rigid": 3, "similarity": 4, "affine": 5}
            if rank[t] > rank.get(stack_types.get((sig, i), "identity"), 0):
                stack_types[(sig, i)] = t
    def reset_keep(layers, size):
        # human order = reversed document order: calibration first
        human = list(reversed(layers))
        keep = 0
        diag = math.sqrt(sum(s * s for s in size))
        for n, L in human:
            t, tnorm = layer_type(L)
            if "calibration" in n.lower() or t in ("identity", "scaling") and keep == 0:
                keep += 1
            elif t == "translation" and tnorm > 0.05 * diag:
                keep += 1
            else:
                break
        return keep
    resets = {}
    for sig, ks in stacks.items():
        resets[sig] = max(reset_keep(views[k]["layers"], setups[k[1]]["size"]) for k in ks)

    # labels
    labels = {}
    for e in root.iter("ViewInterestPointsFile"):
        key = (int(e.get("timepoint")), int(e.get("setup")))
        if key not in views:
            continue
        lab = e.get("label")
        d = labels.setdefault(lab, {"views": 0, "params": e.get("params"), "base": e.get("base"), "filter": e.get("filter")})
        d["views"] += 1

    # pairs
    boxes = {k: bbox(views[k]["M"], setups[k[1]]["size"]) for k in keys}
    pairs = []
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if ka[0] != kb[0]:
                continue
            (lo_a, hi_a), (lo_b, hi_b) = boxes[ka], boxes[kb]
            lo = [max(lo_a[i], lo_b[i]) for i in range(3)]
            hi = [min(hi_a[i], hi_b[i]) for i in range(3)]
            if any(hi[i] <= lo[i] for i in range(3)):
                continue
            inter = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
            vol = min((hi_a[0] - lo_a[0]) * (hi_a[1] - lo_a[1]) * (hi_a[2] - lo_a[2]), (hi_b[0] - lo_b[0]) * (hi_b[1] - lo_b[1]) * (hi_b[2] - lo_b[2]))
            pairs.append({"a": f"{ka[0]},{ka[1]}", "b": f"{kb[0]},{kb[1]}", "overlap_frac": inter / vol, "overlap_size": [hi[i] - lo[i] for i in range(3)]})
    pairs.sort(key=lambda p: -p["overlap_frac"])
    unconnected = [k for k in keys if not any(p["a"] == f"{k[0]},{k[1]}" or p["b"] == f"{k[0]},{k[1]}" for p in pairs)]

    # ladder + intensity per group
    group_rows = []
    for (vox, size), ks in groups.items():
        k0 = ks[0]
        factors = pyramid_factors(il_fmt, img_base, zgroups.get(k0, ""), k0[1], k0[0]) if img_base else None
        row = {"voxel": list(vox), "size": list(size), "n_views": len(ks), "setups": sorted({k[1] for k in ks}),
               "anisotropy": (vox[2] / vox[0]) if vox else None, "pyramid": factors, "ladder": ladder(vox or (1, 1, 1), size, factors)}
        if a.intensity:
            samp = []
            picks = ks if len(ks) <= a.intensity_max else [ks[i * (len(ks) - 1) // (a.intensity_max - 1)] for i in range(a.intensity_max)]
            for k in picks:
                r = sample_intensity(il_fmt, img_base, None, zgroups.get(k, ""), k[1], k[0])
                if r is not None:
                    if "error" not in r:        # an empty tile: the bright tail sits at the background level
                        r["empty"] = r["p99.9"] <= 3 * max(r["p50"], 1e-9) or r["max"] <= 3 * max(r["p50"], 1e-9)
                    samp.append({"view": f"{k[0]},{k[1]}", **r})
            row["intensity"] = samp
        group_rows.append(row)

    result = {"xml": a.xml, "image_loader": il_fmt, "image_base": img_base, "timepoints": tps, "n_views": len(keys), "n_missing": len(missing),
              "attribute_dims": dims, "groups": group_rows,
              "stacks": [{"layers": [{"name": n, "type": stack_types.get((sig, i), "identity")} for i, n in enumerate(sig)], "views": len(ks),
                          "reset_keep": resets[sig]} for sig, ks in stacks.items()],
              "labels": {k: {**v, "parsed": parse_params(v["params"])} for k, v in labels.items()},
              "pairs": pairs, "unconnected_views": [f"{k[0]},{k[1]}" for k in unconnected]}
    if a.json:
        with open(a.json, "w") as f:
            json.dump(result, f, indent=1)

    print(f"== {a.xml}")
    print(f"   loader {il_fmt}  images {img_base}")
    print(f"   {len(keys)} views ({len(missing)} missing), timepoints {tps[:5]}{'...' if len(tps) > 5 else ''}; varying attributes: "
          + (", ".join(f"{n} {v if len(v) <= 12 else str(v[:12]) + '...'}" for n, v in dims.items()) or "none"))
    for g in group_rows:
        print(f"   group: {g['n_views']} views, size {g['size']}, voxel {g['voxel']} (anisotropy {g['anisotropy']:.2f}), setups "
              f"{g['setups'][:12]}{'...' if len(g['setups']) > 12 else ''}")
        if g.get("pyramid"):
            print(f"      image pyramid factors (x,y,z): {g['pyramid']}")
        for l in g["ladder"]:
            line = f"      level dsxy {l['dsxy']} dsz {l['dsz']}: grid {l['grid_vox_xy']:.3g} x {l['grid_vox_z']:.3g} units, rme {l['rme_start']:g}"
            if "read_level" in l:
                line += f"; reads stored level {l['read_level']} = {l['read_gvox']:.2f} Gvox per view"
                if "dsz_cheap" in l:
                    line += f" -- CHEAPER: dsz {l['dsz_cheap']} reads a stored level directly ({l['read_gvox_cheap']:.2f} Gvox)"
            print(line)
        for s in g.get("intensity", []):
            if "error" in s:
                print(f"      intensity view {s['view']}: {s['error']}")
            else:
                print(f"      intensity view {s['view']} (coarsest level {s['level_shape']}): min {s['min']:g} p0.1 {s['p0.1']:g} p50 {s['p50']:g} "
                      f"p99 {s['p99']:g} p99.9 {s['p99.9']:g} p99.99 {s['p99.99']:g} max {s['max']:g}; zeros {100 * s['zero_fraction']:.1f}%"
                      + ("   <-- EMPTY tile (no signal above background): exclude it, it cannot be registered" if s.get("empty") else ""))
    if a.intensity and not any(g.get("intensity") for g in group_rows):
        print("      (intensity sampling needs tensorstore + numpy and an N5 / OME-Zarr loader; read min/max off BigStitcher instead)")
    for st in result["stacks"]:
        print(f"   transforms ({st['views']} views), applied last -> first: " + " | ".join(f"{l['name']} [{l['type']}]" for l in st["layers"]))
        print(f"      reset proposal: clear-registrations --keep {st['reset_keep']}  (keeps "
              + ", ".join(l["name"] for l in list(reversed(st["layers"]))[:st["reset_keep"]]) + ")")
    if labels:
        for lab, d in labels.items():
            print(f"   label '{lab}' on {d['views']} views: {d['params']}" + (f" (filtered from {d['base']})" if d["base"] else ""))
    else:
        print("   no interest points yet")
    print(f"   {len(pairs)} overlapping pairs under the current registration" + (f"; views without partner: {result['unconnected_views']}" if unconnected else ""))
    for p in pairs[:20]:
        print(f"      {p['a']:>6} - {p['b']:<6} {100 * p['overlap_frac']:6.1f}%  ({p['overlap_size'][0]:.0f} x {p['overlap_size'][1]:.0f} x {p['overlap_size'][2]:.0f} px)")
    if len(pairs) > 20:
        print(f"      ... {len(pairs) - 20} more")


if __name__ == "__main__":
    main()
