#!/usr/bin/env python
"""Build an entity-to-entity (ICEWS-shaped) TLogic dataset from VR-Forces.

Every object is an actor -- no landmark ever appears as a subject or an object.
Position moves out of the graph and into the edge's metadata column, the way a
conventional STKG carries it:

    subject \t relation \t object \t ts_token \t location

Sources, and why only these:

  Fire-Weapon   the only entity->entity relation the SIMULATION itself emits, so
                it is the only one whose timestamps are execution times that line
                up with the position track.
  partOf        order of battle from build/registry/master_entities.csv. Static
                structure, replicated across ticks exactly as convert_battlefield.py
                does for hill395.

Deliberately excluded:

  battle.jsonl actions (directFireAt / hitBy / damages / firesUpon ...). These are
  AUTHORING-timeline events. Measured against the simulation, the same shooter-target
  pair fires between 264 s and 1057 s later than the script says (sd 296 s) -- the
  units arrive late. Their times cannot be used as STKG timestamps, and attaching
  positions to them would attach the wrong positions.

  behind / in_front_of / next_to / in_range_of. Entity-to-entity and plentiful
  (89,551 triples), but each is a deterministic function of the very coordinates the
  spatial model reads, so predicting them measures rule reconstruction rather than
  forecasting. --with-spatial includes them for anyone who wants to measure that.

Usage:
    python tools/build_vrforces_entity_dataset.py [--stride 10] [--with-spatial]
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_vrforces_dataset import (EnuFrame, pick_grid, split_grid,  # noqa: E402
                                    load_landmarks, DEFAULT_SRC, DEFAULT_SCENARIO,
                                    DEFAULT_DATA)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def read_entity_edges(src):
    """(epoch, subject, predicate, object, lat, lon) for entity-object rows only."""
    path = os.path.join(src, "ground_truth_ver2.0.csv")
    out = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            obj = r["object"].strip()
            if not obj or obj.startswith("LOC_"):
                continue                      # landmark object -> not an actor
            lat, lon = r["latitude"].strip(), r["longitude"].strip()
            if not lat or not lon:
                continue
            out.append((int(dt.datetime.fromisoformat(r["timestamp"]).timestamp()),
                        r["subject"].strip(), r["predicate"].strip(), obj,
                        float(lat), float(lon)))
    return out


def read_units(scenario):
    """[(entity, unit)] from the registry, ids normalised to the STKG spelling."""
    path = os.path.join(scenario, "build", "registry", "master_entities.csv")
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["unit"]:
                out.append((r["entity_id"].replace("-", ""),
                            "UNIT_" + r["unit"].replace("-", "")))
    return out


def read_spatial(scenario, grid):
    """Derived spatial relation intervals expanded onto the tick grid."""
    path = os.path.join(scenario, "build", "spatial", "ver2.0_relations.csv")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            a = int(dt.datetime.fromisoformat(r["t_start"]).timestamp())
            b = int(dt.datetime.fromisoformat(r["t_end"]).timestamp())
            for t in grid:
                if a <= t <= b:
                    out.append((t, r["subject"], r["predicate"], r["object"]))
    return out


def build(src, scenario, dst, stride, train_frac, valid_frac, with_spatial):
    obs = read_entity_edges(src)
    if not obs:
        raise ValueError("no entity-object rows found")

    # Position track comes from every row, landmark-object ones included: the track is
    # metadata, not graph content, so it should not thin out with the edge filter.
    track = {}
    with open(os.path.join(src, "ground_truth_ver2.0.csv"),
              "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            lat, lon = r["latitude"].strip(), r["longitude"].strip()
            if not lat or not lon:
                continue
            t = int(dt.datetime.fromisoformat(r["timestamp"]).timestamp())
            track[(r["subject"].strip(), t)] = (float(lat), float(lon))

    landmarks_ll = load_landmarks(scenario)
    lats = [v[0] for v in track.values()] + [v[0] for v in landmarks_ll.values()]
    lons = [v[1] for v in track.values()] + [v[1] for v in landmarks_ll.values()]
    frame = EnuFrame(sum(lats)/len(lats), sum(lons)/len(lons))

    grid = pick_grid([t for (_, t) in track], stride)
    on_grid = set(grid)
    train_t, valid_t, test_t = split_grid(grid, train_frac, valid_frac)
    bucket = {}
    for name, block in (("train", train_t), ("valid", valid_t), ("test", test_t)):
        for t in block:
            bucket[t] = name

    rows = {"train": [], "valid": [], "test": []}
    seen = {"train": set(), "valid": set(), "test": set()}
    entities, relations = set(), set()
    counts = {}

    def emit(t, sub, pred, obj):
        if t not in on_grid:
            return
        split = bucket[t]
        token = dt.datetime.fromtimestamp(t).isoformat()
        key = (sub, pred, obj, token)
        if key in seen[split]:
            return
        seen[split].add(key)
        ll = track.get((sub, t))
        loc = "%.3f,%.3f" % frame.to_enu(*ll) if ll else ""
        rows[split].append((sub, pred, obj, token, loc))
        entities.add(sub); entities.add(obj); relations.add(pred)
        counts[pred] = counts.get(pred, 0) + 1

    for t, sub, pred, obj, _, _ in obs:
        emit(t, sub, pred, obj)

    for ent, unit in read_units(scenario):
        for t in grid:
            emit(t, ent, "partOf", unit)

    if with_spatial:
        for t, sub, pred, obj in read_spatial(scenario, grid):
            emit(t, sub, pred, obj)

    os.makedirs(dst, exist_ok=True)
    ts2id = {}
    for i, t in enumerate(grid):
        ts2id[dt.datetime.fromtimestamp(t).isoformat()] = i
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
    # No landmarks.tsv: by construction no landmark is a node in this graph.
    with open(os.path.join(dst, "entity_types.tsv"), "w",
              encoding="utf-8", newline="\n") as f:
        cls = {}
        with open(os.path.join(scenario, "build", "registry", "master_entities.csv"),
                  newline="", encoding="utf-8-sig") as g:
            for r in csv.DictReader(g):
                cls[r["entity_id"].replace("-", "")] = r["entity_class"]
        for e in sorted(entities):
            if e in cls:
                f.write("%s\t%s\n" % (e, cls[e]))

    # what the graph actually contains, for the caller to judge
    triples = set()
    per_rel_triples = {}
    for split in rows:
        for s, p, o, _, _ in rows[split]:
            triples.add((s, p, o))
            per_rel_triples.setdefault(p, set()).add((s, o))
    changes = {}
    last = {}
    for split in ("train", "valid", "test"):
        for s, p, o, tok, _ in rows[split]:
            k = (s, p)
            if k in last and last[k] != o:
                changes[p] = changes.get(p, 0) + 1
            last[k] = o

    return {
        "ticks": len(grid),
        "ticks_train_valid_test": (len(train_t), len(valid_t), len(test_t)),
        "entities": len(entity2id),
        "relations": sorted(relation2id),
        "edges": dict((s, len(rows[s])) for s in rows),
        "edges_by_relation": counts,
        "distinct_triples": len(triples),
        "distinct_triples_by_relation": {k: len(v) for k, v in per_rel_triples.items()},
        "object_changes_by_relation": changes or {"(none)": 0},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--scenario", default=DEFAULT_SCENARIO)
    ap.add_argument("--dst", default=None)
    ap.add_argument("--stride", type=int, default=10)
    ap.add_argument("--train-frac", type=float, default=0.70)
    ap.add_argument("--valid-frac", type=float, default=0.15)
    ap.add_argument("--with-spatial", action="store_true",
                    help="also emit behind/in_front_of/next_to/in_range_of")
    a = ap.parse_args()
    dst = a.dst or os.path.join(
        DEFAULT_DATA, "VR-Forces_entity%s_s%d" % ("_sp" if a.with_spatial else "", a.stride))
    stats = build(a.src, a.scenario, dst, a.stride, a.train_frac, a.valid_frac,
                  a.with_spatial)
    print("dst = %s" % dst)
    for k, v in stats.items():
        print("  %-30s %s" % (k, v))


if __name__ == "__main__":
    main()
