#!/usr/bin/env python
"""Export a STLogic dataset into the RE-Net / CyGNet / TiRGN input format.

All three read the same thing:

    train.txt / valid.txt / test.txt    s \t r \t o \t t \t 0
    stat.txt                            num_entities \t num_relations \t 0

and TiRGN additionally wants `entity2id.txt` / `relation2id.txt` (`name \t id`).

Ids come straight from the STLogic dataset's own maps, so a quadruple means the
same thing in every system and the comparison is like-for-like. Timestamps are the
contiguous tick ids (granularity 1), matching how these repos treat ICEWS-style
data once divided by their time unit.

Only FORWARD quadruples are written. Every one of these models builds its own
inverse relations internally, exactly as STLogic's Grapher does at load time;
writing inverses here would double-count them.

Usage:
    python tools/export_for_baselines.py -d VR-Forces_ground_truth_s10 --dst <dir>
"""
import argparse
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.normpath(os.path.join(HERE, "..", "data"))


def read_split(path, entity2id, relation2id, ts2id):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            out.append((entity2id[p[0]], relation2id[p[1]], entity2id[p[2]], ts2id[p[3]]))
    return out


def export(src_dir, dst_dir, delta=600):
    with open(os.path.join(src_dir, "entity2id.json"), encoding="utf-8") as f:
        entity2id = json.load(f)
    with open(os.path.join(src_dir, "relation2id.json"), encoding="utf-8") as f:
        relation2id = json.load(f)
    with open(os.path.join(src_dir, "ts2id.json"), encoding="utf-8") as f:
        ts2id = json.load(f)

    os.makedirs(dst_dir, exist_ok=True)
    counts = {}
    # The embargo block is evidence, never learned and never evaluated. These models
    # have no third category, so it is folded into train.txt -- which WOULD let them
    # fit on it. Excluded instead, matching what STLogic's rule learner sees.
    for split in ("train", "valid", "test"):
        quads = read_split(os.path.join(src_dir, split + ".txt"),
                           entity2id, relation2id, ts2id)
        quads.sort(key=lambda q: (q[3], q[0], q[1], q[2]))
        with open(os.path.join(dst_dir, split + ".txt"), "w",
                  encoding="utf-8", newline="\n") as f:
            for s, r, o, t in quads:
                f.write("%d\t%d\t%d\t%d\t0\n" % (s, r, o, t))
        counts[split] = len(quads)

    with open(os.path.join(dst_dir, "stat.txt"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write("%d\t%d\t0\n" % (len(entity2id), len(relation2id)))

    for name, mapping in (("entity2id.txt", entity2id),
                          ("relation2id.txt", relation2id)):
        with open(os.path.join(dst_dir, name), "w",
                  encoding="utf-8", newline="\n") as f:
            for k, v in sorted(mapping.items(), key=lambda kv: kv[1]):
                f.write("%s\t%d\n" % (k, v))

    # horizon_map.txt: tick -> the tick whose facts a query at that tick may see,
    # under the exact-seconds rule  {t : epoch(t) <= epoch(q) - delta}.
    # Every baseline reads this instead of subtracting tick ids, so all models and
    # the evaluator cut at the same place. Subtracting ids is only equivalent on a
    # uniform grid, and this one has four 20 s gaps.
    import bisect
    order = sorted(ts2id.items(), key=lambda kv: kv[1])
    tick_ep = [int(dt.datetime.fromisoformat(tok).timestamp()) for tok, _ in order]
    ids = [i for _, i in order]
    with open(os.path.join(dst_dir, "horizon_map.txt"), "w",
              encoding="utf-8", newline="\n") as f:
        for k, e in zip(ids, tick_ep):
            j = bisect.bisect_right(tick_ep, e - delta) - 1
            f.write("%d\t%d\n" % (k, ids[j] if j >= 0 else ids[0]))

    return {"entities": len(entity2id), "relations": len(relation2id),
            "timestamps": len(ts2id), **counts}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", "-d", required=True)
    ap.add_argument("--src", default=None)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--delta", type=int, default=600,
                    help="forecasting horizon in seconds for horizon_map.txt")
    a = ap.parse_args()
    src = a.src or os.path.join(DEFAULT_DATA, a.dataset)
    stats = export(src, a.dst, a.delta)
    print("src = %s" % src)
    print("dst = %s" % a.dst)
    for k, v in stats.items():
        print("  %-12s %s" % (k, v))


if __name__ == "__main__":
    main()
