import json
import json
import time
import argparse
import itertools
import numpy as np
from joblib import Parallel, delayed

import rule_application as ra
import spatial_context as sc
from grapher import Grapher
from temporal_walk import store_edges
from rule_learning import rules_statistics
from score_functions import score_12
from spatial_context import PositionIndex, FEATURE_SETS


parser = argparse.ArgumentParser()
parser.add_argument("--dataset", "-d", default="", type=str)
parser.add_argument("--test_data", default="test", type=str)
parser.add_argument("--rules", "-r", default="", type=str)
parser.add_argument("--rule_lengths", "-l", default=1, type=int, nargs="+")
parser.add_argument("--window", "-w", default=-1, type=int)
parser.add_argument("--top_k", default=20, type=int)
parser.add_argument("--num_processes", "-p", default=1, type=int)
parser.add_argument(
    "--spatial", default="off", type=str, choices=list(FEATURE_SETS.keys())
)  # STLogic spatial fit: off | dist | dist_dd | dist_dd_bearing
parser.add_argument("--type_cond", action="store_true")  # ② type-conditioned sigma
parser.add_argument("--fmin", default=0.0, type=float)    # ③ tie-gating clamp [0,1]
parser.add_argument("--backoff", action="store_true")     # ① spatial candidate backoff
parsed = vars(parser.parse_args())

dataset = parsed["dataset"]
rules_file = parsed["rules"]
window = parsed["window"]
top_k = parsed["top_k"]
num_processes = parsed["num_processes"]
rule_lengths = parsed["rule_lengths"]
rule_lengths = [rule_lengths] if (type(rule_lengths) == int) else rule_lengths
spatial_mode = parsed["spatial"]
feature_set = FEATURE_SETS[spatial_mode]
type_cond = parsed["type_cond"]
f_min = parsed["fmin"]
do_backoff = parsed["backoff"]

dataset_dir = "../data/" + dataset + "/"
dir_path = "../output/" + dataset + "/"
data = Grapher(dataset_dir)
# Unit membership (for centroid positions) from ALL splits so test-sector units are
# covered — this is background order-of-battle structure, not a forecasting target.
_unit_members = sc.build_unit_members(data.all_idx, data.relation2id.get("partOf"))
positions = (
    PositionIndex(data.loc_by_sub_ts, data.landmark_pos, data.entity_type, _unit_members)
    if (feature_set or do_backoff)
    else None
)

# ① spatial backoff setup: per-relation spatial signature + per-sector candidate pool
rel_spatial = {}
id2sector = {}
sector2ents = {}
if do_backoff:
    rel_spatial = sc.fit_relation_spatial(positions, data.train_idx)
    for name, eid in data.entity2id.items():
        sec = name.split("/")[0] if "/" in name else None
        if sec is not None:
            id2sector[eid] = sec
            sector2ents.setdefault(sec, []).append(eid)


def backoff_for(test_query):
    """① candidates for a no-rule-candidate query, ranked by relation spatial fit."""
    sub, rel, ts = int(test_query[0]), int(test_query[1]), int(test_query[3])
    sec = id2sector.get(sub)
    if sec is None:
        return {}
    return sc.backoff_candidates(
        positions, rel_spatial, feature_set, sub, rel, ts,
        sector2ents.get(sec, []), topk=top_k,
    )
test_data = data.test_idx if (parsed["test_data"] == "test") else data.valid_idx
rules_dict = json.load(open(dir_path + rules_file))
rules_dict = {int(k): v for k, v in rules_dict.items()}
print("Rules statistics:")
rules_statistics(rules_dict)
rules_dict = ra.filter_rules(
    rules_dict, min_conf=0.01, min_body_supp=2, rule_lengths=rule_lengths
)
print("Rules statistics after pruning:")
rules_statistics(rules_dict)
learn_edges = store_edges(data.train_idx)

score_func = score_12
# It is possible to specify a list of list of arguments for tuning
args = [[0.1, 0.5]]


