#!/usr/bin/env python3
"""
Make a safe working copy of a BigStitcher / SpimData2 project: a directory with a copy of the XML, a copy of the
interest points and SYMLINKS to the image data. Everything a registration run writes (XML, interestpoints.n5 /
interestpoints.zarr) then lands in the copy; the original project is never touched.

  python3 make_working_copy.py /data/run1/dataset.xml /scratch/run1_tune            # copy XML + points, link images
  python3 make_working_copy.py /data/run1/dataset.xml /scratch/run1_tune --points none   # start without interest points
  python3 make_working_copy.py ... --dry-run                                           # only print what would happen

Rules:
  * <BasePath> becomes "." in the copy, so every relative reference resolves inside the copy.
  * Every relative reference under <ImageLoader> (n5, zarr, hdf5 + partitions, imagedirectory, ...) is symlinked
    to the original location, read-only by convention: the registration tools never write image data.
  * Absolute references (file:/..., s3://...) are left alone.
  * interestpoints.n5 / interestpoints.zarr are COPIED (--points copy, default) or dropped (--points none, which
    also removes the <ViewInterestPoints> entries so the XML stays consistent). Never symlink them: BigStitcher
    writes into them.
  * dataset.xml.orig = the copy's initial state (the starting registration; chains reset to it).
  * Refuses a non-empty destination.
"""
import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET


def strip_file_uri(p):
    p = p.strip()
    if p.startswith("file://"):
        p = p[7:]
    elif p.startswith("file:"):
        p = p[5:]
    return p


def dir_size(path, limit=None):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
            if limit and total > limit:
                return total
    return total


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xml", help="the original project XML (never modified)")
    ap.add_argument("dest", help="destination directory (created; must not exist or be empty)")
    ap.add_argument("--name", default=None, help="file name of the XML in the copy (default: same as the source)")
    ap.add_argument("--points", choices=["copy", "none"], default="copy",
                    help="copy interestpoints.n5/.zarr (default) or start without interest points")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    a = ap.parse_args()

    src = os.path.abspath(a.xml)
    if not os.path.isfile(src):
        sys.exit(f"not a file: {src}")
    src_dir = os.path.dirname(src)
    tree = ET.parse(src)
    root = tree.getroot()
    bp = root.find("BasePath")
    if bp is None or bp.get("type", "relative") == "relative":
        base = os.path.normpath(os.path.join(src_dir, (bp.text or ".").strip() if bp is not None else "."))
    else:
        base = os.path.normpath(strip_file_uri(bp.text or ""))
    dest = os.path.abspath(a.dest)
    name = a.name or os.path.basename(src)
    if os.path.realpath(dest) in (os.path.realpath(base), os.path.realpath(src_dir)):
        sys.exit("destination is the original project directory -- refusing")
    if os.path.exists(dest) and os.listdir(dest):
        sys.exit(f"destination exists and is not empty: {dest}")

    actions = []  # (kind, target_in_copy, source)
    il = root.find("SequenceDescription/ImageLoader")
    if il is None:
        sys.exit("no <ImageLoader> in the XML")
    for el in il.iter():
        if el.get("type") == "relative" and el.text and el.text.strip():
            rel = el.text.strip()
            if rel.rstrip("/") in ("", "."):
                sys.exit(f"<{el.tag}> points at the project directory itself ('{rel}'): the image files live next to "
                         f"the XML. Link or copy them by hand into {dest} and set <{el.tag}> accordingly.")
            source = os.path.normpath(os.path.join(base, rel))
            if not os.path.exists(source):
                print(f"WARNING: image reference does not exist: {source} (linking anyway)", file=sys.stderr)
            actions.append(("link", os.path.join(dest, rel.rstrip("/")), source))
    for ipdir in ("interestpoints.n5", "interestpoints.zarr"):
        p = os.path.join(base, ipdir)
        if os.path.isdir(p):
            actions.append(("copy" if a.points == "copy" else "drop", os.path.join(dest, ipdir), p))

    print(f"source XML : {src}\nbase path  : {base}\ndestination: {dest}/{name}")
    for kind, tgt, s in actions:
        extra = f" ({human(dir_size(s))})" if kind == "copy" else ""
        print(f"  {kind:5s} {tgt}  <-  {s}{extra}")
    vip = root.find("ViewInterestPoints")
    n_ip = len(vip.findall("ViewInterestPointsFile")) if vip is not None else 0
    if a.points == "none" and n_ip:
        print(f"  drop  {n_ip} <ViewInterestPointsFile> entries from the XML (no interest points in the copy)")
    print(f"  write {dest}/{name} with <BasePath>. and {dest}/{name}.orig (initial state)")
    if a.dry_run:
        return

    os.makedirs(dest, exist_ok=True)
    for kind, tgt, s in actions:
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        if kind == "link":
            os.symlink(s, tgt)
        elif kind == "copy":
            shutil.copytree(s, tgt, symlinks=True)
    if bp is None:
        bp = ET.SubElement(root, "BasePath")
        root.remove(bp)
        root.insert(0, bp)
    bp.set("type", "relative")
    bp.text = "."
    if a.points == "none" and vip is not None:
        for e in list(vip):
            vip.remove(e)
    out = os.path.join(dest, name)
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    shutil.copyfile(out, out + ".orig")
    print(f"done: {out}")


if __name__ == "__main__":
    main()
