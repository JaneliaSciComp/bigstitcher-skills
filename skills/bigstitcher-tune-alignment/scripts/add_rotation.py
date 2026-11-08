#!/usr/bin/env python3
"""
Add a manual rotation to selected views of a BigStitcher XML (the CLI twin of the GUI's "Apply Transformation ->
rotate around axis"). Stdlib only. Use it when a group of views (another objective, a camera mounted at an angle)
is known to be rotated against the rest before any interest-point matching; the learned-descriptor matcher is
NOT rotation tolerant, so after a manual rotation run the geometric matcher only.

  python3 add_rotation.py dataset.xml --setups 6-11 --axis y --degrees 90 -o dataset_rot.xml
  python3 add_rotation.py dataset.xml --setups 6-11 --axis z --degrees -90 --in-place      # keeps dataset.xml~rot
  python3 add_rotation.py dataset.xml --setups 6-11 --axis x --degrees 90 --dry-run

The rotation is applied in the GLOBAL frame as a new outermost <ViewTransform> (listed first), about the centre
of each view's registered bounding box (default) or about --center X,Y,Z (global px). Positive angles follow the
right-hand rule about the given axis. Run it before resetting / matching, check with registration_report.py.
"""
import argparse
import math
import shutil
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


def affine_from_text(text):
    v = [float(x) for x in text.split()]
    return [v[0:4], v[4:8], v[8:12], [0.0, 0.0, 0.0, 1.0]]


def rotation(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == "x":
        R = [[1, 0, 0], [0, c, -s], [0, s, c]]
    elif axis == "y":
        R = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    else:
        R = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    return [R[0] + [0.0], R[1] + [0.0], R[2] + [0.0], [0.0, 0.0, 0.0, 1.0]]


def translation(t, sign=1.0):
    return [[1, 0, 0, sign * t[0]], [0, 1, 0, sign * t[1]], [0, 0, 1, sign * t[2]], [0, 0, 0, 1]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml")
    ap.add_argument("--setups", required=True, help="view setup ids to rotate, e.g. 6-11 or 3,7")
    ap.add_argument("--tp", type=int, default=None, help="timepoint (default: all)")
    ap.add_argument("--axis", required=True, choices=["x", "y", "z"])
    ap.add_argument("--degrees", required=True, type=float)
    ap.add_argument("--center", help="rotation centre X,Y,Z in global px (default: each view's registered bounding-box centre)")
    ap.add_argument("--name", default=None, help="name of the new ViewTransform (default: 'manual rotation <axis> <deg> deg')")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("-o", "--out", help="write the result here (default: required unless --in-place)")
    g.add_argument("--in-place", action="store_true", help="overwrite the XML, keeping a copy as <xml>~rot")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.out and not a.in_place and not a.dry_run:
        sys.exit("give -o OUT or --in-place (or --dry-run)")

    tree = ET.parse(a.xml)
    root = tree.getroot()
    sizes = {int(vs.findtext("id")): [int(x) for x in vs.findtext("size").split()] for vs in root.iter("ViewSetup") if vs.findtext("size")}
    sel = parse_ids(a.setups)
    name = a.name or f"manual rotation {a.axis} {a.degrees:g} deg"
    centre_fixed = [float(x) for x in a.center.split(",")] if a.center else None
    R = rotation(a.axis, a.degrees)
    n = 0
    for vr in root.iter("ViewRegistration"):
        tp, setup = int(vr.get("timepoint")), int(vr.get("setup"))
        if setup not in sel or (a.tp is not None and tp != a.tp):
            continue
        M = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        for vt in vr.findall("ViewTransform"):
            aff = vt.find("affine")
            if aff is not None:
                M = mat_mul(M, affine_from_text(aff.text))
        if centre_fixed:
            c = centre_fixed
        else:
            half = [s / 2.0 for s in sizes[setup]] + [1.0]
            c = [sum(M[i][k] * half[k] for k in range(4)) for i in range(3)]
        T = mat_mul(mat_mul(translation(c), R), translation(c, -1.0))
        text = " ".join(f"{T[i][j]!r}" for i in range(3) for j in range(4))
        print(f"view tp{tp} setup {setup}: rotate {a.degrees:g} deg about {a.axis} through ({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f})")
        if a.dry_run:
            n += 1
            continue
        vt = ET.Element("ViewTransform", type="affine")
        ET.SubElement(vt, "Name").text = name
        ET.SubElement(vt, "affine").text = text
        vr.insert(0, vt)
        n += 1
    if not n:
        sys.exit("no matching views")
    if a.dry_run:
        print(f"dry run: {n} view(s) would get the transform '{name}'")
        return
    out = a.xml if a.in_place else a.out
    if a.in_place:
        shutil.copyfile(a.xml, a.xml + "~rot")
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    print(f"wrote {out}: '{name}' added to {n} view(s) as the outermost transform")


if __name__ == "__main__":
    main()
