#!/usr/bin/env python
"""Build a TLogic/STLogic dataset from the VR-Forces ver2.0 export.

Output (in --dst), the same layout convert_battlefield.py produces:

    train.txt / valid.txt / test.txt   # sub \t rel \t obj \t ts_token \t location
    entity2id.json  relation2id.json  ts2id.json
    landmarks.tsv                      # LOC_name \t east \t north
    entity_types.tsv                   # entity \t entity_class

`location` is the SUBJECT's position at that tick, in **local ENU metres** -- not
the raw lat/lon of the export. Degrees are not a metric: at this scenario's
latitude one degree of longitude is ~7% shorter than one of latitude, so
norm() over raw lat/lon distorts distance and badly distorts bearing.
Everything downstream (spatial_context) assumes metres.

Two things this reads beyond the STKG CSVs, both from the scenario repo:
  config/battlefield_layout.json     -- LOC_* coordinates (the `move to` targets,
                                        92% of all edges, are landmarks)
  build/registry/master_entities.csv -- entity_id -> entity_class / force / unit

The tick grid is subsampled to --stride seconds. The simulator logs at 1 Hz but a
movement order persists for minutes, so consecutive ticks are near-identical; a
uniform grid also makes a forecasting horizon an exact number of ticks
(horizon_ticks = horizon_seconds / stride).

Usage:
    python tools/build_vrforces_dataset.py [--observer ground_truth|uav] [--stride 10]
"""
import argparse
import csv
import datetime as dt
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.normpath(os.path.join(HERE, "..", "..", "dataset", "VR-Forces"))
DEFAULT_SCENARIO = os.path.normpath(os.path.join(HERE, "..", "..", "..", "VR-Forces"))
DEFAULT_DATA = os.path.normpath(os.path.join(HERE, "..", "data"))

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


class EnuFrame:
    """Local east/north tangent plane anchored at (lat0, lon0).

    Metres-per-degree from the standard meridian/parallel series (WGS84), which is
    accurate to well under a metre over a few km -- far inside what this scenario
    spans. No projection library needed.
    """

    def __init__(self, lat0, lon0):
        self.lat0 = lat0
        self.lon0 = lon0
        p = math.radians(lat0)
        self.m_per_deg_lat = (111132.92 - 559.82 * math.cos(2 * p)
                              + 1.175 * math.cos(4 * p) - 0.0023 * math.cos(6 * p))
        self.m_per_deg_lon = (111412.84 * math.cos(p) - 93.5 * math.cos(3 * p)
                              + 0.118 * math.cos(5 * p))

    def to_enu(self, lat, lon):
        return ((lon - self.lon0) * self.m_per_deg_lon,
                (lat - self.lat0) * self.m_per_deg_lat)


def pick_grid(seconds, stride):
    """Ticks on a uniform `stride`-second grid, keeping only observed ones."""
    if not seconds:
        return []
    t0 = min(seconds)
    return [s for s in sorted(set(seconds)) if (s - t0) % stride == 0]


def split_grid(grid, train_frac, valid_frac):
    """Contiguous time split -- the forecasting protocol: past trains, future tests."""
    n = len(grid)
    a = int(n * train_frac)
    b = a + int(n * valid_frac)
    return grid[:a], grid[a:b], grid[b:]


def _epoch(ts):
    return int(dt.datetime.fromisoformat(ts).timestamp())


def read_observations(paths):
    """[(epoch, subject, predicate, object, lat, lon)] from the 68-column exports."""
    out = []
    for p in paths:
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                obj = r["object"].strip()
                if not obj:
                    continue                    # no object -> no triple
                lat, lon = r["latitude"].strip(), r["longitude"].strip()
                if not lat or not lon:
                    continue
                out.append((_epoch(r["timestamp"]), r["subject"].strip(),
                            r["predicate"].strip(), obj, float(lat), float(lon)))
    return out


def load_landmarks(scenario):
    path = os.path.join(scenario, "config", "battlefield_layout.json")
    with open(path, encoding="utf-8") as f:
        locs = json.load(f)["locations"]
    return {name: (v["lat"], v["lon"]) for name, v in locs.items()}


def load_registry(scenario):
    """{normalised_entity_id: entity_class}. Registry ids carry hyphens; STKG ids do not."""
    path = os.path.join(scenario, "build", "registry", "master_entities.csv")
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[r["entity_id"].replace("-", "")] = r["entity_class"]
    return out


