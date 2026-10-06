"""Tests for mycode/spatial.py — [d, v_d] features and the relation spatial model.

Pins down the frozen core (spec §3, §5):
  φ = [d̃, ṽ_d]          δ chosen per query, not globally
  F_r(o) = log P(φ|y=1,r) / P(φ|y=0,r)
  no spatial evidence -> None, never a fabricated score
"""
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mycode"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

from data import load_vrforces  # noqa: E402
import spatial  # noqa: E402

HEADER = ("subject,predicate,object,timestamp,latitude,longitude,"
          "obj_lat,obj_lon,source,Heading,CurrentSpeed,EntityType,Force\r\n")


def row(sub, pred, obj, ts, lat, lon):
    return ("{},{},{},{},{},{},,,GT,0,0,1:1:1:1:0:0:0,1\r\n"
            .format(sub, pred, obj, ts, lat, lon))


def ts(s):
    import datetime as dt
    return int(dt.datetime.fromisoformat("2026-09-11T" + s).timestamp())


def scene(rows, locations=None):
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "gt.csv")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(HEADER)
        for r in rows:
            f.write(r)
    reg = None
    if locations:
        reg = os.path.join(tmp, "l.json")
        with open(reg, "w", encoding="utf-8") as f:
            json.dump({"locations": locations}, f, ensure_ascii=False)
    return load_vrforces([p], registry_path=reg)


# A unit driving north toward LOC_T, which sits further north.
APPROACH = [
    row("U1", "move to", "LOC_T", "2026-09-11T13:00:00", "21.3800", "-157.7500"),
    row("U1", "move to", "LOC_T", "2026-09-11T13:00:10", "21.3810", "-157.7500"),
    row("U1", "move to", "LOC_T", "2026-09-11T13:00:20", "21.3820", "-157.7500"),
]
LOCS = {"LOC_T": {"lat": 21.3900, "lon": -157.7500},
        "LOC_F": {"lat": 21.3700, "lon": -157.7500}}


# --------------------------------------------------------------- features

def test_distance_is_metres():
    g = scene(APPROACH, LOCS)
    phi = spatial.features(g.positions, "U1", "LOC_T", ts("13:00:20"))
    assert phi is not None
    d, v = phi
    assert 800 < d < 950, d          # ~0.008 deg of latitude


def test_approach_is_negative_recede_is_positive():
    g = scene(APPROACH, LOCS)
    toward = spatial.features(g.positions, "U1", "LOC_T", ts("13:00:20"))
    away = spatial.features(g.positions, "U1", "LOC_F", ts("13:00:20"))
    assert toward[1] < 0, "closing on LOC_T"
    assert away[1] > 0, "opening from LOC_F"


def test_delta_is_the_latest_available_interval():
    """Two observations 10 s apart -> δ = 10 s, so |v_d| ≈ distance moved / 10."""
    g = scene(APPROACH, LOCS)
    _, v = spatial.features(g.positions, "U1", "LOC_T", ts("13:00:20"))
    step = math.dist(g.get_position("U1", ts("13:00:10")),
                     g.get_position("U1", ts("13:00:20")))
    assert abs(abs(v) - step / 10.0) < 1e-6


def test_delta_uses_a_gap_not_a_constant():
    """A 60 s gap must divide by 60, not by the earlier 10 s cadence."""
    rows = APPROACH + [row("U1", "move to", "LOC_T", "2026-09-11T13:01:20",
                           "21.3830", "-157.7500")]
    g = scene(rows, LOCS)
    _, v = spatial.features(g.positions, "U1", "LOC_T", ts("13:01:20"))
    step = math.dist(g.get_position("U1", ts("13:00:20")),
                     g.get_position("U1", ts("13:01:20")))
    assert abs(abs(v) - step / 60.0) < 1e-6


def test_single_observation_has_no_velocity():
    one = [row("U1", "move to", "LOC_T", "2026-09-11T13:00:00", "21.38", "-157.75")]
    g = scene(one, LOCS)
    assert spatial.features(g.positions, "U1", "LOC_T", ts("13:00:00")) is None


