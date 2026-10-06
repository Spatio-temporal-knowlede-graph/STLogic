#!/usr/bin/env python
"""Export an embargo dataset for RE-Net / CyGNet / TiRGN, keeping the protocol.

The embargo protocol has three categories, these models have two. Folding the
embargo block into train.txt would let them fit on facts the protocol forbids;
dropping it entirely would deny them evidence STLogic does use (a test query at
the last tick has its cutoff inside the embargo window). So four files are written
and the runners are told which is which:

    train.txt      learnable      ticks [fit_lo, fit_hi]
    valid.txt      learnable      ticks [calib_lo, calib_hi]   (their validation)
    evidence.txt   NOT learnable  ticks [embargo_lo, embargo_hi]
    test.txt       queries        ticks [test_lo, test_hi]
    vocab.txt      train + valid + evidence, i.e. everything ever observable

`vocab.txt` exists because CyGNet's copy vocabulary and TiRGN's history vocabulary
are built from a file rather than from the training loop's data. Pointing them at
vocab.txt gives them the same evidence STLogic grounds against, while gradients
still come from train.txt alone.

`horizon_map.txt` carries the exact-seconds cutoff so every model and the evaluator
cut at the same tick; id subtraction only matches on a uniform grid.
"""
import argparse
import bisect
import datetime as dt
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.normpath(os.path.join(HERE, "..", "data"))


def read_split(path, e2i, r2i, t2i):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 4:
                continue
            out.append((e2i[p[0]], r2i[p[1]], e2i[p[2]], t2i[p[3]]))
    return out


def write(path, quads):
    quads = sorted(quads, key=lambda q: (q[3], q[0], q[1], q[2]))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for s, r, o, t in quads:
            f.write("%d\t%d\t%d\t%d\t0\n" % (s, r, o, t))
    return len(quads)


def export(src, dst, delta):
    load = lambda n: json.load(open(os.path.join(src, n), encoding="utf-8"))
    e2i, r2i, t2i = load("entity2id.json"), load("relation2id.json"), load("ts2id.json")
    meta = load("split_meta.json")
    os.makedirs(dst, exist_ok=True)

    train_all = read_split(os.path.join(src, "train.txt"), e2i, r2i, t2i)
    embargo = read_split(os.path.join(src, "valid.txt"), e2i, r2i, t2i)
    test = read_split(os.path.join(src, "test.txt"), e2i, r2i, t2i)

    lo, hi = meta["calib_ticks"]
    fit = [q for q in train_all if q[3] < lo]
    calib = [q for q in train_all if lo <= q[3] <= hi]

    counts = {
        "train": write(os.path.join(dst, "train.txt"), fit),
        "valid": write(os.path.join(dst, "valid.txt"), calib),
        "evidence": write(os.path.join(dst, "evidence.txt"), embargo),
        "test": write(os.path.join(dst, "test.txt"), test),
        "vocab": write(os.path.join(dst, "vocab.txt"), fit + calib + embargo),
    }

    with open(os.path.join(dst, "stat.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("%d\t%d\t0\n" % (len(e2i), len(r2i)))
    for name, m in (("entity2id.txt", e2i), ("relation2id.txt", r2i)):
        with open(os.path.join(dst, name), "w", encoding="utf-8", newline="\n") as f:
            for k, v in sorted(m.items(), key=lambda kv: kv[1]):
                f.write("%s\t%d\n" % (k, v))

    order = sorted(t2i.items(), key=lambda kv: kv[1])
    eps = [int(dt.datetime.fromisoformat(tok).timestamp()) for tok, _ in order]
    ids = [i for _, i in order]
    with open(os.path.join(dst, "horizon_map.txt"), "w",
              encoding="utf-8", newline="\n") as f:
        for k, e in zip(ids, eps):
            j = bisect.bisect_right(eps, e - delta) - 1
            f.write("%d\t%d\n" % (k, ids[j] if j >= 0 else ids[0]))

    with open(os.path.join(dst, "protocol.json"), "w", encoding="utf-8") as f:
        json.dump({"delta_seconds": delta, "source": os.path.basename(src),
                   "ticks": {k: meta[k] for k in ("fit_ticks", "calib_ticks",
                                                  "embargo_ticks", "test_ticks")},
                   "roles": {"train.txt": "learnable", "valid.txt": "learnable",
                             "evidence.txt": "evidence only -- never fit on",
                             "vocab.txt": "train+valid+evidence, for vocabulary builds",
                             "test.txt": "queries"},
                   "counts": counts}, f, indent=2)
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", "-d", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--delta", type=int, default=600)
    a = ap.parse_args()
    c = export(os.path.join(DEFAULT_DATA, a.dataset), a.dst, a.delta)
    print("dst = %s" % a.dst)
    for k, v in c.items():
        print("  %-10s %d" % (k, v))


if __name__ == "__main__":
    main()