def build(src, scenario, dst, observer, stride, train_frac, valid_frac):
    paths = (sorted(glob.glob(os.path.join(src, "UAV*_ver2.0.csv")))
             if observer == "uav"
             else [os.path.join(src, "ground_truth_ver2.0.csv")])
    if not paths:
        raise ValueError("no source CSV for observer=%s in %s" % (observer, src))

    obs = read_observations(paths)
    if not obs:
        raise ValueError("no usable observations found")

    landmarks_ll = load_landmarks(scenario)
    entity_class = load_registry(scenario)

    # ENU origin: centroid of everything that has a position, so coordinates stay
    # small and symmetric around the scene rather than around an arbitrary corner.
    lats = [o[4] for o in obs] + [v[0] for v in landmarks_ll.values()]
    lons = [o[5] for o in obs] + [v[1] for v in landmarks_ll.values()]
    frame = EnuFrame(sum(lats) / len(lats), sum(lons) / len(lons))

    grid = pick_grid([o[0] for o in obs], stride)
    on_grid = set(grid)
    train_t, valid_t, test_t = split_grid(grid, train_frac, valid_frac)
    bucket = {}
    for t in train_t:
        bucket[t] = "train"
    for t in valid_t:
        bucket[t] = "valid"
    for t in test_t:
        bucket[t] = "test"

    ts2id = {}
    for i, t in enumerate(grid):
        ts2id[dt.datetime.fromtimestamp(t).isoformat()] = i

    rows = {"train": [], "valid": [], "test": []}
    seen = {"train": set(), "valid": set(), "test": set()}
    entities, relations = set(), set()
    for t, sub, pred, obj, lat, lon in obs:
        if t not in on_grid:
            continue
        split = bucket[t]
        token = dt.datetime.fromtimestamp(t).isoformat()
        key = (sub, pred, obj, token)
        if key in seen[split]:
            continue                            # several UAVs can report one fact
        seen[split].add(key)
        e, n = frame.to_enu(lat, lon)
        rows[split].append((sub, pred, obj, token, "%.3f,%.3f" % (e, n)))
        entities.add(sub)
        entities.add(obj)
        relations.add(pred)

    landmarks = {name: frame.to_enu(*ll)
                 for name, ll in landmarks_ll.items() if name in entities}

    os.makedirs(dst, exist_ok=True)
    entity2id = {e: i for i, e in enumerate(sorted(entities))}
    relation2id = {r: i for i, r in enumerate(sorted(relations))}

    for split in ("train", "valid", "test"):
        rows[split].sort(key=lambda x: (ts2id[x[3]], x[0], x[1], x[2]))
        with open(os.path.join(dst, split + ".txt"), "w",
                  encoding="utf-8", newline="\n") as f:
            for row in rows[split]:
                f.write("\t".join(row) + "\n")

    for name, obj in (("entity2id.json", entity2id),
                      ("relation2id.json", relation2id),
                      ("ts2id.json", ts2id)):
        with open(os.path.join(dst, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    with open(os.path.join(dst, "landmarks.tsv"), "w",
              encoding="utf-8", newline="\n") as f:
        for name in sorted(landmarks):
            e, n = landmarks[name]
            f.write("%s\t%.3f\t%.3f\n" % (name, e, n))

    with open(os.path.join(dst, "entity_types.tsv"), "w",
              encoding="utf-8", newline="\n") as f:
        for ent in sorted(entities):
            if ent in entity_class:
                f.write("%s\t%s\n" % (ent, entity_class[ent]))

    return {
        "observer": observer,
        "stride_s": stride,
        "origin": (round(frame.lat0, 7), round(frame.lon0, 7)),
        "ticks": len(grid),
        "ticks_train_valid_test": (len(train_t), len(valid_t), len(test_t)),
        "entities": len(entity2id),
        "relations": len(relation2id),
        "landmarks": len(landmarks),
        "typed_entities": sum(1 for e in entities if e in entity_class),
        "edges": dict((s, len(rows[s])) for s in rows),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--scenario", default=DEFAULT_SCENARIO)
    ap.add_argument("--dst", default=None,
                    help="default: ../data/VR-Forces_<observer>_s<stride>")
    ap.add_argument("--observer", default="ground_truth",
                    choices=("ground_truth", "uav"))
    ap.add_argument("--stride", type=int, default=10, help="tick grid, seconds")
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--valid-frac", type=float, default=0.15)
    args = ap.parse_args()

    dst = args.dst or os.path.join(
        DEFAULT_DATA, "VR-Forces_%s_s%d" % (args.observer, args.stride))
    stats = build(args.src, args.scenario, dst, args.observer, args.stride,
                  args.train_frac, args.valid_frac)
    print("dst = %s" % dst)
    for k, v in stats.items():
        print("  %-24s %s" % (k, v))


if __name__ == "__main__":
    main()
