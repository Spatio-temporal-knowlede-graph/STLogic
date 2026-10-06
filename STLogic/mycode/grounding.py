"""Thin reuse layer over TLogic rule grounding.

Two callers need the same thing — "which objects do the temporal rules propose for
(s, r, ?) given only what was visible at obs?":

  * training, to build hard negatives (C_T minus the true object) for spatial.py
  * inference, to build C_T itself

Nothing here changes how rules are learned or applied. It calls
`rule_application`'s existing functions and caches the per-timestamp edge window,
exactly as apply.py does, so `RuleLearning_STLogic = RuleLearning_TLogic` holds.

Ids vs names: rules and the Grapher speak integer ids; data.PositionProvider speaks
entity names. `NameGrounder` is the adapter, so spatial.py never imports TLogic.
"""
import datetime as dt

import rule_application as ra
from temporal_walk import store_edges


class TemporalGrounder:
    """Candidate object ids proposed by the temporal rules, in Grapher id space."""

    def __init__(self, grapher, rules_dict, rule_lengths=(1, 2, 3), window=3,
                 min_conf=0.01, min_body_supp=2):
        self.data = grapher
        self.window = window
        self.learn_edges = store_edges(grapher.train_idx)
        self.rules = ra.filter_rules(
            {int(k): v for k, v in rules_dict.items()},
            min_conf=min_conf, min_body_supp=min_body_supp,
            rule_lengths=list(rule_lengths))
        self._edges_ts = None
        self._edges = None

    def _window_edges(self, obs_ts):
        if obs_ts != self._edges_ts:
            self._edges = ra.get_window_edges(
                self.data.all_idx, obs_ts, self.learn_edges, self.window)
            self._edges_ts = obs_ts
        return self._edges

    def candidates(self, sub_id, rel_id, obs_ts):
        """set[int] — objects any rule for `rel_id` grounds to, using edges < obs_ts."""
        rules = self.rules.get(int(rel_id))
        if not rules:
            return set()
        edges = self._window_edges(int(obs_ts))
        out = set()
        for rule in rules:
            walk_edges = ra.match_body_relations(rule, edges, int(sub_id))
            if 0 in [len(x) for x in walk_edges]:
                continue
            walks = ra.get_walks(rule, walk_edges)
            if rule["var_constraints"]:
                walks = ra.check_var_constraints(rule["var_constraints"], walks)
            if walks.empty:
                continue
            out.update(int(x) for x in walks["entity_" + str(len(rule["body_rels"]))])
        return out


class NameGrounder:
    """`(subject_name, relation_name, obs_epoch) -> set[object_name]`.

    Drop-in for spatial.build_samples(hard_negatives_fn=...).
    """

    def __init__(self, grounder, grapher):
        self.g = grounder
        self.entity2id = grapher.entity2id
        self.id2entity = grapher.id2entity
        self.relation2id = grapher.relation2id
        # ts token -> id, and the epoch each id stands for
        self.ts2id = grapher.ts2id
        self.epoch2tsid = {}
        for token, tid in grapher.ts2id.items():
            try:
                self.epoch2tsid[int(dt.datetime.fromisoformat(token).timestamp())] = tid
            except ValueError:
                pass                       # non-ISO token (e.g. hill395 "sector@n")

    def ts_id_at_or_before(self, epoch):
        """Largest ts id whose epoch is <= `epoch`, or None."""
        best = None
        for e, tid in self.epoch2tsid.items():
            if e <= epoch and (best is None or e > best[0]):
                best = (e, tid)
        return best[1] if best else None

    def __call__(self, subject, relation, obs_epoch):
        sid = self.entity2id.get(subject)
        rid = self.relation2id.get(relation)
        tid = self.ts_id_at_or_before(obs_epoch)
        if sid is None or rid is None or tid is None:
            return set()
        return {self.id2entity[c] for c in self.g.candidates(sid, rid, tid)
                if c in self.id2entity}
