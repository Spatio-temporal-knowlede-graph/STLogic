"""STLogic spatial context model.

Frame-invariant relative spatial features of a (head, tail) pair over time —
distance d, approach rate Δd, and relative bearing cos(β) — all computed from
entity positions over time (velocity is estimated by finite difference, so only
positions + timestamps are required). Each temporal rule gets a per-feature
Gaussian (μ, σ) fitted over its grounding instances; at inference a candidate's
features are scored against that Gaussian (spatial fit), and the learned σ
automatically gates how much space matters for that rule.

Absolute position is deliberately NOT used: it is frame-dependent and does not
transfer across scenes. See docs/STLogic_연구내용.md.
"""
import numpy as np

FEATURE_KEYS = ("d", "dd", "cosb")

# Feature subsets for the ablation ladder (used by apply.py --spatial).
FEATURE_SETS = {
    "off": (),
    "dist": ("d",),
    "dist_dd": ("d", "dd"),
    "dist_dd_bearing": ("d", "dd", "cosb"),
}


class PositionIndex:
    """Entity/landmark positions over time, built from a Grapher.

    - moving entities: trajectory from the per-row location column
      (grapher.loc_by_sub_ts, keyed by (subject_id, ts_id))
    - landmarks: static coordinate from landmarks.tsv (grapher.landmark_pos)
    """

    def __init__(self, loc_by_sub_ts, landmark_pos, entity_type=None,
                 unit_members=None):
        self.landmark_pos = {int(k): np.asarray(v, dtype=np.float64)
                             for k, v in landmark_pos.items()}
        self.entity_type = {int(k): v for k, v in (entity_type or {}).items()}
        # ① coverage: units get a (time-varying) position = centroid of their member
        # entities, so organizational relations (partOf/supports/reinforces) become
        # spatial. Members come from partOf edges.
        self.unit_members = {int(u): [int(m) for m in ms]
                             for u, ms in (unit_members or {}).items()}
        self._unit_cache = {}
        traj = {}
        for (ent, ts), pos in loc_by_sub_ts.items():
            traj.setdefault(int(ent), []).append((int(ts), pos))
        self.traj = {}
        for ent, lst in traj.items():
            lst.sort()
            ts_arr = np.array([t for t, _ in lst], dtype=np.int64)
            pos_arr = np.array([p for _, p in lst], dtype=np.float64)
            self.traj[ent] = (ts_arr, pos_arr)

    def _idx_at(self, ts_arr, ts):
        """Index of the observation at-or-before ts (or 0 if all are later)."""
        idx = int(np.searchsorted(ts_arr, ts, side="right")) - 1
        return idx if idx >= 0 else None

    def type_of(self, ent_id):
        """Entity type string (e.g. 'ROK_Tank') or None."""
        return self.entity_type.get(int(ent_id))

    def _unit_centroid(self, unit_id, ts_id, exclude=None, _depth=0):
        """Centroid of a unit's members at-or-before ts_id (cached, recursive).

        Members may themselves be units (a regiment's members are battalions), so
        recurse into sub-unit centroids. `exclude` drops one member id (leave-one-out
        to avoid leaking the very endpoint being predicted). partOf is a shallow DAG;
        _depth guards against pathological cycles.
        """
        key = (unit_id, ts_id, exclude)
        if key in self._unit_cache:
            return self._unit_cache[key]
        if _depth > 8:
            self._unit_cache[key] = None
            return None
        ps = []
        for m in self.unit_members.get(unit_id, ()):
            if m == exclude:
                continue
            p = (self._unit_centroid(m, ts_id, exclude, _depth + 1)
                 if self._is_unit(m) else self._entity_pos(m, ts_id))
            if p is not None:
                ps.append(p)
        c = np.mean(ps, axis=0) if ps else None
        self._unit_cache[key] = c
        return c

    def _entity_pos(self, ent_id, ts_id):
        """Position of a landmark (static) or a moving entity (at-or-before ts); None."""
        if ent_id in self.landmark_pos:
            return self.landmark_pos[ent_id]
        tr = self.traj.get(ent_id)
        if tr is None:
            return None
        ts_arr, pos_arr = tr
        i = self._idx_at(ts_arr, ts_id)
        return pos_arr[i] if i is not None else None

    def _is_unit(self, ent_id):
        return (ent_id in self.unit_members
                and ent_id not in self.traj and ent_id not in self.landmark_pos)

    def pos(self, ent_id, ts_id, exclude=None):
        """Position at-or-before ts_id: landmark (static) / entity (traj) / unit (centroid).

        `exclude` (an entity id) is left out of a unit centroid — leave-one-out so a
        query endpoint does not leak into the position of the unit it is linked to.
        """
        ent_id, ts_id = int(ent_id), int(ts_id)
        if self._is_unit(ent_id):
            return self._unit_centroid(ent_id, ts_id,
                                       None if exclude is None else int(exclude))
        return self._entity_pos(ent_id, ts_id)

    def pos_now_prev(self, ent_id, ts_id):
        """(pos_now, pos_prev, ts_prev): the two most recent positions <= ts_id.

        Landmarks (static): pos_prev == pos_now. Units: only pos_now (centroid), so
        distance is defined but Δd/bearing are not. Returns Nones where undefined.
        """
        ent_id, ts_id = int(ent_id), int(ts_id)
        if ent_id in self.landmark_pos:
            p = self.landmark_pos[ent_id]
            return p, p, ts_id
        if self._is_unit(ent_id):
            return self._unit_centroid(ent_id, ts_id), None, None
        tr = self.traj.get(ent_id)
        if tr is None:
            return None, None, None
        ts_arr, pos_arr = tr
        i = self._idx_at(ts_arr, ts_id)
        if i is None:
            return None, None, None
        pos_now = pos_arr[i]
        if i >= 1:
            return pos_now, pos_arr[i - 1], int(ts_arr[i - 1])
        return pos_now, None, None


