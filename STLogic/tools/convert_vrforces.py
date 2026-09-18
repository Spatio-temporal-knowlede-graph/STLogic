#!/usr/bin/env python
"""Convert the VR-Forces ver2.0 CSV exports into STLogic pre-made input.

Each source CSV in --src carries 66 columns; only six of them matter here.
The converter keeps the quadruple as-is and folds the head entity's coordinate
into a single `location` field:

    subject,predicate,object,timestamp,location

    location = "(latitude, longitude)"   e.g. "(21.37337840, -157.74310685)"

Rows whose `object` is empty (predicate "none", mostly) are dropped: they do not
form a triple. `obj_lat`/`obj_lon` (populated only on Fire-Weapon rows) are
ignored -- `location` is always the subject's position, matching the head-entity
convention in convert_battlefield.py.

Sources are streamed row by row, so the 800MB ground_truth export converts in
constant memory. One output file per source file, same basename, LF endings,
UTF-8.

Usage:
    python tools/convert_vrforces.py [--src DIR] [--dst DIR]
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.normpath(os.path.join(HERE, "..", "..", "dataset", "VR-Forces"))
DEFAULT_DST = os.path.normpath(os.path.join(HERE, "..", "data", "VR-Forces"))

OUT_HEADER = ["subject", "predicate", "object", "timestamp", "location"]
NEEDED = ("subject", "predicate", "object", "timestamp", "latitude", "longitude")

# The ground_truth export has single fields well past csv's 128KB default.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def format_location(lat, lon):
    """"(lat, lon)" from the raw source strings, or "" when either is missing.

    The source text is passed through verbatim rather than parsed as a float, so
    the 8-decimal precision of the export survives the round trip untouched.
    """
    lat = lat.strip()
    lon = lon.strip()
    if not lat or not lon:
        return ""
    return "({}, {})".format(lat, lon)


def convert_file(src_path, dst_path):
    """Convert one VR-Forces CSV. Returns counts for the caller to report."""
    stats = {"read": 0, "written": 0, "skipped_empty_object": 0, "missing_location": 0}

    with open(src_path, "r", encoding="utf-8-sig", newline="") as fin, \
            open(dst_path, "w", encoding="utf-8", newline="") as fout:
        reader = csv.reader(fin)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("{}: file is empty".format(src_path))

        col = {name: i for i, name in enumerate(h.strip() for h in header)}
        missing = [c for c in NEEDED if c not in col]
        if missing:
            raise ValueError("{}: missing column(s) {}".format(src_path, ", ".join(missing)))
        i_sub, i_pred, i_obj = col["subject"], col["predicate"], col["object"]
        i_ts, i_lat, i_lon = col["timestamp"], col["latitude"], col["longitude"]
        width = max(i_sub, i_pred, i_obj, i_ts, i_lat, i_lon) + 1

        writer = csv.writer(fout, lineterminator="\n")
        writer.writerow(OUT_HEADER)

        for row in reader:
            if not row or len(row) < width:
                continue  # blank or truncated trailing line
            stats["read"] += 1
            obj = row[i_obj].strip()
            if not obj:
                stats["skipped_empty_object"] += 1
                continue
            location = format_location(row[i_lat], row[i_lon])
            if not location:
                stats["missing_location"] += 1
            writer.writerow([row[i_sub].strip(), row[i_pred].strip(), obj,
                             row[i_ts].strip(), location])
            stats["written"] += 1

    return stats


def convert(src, dst):
    names = sorted(n for n in os.listdir(src) if n.lower().endswith(".csv"))
    if not names:
        raise ValueError("no .csv files found in {}".format(src))
    os.makedirs(dst, exist_ok=True)

    for name in names:
        stats = convert_file(os.path.join(src, name), os.path.join(dst, name))
        print("{}: {} rows -> {} written "
              "({} dropped: empty object, {} without location)".format(
                  name, stats["read"], stats["written"],
                  stats["skipped_empty_object"], stats["missing_location"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--dst", default=DEFAULT_DST)
    args = ap.parse_args()
    print("src = {}".format(args.src))
    print("dst = {}".format(args.dst))
    convert(args.src, args.dst)


if __name__ == "__main__":
    main()
