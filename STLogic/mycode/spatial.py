"""Spatial features and the relation-conditioned spatial model (spec §3, §5).

Two features, frozen:

    d    = ‖ P(s, obs) − P(o, obs) ‖
    v_d  = ( d(t₁) − d(t₀) ) / (t₁ − t₀)          δ = t₁ − t₀, per query

Both are functions of distances only, so both are invariant to translation AND
rotation of the scene. `[Δx, Δy]` was measured and rejected: it lowered hard MRR
(0.5310 → 0.4960) and is not rotation-invariant.

`δ` is deliberately not a constant. Measured on VR-Forces, hard MRR falls monotonically
as δ grows — 0.5268 at 10 s, 0.4283 at 300 s, 0.2643 at 600 s — because an old baseline
averages over whatever the subject was doing before. The most recent available interval
is the rule; observation noise sets the floor.

The model learns, per relation, how the TRUE object's pattern differs from the
patterns of candidates that were plausible but wrong:

    F_r(o) = log [ P(φ | y=1, r) / P(φ | y=0, r) ]

This discriminative form is what makes v_d work at all: ranking by −Δd directly is
worse than chance, but contrasting positives against negatives lifts hard MRR from
0.2814 ([d] alone) to 0.5310.

This module never reads a position later than `obs` — data.PositionProvider enforces
that — and never invents one.
"""
import json
import math
import random

VAR_FLOOR = 1e-3            # relative floor; stops a degenerate σ from scoring ±inf


# --------------------------------------------------------------------- features

# Minimum gap, in seconds, between the two observations v_d is differenced over.
#
# Differencing the two LATEST observations (1 s apart at 1 Hz) amplified position
# noise by ~sqrt(2)*sigma / 1 s: with sigma = 5 m that is ~7 m/s, above typical
# approach speeds, and hard MRR fell 0.1417 -> 0.0965. Widening the gap divides the
# noise by the gap. 30 s was selected on the calibration split (ticks 77-89, spatial
# model fitted on 0-76 only) by the mean of noise-free and sigma = 25 m hard MRR,
# a criterion fixed before the results were seen; noise-free accuracy is flat across
# 1-300 s (within 0.003), so robustness is what decides it.
VD_MIN_GAP = 30


def features(provider, subject, obj, at, min_gap=None):
    """(d, v_d) at `at`, or None when the evidence is not there.

    None is returned — never a substitute value — when either endpoint has no
    position, or when the subject has only one observation so no interval exists.

    v_d is differenced against the latest observation at least `min_gap` seconds
    older than the newest one. When no observation is that old -- a sparse track --
    the oldest available one is used, which for a two-observation track is exactly
    the previous behaviour.
    """
    gap = VD_MIN_GAP if min_gap is None else min_gap
    p_s = provider.get_position(subject, at)
    p_o = provider.get_position(obj, at)
    if p_s is None or p_o is None:
        return None

    # A static object contributes no observation times, so the subject's cadence
    # decides. k = gap + 2 covers the gap at 1 Hz; sparser tracks reach further back.
    k = max(2, int(gap) + 2)
    times = sorted(set(provider.recent_times(subject, at, k))
                   | set(provider.recent_times(obj, at, k)), reverse=True)
    if len(times) < 2:
        return None
    t1 = times[0]
    older = [t for t in times[1:] if t <= t1 - gap]
    t0 = older[0] if older else times[-1]
    if t1 <= t0:
        return None

    p_s0 = provider.get_position(subject, t0)
    p_o0 = provider.get_position(obj, t0)
    if p_s0 is None or p_o0 is None:
        return None

    d1 = math.dist(p_s, p_o)
    d0 = math.dist(p_s0, p_o0)
    return d1, (d1 - d0) / (t1 - t0)


