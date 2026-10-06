"""STLogic evaluation: candidate generation and final ranking, reported apart.

Candidate generation is judged on whether the answer is *present*, ranking on where
it lands. Collapsing them into one MRR hides which half is working.

    Candidate Recall@K   answer inside the top-K of a candidate set
    Spatial Recovery     of the answers TLogic missed entirely, how many C_S found
    MRR / Hits@k         ALL and HARD, hard carrying a cluster bootstrap CI

Usage:
    python evaluate_stlogic.py -d <dataset> --baseline <cands.json> \
        --stlogic <cands.json> --horizon <ticks> [--test_data test|valid]
"""
import argparse
import json

from grapher import Grapher
from temporal_walk import store_edges
from baseline import baseline_candidates, calculate_obj_distribution
from evaluate_horizon import (build_index, answers_at, metrics, cluster_bootstrap,
                              filter_candidates, calculate_rank)


def rank_of(answer, cands, num_entities, query, test_data, setting="average"):
    # calculate_rank reads the dict in INSERTION order -- TLogic's own convention is
    # that candidate dicts arrive pre-sorted. Anything we build ourselves must be
    # sorted here or every rank is meaningless.
    c = filter_candidates(query, dict(cands), test_data)
    c = dict(sorted(c.items(), key=lambda kv: -kv[1]))
    return calculate_rank(answer, c, num_entities, setting=setting)


def top_k(cands, k):
    return set(sorted(cands, key=lambda o: -cands[o])[:k])


def evaluate(data, cands, index, horizon, num_entities, learn_edges,
             obj_dist, rel_obj_dist, ks=(1, 3, 10, 20), setting="average"):
    """Ranks and candidate-presence counts for one candidate file.

    Ties take their AVERAGE rank. This is the primary convention for every model,
    not a special case: candidate augmentation can put many equal-scored entries in
    one block, and "best" then hands the whole block the front position. Measured on
    test, random augmentation swings 0.0377–0.1673 in hard MRR across tie settings
    (mean tie block 9.0) while the spatial models do not move at all (block 1.0).
    Reporting "best" would make random augmentation look like it beats them.
    """
    all_ranks, hard_ranks = [], []
    by_cluster = {}
    recall = {k: [0, 0] for k in ks}          # k -> [hit, total]
    hard_flags = []
    for i in range(len(data)):
        q = data[i]
        sub, rel, obj, ts = (int(x) for x in q)
        c = cands.get(i) or baseline_candidates(rel, learn_edges, obj_dist, rel_obj_dist)
        r = rank_of(obj, c, num_entities, q, data, setting)
        all_ranks.append(r)

        known = answers_at(index, sub, rel, ts - horizon)
        is_hard = bool(known) and obj not in known
        hard_flags.append(is_hard)
        if is_hard:
            hard_ranks.append(r)
            by_cluster.setdefault((sub, rel, tuple(sorted(known)), obj), []).append(r)
        for k in ks:
            recall[k][1] += 1
            if obj in top_k(c, k):
                recall[k][0] += 1
    return {"all": metrics(all_ranks), "hard": metrics(hard_ranks),
            "clusters": by_cluster, "recall": recall, "hard_flags": hard_flags}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", "-d", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--stlogic", required=True)
    ap.add_argument("--horizon", type=int, default=0)
    # Must match how the candidates were generated; see evaluate_horizon.py.
    ap.add_argument("--horizon-seconds", type=int, default=0)
    ap.add_argument("--test_data", default="test", choices=("test", "valid"))
    ap.add_argument("--n_boot", type=int, default=2000)
    a = ap.parse_args()

    g = Grapher("../data/%s/" % a.dataset)
    data = g.test_idx if a.test_data == "test" else g.valid_idx
    ne = len(g.id2entity)
    learn_edges = store_edges(g.train_idx)
    od, rod = calculate_obj_distribution(g.train_idx, learn_edges)
    index = build_index(g.all_idx)

    def load(name):
        d = json.load(open("../output/%s/%s" % (a.dataset, name), encoding="utf-8"))
        return {int(k): {int(c): v for c, v in v2.items()} for k, v2 in d.items()}

    base_c, stl_c = load(a.baseline), load(a.stlogic)
    B = evaluate(data, base_c, index, a.horizon, ne, learn_edges, od, rod)
    S = evaluate(data, stl_c, index, a.horizon, ne, learn_edges, od, rod)

    print("dataset=%s  split=%s  horizon=%d ticks  쿼리 %d"
          % (a.dataset, a.test_data, a.horizon, len(data)))

    print("\n① Candidate Recall@K")
    print("  %-6s %12s %12s %10s" % ("K", "TLogic", "STLogic", "차이"))
    for k in (1, 3, 10, 20):
        b = B["recall"][k][0] / B["recall"][k][1]
        s = S["recall"][k][0] / S["recall"][k][1]
        print("  %-6d %11.4f %12.4f %+10.4f" % (k, b, s, s - b))

    # Spatial Recovery Rate: of the answers absent from C_T, how many C_S supplied
    missed = recovered = 0
    for i in range(len(data)):
        obj = int(data[i][2])
        bc = base_c.get(i) or {}
        if obj in bc:
            continue
        missed += 1
        if obj in (stl_c.get(i) or {}):
            recovered += 1
    print("\n② Spatial Recovery Rate")
    print("  TLogic 후보에 정답이 없던 쿼리 %d건 중 %d건 복구 = %.2f%%"
          % (missed, recovered, 100 * recovered / missed if missed else 0.0))

    print("\n③ Ranking")
    print("  %-10s %8s %9s %9s %9s %9s" % ("", "subset", "n", "MRR", "H@1", "H@10"))
    for name, res in (("TLogic", B), ("STLogic", S)):
        for sub in ("all", "hard"):
            m = res[sub]
            print("  %-10s %8s %9d %9.4f %9.4f %9.4f"
                  % (name, sub, m["n"], m["mrr"], m["h1"], m["h10"]))
    print("\n④ 동점 처리 민감도 (hard MRR)")
    print("  %-10s %10s %10s %10s" % ("", "best", "average", "worst"))
    for name, cc in (("TLogic", base_c), ("STLogic", stl_c)):
        vals = []
        for st in ("best", "average", "worst"):
            r = evaluate(data, cc, index, a.horizon, ne, learn_edges, od, rod, setting=st)
            vals.append(r["hard"]["mrr"])
        print("  %-10s %10.4f %10.4f %10.4f" % (name, vals[0], vals[1], vals[2]))

    lo_b, hi_b = cluster_bootstrap(B["clusters"], a.n_boot)
    lo_s, hi_s = cluster_bootstrap(S["clusters"], a.n_boot)
    print("  hard 클러스터 %d개" % len(S["clusters"]))
    print("  hard MRR 95%% CI   TLogic [%.4f, %.4f]   STLogic [%.4f, %.4f]"
          % (lo_b, hi_b, lo_s, hi_s))
    print("  Δ hard MRR = %+.4f" % (S["hard"]["mrr"] - B["hard"]["mrr"]))
    print("  Δ all  MRR = %+.4f" % (S["all"]["mrr"] - B["all"]["mrr"]))


if __name__ == "__main__":
    main()
