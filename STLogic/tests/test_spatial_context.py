"""Unit tests for spatial_context: features, gaussian fit, spatial fit."""
import os
import sys
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mycode"))

import spatial_context as sc


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def build_index():
    # Head entity H (id 1) moves east: ts0 (300000,400000) -> ts1 (300100,400000).
    # Landmark L (id 2) static at (300200,400000).
    loc = {(1, 0): (300000.0, 400000.0), (1, 1): (300100.0, 400000.0)}
    landmarks = {2: (300200.0, 400000.0)}
    return sc.PositionIndex(loc, landmarks)


def test_features_head_to_landmark():
    pi = build_index()
    f = sc.features(pi, head=1, tail=2, t_ref=1)
    assert approx(f["d"], 100.0), f["d"]          # 300200 - 300100
    assert approx(f["dd"], -100.0), f["dd"]        # 100 (now) - 200 (prev) = approaching
    assert approx(f["cosb"], 1.0), f["cosb"]       # moving straight toward the landmark
    print("test_features_head_to_landmark OK", f)


def test_features_missing_position():
    pi = build_index()
    # tail id 99 has no coordinate -> all None
    f = sc.features(pi, head=1, tail=99, t_ref=1)
    assert f["d"] is None and f["dd"] is None and f["cosb"] is None
    print("test_features_missing_position OK")


def test_features_no_prev_obs():
    pi = build_index()
    # at t_ref=0 the head has no previous observation -> dd/cosb undefined, d defined
    f = sc.features(pi, head=1, tail=2, t_ref=0)
    assert approx(f["d"], 200.0), f["d"]
    assert f["dd"] is None and f["cosb"] is None
    print("test_features_no_prev_obs OK", f)


def test_fit_gaussian():
    feats = [{"d": 100.0, "dd": -10.0, "cosb": 1.0},
             {"d": 120.0, "dd": -14.0, "cosb": 0.9},
             {"d": 110.0, "dd": None, "cosb": None}]
    fit = sc.fit_gaussian(feats)
    assert approx(fit["d"]["mu"], 110.0), fit["d"]
    assert fit["d"]["n"] == 3
    assert fit["dd"]["n"] == 2          # one None skipped
    assert "cosb" in fit
    print("test_fit_gaussian OK", fit)


def test_spatial_fit():
    rule_spatial = {"d": {"mu": 100.0, "sigma": 10.0, "n": 5}}
    # candidate exactly at mu -> fit 1.0
    s1 = sc.spatial_fit({"d": 100.0}, rule_spatial, ("d",))
    assert approx(s1, 1.0), s1
    # candidate far from mu -> small fit
    s2 = sc.spatial_fit({"d": 100.0 + 3 * 10.0}, rule_spatial, ("d",))
    assert approx(s2, math.exp(-4.5), 1e-4), s2
    # feature not modelled / disabled -> 1.0 fallback
    assert sc.spatial_fit({"d": 100.0}, rule_spatial, ()) == 1.0
    assert sc.spatial_fit({"d": 100.0}, None, ("d",)) == 1.0
    print("test_spatial_fit OK", s1, s2)


if __name__ == "__main__":
    test_features_head_to_landmark()
    test_features_missing_position()
    test_features_no_prev_obs()
    test_fit_gaussian()
    test_spatial_fit()
    print("\nAll spatial_context tests passed.")