def features(pi, head, tail, t_ref):
    """Frame-invariant relative features of (head -> tail) at reference time t_ref.

    Returns {"d", "dd", "cosb"} with None where a component is undefined
    (missing coordinate, stationary subject, etc.).
    """
    feat = {"d": None, "dd": None, "cosb": None}
    ph_now, ph_prev, ts_prev = pi.pos_now_prev(head, t_ref)
    pt_now = pi.pos(tail, t_ref)
    if ph_now is None or pt_now is None:
        return feat

    feat["d"] = float(np.linalg.norm(ph_now - pt_now))

    if ph_prev is not None:
        pt_prev = pi.pos(tail, ts_prev)
        if pt_prev is not None:
            d_prev = float(np.linalg.norm(ph_prev - pt_prev))
            feat["dd"] = feat["d"] - d_prev
        v = ph_now - ph_prev          # head velocity (finite difference)
        u = pt_now - ph_now           # head -> tail direction
        nv = float(np.linalg.norm(v))
        nu = float(np.linalg.norm(u))
        if nv > 1e-6 and nu > 1e-6:
            feat["cosb"] = float(np.dot(v, u) / (nv * nu))
    return feat


def fit_gaussian(feature_dicts):
    """Per-feature {mu, sigma, n} over grounding instances (features with >=2 samples)."""
    out = {}
    for k in FEATURE_KEYS:
        vals = [f[k] for f in feature_dicts if f.get(k) is not None]
        if len(vals) >= 2:
            arr = np.asarray(vals, dtype=np.float64)
            out[k] = {"mu": float(arr.mean()), "sigma": float(arr.std()), "n": len(vals)}
    return out


def _fit_score(x, mu, sigma):
    # Relative sigma floor prevents degenerate over-confidence when a feature is
    # near-constant; large sigma (unstructured relation) -> flat fit -> auto-gate off.
    s = max(sigma, 1e-3 * (abs(mu) + 1.0))
    return float(np.exp(-((x - mu) ** 2) / (2.0 * s * s)))