def test_missing_position_yields_none():
    g = scene(APPROACH, LOCS)
    assert spatial.features(g.positions, "GHOST", "LOC_T", ts("13:00:20")) is None
    assert spatial.features(g.positions, "U1", "GHOST", ts("13:00:20")) is None


def test_features_never_read_the_future():
    """Features at t must not change when later observations are added.

    Not bit-exact: the ENU origin is the centroid of everything loaded, so a longer
    file shifts the tangent plane and the metres-per-degree coefficients with it.
    Distances are translation-invariant so the values agree to ~0.04 mm over a km —
    projection noise, not leakage.
    """
    g = scene(APPROACH, LOCS)
    g_short = scene(APPROACH[:2], LOCS)
    a = spatial.features(g.positions, "U1", "LOC_T", ts("13:00:10"))
    b = spatial.features(g_short.positions, "U1", "LOC_T", ts("13:00:10"))
    assert abs(a[0] - b[0]) < 1e-3, (a, b)
    assert abs(a[1] - b[1]) < 1e-5, (a, b)


# --------------------------------------------------------------- scale

def test_scale_is_pairwise_median_and_tau_is_median_interval():
    g = scene(APPROACH, LOCS)
    L, tau = spatial.scene_scale(g.positions, ts("13:00:20"))
    assert L > 0 and tau == 10


def test_normalisation_is_dimensionless():
    g = scene(APPROACH, LOCS)
    L, tau = spatial.scene_scale(g.positions, ts("13:00:20"))
    d, v = spatial.features(g.positions, "U1", "LOC_T", ts("13:00:20"))
    dn, vn = spatial.normalise((d, v), L, tau)
    assert abs(dn - d / L) < 1e-12
    assert abs(vn - v * tau / L) < 1e-12


# --------------------------------------------------------------- model

def _samples():
    """Positives cluster near (0.2, -0.5); negatives near (0.9, +0.4)."""
    pos = [(0.20, -0.50), (0.22, -0.48), (0.18, -0.52), (0.21, -0.49)]
    neg = [(0.90, 0.40), (0.92, 0.38), (0.88, 0.42), (0.91, 0.39)]
    return {"r": {"pos": pos, "neg": neg}}


def test_score_is_positive_for_positive_like_patterns():
    m = spatial.fit(_samples())
    assert m.score("r", (0.20, -0.50)) > 0
    assert m.score("r", (0.90, 0.40)) < 0


def test_score_is_none_for_unknown_relation():
    m = spatial.fit(_samples())
    assert m.score("other", (0.2, -0.5)) is None


def test_relation_with_identical_distributions_is_uninformative():
    """P(φ|y=1) ≈ P(φ|y=0) -> F_r ≈ 0, so the relation gates itself off."""
    same = [(0.5, 0.0), (0.6, 0.1), (0.4, -0.1), (0.55, 0.05)]
    m = spatial.fit({"r": {"pos": same, "neg": list(same)}})
    assert abs(m.score("r", (0.5, 0.0))) < 1e-6


def test_variance_floor_prevents_degenerate_confidence():
    """A relation whose positives are a single repeated point must not score ±inf."""
    m = spatial.fit({"r": {"pos": [(0.2, -0.5)] * 5, "neg": [(0.9, 0.4)] * 5}})
    s = m.score("r", (0.2, -0.5))
    assert s is not None and math.isfinite(s)


def test_too_few_samples_drops_the_relation():
    m = spatial.fit({"r": {"pos": [(0.2, -0.5)], "neg": [(0.9, 0.4)]}}, min_samples=2)
    assert m.score("r", (0.2, -0.5)) is None


def test_model_round_trips_through_json():
    m = spatial.fit(_samples())
    again = spatial.SpatialModel.from_dict(json.loads(json.dumps(m.to_dict())))
    assert abs(again.score("r", (0.2, -0.5)) - m.score("r", (0.2, -0.5))) < 1e-9


# --------------------------------------------------------------- samples

