"""Spatial candidate augmentation and spatial-temporal reranking (spec §7, §9).

    C_S = TopK_{ o ∈ O_vis(r,obs),  F_r(o) > 0 }  F_r(o)
    C   = C_T ∪ C_S
    E_S = 2·Norm(F_r) − 1                          0 when no spatial evidence
    S   = (1−λ)·S_T(o) + λ·E_S(o)                  convex fusion

`C_T` and `S_T` are read from apply.py's own candidate file rather than recomputed,
so the temporal half is byte-identical to the baseline being compared against and
`RuleLearning_STLogic = RuleLearning_TLogic` is true by construction.

Graceful degradation: a query whose subject has no position, or whose relation has
no spatial model, or where no candidate clears F_r > 0, gets C_S = ∅ and therefore
exactly the baseline ranking.

Usage:
    python apply_stlogic.py -d <dataset> -c <baseline candidates.json> \
        -m <spatial_model.json> --horizon <ticks> [--topk 5] [--lam 0.3] \
        [--test_data test|valid]
"""
import argparse
import datetime as dt
import json
import math
import os

from grapher import Grapher
from data import load_vrforces
import spatial


def sigmoid(z):
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


class Augmenter:
    """Adds spatial candidates to a baseline ranking, in Grapher id space."""

    def __init__(self, grapher, stkg, model, horizon, topk, lam, norm_stats=None,
                 horizon_seconds=0):
        self.g = grapher
        self.stkg = stkg
        self.model = model
        self.horizon = horizon
        # Exact-seconds cutoff. Tick subtraction only equals the intended gap on a
        # uniform grid; VR-Forces has four 20 s gaps, so `horizon=60` actually
        # reached 610-630 s back. The spatial side is already epoch-based, so this
        # only changes how the epoch is derived.
        self.horizon_seconds = horizon_seconds
        self.topk = topk
        self.lam = lam
        self.norm = norm_stats or {}
        self.L, self.tau = model.scale if model.scale else (1.0, 1.0)

        self.tsid2epoch = {}
        for token, tid in grapher.ts2id.items():
            try:
                self.tsid2epoch[tid] = int(dt.datetime.fromisoformat(token).timestamp())
            except ValueError:
                pass
        # O_vis(r, obs) grows monotonically with obs, and obs only ever lands on a
        # dataset tick. Precompute the prefix union at each tick once -- scanning the
        # fact timeline per query is what made the grid search intractable.
        self._epochs = sorted(set(self.tsid2epoch.values()))
        by_rel = {}
        # Inverse relations must be in the pool too: the CSV names only forward
        # relations, so without this `_move to` has no key and half the query set
        # gets no spatial candidates at all.
        for sub, rel, obj, t in spatial.with_inverses(stkg.get_facts()):
            by_rel.setdefault(rel, []).append((t, obj))
        self._domain = {}
        for rel, timeline in by_rel.items():
            timeline.sort()
            seen, j, per_tick = set(), 0, {}
            for e in self._epochs:
                while j < len(timeline) and timeline[j][0] < e:
                    seen.add(timeline[j][1])
                    j += 1
                per_tick[e] = frozenset(seen)
            self._domain[rel] = per_tick
        self._score_cache = {}
        self._pair_cache = {}

    def observation_epoch(self, ts):
        """Real time a query at tick `ts` may see up to (inclusive)."""
        if self.horizon_seconds:
            here = self.tsid2epoch.get(int(ts))
            return None if here is None else here - self.horizon_seconds
        return self.tsid2epoch.get(int(ts) - self.horizon)

    def relation_domain(self, relation, obs_epoch):
        per_tick = self._domain.get(relation)
        if not per_tick:
            return frozenset()
        hit = per_tick.get(obs_epoch)
        if hit is not None:
            return hit
        best = frozenset()
        for e in self._epochs:                 # obs off-grid: nearest tick at or below
            if e > obs_epoch:
                break
            best = per_tick[e]
        return best

    def spatial_scores(self, sub_name, rel_name, obs_epoch):
        """{object_name: F_r} over the relation-compatible pool, F_r > 0 only.

        Cached on (subject, relation, obs): it depends on neither K nor λ, so a
        hyperparameter sweep pays for it once.
        """
        key = (sub_name, rel_name, obs_epoch)
        hit = self._score_cache.get(key)
        if hit is not None:
            return hit
        out = self._spatial_scores(sub_name, rel_name, obs_epoch)
        self._score_cache[key] = out
        return out

    def _spatial_scores(self, sub_name, rel_name, obs_epoch):
        if self.stkg.get_position(sub_name, obs_epoch) is None:
            return {}                                   # no subject position
        out = {}
        for obj in self.relation_domain(rel_name, obs_epoch):
            if obj == sub_name:
                continue
            phi = spatial.features(self.stkg.positions, sub_name, obj, obs_epoch)
            if phi is None:
                continue                                # no candidate position
            f = self.model.score(rel_name, spatial.normalise(phi, self.L, self.tau))
            if f is not None and f > 0.0:
                out[obj] = f
        return out

    def normalised(self, rel_name, f):
        """Norm(F_r) -> [0,1] using validation statistics (spec §9)."""
        mu, sd = self.norm.get(rel_name, (0.0, 1.0))
        return sigmoid((f - mu) / (sd if sd > 1e-9 else 1.0))

    def evidence(self, rel_name, f):
        """E_S = 2·Norm(F_r) − 1 ∈ [−1, 1]; exactly 0 when there is no evidence.

        Centering matters here: 80.2% of temporal candidates get no spatial evidence
        at all (measured on valid), so a "neutral" of 0.5 would inject λ/2 into the
        score of four candidates in five. At 0 they contribute nothing and the
        temporal score passes through untouched.
        """
        return 0.0 if f is None else 2.0 * self.normalised(rel_name, f) - 1.0

    def _f_for(self, sub_name, rel_name, obs_epoch, obj_name):
        """F_r for one candidate, which may sit outside O_vis (a C_T candidate)."""
        key = (sub_name, rel_name, obs_epoch, obj_name)
        if key in self._pair_cache:
            return self._pair_cache[key]
        phi = spatial.features(self.stkg.positions, sub_name, obj_name, obs_epoch)
        f = None
        if phi is not None:
            f = self.model.score(rel_name, spatial.normalise(phi, self.L, self.tau))
        self._pair_cache[key] = f
        return f

    def augment(self, query, baseline):
        """(final scores sorted desc, C_S ids) for one query.

        E_S is computed for EVERY candidate in C_T ∪ C_S. Scoring only the injected
        ones leaves every temporal candidate at E_S = 0, which makes λ unable to
        reorder them -- reranking would be structurally impossible.
        """
        def as_sorted(d):
            return dict(sorted(d.items(), key=lambda kv: -kv[1]))

        sub, rel, _, ts = (int(x) for x in query)
        obs_epoch = self.observation_epoch(ts)
        sub_name = self.g.id2entity.get(sub)
        rel_name = self.g.id2relation.get(rel)
        if obs_epoch is None or sub_name is None or rel_name is None:
            return as_sorted(dict(baseline)), set()

        raw = self.spatial_scores(sub_name, rel_name, obs_epoch)
        pairs = {}
        for oid, s_t in baseline.items():                       # C_T
            name = self.g.id2entity.get(int(oid))
            f = self._f_for(sub_name, rel_name, obs_epoch, name) if name else None
            pairs[int(oid)] = (s_t, self.evidence(rel_name, f))

        c_s = set()
        for name, f in sorted(raw.items(), key=lambda kv: -kv[1])[:self.topk]:
            oid = self.g.entity2id.get(name)
            if oid is None:
                continue
            c_s.add(oid)
            if oid not in pairs:                                # C_S \ C_T
                pairs[oid] = (0.0, self.evidence(rel_name, f))

        lam = self.lam
        final = {o: (1.0 - lam) * s_t + lam * e_s for o, (s_t, e_s) in pairs.items()}
        return as_sorted(final), c_s


