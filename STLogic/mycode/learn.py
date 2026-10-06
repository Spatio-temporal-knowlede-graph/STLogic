import time
import argparse
import numpy as np
from datetime import datetime
from joblib import Parallel, delayed

from grapher import Grapher
from temporal_walk import Temporal_Walk
from rule_learning import Rule_Learner, rules_statistics
from spatial_context import PositionIndex, build_unit_members


parser = argparse.ArgumentParser()
parser.add_argument("--dataset", "-d", default="", type=str)
parser.add_argument("--rule_lengths", "-l", default="3", type=int, nargs="+")
parser.add_argument("--num_walks", "-n", default="100", type=int)
parser.add_argument("--transition_distr", default="exp", type=str)
parser.add_argument("--num_processes", "-p", default=1, type=int)
parser.add_argument("--seed", "-s", default=None, type=int)
parser.add_argument("--head-relations", default=None, type=str,
                    help="comma-separated relation names to learn rules FOR "
                         "(inverses included automatically); default: all")
parsed = vars(parser.parse_args())

dataset = parsed["dataset"]
rule_lengths = parsed["rule_lengths"]
rule_lengths = [rule_lengths] if (type(rule_lengths) == int) else rule_lengths
num_walks = parsed["num_walks"]
transition_distr = parsed["transition_distr"]
num_processes = parsed["num_processes"]
seed = parsed["seed"]

dataset_dir = "../data/" + dataset + "/"
data = Grapher(dataset_dir)
temporal_walk = Temporal_Walk(data.train_idx, data.inv_relation_id, transition_distr)
unit_members = build_unit_members(data.train_idx, data.relation2id.get("partOf"))
positions = PositionIndex(
    data.loc_by_sub_ts, data.landmark_pos, data.entity_type, unit_members
)
rl = Rule_Learner(
    temporal_walk.edges, data.id2relation, data.inv_relation_id, dataset, positions
)
# Restrict which HEAD relations get rules. The extended dataset adds derived
# spatial relations as body evidence, but they are never queried -- they are kept
# out of test.txt on purpose. Learning rules to predict them spends the walk budget
# on heads nobody asks about: measured, 341 of 403 rules (85%) had a spatial head
# while queries with no candidate at all went from 294 to 5,290. Body atoms are
# unaffected; walks still traverse spatial edges freely.
head_filter = parsed["head_relations"]
if head_filter:
    wanted = set(head_filter.split(","))
    keep = {r for r in temporal_walk.edges
            if data.id2relation[r].lstrip("_") in wanted}
    all_relations = sorted(keep)
    print("head 관계 %d/%d 로 제한: %s"
          % (len(all_relations), len(temporal_walk.edges),
             sorted({data.id2relation[r] for r in all_relations})))
else:
    all_relations = sorted(temporal_walk.edges)  # Learn for all relations


def learn_rules(i, num_relations):
    """
    Learn rules (multiprocessing possible).

    Parameters:
        i (int): process number
        num_relations (int): minimum number of relations for each process

    Returns:
        rl.rules_dict (dict): rules dictionary
    """

    if seed:
        np.random.seed(seed)

    # The last process takes whatever is left. The original rule only did so when
    # the remainder was smaller than one share, so with 8 relations and -p 6
    # (share 1, remainder 2) relations 6 and 7 -- `_Provide-Suppressive-Fire-Loc`
    # and `_move to` -- were assigned to nobody and silently got no rules.
    n = len(all_relations)
    start = min(i * num_relations, n)
    end = n if i == num_processes - 1 else min((i + 1) * num_relations, n)
    relations_idx = range(start, end)

    num_rules = [0]
    for k in relations_idx:
        rel = all_relations[k]
        for length in rule_lengths:
            it_start = time.time()
            for _ in range(num_walks):
                walk_successful, walk = temporal_walk.sample_walk(length + 1, rel)
                if walk_successful:
                    rl.create_rule(walk)
            it_end = time.time()
            it_time = round(it_end - it_start, 6)
            num_rules.append(sum([len(v) for k, v in rl.rules_dict.items()]) // 2)
            num_new_rules = num_rules[-1] - num_rules[-2]
            print(
                "Process {0}: relation {1}/{2}, length {3}: {4} sec, {5} rules".format(
                    i,
                    k - relations_idx[0] + 1,
                    len(relations_idx),
                    length,
                    it_time,
                    num_new_rules,
                )
            )

    return rl.rules_dict


start = time.time()
# max(1, ...) because integer division silently yields 0 when there are fewer
# relations than processes, and then every worker gets an empty range and learns
# nothing. Hit on the embargo split: its shorter train period contains only 6 of
# the 8 relations, so `-p 8` produced zero rules with no error.
num_relations = max(1, len(all_relations) // num_processes)
output = Parallel(n_jobs=num_processes)(
    delayed(learn_rules)(i, num_relations) for i in range(num_processes)
)
end = time.time()

all_rules = output[0]
for i in range(1, num_processes):
    all_rules.update(output[i])

total_time = round(end - start, 6)
print("Learning finished in {} seconds.".format(total_time))

rl.rules_dict = all_rules
rl.sort_rules_dict()
dt = datetime.now()
dt = dt.strftime("%d%m%y%H%M%S")
rl.save_rules(dt, rule_lengths, num_walks, transition_distr, seed)
rl.save_rules_verbalized(dt, rule_lengths, num_walks, transition_distr, seed)
rules_statistics(rl.rules_dict)