def test_build_samples_uses_injected_hard_negatives():
    """Hard negatives come from the caller (TLogic C_T); spatial.py stays independent."""
    g = scene(APPROACH, LOCS)
    facts = [("U1", "move to", "LOC_T", ts("13:00:20"))]
    domain = {"move to": {"LOC_T", "LOC_F"}}
    seen = []

    def hard(sub, rel, at):
        seen.append((sub, rel, at))
        return {"LOC_F"}

    s = spatial.build_samples(facts, g.positions, domain, hard_negatives_fn=hard,
                              horizon=0, rng_seed=0)
    assert seen == [("U1", "move to", ts("13:00:20"))]
    assert len(s["move to"]["pos"]) == 1
    assert len(s["move to"]["neg"]) >= 1


def test_build_samples_respects_horizon():
    """Features must be read at obs = t − Δ, never at t."""
    g = scene(APPROACH, LOCS)
    facts = [("U1", "move to", "LOC_T", ts("13:00:20"))]
    domain = {"move to": {"LOC_T", "LOC_F"}}
    a = spatial.build_samples(facts, g.positions, domain, horizon=0, rng_seed=0)
    b = spatial.build_samples(facts, g.positions, domain, horizon=10, rng_seed=0)
    assert a["move to"]["pos"] != b["move to"]["pos"]


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS " + name)
            except Exception:
                failures += 1; print("FAIL " + name); traceback.print_exc()
    print("\n%d failed" % failures if failures else "\nall passed")
    sys.exit(1 if failures else 0)


# ---------------------------------------------------------- v_d differencing gap

def _dense_approach(jitter_deg):
    """61 s of 1 Hz track driving north toward LOC_T at ~11 m/s; every other second
    the reported position is nudged along the line of sight by +-jitter_deg."""
    import datetime as dt
    base = dt.datetime.fromisoformat("2026-09-11T13:00:00")
    out = []
    for k in range(61):
        lat = 21.3800 + 0.0001 * k + (jitter_deg if k % 2 == 0 else -jitter_deg)
        t = (base + dt.timedelta(seconds=k)).isoformat()
        out.append(row("U1", "move to", "LOC_T", t, "%.6f" % lat, "-157.7500"))
    return out


def test_vd_gap_suppresses_position_noise():
    """Differencing the two latest 1 Hz fixes turns ~5 m of position noise into
    ~11 m/s of v_d error; differencing over VD_MIN_GAP seconds divides it away."""
    at = ts("13:01:00")
    clean = scene(_dense_approach(0.0), LOCS)
    noisy = scene(_dense_approach(0.00005), LOCS)          # ~5.5 m along the sight line
    _, v_true = spatial.features(clean.positions, "U1", "LOC_T", at)
    _, v_gap = spatial.features(noisy.positions, "U1", "LOC_T", at)
    _, v_1s = spatial.features(noisy.positions, "U1", "LOC_T", at, min_gap=1)
    assert spatial.VD_MIN_GAP == 30
    assert v_true < -10.0                                   # approaching at ~11 m/s
    assert abs(v_gap - v_true) < 1.0
    assert abs(v_1s - v_true) > 5.0


def test_vd_gap_falls_back_on_sparse_tracks():
    """No fix is VD_MIN_GAP older -> the oldest available one is used.

    With two fixes that is exactly the pair the latest-two rule picked. With three
    evenly spaced fixes it is the widest pair, which for uniform motion gives the
    same velocity."""
    import pytest
    at = ts("13:00:20")
    two = scene(APPROACH[1:], LOCS)
    assert spatial.features(two.positions, "U1", "LOC_T", at) == \
        spatial.features(two.positions, "U1", "LOC_T", at, min_gap=1)
    three = scene(APPROACH, LOCS)
    d_gap, v_gap = spatial.features(three.positions, "U1", "LOC_T", at)
    d_1s, v_1s = spatial.features(three.positions, "U1", "LOC_T", at, min_gap=1)
    assert d_gap == d_1s
    assert v_gap == pytest.approx(v_1s, rel=1e-3)