def calibration_rows(grapher, dataset_dir):
    """Rows reserved for calibrating Norm() and the expiry gate.

    Under the embargo protocol valid.txt is the embargo block -- facts the model is
    forbidden to fit on -- so calibration comes from the tail of train, the range
    split_meta.json records as `calib_ticks`. Without split_meta (the pre-embargo
    datasets) this falls back to valid_idx, which is what those datasets meant it
    to be.
    """
    path = os.path.join(dataset_dir, "split_meta.json")
    if not os.path.exists(path):
        return grapher.valid_idx
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    # TLogic-style split: valid.txt is the validation set proper and the gap lives in
    # embargo.txt, so calibration rows are simply the validation rows.
    if meta.get("mode") == "tvt":
        return grapher.valid_idx
    lo, hi = meta["calib_ticks"]
    rows = grapher.train_idx
    keep = (rows[:, 3] >= lo) * (rows[:, 3] <= hi)
    return rows[keep]


def fit_norm_stats(augmenter, grapher, split_idx, limit=2000):
    """Per-relation mean/std of F_r over the given rows, for Norm().

    The caller chooses the rows. Under the embargo protocol valid.txt holds the
    embargo block -- data the model must not fit on -- so calibration has to come
    from the tail of train instead; see split_meta.json's `calib_ticks`.
    """
    acc = {}
    for i in range(min(len(split_idx), limit)):
        sub, rel, _, ts = (int(x) for x in split_idx[i])
        obs_epoch = augmenter.observation_epoch(ts)
        if obs_epoch is None:
            continue
        sn = grapher.id2entity.get(sub)
        rn = grapher.id2relation.get(rel)
        if sn is None or rn is None:
            continue
        for f in augmenter.spatial_scores(sn, rn, obs_epoch).values():
            acc.setdefault(rn, []).append(f)
    out = {}
    for rel, vals in acc.items():
        n = len(vals)
        mu = sum(vals) / n
        sd = (sum((v - mu) ** 2 for v in vals) / n) ** 0.5
        out[rel] = (mu, sd)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", "-d", required=True)
    ap.add_argument("--candidates", "-c", required=True, help="apply.py 산출 baseline")
    ap.add_argument("--model", "-m", required=True)
    ap.add_argument("--source", required=True, help="관측 CSV (쉼표 구분)")
    ap.add_argument("--registry", default=None)
    ap.add_argument("--horizon", type=int, default=0, help="틱 단위")
    ap.add_argument("--horizon-seconds", type=int, default=0,
                    help="실제 초 단위 cutoff. 설정 시 --horizon 보다 우선한다.")
    ap.add_argument("--topk", "-K", type=int, default=5)
    ap.add_argument("--lam", type=float, default=0.3)
    ap.add_argument("--test_data", default="test", choices=("test", "valid"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    g = Grapher("../data/%s/" % a.dataset)
    stkg = load_vrforces(a.source.split(","), registry_path=a.registry)
    model = spatial.SpatialModel.load(a.model)
    base = json.load(open("../output/%s/%s" % (a.dataset, a.candidates), encoding="utf-8"))
    base = {int(k): {int(c): v for c, v in d.items()} for k, d in base.items()}

    aug = Augmenter(g, stkg, model, a.horizon, a.topk, a.lam,
                    horizon_seconds=a.horizon_seconds)
    aug.norm = fit_norm_stats(aug, g, calibration_rows(g, "../data/%s" % a.dataset))          # valid statistics only
    print("Norm(F_r) 통계 (valid):",
          {r: (round(m, 2), round(s, 2)) for r, (m, s) in aug.norm.items()})

    data = g.test_idx if a.test_data == "test" else g.valid_idx
    out, cs_sizes, touched = {}, [], 0
    for i in range(len(data)):
        final, c_s = aug.augment(data[i], base.get(i, {}))
        out[i] = {int(k): float(v) for k, v in final.items()}
        cs_sizes.append(len(c_s))
        if c_s:
            touched += 1
    print("쿼리 %d · C_S 생성 %d (%.1f%%) · 평균 |C_S| %.2f"
          % (len(data), touched, 100 * touched / len(data),
             sum(cs_sizes) / max(len(cs_sizes), 1)))

    path = a.out or ("../output/%s/%s" % (
        a.dataset, a.candidates.replace(".json", "_stl_K%d_l%g.json" % (a.topk, a.lam))))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print("저장:", os.path.basename(path))


if __name__ == "__main__":
    main()