def apply_rules(i, num_queries):
    """
    Apply rules (multiprocessing possible).

    Parameters:
        i (int): process number
        num_queries (int): minimum number of queries for each process

    Returns:
        all_candidates (list): answer candidates with corresponding confidence scores
        no_cands_counter (int): number of queries with no answer candidates
    """

    print("Start process", i, "...")
    all_candidates = [dict() for _ in range(len(args))]
    no_cands_counter = 0

    num_rest_queries = len(test_data) - (i + 1) * num_queries
    if num_rest_queries >= num_queries:
        test_queries_idx = range(i * num_queries, (i + 1) * num_queries)
    else:
        test_queries_idx = range(i * num_queries, len(test_data))

    cur_ts = test_data[test_queries_idx[0]][3]
    edges = ra.get_window_edges(data.all_idx, cur_ts, learn_edges, window)

    it_start = time.time()
    for j in test_queries_idx:
        test_query = test_data[j]
        cands_dict = [dict() for _ in range(len(args))]

        if test_query[3] != cur_ts:
            cur_ts = test_query[3]
            edges = ra.get_window_edges(data.all_idx, cur_ts, learn_edges, window)

        if test_query[1] in rules_dict:
            dicts_idx = list(range(len(args)))
            for rule in rules_dict[test_query[1]]:
                walk_edges = ra.match_body_relations(rule, edges, test_query[0])

                if 0 not in [len(x) for x in walk_edges]:
                    rule_walks = ra.get_walks(rule, walk_edges)
                    if rule["var_constraints"]:
                        rule_walks = ra.check_var_constraints(
                            rule["var_constraints"], rule_walks
                        )

                    if not rule_walks.empty:
                        cands_dict = ra.get_candidates(
                            rule,
                            rule_walks,
                            cur_ts,
                            cands_dict,
                            score_func,
                            args,
                            dicts_idx,
                            test_query[0],
                            positions,
                            feature_set,
                            type_cond,
                            f_min,
                        )
                        for s in dicts_idx:
                            cands_dict[s] = {
                                x: sorted(cands_dict[s][x], reverse=True)
                                for x in cands_dict[s].keys()
                            }
                            cands_dict[s] = dict(
                                sorted(
                                    cands_dict[s].items(),
                                    key=lambda item: item[1],
                                    reverse=True,
                                )
                            )
                            top_k_scores = [v for _, v in cands_dict[s].items()][:top_k]
                            unique_scores = list(
                                scores for scores, _ in itertools.groupby(top_k_scores)
                            )
                            if len(unique_scores) >= top_k:
                                dicts_idx.remove(s)
                        if not dicts_idx:
                            break

            if cands_dict[0]:
                for s in range(len(args)):
                    # Calculate noisy-or scores
                    scores = list(
                        map(
                            lambda x: 1 - np.product(1 - np.array(x)),
                            cands_dict[s].values(),
                        )
                    )
                    cands_scores = dict(zip(cands_dict[s].keys(), scores))
                    noisy_or_cands = dict(
                        sorted(cands_scores.items(), key=lambda x: x[1], reverse=True)
                    )
                    all_candidates[s][j] = noisy_or_cands
            else:  # No candidates found by applying rules
                bo = backoff_for(test_query) if do_backoff else {}
                if bo:
                    for s in range(len(args)):
                        all_candidates[s][j] = dict(bo)
                else:
                    no_cands_counter += 1
                    for s in range(len(args)):
                        all_candidates[s][j] = dict()

        else:  # No rules exist for this relation
            bo = backoff_for(test_query) if do_backoff else {}
            if bo:
                for s in range(len(args)):
                    all_candidates[s][j] = dict(bo)
            else:
                no_cands_counter += 1
                for s in range(len(args)):
                    all_candidates[s][j] = dict()

        if not (j - test_queries_idx[0] + 1) % 100:
            it_end = time.time()
            it_time = round(it_end - it_start, 6)
            print(
                "Process {0}: test samples finished: {1}/{2}, {3} sec".format(
                    i, j - test_queries_idx[0] + 1, len(test_queries_idx), it_time
                )
            )
            it_start = time.time()

    return all_candidates, no_cands_counter


start = time.time()
num_queries = len(test_data) // num_processes
output = Parallel(n_jobs=num_processes)(
    delayed(apply_rules)(i, num_queries) for i in range(num_processes)
)
end = time.time()

final_all_candidates = [dict() for _ in range(len(args))]
for s in range(len(args)):
    for i in range(num_processes):
        final_all_candidates[s].update(output[i][0][s])
        output[i][0][s].clear()

final_no_cands_counter = 0
for i in range(num_processes):
    final_no_cands_counter += output[i][1]

total_time = round(end - start, 6)
print("Application finished in {} seconds.".format(total_time))
print("No candidates: ", final_no_cands_counter, " queries")

for s in range(len(args)):
    score_func_str = (
        score_func.__name__ + str(args[s]) + "_sp-" + spatial_mode
        + ("_tc" if type_cond else "") + ("_fm" + str(f_min) if f_min else "")
        + ("_bo" if do_backoff else "")
    )
    score_func_str = score_func_str.replace(" ", "")
    ra.save_candidates(
        rules_file,
        dir_path,
        final_all_candidates[s],
        rule_lengths,
        window,
        score_func_str,
    )