def effective_spatial(rule, cand_type, min_n=10):
    """Per-candidate spatial params: prefer the type-conditioned Gaussian (② σ
    tightening) when it has enough grounding samples, else fall back per-feature to
    the rule's pooled Gaussian. cand_type None or type_cond off -> pooled only.
    """
    pooled = rule.get("spatial") or {}
    if cand_type is None:
        return pooled
    by_type = (rule.get("spatial_by_type") or {}).get(cand_type, {})
    eff = {}
    for k in FEATURE_KEYS:
        t = by_type.get(k)
        if t is not None and t["n"] >= min_n:
            eff[k] = t
        elif k in pooled:
            eff[k] = pooled[k]
    return eff


def spatial_fit(feat, rule_spatial, feature_set, f_min=0.0):
    """Combine per-feature Gaussian fits into S_spatial in [f_min, 1].

    Mean over the selected features that are both defined for the candidate and
    modelled for the rule. If none apply, returns 1.0 (TLogic fallback).
    f_min clamps the result from below (③ tie-gating): a larger f_min keeps spatial
    a gentle nudge that cannot overturn a confidently-scored candidate.
    """
    if not rule_spatial or not feature_set:
        return 1.0
    scores = []
    for k in feature_set:
        rs = rule_spatial.get(k)
        x = feat.get(k)
        if rs is not None and x is not None:
            scores.append(_fit_score(x, rs["mu"], rs["sigma"]))
    if not scores:
        return 1.0
    s = float(np.mean(scores))
    return s if s >= f_min else f_min


def build_unit_members(edges_idx, partof_rel_id):
    """{unit_id: [member_entity_ids]} from forward partOf edges (member, partOf, unit)."""
    members = {}
    if partof_rel_id is None:
        return members
    for x in edges_idx[edges_idx[:, 1] == partof_rel_id]:
        members.setdefault(int(x[2]), set()).add(int(x[0]))
    return {u: list(ms) for u, ms in members.items()}


# ---- ① spatial backoff candidate generation (for no-rule-candidate queries) ----

def fit_relation_spatial(positions, edges_idx, sample_cap=5000):
    """Per-relation Gaussian over (d, Δd, cosb) of training edges (h, r, o, t).

    Aggregates far more groundings than a single rule, giving a stable spatial
    signature for a relation. Used to rank candidates when no temporal rule fires.
    """
    out = {}
    for r in np.unique(edges_idx[:, 1]):
        rows = edges_idx[edges_idx[:, 1] == r]
        if len(rows) > sample_cap:            # deterministic thinning
            rows = rows[:: (len(rows) // sample_cap) + 1]
        feats = [features(positions, int(x[0]), int(x[2]), int(x[3])) for x in rows]
        out[int(r)] = fit_gaussian(feats)
    return out


def backoff_candidates(positions, rel_spatial, feature_set, sub, rel, ts,
                       cand_pool, topk=20):
    """Rank same-scene candidates for query (sub, rel, ?, ts) by fit to the
    relation's distance signature. Returns {cand_id: score} (top-k), or {} if the
    relation has no distance model.

    Distance only (units have no velocity, so no Δd/bearing). Leave-one-out: when an
    endpoint is a unit, the other endpoint is excluded from its centroid so the
    predicted link cannot leak into the position estimate.
    """
    rs = rel_spatial.get(int(rel))
    if not rs or "d" not in rs:
        return {}
    dmodel = rs["d"]
    scored = []
    for c in cand_pool:
        if c == sub:
            continue
        p_sub = positions.pos(sub, ts, exclude=c)   # leave-one-out on unit centroids
        p_cand = positions.pos(c, ts, exclude=sub)
        if p_sub is None or p_cand is None:
            continue
        d = float(np.linalg.norm(p_sub - p_cand))
        scored.append((int(c), _fit_score(d, dmodel["mu"], dmodel["sigma"])))
    scored.sort(key=lambda x: x[1], reverse=True)
    return {c: float(s) for c, s in scored[:topk]}
