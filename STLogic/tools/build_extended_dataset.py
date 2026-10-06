#!/usr/bin/env python
"""Build the VR-Forces dataset extended with derived spatial relations.

VR-Forces already ships `build/spatial/ver2.0_relations.csv`: 114,248 INTERVALS of
`in_front_of / behind / in_range_of / next_to` between entity pairs, each with a
t_start and t_end. Those are folded in here as edges, but only at the moment the
relation STARTS -- an interval's beginning is the event, its continuation is not
news. Writing every tick of every interval would bury the task relations: measured,
the spatial carpet is 113,048 start events against 22,637 task edges, and a random
walk would then spend almost all its steps on spatial edges.

Four containers, so the protocol survives contact with the extra relations:

    train.txt     rules and the spatial model are learned here
    valid.txt     calibration / model selection (a real validation split)
    embargo.txt   NEITHER learned NOR evaluated, but visible as evidence: a test
                  query at t may observe facts up to t - delta, and for later test
                  queries that cutoff lands inside this block
    test.txt      evaluation; task relations ONLY

Spatial relations are deliberately kept out of test.txt. They are derived from
positions, so making them prediction targets would score the model on recovering
its own inputs. As body atoms they are ordinary evidence; as queries they would be
circular. Keeping them out also leaves the query set identical to the unextended
dataset, so every number stays comparable.

Usage:
    python tools/build_extended_dataset.py --embargo 600 --test-ticks 27 \
        --dst ../data/VR-Forces_gt_s10_ext
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from build_vrforces_dataset import (EnuFrame, load_landmarks, load_registry,   # noqa: E402
                                    pick_grid, read_observations)

DEFAULT_DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
DEFAULT_SRC = os.path.normpath(os.path.join(HERE, "..", "..", "dataset", "VR-Forces"))
DEFAULT_SCENARIO = os.path.normpath(
    os.path.join(HERE, "..", "..", "..", "VR-Forces"))
SPATIAL_CSV = os.path.join("build", "spatial", "ver2.0_relations.csv")


def _epoch(ts):
    return int(dt.datetime.fromisoformat(ts).timestamp())


def read_spatial_starts(scenario, predicates=None, min_support=1):
    """[(epoch, subject, predicate, object)] -- one row per interval START.

    `support_count` is how many samples backed the interval; 1.3% of intervals last
    zero seconds, which is a pair brushing past a threshold rather than a relation
    holding, so a floor is available.
    """
    path = os.path.join(scenario, SPATIAL_CSV)
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            pred = r["predicate"].strip()
            if predicates and pred not in predicates:
                continue
            try:
                if int(r["support_count"]) < min_support:
                    continue
            except (TypeError, ValueError):
                pass
            out.append((_epoch(r["t_start"]), r["subject"].strip(), pred,
                        r["object"].strip()))
    return out


def snap(epochs, grid):
    """Map each epoch to the grid tick at or before it (None when earlier than all)."""
    import bisect
    out = []
    for e in epochs:
        i = bisect.bisect_right(grid, e) - 1
        out.append(grid[i] if i >= 0 else None)
    return out


def build(src, scenario, dst, stride, delta, test_ticks, valid_ticks,
          predicates, min_support):
    obs = read_observations([os.path.join(src, "ground_truth_ver2.0.csv")])
    landmarks_ll = load_landmarks(scenario)
    entity_class = load_registry(scenario)

    lats = [o[4] for o in obs] + [v[0] for v in landmarks_ll.values()]
    lons = [o[5] for o in obs] + [v[1] for v in landmarks_ll.values()]
    frame = EnuFrame(sum(lats) / len(lats), sum(lons) / len(lons))

    grid = pick_grid([o[0] for o in obs], stride)
    on_grid = set(grid)

    # --- split: everything learned must predate the earliest test cutoff ---------
    test_t = grid[-test_ticks:]
    cut = test_t[0] - delta
    learnable = [t for t in grid if t <= cut]
    if len(learnable) <= valid_ticks:
        raise ValueError("embargo leaves %d learnable ticks; valid_ticks=%d is too big"
                         % (len(learnable), valid_ticks))
    train_t = learnable[:-valid_ticks]
    valid_t = learnable[-valid_ticks:]
    embargo_t = [t for t in grid if cut < t < test_t[0]]
    role = {}
    for name, ts in (("train", train_t), ("valid", valid_t),
                     ("embargo", embargo_t), ("test", test_t)):
        for t in ts:
            role[t] = name

    ts2id = {}
    for i, t in enumerate(grid):
        ts2id[dt.datetime.fromtimestamp(t).isoformat()] = i

    rows = {k: [] for k in ("train", "valid", "embargo", "test")}
    seen = {k: set() for k in rows}
    entities, relations = set(), set()

    # --- task relations (subject position rides along in column 5) --------------
    task_counts = {}
    for t, sub, pred, obj, lat, lon in obs:
        if t not in on_grid:
            continue
        split = role[t]
        token = dt.datetime.fromtimestamp(t).isoformat()
        key = (sub, pred, obj, token)
        if key in seen[split]:
            continue
        seen[split].add(key)
        e, n = frame.to_enu(lat, lon)
        rows[split].append((sub, pred, obj, token, "%.3f,%.3f" % (e, n)))
        entities.add(sub)
        entities.add(obj)
        relations.add(pred)
        task_counts[pred] = task_counts.get(pred, 0) + 1

    # --- derived spatial relations, at interval starts only ---------------------
    starts = read_spatial_starts(scenario, predicates, min_support)
    ticks = snap([s[0] for s in starts], grid)
    spatial_counts = {}
    dropped_test = 0
    for (e_raw, sub, pred, obj), t in zip(starts, ticks):
        if t is None:
            continue
        split = role[t]
        if split == "test":
            dropped_test += 1        # never a query: derived from the positions
            continue                 # the model is being scored on
        token = dt.datetime.fromtimestamp(t).isoformat()
        key = (sub, pred, obj, token)
        if key in seen[split]:
            continue
        seen[split].add(key)
        # No location column: these are pair-level facts, not observations of a
        # single head, and Grapher only reads column 5 for the head's position.
        rows[split].append((sub, pred, obj, token, ""))
        entities.add(sub)
        entities.add(obj)
        relations.add(pred)
        spatial_counts[pred] = spatial_counts.get(pred, 0) + 1

    os.makedirs(dst, exist_ok=True)
    entity2id = {e: i for i, e in enumerate(sorted(entities))}
    relation2id = {r: i for i, r in enumerate(sorted(relations))}
    for split, data in rows.items():
        data.sort(key=lambda r: (ts2id[r[3]], r[0], r[1], r[2]))
        with open(os.path.join(dst, split + ".txt"), "w",
                  encoding="utf-8", newline="\n") as f:
            for sub, pred, obj, token, loc in data:
                f.write("\t".join((sub, pred, obj, token, loc)).rstrip("\t") + "\n")
    for name, obj_ in (("entity2id.json", entity2id), ("relation2id.json", relation2id),
                       ("ts2id.json", ts2id)):
        with open(os.path.join(dst, name), "w", encoding="utf-8") as f:
            json.dump(obj_, f, ensure_ascii=False, indent=1)

    with open(os.path.join(dst, "landmarks.tsv"), "w",
              encoding="utf-8", newline="\n") as f:
        for name, (lat, lon) in sorted(landmarks_ll.items()):
            e, n = frame.to_enu(lat, lon)
            f.write("%s\t%.3f\t%.3f\n" % (name, e, n))
    with open(os.path.join(dst, "entity_types.tsv"), "w",
              encoding="utf-8", newline="\n") as f:
        for e in sorted(entities):
            if e in entity_class:
                f.write("%s\t%s\n" % (e, entity_class[e]))

    meta = {
        "mode": "embargo+spatial",
        "embargo_seconds": delta,
        "roles": {
            "train.txt": "learning (rules + spatial model)",
            "valid.txt": "validation / calibration",
            "embargo.txt": "EMBARGO -- evidence only, never learned or evaluated",
            "test.txt": "evaluation; task relations only",
        },
        "spatial_relations": {
            "source": SPATIAL_CSV,
            "policy": "interval START only; excluded from test.txt",
            "predicates": sorted(spatial_counts),
            "min_support": min_support,
            "counts": spatial_counts,
            "dropped_in_test_period": dropped_test,
        },
        "task_relations": task_counts,
        "ticks": {k: [ts2id[dt.datetime.fromtimestamp(v[0]).isoformat()],
                      ts2id[dt.datetime.fromtimestamp(v[-1]).isoformat()]]
                  for k, v in (("train", train_t), ("valid", valid_t),
                               ("embargo", embargo_t), ("test", test_t)) if v},
        "train_end_epoch": valid_t[-1],
        "min_test_cutoff_epoch": test_t[0] - delta,
    }
    assert meta["train_end_epoch"] <= meta["min_test_cutoff_epoch"], meta
    with open(os.path.join(dst, "split_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"entities": len(entity2id), "relations": len(relation2id),
            "ticks": len(grid),
            "rows": {k: len(v) for k, v in rows.items()},
            "task": task_counts, "spatial": spatial_counts,
            "spatial_dropped_in_test": dropped_test}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--scenario", default=DEFAULT_SCENARIO)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--stride", type=int, default=10)
    ap.add_argument("--embargo", type=int, default=600)
    ap.add_argument("--test-ticks", type=int, default=27)
    ap.add_argument("--valid-ticks", type=int, default=13)
    ap.add_argument("--predicates", default=None,
                    help="comma-separated subset; default: all four")
    ap.add_argument("--min-support", type=int, default=1)
    a = ap.parse_args()
    preds = set(a.predicates.split(",")) if a.predicates else None
    stats = build(a.src, a.scenario, a.dst, a.stride, a.embargo, a.test_ticks,
                  a.valid_ticks, preds, a.min_support)
    print("dst = %s" % a.dst)
    for k, v in stats.items():
        print("  %-24s %s" % (k, v))


if __name__ == "__main__":
    main()
