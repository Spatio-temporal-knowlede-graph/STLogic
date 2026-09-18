"""Horizon-aware evaluation: aggregate, hard-subset, and cluster bootstrap CI.

`evaluate.py` reports one filtered MRR over every test quadruple. On VR-Forces that
number is dominated by persistence -- a movement order holds for minutes, so at a
short horizon almost every query is answered by copying the previous tick. This
script adds the two things needed to say anything about a spatial model:

  hard subset   queries whose answer CHANGED between the observation time
                (ts - horizon) and the query time. These are the only queries where
                a forecaster can beat "repeat the last observation".

  cluster CI    hard queries are heavily correlated: one order change at t_change
                spawns up to `horizon` near-identical queries. The independent unit
                is the CHANGE, not the query. Bootstrap resamples clusters
                (subject, relation, old answer, new answer), so the interval
                reflects ~100 real events rather than ~10k correlated rows.

Usage:
    python evaluate_horizon.py -d <dataset> -c <candidates.json> --horizon <ticks>
"""
import argparse
import json
import random

import numpy as np

from grapher import Grapher
from temporal_walk import store_edges
from baseline import baseline_candidates, calculate_obj_distribution

# Copied rather than imported: evaluate.py parses argv and runs a full evaluation at
# module level, so importing it would execute that. These two are byte-for-byte the
# same logic, so the numbers stay comparable with evaluate.py.


def filter_candidates(test_query, candidates, test_data):
    """Time-aware filtered setting: drop other correct answers to the same query."""
    other = test_data[
        (test_data[:, 0] == test_query[0])
        * (test_data[:, 1] == test_query[1])
        * (test_data[:, 2] != test_query[2])
        * (test_data[:, 3] == test_query[3])
    ]
    for obj in other[:, 2]:
        candidates.pop(obj, None)
    return candidates


def calculate_rank(answer, candidates, num_entities, setting="best"):
    """Rank of the correct answer; ties broken as in evaluate.py ('best')."""
    rank = num_entities
    if answer in candidates:
        conf = candidates[answer]
        confs = list(candidates.values())
        ranks = [i for i, x in enumerate(confs) if x == conf]
        if setting == "average":
            rank = (ranks[0] + ranks[-1]) // 2 + 1
        elif setting == "best":
            rank = ranks[0] + 1
        else:
            rank = ranks[-1] + 1
    return rank


def answers_at(index, sub, rel, ts):
    """Objects asserted for (sub, rel) at-or-before ts; empty when never seen."""
    key = (sub, rel)
    series = index.get(key)
    if not series:
        return frozenset()
    lo, hi = 0, len(series)
    while lo < hi:                       # last entry with ts' <= ts
        mid = (lo + hi) // 2
        if series[mid][0] <= ts:
            lo = mid + 1
        else:
            hi = mid
    return series[lo - 1][1] if lo else frozenset()


def build_index(all_idx):
    """{(sub, rel): [(ts, frozenset(objs)), ...]} sorted by ts."""
    per = {}
    for s, r, o, t in all_idx:
        per.setdefault((int(s), int(r)), {}).setdefault(int(t), set()).add(int(o))
    return {k: sorted((t, frozenset(v)) for t, v in d.items()) for k, d in per.items()}


def metrics(ranks):
    if not ranks:
        return dict(n=0, mrr=float("nan"), h1=float("nan"),
                    h3=float("nan"), h10=float("nan"))
    a = np.asarray(ranks, dtype=np.float64)
    return dict(n=len(a), mrr=float((1.0 / a).mean()),
                h1=float((a <= 1).mean()), h3=float((a <= 3).mean()),
                h10=float((a <= 10).mean()))


def cluster_bootstrap(by_cluster, n_boot=2000, seed=0):
    """95% CI of hard-subset MRR, resampling clusters with replacement."""
    keys = list(by_cluster)
    if len(keys) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        picked = [by_cluster[keys[rng.randrange(len(keys))]] for _ in keys]
        flat = [r for group in picked for r in group]
        means.append(float(np.mean([1.0 / r for r in flat])))
    means.sort()
    return (means[int(0.025 * n_boot)], means[int(0.975 * n_boot)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", "-d", required=True)
    ap.add_argument("--candidates", "-c", required=True)
    ap.add_argument("--horizon", type=int, default=0)
    ap.add_argument("--test_data", default="test")
    ap.add_argument("--n_boot", type=int, default=2000)
    a = ap.parse_args()

    data = Grapher("../data/" + a.dataset + "/")
    num_entities = len(data.id2entity)
    test_data = data.test_idx if a.test_data == "test" else data.valid_idx
    learn_edges = store_edges(data.train_idx)
    obj_dist, rel_obj_dist = calculate_obj_distribution(data.train_idx, learn_edges)
    index = build_index(data.all_idx)

    cands = json.load(open("../output/" + a.dataset + "/" + a.candidates,
                           encoding="utf-8"))
    cands = {int(k): {int(c): v for c, v in d.items()} for k, d in cands.items()}

    all_ranks, hard_ranks, unseen = [], [], 0
    by_cluster = {}
    for i in range(len(test_data)):
        q = test_data[i]
        sub, rel, obj, ts = int(q[0]), int(q[1]), int(q[2]), int(q[3])
        c = cands[i] if cands.get(i) else baseline_candidates(
            rel, learn_edges, obj_dist, rel_obj_dist)
        c = filter_candidates(q, dict(c), test_data)
        rank = calculate_rank(obj, c, num_entities)
        all_ranks.append(rank)

        known = answers_at(index, sub, rel, ts - a.horizon)
        if not known:
            unseen += 1
            continue
        if obj not in known:                      # the answer changed -> hard
            hard_ranks.append(rank)
            key = (sub, rel, tuple(sorted(known)), obj)
            by_cluster.setdefault(key, []).append(rank)

    lo, hi = cluster_bootstrap(by_cluster, a.n_boot)
    ov, hd = metrics(all_ranks), metrics(hard_ranks)
    print("dataset=%s  horizon=%d ticks  candidates=%s" % (a.dataset, a.horizon, a.candidates))
    print("  %-10s %7s %8s %8s %8s %8s" % ("subset", "n", "MRR", "H@1", "H@3", "H@10"))
    print("  %-10s %7d %8.4f %8.4f %8.4f %8.4f"
          % ("all", ov["n"], ov["mrr"], ov["h1"], ov["h3"], ov["h10"]))
    print("  %-10s %7d %8.4f %8.4f %8.4f %8.4f"
          % ("hard", hd["n"], hd["mrr"], hd["h1"], hd["h3"], hd["h10"]))
    print("  hard clusters = %d   hard MRR 95%% CI = [%.4f, %.4f]"
          % (len(by_cluster), lo, hi))
    print("  queries with no prior observation (excluded from hard) = %d" % unseen)


if __name__ == "__main__":
    main()
