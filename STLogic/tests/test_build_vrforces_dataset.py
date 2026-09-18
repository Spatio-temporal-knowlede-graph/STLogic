"""Tests for tools/build_vrforces_dataset.py (ENU projection + dataset layout)."""
import os
import sys
import math

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))

from build_vrforces_dataset import EnuFrame, pick_grid, split_grid  # noqa: E402


# Ala Moana scenario latitude — the frame the real data lives in.
LAT0, LON0 = 21.3800, -157.7450


def test_origin_maps_to_zero():
    f = EnuFrame(LAT0, LON0)
    e, n = f.to_enu(LAT0, LON0)
    assert abs(e) < 1e-9 and abs(n) < 1e-9


def test_one_degree_north_is_about_110_km():
    f = EnuFrame(LAT0, LON0)
    _, n = f.to_enu(LAT0 + 1.0, LON0)
    assert 110_000 < n < 111_600


def test_longitude_is_compressed_by_cos_latitude():
    """At 21.38N a degree of longitude is ~7% shorter than a degree of latitude."""
    f = EnuFrame(LAT0, LON0)
    e, _ = f.to_enu(LAT0, LON0 + 1.0)
    _, n = f.to_enu(LAT0 + 1.0, LON0)
    assert 0.92 < e / n < 0.94


def vincenty(a_ll, b_ll):
    """WGS84 geodesic distance, millimetre-accurate. The reference this frame is
    checked against -- haversine is a *sphere* and is off by ~0.4% here (a degree
    of meridian is 110,722 m on the ellipsoid at this latitude, 111,195 m on the
    sphere), which would swamp the projection error we actually want to bound.
    """
    a, f_, b = 6378137.0, 1 / 298.257223563, 6356752.314245
    L = math.radians(b_ll[1] - a_ll[1])
    U1 = math.atan((1 - f_) * math.tan(math.radians(a_ll[0])))
    U2 = math.atan((1 - f_) * math.tan(math.radians(b_ll[0])))
    sU1, cU1, sU2, cU2 = math.sin(U1), math.cos(U1), math.sin(U2), math.cos(U2)
    lam = L
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        ss = math.sqrt((cU2 * sl) ** 2 + (cU1 * sU2 - sU1 * cU2 * cl) ** 2)
        if ss == 0:
            return 0.0
        cs = sU1 * sU2 + cU1 * cU2 * cl
        sigma = math.atan2(ss, cs)
        sa = cU1 * cU2 * sl / ss
        c2a = 1 - sa ** 2
        c2sm = cs - 2 * sU1 * sU2 / c2a if c2a != 0 else 0.0
        C = f_ / 16 * c2a * (4 + f_ * (4 - 3 * c2a))
        prev = lam
        lam = L + (1 - C) * f_ * sa * (
            sigma + C * ss * (c2sm + C * cs * (-1 + 2 * c2sm ** 2)))
        if abs(lam - prev) < 1e-12:
            break
    u2 = c2a * (a * a - b * b) / (b * b)
    A = 1 + u2 / 16384 * (4096 + u2 * (-768 + u2 * (320 - 175 * u2)))
    B = u2 / 1024 * (256 + u2 * (-128 + u2 * (74 - 47 * u2)))
    dsig = B * ss * (c2sm + B / 4 * (cs * (-1 + 2 * c2sm ** 2) - B / 6 * c2sm
                     * (-3 + 4 * ss ** 2) * (-3 + 4 * c2sm ** 2)))
    return b * A * (sigma - dsig)


def test_distance_matches_geodesic_over_scenario_extent():
    """Local tangent plane must agree with the WGS84 geodesic to <1 m across ~2 km."""
    f = EnuFrame(LAT0, LON0)
    a = (21.3698895, -157.7445502)   # LOC_북측관측소
    b = (21.3898377, -157.7418324)   # LOC_남측제2방어선
    ea, na = f.to_enu(*a)
    eb, nb = f.to_enu(*b)
    planar = math.hypot(ea - eb, na - nb)
    geo = vincenty(a, b)
    assert abs(planar - geo) < 1.0, (planar, geo)


def test_raw_degree_distance_would_have_been_wrong():
    """Guards the bug this frame exists to fix: norm() on raw lat/lon."""
    a = (21.3698895, -157.7445502)
    b = (21.3898377, -157.7418324)
    raw = math.hypot(a[0]-b[0], a[1]-b[1])          # degrees, meaningless
    f = EnuFrame(LAT0, LON0)
    ea, na = f.to_enu(*a); eb, nb = f.to_enu(*b)
    metres = math.hypot(ea-eb, na-nb)
    assert metres > 2000            # ~2.2 km apart in reality
    assert raw < 1                  # raw degrees are off by ~5 orders of magnitude


def test_pick_grid_is_uniform_and_keeps_stride():
    secs = list(range(1000, 1000 + 100))
    grid = pick_grid(secs, stride=10)
    assert grid == list(range(1000, 1100, 10))


def test_pick_grid_drops_missing_ticks():
    secs = [1000, 1010, 1030]        # 1020 never observed
    assert pick_grid(secs, stride=10) == [1000, 1010, 1030]


def test_split_grid_is_contiguous_and_ordered():
    grid = list(range(100))
    tr, va, te = split_grid(grid, 0.70, 0.15)
    assert len(tr) == 70 and len(va) == 15 and len(te) == 15
    assert tr + va + te == grid


if __name__ == "__main__":
    import traceback
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS " + name)
            except Exception:
                failures += 1; print("FAIL " + name); traceback.print_exc()
    sys.exit(1 if failures else 0)