def scene_scale(provider, at, sample=20000, rng_seed=0):
    """(L, τ) — the pair the normalisation uses (spec §3.4).

    L = median pairwise distance between groundable entities
    τ = median observation interval

    They exist so a model fitted on one STKG can be applied to another.

    L IS NOT NEUTRAL, despite the affine-invariance of a diagonal-Gaussian log
    ratio: measured on VR-Forces at horizon 60, hard MRR runs 0.1279 / 0.1272 /
    0.1233 / 0.1167 for L = 1002.8 / 1007.6 / 1021.1 / 1057.0 on one fixed seed.
    So L has to be reproducible. `entities_with_position` returns a set, and set
    iteration order over strings is hash-randomised per process, so sampling from
    it unsorted made L -- and every number downstream -- drift run to run by more
    than the whole across-seed spread. Sorting first is what pins it.
    """
    pts = []
    for e in sorted(provider.entities_with_position(at)):
        p = provider.get_position(e, at)
        if p is not None:
            pts.append(p)
    rng = random.Random(rng_seed)
    dists = []
    if len(pts) >= 2:
        for _ in range(sample):
            a, b = rng.choice(pts), rng.choice(pts)
            dists.append(math.dist(a, b))
        dists.sort()
    L = dists[len(dists) // 2] if dists else 1.0
    if L <= 0:
        L = 1.0

    gaps = []
    for e in sorted(provider.entities_with_position(at)):
        ts = provider.recent_times(e, at, 8)
        gaps += [a - b for a, b in zip(ts, ts[1:]) if a > b]
    gaps.sort()
    tau = gaps[len(gaps) // 2] if gaps else 1.0
    return L, tau


def normalise(phi, L, tau):
    """Dimensionless φ. v_d is m/s, so it needs τ as well as L — v_d/L is 1/s."""
    d, v = phi
    return d / L, v * tau / L


# --------------------------------------------------------------------- model

class _Gauss:
    __slots__ = ("mu", "sd", "n")

    def __init__(self, mu, sd, n):
        self.mu, self.sd, self.n = list(mu), list(sd), n

    @staticmethod
    def fit(rows):
        k = len(rows[0])
        n = len(rows)
        mu = [sum(r[j] for r in rows) / n for j in range(k)]
        sd = []
        for j in range(k):
            var = sum((r[j] - mu[j]) ** 2 for r in rows) / n
            sd.append(max(var ** 0.5, VAR_FLOOR * (abs(mu[j]) + 1.0)))
        return _Gauss(mu, sd, n)

    def logpdf(self, phi):
        return sum(-((phi[j] - self.mu[j]) ** 2) / (2 * self.sd[j] ** 2)
                   - math.log(self.sd[j])
                   for j in range(len(self.mu)))


class SpatialModel:
    """Per-relation positive/negative densities and their log ratio."""

    def __init__(self, per_relation, scale=None):
        self._m = per_relation                 # relation -> (pos _Gauss, neg _Gauss)
        self.scale = scale                     # (L, tau) the samples were built with

    def relations(self):
        return sorted(self._m)

    def score(self, relation, phi):
        """F_r(φ), or None when this relation has no model.

        > 0  this pattern is commoner among true objects than among wrong ones
        ≈ 0  space does not separate right from wrong for this relation
        < 0  commoner among the wrong ones
        """
        m = self._m.get(relation)
        if m is None:
            return None
        pos, neg = m
        return pos.logpdf(phi) - neg.logpdf(phi)

    def to_dict(self):
        return {"scale": list(self.scale) if self.scale else None,
                "relations": {r: {"pos": [g[0].mu, g[0].sd, g[0].n],
                                  "neg": [g[1].mu, g[1].sd, g[1].n]}
                              for r, g in self._m.items()}}

    @staticmethod
    def from_dict(doc):
        per = {}
        for r, d in doc["relations"].items():
            per[r] = (_Gauss(*d["pos"]), _Gauss(*d["neg"]))
        scale = tuple(doc["scale"]) if doc.get("scale") else None
        return SpatialModel(per, scale)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False)

    @staticmethod
    def load(path):
        with open(path, encoding="utf-8") as f:
            return SpatialModel.from_dict(json.load(f))


def fit(samples, min_samples=2, scale=None):
    """samples: {relation: {"pos": [φ...], "neg": [φ...]}} -> SpatialModel.

    A relation with fewer than `min_samples` on either side is dropped rather than
    modelled from noise; score() then returns None for it and the query falls back
    to TLogic alone.
    """
    per = {}
    for rel, d in samples.items():
        pos, neg = d.get("pos") or [], d.get("neg") or []
        if len(pos) < min_samples or len(neg) < min_samples:
            continue
        per[rel] = (_Gauss.fit(pos), _Gauss.fit(neg))
    return SpatialModel(per, scale)


# --------------------------------------------------------------------- samples

def build_samples(facts, provider, relation_domain, hard_negatives_fn=None,
                  horizon=0, neg_per_positive=8, rng_seed=0, scale=None):
    """Positive/negative φ per relation, read at obs = t − horizon.

    `hard_negatives_fn(subject, relation, obs) -> set[str]` supplies the temporal
    candidates that were NOT the answer. It is injected rather than imported so this
    module stays independent of TLogic; the caller (apply_stlogic) wires it to rule
    grounding. Without it only relation-compatible negatives are used, and the model
    learns the easier job of rejecting obviously distant entities.

    `relation_domain[r]` is the relation-compatible pool O_vis(r). Sampling negatives
    from it — rather than from every entity — matters: measured, widening the pool to
    all spatially observable entities collapsed MRR from 0.4960 to 0.0311.
    """
    rng = random.Random(rng_seed)
    out = {}
    for sub, rel, obj, t in facts:
        obs = t - horizon
        phi_pos = features(provider, sub, obj, obs)
        if phi_pos is None:
            continue                            # no spatial evidence -> no sample
        if scale:
            phi_pos = normalise(phi_pos, *scale)

        negatives = set()
        if hard_negatives_fn is not None:
            negatives |= {c for c in hard_negatives_fn(sub, rel, obs) if c != obj}
        # sorted: relation_domain values are sets of strings, whose iteration order is
        # hash-randomised per process. Sampling from them unsorted made the negatives --
        # and so the fitted model -- differ run to run (HARD MRR drifted by ~0.001 on
        # identical settings), the same failure scene_scale had.
        pool = sorted(c for c in relation_domain.get(rel, ()) if c != obj)
        if pool:
            k = min(len(pool), max(0, neg_per_positive - len(negatives)))
            negatives |= set(rng.sample(pool, k))

        neg_phi = []
        for c in negatives:
            phi = features(provider, sub, c, obs)
            if phi is None:
                continue
            neg_phi.append(normalise(phi, *scale) if scale else phi)
        if not neg_phi:
            continue

        bucket = out.setdefault(rel, {"pos": [], "neg": []})
        bucket["pos"].append(phi_pos)
        bucket["neg"].extend(neg_phi)
    return out


INVERSE_PREFIX = "_"


def inverse_relation(rel):
    """TLogic's naming: the inverse of `r` is `_r`, and of `_r` is `r`."""
    return rel[1:] if rel.startswith(INVERSE_PREFIX) else INVERSE_PREFIX + rel


def with_inverses(facts):
    """Forward facts plus their inverses, so every stage sees both directions.

    `relation_domain()` and `build_samples()` are generic over (sub, rel, obj, t),
    so feeding them (obj, _r, sub, t) gives the inverse relation its own candidate
    pool and its own fitted model with no further change.

    Without this the spatial branch is silently FORWARD-ONLY: the fact stream comes
    from the observation CSV, which only ever names forward relations, so `_move to`
    has no key at all. `spatial_scores()` then returns {} and `model.score("_move to")`
    returns None, i.e. no injection and no evidence. Measured before this existed:
    inverse HARD MRR 0.0029 -- exactly the persistence floor -- for every fusion
    variant tried, across half of the 10,340 queries.

    The distance feature is symmetric (d(s,o) = d(o,s)) but the PROBLEM is not: the
    forward pool is ~15 landmarks while the inverse pool is ~323 units, so the two
    directions get separately fitted models rather than a shared one.
    """
    out = []
    for sub, rel, obj, t in facts:
        out.append((sub, rel, obj, t))
        out.append((obj, inverse_relation(rel), sub, t))
    return out


def relation_domain(facts, before=None):
    """O_vis(r, obs) = objects seen with relation r strictly before `before`."""
    dom = {}
    for sub, rel, obj, t in facts:
        if before is not None and t >= before:
            continue
        dom.setdefault(rel, set()).add(obj)
    return dom
