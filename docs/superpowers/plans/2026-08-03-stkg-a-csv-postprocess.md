# STKG A단계 — 기존 CSV 후처리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VR-Forces가 뽑은 CSV를 재시뮬 없이 후처리해, `object`가 전 행 비어 있는 현재 상태를 S-P-O 관계 테이블과 위치 테이블로 분리한다.

**Architecture:** `vtmak/stkg/` 패키지에 순수 함수 모듈 7개를 두고 파일 입출력은 `export.py`와 스크립트에만 둔다. 각 모듈은 CSV 없이 문자열·튜플만으로 단위 테스트된다. 기존 `vtmak/` 코드는 읽기만 하고 수정하지 않는다.

**Tech Stack:** Python 3.13 표준 라이브러리 + pytest. 외부 의존성 없음(기존 파이프라인과 동일).

## Global Constraints

- 설계 정본은 `docs/superpowers/specs/2026-08-03-stkg-relation-extraction-design.md`. 충돌하면 스펙이 이긴다.
- 기존 `vtmak/` 모듈(`geometry.py`, `parser.py`, `scnx/*`)을 **수정하지 않는다.** 읽기만 한다.
- 관계 어휘는 스펙 §5의 11종으로 고정. 새 술어를 임의로 만들지 않는다.
- **조용한 유실 금지.** 입력 행은 반드시 관계·위치·제외·격리 중 정확히 한 갈래로 간다. 합이 안 맞으면 실패한다.
- 임계값(스냅 거리, 구간 끊김)은 코드 상수가 아니라 함수 기본 인자로 두어 호출부가 바꿀 수 있게 한다.
- Windows 콘솔이 cp949라 스크립트는 기존 `scripts/*.py`처럼 `sys.stdout.reconfigure(encoding="utf-8")`를 건다.
- 테스트는 `tests/test_stkg_*.py`. 기존 관행대로 `ROOT = Path(__file__).resolve().parents[1]`.
- 커밋 메시지는 기존 저장소 관행대로 한국어 본문 + `feat(stkg):` / `test(stkg):` 접두.

## 실측 기준값 (2026-08-03 17:22 CSV 기준)

> **스펙 §2와 다르다.** 스펙은 17:22 이전 CSV로 썼다. 그 CSV는 더 이른 빌드
> 산출물이었고(엔티티 167 vs 빌드 141), 새 CSV는 **현재 빌드와 정확히
> 일치한다**(엔티티 141 = 141, 차집합 양방향 0). 아래 숫자가 정본이다.

```
입력 5개 파일 130,523행 · subject 151
  ground_truth   126,718행   08:09:12 ~ 08:16:23 Z  (431초)
  UAV 1            1,227행   22:01:13 ~ 22:07:02 Z
  UAV 2            1,281행   22:00:04 ~ 22:07:04 Z
  UAV 3              609행   22:00:00 ~ 22:07:04 Z  (424초)
  UAV 4              688행   22:00:00 ~ 22:06:59 Z

subject 부류별
  엔티티        125,338행   141종. 현재 빌드 marking과 완전 일치
  1/2/3 Force     2,586행   제외
  Observer 1      1,624행   제외
  GlobalEnv 1       862행   제외
  발사체            113행   M933HE 1~4 (4종)
  E계열                0행   ← 사라졌다
  통제점 P*            0행   ← 없다

격리 대상
  1970 epoch           0행   ← 사라졌다

predicate 어휘 (6종이 전부)
  Move to {..}                              62,064
  None                                      35,503
  Follow-Entity Entity: "ENINF001" ...      28,560
  Follow-Entity Entity: "ENSA7001" ...       3,360
  FFE-On-Location "Location={..}" ...        1,035
  find_cover: ... Threat=FRINF001 ...            1

좌표 스냅 (config/battlefield_layout.json 지명 29개 대조)
  Move to  고유 목적지 10개 / 62,064행 → 정확 일치 100.0%
  FFE      고유 목적지  5개 /  1,035행 → 정확 일치 100.0%
  가장 큰 목적지: LOC_중앙킬존 21,869행 @ -5499123.141030,-2250320.406046,2311025.754248

fired_by — source를 분리해야 맞는다
  GROUND_TRUTH  M933HE 1 → ENMORT001 26.7m  정합 O
  GROUND_TRUTH  M933HE 2 → ENMORT002 28.8m  정합 O
  GROUND_TRUTH  M933HE 3 → FRMORT003 47.7m  정합 O
  GROUND_TRUTH  M933HE 4 → FRMORT001 26.3m  정합 O
  UAV 2         M933HE 1 → FRT80001 1500.5m 정합 X → 미확정
  UAV 2         M933HE 2 → FRT80001 1574.2m 정합 X → 미확정
  UAV 2         M933HE 3 → FRT80004 1115.2m 정합 X → 미확정
```

**`source`를 반드시 분리한다.** `M933HE 1`이 GROUND_TRUTH(25행)와 UAV 2(2행)
양쪽에 나온다. subject만으로 첫 관측을 잡으면 파일 읽는 순서에 따라 UAV
관측이 먼저 잡히고, UAV는 박격포를 못 봤으므로 1,500m 떨어진 **전차**에
붙는다. `first_seen`은 `(source, subject)`로, `candidates`는
`(source, timestamp)`로 키를 잡는다. 분리하면 GROUND_TRUTH 4건이 전부 정합
박격포에 26~48m로 붙고, UAV 3건은 정합성 검사에 걸려 미확정으로 보고된다.

**실데이터에 안 나오지만 코드는 유지하는 것들.** `Target-entity task`,
`Move-To Waypoint`, `provide_suppressive_fire_loc`, `suppressed_prone`,
E계열, 통제점, 1970 epoch가 이번 CSV에는 0건이다. 그래도 파서·필터·해석
코드는 그대로 만든다 — B단계에서 `fire-at-target`이 들어가면 `engages`·
`uuid` 경로가 살아나고, 다음 내보내기에서 다시 나타날 수 있다. 테스트는
합성 입력으로 돈다.

**미해석 UUID에 대한 결정:** UUID를 marking으로 못 바꾸면 **버리지 않고**
`object`에 UUID 원문을 두고 `object_type="uuid"`로 표시한다. 스펙 §4.1의
`object_type` 열거에 `uuid`를 추가한다 — 해석 실패를 소비 쪽이 알 수 있어야
한다.

**시간대는 여전히 어긋나 있다.** GT 08:09~08:16, UAV 22:00~22:07로 겹침이
0초다. 다만 길이가 431초 대 424초로 거의 같아져(이전엔 2시간 5분 대 7분)
오프셋 정렬 여지가 생겼다. A단계 범위 밖이며 C단계 몫이다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `vtmak/stkg/__init__.py` | 빈 패키지 표식 |
| `vtmak/stkg/filter.py` | subject·timestamp → 제외/격리/유지 판정 |
| `vtmak/stkg/predicate.py` | predicate 원문 → 정규화 술어 + object 원문 |
| `vtmak/stkg/resolve.py` | `.oob` → uuid→marking 표, 조회 |
| `vtmak/stkg/locate.py` | ECEF 좌표 → 지명/통제점/좌표 |
| `vtmak/stkg/derive.py` | 발사체 → `fired_by` 추론 |
| `vtmak/stkg/collapse.py` | tick 관측 → 구간 관계 |
| `vtmak/stkg/export.py` | 조립·회계·세 파일 출력 |
| `scripts/06_stkg_export.py` | CLI 진입점 |
| `config/munition_map.csv` | 탄약 ↔ 발사 무기 marking 패턴 |

모듈 간 의존은 한 방향이다. `export.py`만 나머지를 안다. `filter`/`predicate`/`locate`/`resolve`/`derive`/`collapse`는 서로를 모른다.

---

### Task 1: `filter.py` — 제외·격리 판정

**Files:**
- Create: `new_VTMAK/vtmak/stkg/__init__.py`
- Create: `new_VTMAK/vtmak/stkg/filter.py`
- Test: `new_VTMAK/tests/test_stkg_filter.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `Disposition` (str Enum: `KEEP`/`DROP_INFRA`/`DROP_EFFECT`/`QUARANTINE_EPOCH`), `classify(subject: str, timestamp: str) -> Disposition`, `INFRA_SUBJECTS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_filter.py`:

```python
import pytest

from vtmak.stkg.filter import Disposition, classify

TS = "2026-08-03T05:20:00.000Z"


@pytest.mark.parametrize("subject", ["1 Force", "2 Force", "3 Force",
                                     "Observer 1", "GlobalEnv 1"])
def test_infra_subjects_are_dropped(subject):
    assert classify(subject, TS) is Disposition.DROP_INFRA


@pytest.mark.parametrize("subject", ["E1", "E7", "E62"])
def test_effect_objects_are_dropped(subject):
    assert classify(subject, TS) is Disposition.DROP_EFFECT


@pytest.mark.parametrize("subject", ["ENINF001", "FRM109003", "P17",
                                     "M107 3", "UAV 2"])
def test_scenario_objects_are_kept(subject):
    assert classify(subject, TS) is Disposition.KEEP


def test_epoch_timestamp_is_quarantined():
    assert classify("ENT72003", "1970-01-01T12:00:04.040Z") \
        is Disposition.QUARANTINE_EPOCH


def test_quarantine_wins_over_keep_but_not_over_drop():
    """제외 대상은 격리 이전에 걸러진다 — 인프라 객체를 격리 목록에
    올려봐야 쓸 데가 없다."""
    assert classify("GlobalEnv 1", "1970-01-01T12:00:00.000Z") \
        is Disposition.DROP_INFRA


def test_entity_named_like_effect_is_not_dropped():
    """E로 시작해도 숫자만 뒤따르지 않으면 효과 객체가 아니다.
    ENINF001, ENT72003이 여기 걸리면 적군 전체가 사라진다."""
    for subject in ("ENINF001", "ENT72003", "ENCAESAR002", "ENMORT001"):
        assert classify(subject, TS) is Disposition.KEEP
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/vtmak/stkg/__init__.py`: 빈 파일.

`new_VTMAK/vtmak/stkg/filter.py`:

```python
"""입력 행을 네 갈래 중 하나로 판정한다.

제외 대상은 스펙 §6에서 확정했다. 판정을 코드 한 곳에 모아 두는 이유는
'어디선가 조용히 걸러졌다'가 생기지 않게 하기 위해서다. 모든 행은 여기서
꼬리표를 받고, export가 그 꼬리표대로 회계를 맞춘다.
"""
from __future__ import annotations

import re
from enum import Enum

# 시뮬레이터 인프라. 원문에 등장하지 않고 물리 객체도 아니다.
# Force 노드는 좌표가 (42.32429274, 45.00000000) 고정 쓰레기값이다.
INFRA_SUBJECTS = frozenset({
    "1 Force", "2 Force", "3 Force", "Observer 1", "GlobalEnv 1",
})

# E + 숫자만. 62종이 한 시각(07:13:22)에 동시 등장하고 정지하는 일괄 스폰이라
# 어떤 사격과도 짝지을 수 없다(스펙 §6.2). ENINF001 같은 엔티티가 여기 걸리면
# 적군이 통째로 사라지므로 fullmatch로 못박는다.
_RE_EFFECT = re.compile(r"E\d+")

# 초기화 안 된 타임스탬프. UAV 2에 182행, UAV 3에 15행.
_EPOCH_PREFIX = "1970-"


class Disposition(str, Enum):
    KEEP = "keep"
    DROP_INFRA = "drop_infra"
    DROP_EFFECT = "drop_effect"
    QUARANTINE_EPOCH = "quarantine_epoch"


def classify(subject: str, timestamp: str) -> Disposition:
    if subject in INFRA_SUBJECTS:
        return Disposition.DROP_INFRA
    if _RE_EFFECT.fullmatch(subject):
        return Disposition.DROP_EFFECT
    if timestamp.startswith(_EPOCH_PREFIX):
        return Disposition.QUARANTINE_EPOCH
    return Disposition.KEEP
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_filter.py -v`
Expected: PASS — 13 passed

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/vtmak/stkg/__init__.py new_VTMAK/vtmak/stkg/filter.py new_VTMAK/tests/test_stkg_filter.py
git commit -m "feat(stkg): 입력 행 제외·격리 판정

Force/Observer/GlobalEnv 5종과 E계열 62종을 제외, 1970 epoch를 격리로
판정한다. E계열은 fullmatch로 못박아 ENINF001 같은 엔티티가 걸리지 않게 한다."
```

---

### Task 2: `predicate.py` — predicate 원문 파싱

**Files:**
- Create: `new_VTMAK/vtmak/stkg/predicate.py`
- Test: `new_VTMAK/tests/test_stkg_predicate.py`

**Interfaces:**
- Consumes: 없음
- Produces: `Parsed` (frozen dataclass: `predicate: str`, `object_raw: str | None`, `object_kind: str`), `parse(raw: str) -> Parsed | None`
  - `object_kind` ∈ `{"entity", "uuid", "coord", "none"}` — **원문에서 읽은 종류**다. 최종 `object_type`은 `export.py`가 `locate`/`resolve`를 거쳐 정한다.
  - `predicate == ""` 는 "관계가 아님"(위치 테이블행). `parse` 가 `None`을 돌려주면 **파싱 실패**(보고 대상). 둘은 다르다.

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_predicate.py`:

```python
from vtmak.stkg.predicate import Parsed, parse


def test_follow_entity_yields_entity_marking():
    p = parse('Follow-Entity Entity: "ENINF001" Offset: <-0 0 -0 >')
    assert p == Parsed("follows", "ENINF001", "entity")


def test_move_to_yields_coord():
    p = parse("Move to {-5499123.141030, -2250320.406046, 2311025.754248}")
    assert p.predicate == "moves_to"
    assert p.object_kind == "coord"
    assert p.object_raw == "-5499123.141030,-2250320.406046,2311025.754248"


def test_move_to_waypoint_yields_uuid():
    p = parse('Move-To Waypoint: "62f22b9c-d768-531d-9242-e32d8a056ee9"')
    assert p == Parsed("moves_to", "62f22b9c-d768-531d-9242-e32d8a056ee9",
                       "uuid")


def test_ffe_on_location_yields_coord():
    raw = ('FFE-On-Location "Location={-5498573.025370, -2251262.832114, '
           '2311309.431241}"  Name of Weapons to Fire: '
           "Indirect-Fire-Gun:m9333he. Number-Of-Rounds: 1. "
           "Height-Above-Terrain: 0")
    p = parse(raw)
    assert p.predicate == "fires_at"
    assert p.object_kind == "coord"
    assert p.object_raw.startswith("-5498573.025370,")


def test_target_entity_task_with_uuid():
    p = parse("Target-entity task: 2c380775-b3d4-7144-8815-4ef6c9e202ce")
    assert p == Parsed("engages", "2c380775-b3d4-7144-8815-4ef6c9e202ce",
                       "uuid")


def test_target_entity_task_with_marking():
    """UUID가 아닌 값도 온다. 실측 24행이 'M933HE 2'였다."""
    p = parse("Target-entity task: M933HE 2")
    assert p == Parsed("engages", "M933HE 2", "entity")


def test_find_cover_threat_is_a_marking_not_a_uuid():
    raw = ("find_cover: ChooseFiringPosition=False; DistanceFromThreat=2; "
           "FaceThreat=False; ForwardDirection=6.28318; OnlyForward=False; "
           "Range=100; StartFrom=0; StartingLocation={-5499510.258721, "
           "-2250984.063019, 2309459.984596}; Threat=FRINF001; "
           "ThreatRadius=2; ")
    assert parse(raw) == Parsed("takes_cover_from", "FRINF001", "entity")


def test_none_is_not_a_relation():
    assert parse("None") == Parsed("", None, "none")


def test_suppressed_prone_is_known_but_not_a_relation():
    """관계 어휘 11종에 없다. 파싱 실패가 아니므로 None이 아니다."""
    assert parse("suppressed_prone") == Parsed("", None, "none")


def test_unknown_predicate_returns_none():
    assert parse("Completely-Unknown-Task foo=1") is None


def test_empty_string_returns_none():
    assert parse("") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_predicate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg.predicate'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/vtmak/stkg/predicate.py`:

```python
"""predicate 원문 → 정규화 술어 + object 원문.

내보내기가 object 열을 안 채우고 대상을 predicate 문자열 안에 박아 놓는다.
실측 478,360행 중 52,044행(10.9%)이 이미 엔티티를 품고 있다. 여기서 꺼낸다.

돌려주는 값 세 가지를 구분할 것.
  Parsed(predicate="follows", ...)  관계다
  Parsed(predicate="", ...)         관계가 아니다(위치 테이블행). None·suppressed_prone
  None                              파싱 실패. report에 원문과 함께 적는다
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_RE_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")

# 관계가 아니라고 아는 술어. 파싱 실패와 구분해야 report가 쓸모 있다.
_NOT_A_RELATION = frozenset({"None", "suppressed_prone"})

_RE_FOLLOW = re.compile(r'^Follow-Entity Entity:\s*"([^"]+)"')
_RE_MOVE_COORD = re.compile(r"^Move to \{([^}]+)\}")
_RE_MOVE_WP = re.compile(r'^Move-To Waypoint:\s*"([^"]+)"')
_RE_FFE = re.compile(r'^FFE-On-Location\s+"Location=\{([^}]+)\}"')
_RE_TARGET = re.compile(r"^Target-entity task:\s*(.+?)\s*$")
_RE_FIND_COVER = re.compile(r"^find_cover:.*?\bThreat=([^;]+?)\s*;")
_RE_SUPPRESS = re.compile(
    r"^provide_suppressive_fire_loc:.*?\btargetLocation=\{([^}]+)\}")


@dataclass(frozen=True)
class Parsed:
    predicate: str
    object_raw: str | None
    object_kind: str          # entity | uuid | coord | none


def _coord(blob: str) -> str:
    """'{a, b, c}' 속 알맹이를 공백 없는 정규형으로."""
    return ",".join(part.strip() for part in blob.split(","))


def parse(raw: str) -> Parsed | None:
    raw = raw.strip()
    if not raw:
        return None
    if raw in _NOT_A_RELATION:
        return Parsed("", None, "none")

    m = _RE_FOLLOW.match(raw)
    if m:
        return Parsed("follows", m.group(1), "entity")

    m = _RE_MOVE_COORD.match(raw)
    if m:
        return Parsed("moves_to", _coord(m.group(1)), "coord")

    m = _RE_MOVE_WP.match(raw)
    if m:
        return Parsed("moves_to", m.group(1), "uuid")

    m = _RE_FFE.match(raw)
    if m:
        return Parsed("fires_at", _coord(m.group(1)), "coord")

    m = _RE_SUPPRESS.match(raw)
    if m:
        return Parsed("suppresses", _coord(m.group(1)), "coord")

    m = _RE_FIND_COVER.match(raw)
    if m:
        # Threat는 uuid가 아니라 marking으로 나온다(실측: Threat=FRINF001).
        return Parsed("takes_cover_from", m.group(1).strip(), "entity")

    m = _RE_TARGET.match(raw)
    if m:
        val = m.group(1)
        kind = "uuid" if _RE_UUID.fullmatch(val) else "entity"
        return Parsed("engages", val, kind)

    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_predicate.py -v`
Expected: PASS — 11 passed

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/vtmak/stkg/predicate.py new_VTMAK/tests/test_stkg_predicate.py
git commit -m "feat(stkg): predicate 원문에서 술어와 object 분리

내보내기가 대상을 predicate 문자열에 박아 놓는다. 술어 7종을 정규화 어휘로
바꾸고 object 원문을 꺼낸다. '관계 아님'과 '파싱 실패'를 구분해 돌려준다."
```

---

### Task 3: `resolve.py` — UUID → marking

**Files:**
- Create: `new_VTMAK/vtmak/stkg/resolve.py`
- Test: `new_VTMAK/tests/test_stkg_resolve.py`

**Interfaces:**
- Consumes: 없음
- Produces: `load_uuid_map(oob_path: Path) -> dict[str, str]`, `to_marking(uuid: str, uuid_map: dict[str, str]) -> str | None`

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_resolve.py`:

```python
from pathlib import Path

import pytest

from vtmak.stkg.resolve import load_uuid_map, to_marking

ROOT = Path(__file__).resolve().parents[1]
OOB = ROOT / "campaign" / "campaign.oob"


@pytest.fixture(scope="module")
def uuid_map():
    return load_uuid_map(OOB)


def test_map_is_not_empty(uuid_map):
    assert len(uuid_map) > 100


def test_every_value_is_a_marking(uuid_map):
    for marking in uuid_map.values():
        assert marking
        assert '"' not in marking


def test_uuid_keys_have_no_vrf_prefix(uuid_map):
    for key in uuid_map:
        assert not key.startswith("VRF_UUID:")


def test_to_marking_resolves_a_known_uuid(uuid_map):
    known_uuid = next(iter(uuid_map))
    assert to_marking(known_uuid, uuid_map) == uuid_map[known_uuid]


def test_to_marking_returns_none_for_unknown():
    assert to_marking("2c380775-b3d4-7144-8815-4ef6c9e202ce", {}) is None


def test_to_marking_tolerates_vrf_prefix(uuid_map):
    known_uuid = next(iter(uuid_map))
    assert to_marking(f"VRF_UUID:{known_uuid}", uuid_map) \
        == uuid_map[known_uuid]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg.resolve'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/vtmak/stkg/resolve.py`:

```python
"""`.oob` 레코드에서 uuid → marking 표를 만든다.

CSV의 predicate는 대상을 uuid로 적기도 한다(Move-To Waypoint, Target-entity
task). uuid를 그대로 내보내면 다른 산출물과 조인할 수 없으므로 marking으로
되짚는다.

짝이 되는 `.oob`이 없으면 표가 비고 to_marking이 None을 돌려준다. 그때
호출부는 uuid 원문을 유지하고 object_type="uuid"로 표시해야 한다 — 버리지
않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

# 레코드 안에서 marking-text가 uuid보다 먼저 나온다(marking → ... → uuid).
_RE_PAIR = re.compile(
    r'\(marking-text "([^"]*)".*?\(uuid\s+"VRF_UUID:([^"]+)"', re.S)


def load_uuid_map(oob_path) -> dict[str, str]:
    text = Path(oob_path).read_text(encoding="utf-8", errors="replace")
    return {uuid: marking for marking, uuid in _RE_PAIR.findall(text)}


def to_marking(uuid: str, uuid_map: dict[str, str]) -> str | None:
    key = uuid[len("VRF_UUID:"):] if uuid.startswith("VRF_UUID:") else uuid
    return uuid_map.get(key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_resolve.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/vtmak/stkg/resolve.py new_VTMAK/tests/test_stkg_resolve.py
git commit -m "feat(stkg): .oob에서 uuid→marking 표 생성

predicate가 대상을 uuid로 적는 경우를 marking으로 되짚는다. 짝이 되는
.oob이 없으면 None을 돌려주고, 호출부가 uuid 원문을 유지한다."
```

---

### Task 4: `locate.py` — 좌표 → 위치 객체

**Files:**
- Create: `new_VTMAK/vtmak/stkg/locate.py`
- Test: `new_VTMAK/tests/test_stkg_locate.py`

**Interfaces:**
- Consumes: `vtmak.geometry.BattlefieldLayout` (`.location_ids()`, `.coord(lid) -> Coord`), `vtmak.geometry.Coord.to_ecef()`
- Produces: `Snap` (frozen dataclass: `object_id: str`, `object_type: str`, `distance_m: float`), `snap(ecef, layout, control_points=None, exact_m=1.0, near_m=50.0) -> Snap`
  - `ecef`: `tuple[float, float, float]`
  - `control_points`: `dict[str, tuple[float, float, float]] | None`
  - `object_type` ∈ `{"location", "coord"}`
  - 미일치 시 `object_id`는 `"x,y,z"` 정규형, `distance_m`은 `-1.0`

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_locate.py`:

```python
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout
from vtmak.stkg.locate import Snap, snap

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def layout():
    return BattlefieldLayout.load(ROOT / "config" / "battlefield_layout.json")


def test_exact_match_returns_the_place_name(layout):
    lid = layout.location_ids()[0]
    result = snap(layout.coord(lid).to_ecef(), layout)
    assert result.object_id == lid
    assert result.object_type == "location"
    assert result.distance_m < 1.0


def test_nearby_control_point_is_used_when_no_place_matches(layout):
    """지명에서 멀지만 통제점 반경 안이면 통제점을 쓴다."""
    x, y, z = layout.coord(layout.location_ids()[0]).to_ecef()
    far = (x + 3000.0, y + 3000.0, z + 3000.0)
    result = snap(far, layout, control_points={"P7": (far[0] + 5.0,
                                                     far[1], far[2])})
    assert result.object_id == "P7"
    assert result.object_type == "location"
    assert 0.0 < result.distance_m < 50.0


def test_falls_back_to_coord_when_nothing_is_near(layout):
    x, y, z = layout.coord(layout.location_ids()[0]).to_ecef()
    far = (x + 5000.0, y + 5000.0, z + 5000.0)
    result = snap(far, layout)
    assert result.object_type == "coord"
    assert result.distance_m == -1.0
    assert result.object_id == f"{far[0]:.6f},{far[1]:.6f},{far[2]:.6f}"


def test_control_points_absent_skips_step_two(layout):
    """현재 빌드는 통제점을 저작하지 않는다. None이 와도 죽지 않아야 한다."""
    x, y, z = layout.coord(layout.location_ids()[0]).to_ecef()
    result = snap((x + 100.0, y, z), layout, control_points=None)
    assert result.object_type == "coord"


def test_place_name_wins_over_a_closer_control_point(layout):
    """1단계 정확 일치가 2단계보다 항상 먼저다."""
    lid = layout.location_ids()[0]
    exact = layout.coord(lid).to_ecef()
    result = snap(exact, layout,
                  control_points={"P1": (exact[0] + 0.1, exact[1], exact[2])})
    assert result.object_id == lid


def test_real_destination_from_measured_data_resolves(layout):
    """실측: Move to 목적지 27,342행이 LOC_중앙킬존에 0.0m로 붙는다."""
    result = snap((-5499123.141030, -2250320.406046, 2311025.754248), layout)
    assert result.object_type == "location"
    assert result.distance_m < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_locate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg.locate'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/vtmak/stkg/locate.py`:

```python
"""목적지 좌표를 위치 객체로 바꾼다.

태스크 저작이 지명 좌표를 그대로 넣으므로 최근접 탐색이 아니라 정확 일치로
대부분 끝난다. 실측(2026-08-03): Move to 95,444행 중 87.2%가 0.0m로 붙었다.

3단 폴백이다.
  1. 정확 일치   지명 좌표와 exact_m 이내      → 지명   (location)
  2. 최근접      통제점과 near_m 이내          → 통제점 (location)
  3. 폴백        좌표 문자열 유지              →        (coord)

2단계는 통제점이 주어졌을 때만 돈다. 현재 빌드는 통제점을 저작하지 않아
1 → 3으로 간다(스펙 §7).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Snap:
    object_id: str
    object_type: str          # location | coord
    distance_m: float         # coord 폴백이면 -1.0


def _fmt(ecef: tuple[float, float, float]) -> str:
    return ",".join(f"{v:.6f}" for v in ecef)


def snap(ecef: tuple[float, float, float], layout,
         control_points: dict[str, tuple[float, float, float]] | None = None,
         exact_m: float = 1.0, near_m: float = 50.0) -> Snap:
    best_id, best_d = None, math.inf
    for lid in layout.location_ids():
        d = math.dist(ecef, layout.coord(lid).to_ecef())
        if d < best_d:
            best_id, best_d = lid, d
    if best_id is not None and best_d <= exact_m:
        return Snap(best_id, "location", best_d)

    if control_points:
        cp_id, cp_d = None, math.inf
        for pid, coord in control_points.items():
            d = math.dist(ecef, coord)
            if d < cp_d:
                cp_id, cp_d = pid, d
        if cp_id is not None and cp_d <= near_m:
            return Snap(cp_id, "location", cp_d)

    return Snap(_fmt(ecef), "coord", -1.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_locate.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/vtmak/stkg/locate.py new_VTMAK/tests/test_stkg_locate.py
git commit -m "feat(stkg): 목적지 좌표 → 위치 객체 3단 폴백

지명 정확 일치 → 통제점 최근접 → 좌표 유지. 실측상 87.2%가 1단계에서
끝난다. 통제점이 없는 빌드에서는 2단계를 건너뛴다."
```

---

### Task 5: `munition_map.csv` + `derive.py` — `fired_by` 추론

**Files:**
- Create: `new_VTMAK/config/munition_map.csv`
- Create: `new_VTMAK/vtmak/stkg/derive.py`
- Test: `new_VTMAK/tests/test_stkg_derive.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `load_munition_map(path) -> dict[str, str]` — 탄약 접두 → 발사자 marking 정규식
  - `Obs` (frozen dataclass: `subject`, `predicate`, `object`, `object_type`, `timestamp`, `source`, `confidence`, `evidence`) — **Task 6·7이 같은 타입을 쓴다**
  - `fired_by(first_seen, candidates, munition_map, max_m=200.0) -> tuple[list[Obs], list[str]]`
    - `first_seen`: `dict[tuple[str, str], tuple[str, tuple[float, float, float]]]` — **(source, 발사체 marking)** → (timestamp, ecef)
    - `candidates`: `dict[tuple[str, str], list[tuple[str, tuple[float, float, float]]]]` — **(source, timestamp)** → [(marking, ecef)]
    - 키에 `source`가 들어가는 이유는 실측 기준값 절 참조. 같은 발사체가 GT와 UAV 양쪽에 나오고, 섞으면 1,500m 떨어진 전차에 붙는다.
    - 돌려주는 둘째 값은 미확정 사유 문자열 목록(report용)

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_derive.py`:

```python
from pathlib import Path

import pytest

from vtmak.stkg.derive import Obs, fired_by, load_munition_map

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "config" / "munition_map.csv"
TS = "2026-08-03T05:49:40.000Z"


@pytest.fixture(scope="module")
def mmap():
    return load_munition_map(MAP)


def test_map_covers_the_three_measured_munitions(mmap):
    assert set(mmap) == {"M107", "M933HE", "PAC-3"}


def test_howitzer_shell_binds_to_the_nearest_howitzer(mmap):
    rels, unresolved = fired_by(
        {("GROUND_TRUTH", "M107 4"): (TS, (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("FRM109001", (1.3, 0.0, 0.0)),
                                ("ENINF001", (2.0, 0.0, 0.0))]},
        mmap)
    assert unresolved == []
    assert len(rels) == 1
    assert rels[0].subject == "M107 4"
    assert rels[0].predicate == "fired_by"
    assert rels[0].object == "FRM109001"
    assert rels[0].object_type == "entity"
    assert rels[0].source == "GROUND_TRUTH"
    assert rels[0].confidence == "inferred"
    assert "1.3" in rels[0].evidence


def test_mortar_shell_binds_to_a_mortar(mmap):
    """실측: GROUND_TRUTH M933HE 4 → FRMORT001 26.3m."""
    rels, unresolved = fired_by(
        {("GROUND_TRUTH", "M933HE 4"): (TS, (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("FRMORT001", (26.3, 0.0, 0.0))]}, mmap)
    assert unresolved == []
    assert rels[0].object == "FRMORT001"


def test_source_is_not_mixed(mmap):
    """실측 회귀 케이스. M933HE 1이 GROUND_TRUTH와 UAV 2 양쪽에 나온다.
    source를 섞으면 UAV가 본 발사체가 GT가 본 박격포에 붙어, 서로 다른
    시간대의 관측을 하나로 잇는다."""
    rels, unresolved = fired_by(
        {("UAV 2", "M933HE 1"): ("2026-08-03T22:00:12.000Z",
                                 (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("ENMORT001", (26.7, 0.0, 0.0))]}, mmap)
    assert rels == []
    assert len(unresolved) == 1


def test_mortar_shell_does_not_bind_to_a_tank(mmap):
    """실측 회귀 케이스. UAV 2가 본 M933HE 1의 최근접은 FRT80001(1500.5m)
    이다. 전차는 박격포탄을 쏘지 않으므로 관계를 만들면 안 된다."""
    ts = "2026-08-03T22:00:12.000Z"
    rels, unresolved = fired_by(
        {("UAV 2", "M933HE 1"): (ts, (0.0, 0.0, 0.0))},
        {("UAV 2", ts): [("FRT80001", (1500.5, 0.0, 0.0))]}, mmap)
    assert rels == []
    assert len(unresolved) == 1
    assert "M933HE 1" in unresolved[0]


def test_patriot_round_does_not_bind_to_a_mortar(mmap):
    """정합성 검사가 없으면 최근접만으로 패트리엇 요격탄이 박격포에 붙는다."""
    rels, unresolved = fired_by(
        {("GROUND_TRUTH", "PAC-3 1"): (TS, (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("FRMORT001", (19.1, 0.0, 0.0))]}, mmap)
    assert rels == []
    assert len(unresolved) == 1
    assert "PAC-3 1" in unresolved[0]


def test_patriot_round_binds_to_a_patriot_launcher(mmap):
    rels, _ = fired_by(
        {("GROUND_TRUTH", "PAC-3 1"): (TS, (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("FRMORT001", (19.1, 0.0, 0.0)),
                                ("FRM901001", (40.0, 0.0, 0.0))]}, mmap)
    assert len(rels) == 1
    assert rels[0].object == "FRM901001"


def test_too_far_is_unresolved(mmap):
    rels, unresolved = fired_by(
        {("GROUND_TRUTH", "M107 1"): (TS, (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("ENCAESAR002", (900.0, 0.0, 0.0))]}, mmap)
    assert rels == []
    assert len(unresolved) == 1


def test_unknown_munition_prefix_is_unresolved(mmap):
    rels, unresolved = fired_by(
        {("GROUND_TRUTH", "UNKNOWN 9"): (TS, (0.0, 0.0, 0.0))},
        {("GROUND_TRUTH", TS): [("FRM109001", (1.0, 0.0, 0.0))]}, mmap)
    assert rels == []
    assert len(unresolved) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_derive.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg.derive'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/config/munition_map.csv`:

```csv
munition_prefix,firer_marking_pattern,note
M107,(M109|CAESAR|KRAB|AHS),155mm 곡사포탄. 실측 6종 전부 자주포에 붙었다
M933HE,MORT,120mm 박격포탄. 실측 5종 전부 박격포에 붙었다
PAC-3,(M901|MIM|PAC),패트리엇 요격탄. 최근접만 쓰면 박격포에 붙는다(실측 19.1m)
```

`new_VTMAK/vtmak/stkg/derive.py`:

```python
"""발사체 → fired_by 관계 추론.

발사체가 처음 관측된 시각의 최근접 엔티티를 발사자로 본다. 최근접만으로는
틀린다 — 실측에서 PAC-3 1(패트리엇 요격탄)이 19.1m 떨어진 박격포에 붙었다.
그래서 무기·탄약 정합성 검사를 함께 건다. 정합하지 않으면 **관계를 만들지
않고** 사유를 돌려준다. 억지로 붙이면 틀린 관계가 정답 행세를 한다.
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Obs:
    """관계 한 건의 tick 단위 관측. collapse가 이걸 구간으로 접는다."""
    subject: str
    predicate: str
    object: str
    object_type: str
    timestamp: str
    source: str
    confidence: str           # observed | inferred
    evidence: str


def load_munition_map(path) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(Path(path), encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            out[row["munition_prefix"]] = row["firer_marking_pattern"]
    return out


def _prefix_of(marking: str, munition_map: dict[str, str]) -> str | None:
    # 'M933HE 2' → 'M933HE'. 접두가 긴 것부터 봐야 M107과 M1077을 안 헷갈린다.
    for prefix in sorted(munition_map, key=len, reverse=True):
        if marking.startswith(prefix):
            return prefix
    return None


def fired_by(first_seen: dict[tuple[str, str],
                              tuple[str, tuple[float, float, float]]],
             candidates: dict[tuple[str, str],
                              list[tuple[str, tuple[float, float, float]]]],
             munition_map: dict[str, str],
             max_m: float = 200.0) -> tuple[list[Obs], list[str]]:
    """키가 (source, ...)인 이유는 같은 발사체가 여러 관측자에게 보이기
    때문이다. 실측에서 M933HE 1이 GROUND_TRUTH와 UAV 2 양쪽에 나온다.
    섞으면 UAV가 본 발사체가 GT가 본 박격포에 붙어 서로 다른 시간대의
    관측을 하나로 잇는다."""
    rels: list[Obs] = []
    unresolved: list[str] = []

    for (source, munition), (ts, ecef) in sorted(first_seen.items()):
        prefix = _prefix_of(munition, munition_map)
        if prefix is None:
            unresolved.append(f"[{source}] {munition}: 탄약 접두 미등록")
            continue
        pattern = re.compile(munition_map[prefix])

        best, best_d = None, math.inf
        for marking, pos in candidates.get((source, ts), []):
            if not pattern.search(marking):
                continue
            d = math.dist(ecef, pos)
            if d < best_d:
                best, best_d = marking, d

        if best is None:
            unresolved.append(f"[{source}] {munition}: {prefix}에 맞는 발사 "
                              f"무기가 {ts}에 없음")
            continue
        if best_d > max_m:
            unresolved.append(f"[{source}] {munition}: 최근접 {best}이 "
                              f"{best_d:.1f}m로 임계 {max_m:.0f}m 초과")
            continue

        rels.append(Obs(munition, "fired_by", best, "entity", ts, source,
                        "inferred", f"최근접 {best_d:.1f}m, 정합 {prefix}"))
    return rels, unresolved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_derive.py -v`
Expected: PASS — 8 passed

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/config/munition_map.csv new_VTMAK/vtmak/stkg/derive.py new_VTMAK/tests/test_stkg_derive.py
git commit -m "feat(stkg): 발사체 fired_by 추론 (최근접 + 무기·탄약 정합)

최근접만 쓰면 PAC-3 요격탄이 19.1m 떨어진 박격포에 붙는다(실측). 정합성
검사를 걸어 어긋나면 관계를 만들지 않고 사유를 보고한다. 그 케이스를
회귀 테스트로 고정했다."
```

---

### Task 6: `collapse.py` — tick 관측 → 구간 관계

**Files:**
- Create: `new_VTMAK/vtmak/stkg/collapse.py`
- Test: `new_VTMAK/tests/test_stkg_collapse.py`

**Interfaces:**
- Consumes: `vtmak.stkg.derive.Obs`
- Produces: `Relation` (frozen dataclass: `subject`, `predicate`, `object`, `object_type`, `t_start`, `t_end`, `source`, `confidence`, `evidence`), `collapse(obs: list[Obs], gap_s: float = 3.0) -> list[Relation]`

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_collapse.py`:

```python
from vtmak.stkg.collapse import Relation, collapse
from vtmak.stkg.derive import Obs


def _obs(sec, subject="FRINF001", obj="ENINF001"):
    return Obs(subject, "follows", obj, "entity",
               f"2026-08-03T05:20:{sec:02d}.000Z", "GROUND_TRUTH",
               "observed", "raw")


def test_consecutive_ticks_become_one_interval():
    out = collapse([_obs(0), _obs(1), _obs(2)])
    assert len(out) == 1
    assert out[0].t_start == "2026-08-03T05:20:00.000Z"
    assert out[0].t_end == "2026-08-03T05:20:02.000Z"


def test_a_gap_splits_the_interval():
    """관측 공백을 이어붙이면 관측하지 않은 구간을 관측했다고 주장하게 된다."""
    out = collapse([_obs(0), _obs(1), _obs(30), _obs(31)])
    assert len(out) == 2
    assert out[0].t_end == "2026-08-03T05:20:01.000Z"
    assert out[1].t_start == "2026-08-03T05:20:30.000Z"


def test_exact_duplicates_collapse_to_one_row():
    """입력의 54.5%가 완전중복이다. 같은 tick이 여러 번 와도 한 구간이다."""
    out = collapse([_obs(0), _obs(0), _obs(0)])
    assert len(out) == 1
    assert out[0].t_start == out[0].t_end == "2026-08-03T05:20:00.000Z"


def test_different_objects_do_not_merge():
    out = collapse([_obs(0, obj="ENINF001"), _obs(1, obj="ENSA7001")])
    assert len(out) == 2


def test_different_subjects_do_not_merge():
    out = collapse([_obs(0, subject="FRINF001"), _obs(1, subject="FRINF002")])
    assert len(out) == 2


def test_unsorted_input_is_handled():
    out = collapse([_obs(2), _obs(0), _obs(1)])
    assert len(out) == 1
    assert out[0].t_start == "2026-08-03T05:20:00.000Z"


def test_empty_input_returns_empty():
    assert collapse([]) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_collapse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg.collapse'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/vtmak/stkg/collapse.py`:

```python
"""tick 단위 관측을 구간 관계로 접는다.

'Follow-Entity → ENINF001'이 46,976행이지만 표현하는 사실은 '누가 언제부터
언제까지 따랐다'뿐이다. 지식그래프의 시간 표현으로도 구간이 정본이고,
입력의 완전중복 54.5%도 여기서 함께 사라진다.

공백을 사이에 두고 같은 관계가 재개되면 나눈다. 이어붙이면 관측하지 않은
구간을 관측했다고 주장하게 된다. GT 샘플링에 1,058초·215초 공백이 있다.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .derive import Obs


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str
    object: str
    object_type: str
    t_start: str
    t_end: str
    source: str
    confidence: str
    evidence: str


def _t(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def collapse(obs: list[Obs], gap_s: float = 3.0) -> list[Relation]:
    key = lambda o: (o.subject, o.predicate, o.object, o.object_type,
                     o.source, o.confidence)
    out: list[Relation] = []
    groups: dict[tuple, list[Obs]] = {}
    for o in obs:
        groups.setdefault(key(o), []).append(o)

    for k, items in groups.items():
        items.sort(key=lambda o: _t(o.timestamp))
        start = prev = items[0]
        for cur in items[1:]:
            if (_t(cur.timestamp) - _t(prev.timestamp)).total_seconds() > gap_s:
                out.append(Relation(*k[:4], start.timestamp, prev.timestamp,
                                    k[4], k[5], start.evidence))
                start = cur
            prev = cur
        out.append(Relation(*k[:4], start.timestamp, prev.timestamp,
                            k[4], k[5], start.evidence))

    out.sort(key=lambda r: (r.t_start, r.subject, r.predicate, r.object))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_collapse.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/vtmak/stkg/collapse.py new_VTMAK/tests/test_stkg_collapse.py
git commit -m "feat(stkg): tick 관측을 구간 관계로 축약

같은 (subject, predicate, object)가 연속되면 한 구간으로 접는다. 관측
공백은 이어붙이지 않고 나눈다. 입력의 완전중복 54.5%도 함께 사라진다."
```

---

### Task 7: `export.py` — 조립·회계·출력

**Files:**
- Create: `new_VTMAK/vtmak/stkg/export.py`
- Test: `new_VTMAK/tests/test_stkg_export.py`

**Interfaces:**
- Consumes: `filter.classify`, `filter.Disposition`, `predicate.parse`, `resolve.to_marking`, `locate.snap`, `derive.Obs`/`fired_by`/`load_munition_map`, `collapse.collapse`
- Produces:
  - `Tally` (dataclass: `total: int`, `relation_rows: int`, `position_rows: int`, `dropped: int`, `quarantined: int`, `unparsed: dict[str, int]`, `snap_hits: dict[str, int]`)
  - `build(rows, layout, uuid_map, munition_map, control_points=None) -> tuple[list[Relation], list[dict], Tally, list[str]]`
    - `rows`: `list[dict]` — CSV `DictReader` 행 그대로
    - 반환: (관계, 위치행, 회계, 미확정 사유)
  - `write_all(out_dir, relations, positions, tally, unresolved) -> None`

- [ ] **Step 1: Write the failing test**

`new_VTMAK/tests/test_stkg_export.py`:

```python
from pathlib import Path

import pytest

from vtmak.geometry import BattlefieldLayout
from vtmak.stkg.export import build

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def layout():
    return BattlefieldLayout.load(ROOT / "config" / "battlefield_layout.json")


def _row(subject, predicate, ts="2026-08-03T05:20:00.000Z",
         lat="21.3", lon="-157.7", source="GROUND_TRUTH"):
    return {"subject": subject, "predicate": predicate, "object": "-",
            "latitude": lat, "longitude": lon, "timestamp": ts,
            "source": source, "CID": "-1"}


def test_accounting_invariant_holds(layout):
    rows = [
        _row("1 Force", "None"),
        _row("E5", "None"),
        _row("ENT72003", "None", ts="1970-01-01T12:00:04.040Z"),
        _row("FRINF001", 'Follow-Entity Entity: "ENINF001" Offset: <-0 0 -0 >'),
        _row("FRINF002", "None"),
        _row("FRINF003", "Completely-Unknown-Task foo=1"),
    ]
    _, positions, tally, _ = build(rows, layout, {}, {})
    assert tally.total == len(rows)
    assert (tally.relation_rows + tally.position_rows
            + tally.dropped + tally.quarantined) == tally.total


def test_infra_and_effects_never_reach_output(layout):
    rows = [_row("1 Force", "None"), _row("GlobalEnv 1", "None"),
            _row("E9", "None"), _row("Observer 1", "None")]
    relations, positions, tally, _ = build(rows, layout, {}, {})
    assert relations == []
    assert positions == []
    assert tally.dropped == 4


def test_follow_entity_becomes_a_relation_with_an_object(layout):
    rows = [_row("FRINF001",
                 'Follow-Entity Entity: "ENINF001" Offset: <-0 0 -0 >')]
    relations, _, _, _ = build(rows, layout, {}, {})
    assert len(relations) == 1
    assert relations[0].predicate == "follows"
    assert relations[0].object == "ENINF001"
    assert relations[0].object_type == "entity"
    assert relations[0].confidence == "observed"


def test_none_predicate_goes_to_positions(layout):
    relations, positions, tally, _ = build([_row("FRINF001", "None")],
                                           layout, {}, {})
    assert relations == []
    assert len(positions) == 1
    assert positions[0]["subject"] == "FRINF001"
    assert positions[0]["kind"] == "entity"


def test_unresolvable_uuid_keeps_the_uuid_and_is_marked(layout):
    """짝이 되는 .oob이 없으면 uuid를 버리지 않고 표시한다."""
    rows = [_row("FRINF001",
                 'Move-To Waypoint: "62f22b9c-d768-531d-9242-e32d8a056ee9"')]
    relations, _, _, _ = build(rows, layout, {}, {})
    assert relations[0].object == "62f22b9c-d768-531d-9242-e32d8a056ee9"
    assert relations[0].object_type == "uuid"


def test_resolvable_uuid_becomes_a_marking(layout):
    rows = [_row("FRINF001",
                 'Move-To Waypoint: "62f22b9c-d768-531d-9242-e32d8a056ee9"')]
    umap = {"62f22b9c-d768-531d-9242-e32d8a056ee9": "P7"}
    relations, _, _, _ = build(rows, layout, umap, {})
    assert relations[0].object == "P7"
    assert relations[0].object_type == "waypoint"


def test_every_relation_has_a_non_empty_object(layout):
    rows = [_row("FRINF001",
                 "Move to {-5499123.141030, -2250320.406046, 2311025.754248}"),
            _row("FRINF002",
                 'Follow-Entity Entity: "ENINF001" Offset: <-0 0 -0 >')]
    relations, _, _, _ = build(rows, layout, {}, {})
    assert relations
    for rel in relations:
        assert rel.object


def test_a_relation_row_does_not_also_become_a_position(layout):
    """한 행은 관계 아니면 위치, 둘 중 하나다. 양쪽에 넣으면 회계가 맞아도
    파일 내용이 어긋난다."""
    rows = [_row("FRINF001",
                 'Follow-Entity Entity: "ENINF001" Offset: <-0 0 -0 >')]
    relations, positions, tally, _ = build(rows, layout, {}, {})
    assert len(relations) == 1
    assert positions == []
    assert tally.position_rows == 0
    assert tally.relation_rows == 1


def test_position_count_matches_the_positions_list(layout):
    rows = [_row("FRINF001", "None"), _row("FRINF002", "None"),
            _row("FRINF003",
                 'Follow-Entity Entity: "ENINF001" Offset: <-0 0 -0 >')]
    _, positions, tally, _ = build(rows, layout, {}, {})
    assert len(positions) == tally.position_rows == 2


def test_unparsed_predicates_are_counted_not_dropped(layout):
    rows = [_row("FRINF001", "Completely-Unknown-Task foo=1")]
    _, positions, tally, _ = build(rows, layout, {}, {})
    assert tally.unparsed == {"Completely-Unknown-Task foo=1": 1}
    assert len(positions) == 1   # 위치는 살린다
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vtmak.stkg.export'`

- [ ] **Step 3: Write minimal implementation**

`new_VTMAK/vtmak/stkg/export.py`:

```python
"""입력 행을 관계·위치 두 테이블로 가르고 회계를 맞춘다.

회계가 이 모듈의 핵심이다. 모든 입력 행은 관계·위치·제외·격리 중 정확히 한
갈래로 간다. 합이 안 맞으면 어딘가에서 조용히 사라진 것이므로 실패시킨다.

파싱 실패는 행을 버리는 사유가 아니다. 관계를 못 만들 뿐 위치는 살리고,
원문을 report에 적는다.
"""
from __future__ import annotations

import collections
import csv
from dataclasses import dataclass, field
from pathlib import Path

from ..geometry import Coord
from .collapse import Relation, collapse
from .derive import Obs, fired_by
from .filter import Disposition, classify
from .locate import snap
from .predicate import parse
from .resolve import to_marking

_MUNITION_HINT = ("M107 ", "M933HE ", "PAC-3 ")


@dataclass
class Tally:
    total: int = 0
    relation_rows: int = 0        # 관계에 기여한 행 (축약 전)
    position_rows: int = 0
    dropped: int = 0
    quarantined: int = 0
    unparsed: dict[str, int] = field(default_factory=dict)
    snap_hits: dict[str, int] = field(default_factory=dict)


def _ecef(blob: str) -> tuple[float, float, float]:
    x, y, z = (float(v) for v in blob.split(","))
    return x, y, z


def _is_munition(subject: str) -> bool:
    return subject.startswith(_MUNITION_HINT)


def build(rows, layout, uuid_map, munition_map, control_points=None):
    tally = Tally()
    obs: list[Obs] = []
    positions: list[dict] = []
    first_seen: dict[str, tuple[str, tuple[float, float, float], str]] = {}
    candidates: dict[str, list] = collections.defaultdict(list)

    for row in rows:
        tally.total += 1
        subject, ts = row["subject"], row["timestamp"]
        verdict = classify(subject, ts)
        if verdict in (Disposition.DROP_INFRA, Disposition.DROP_EFFECT):
            tally.dropped += 1
            continue
        if verdict is Disposition.QUARANTINE_EPOCH:
            tally.quarantined += 1
            continue

        kind = "projectile" if _is_munition(subject) else "entity"
        ecef = _ecef_of(row)
        source = row["source"]

        # fired_by 재료. 관계·위치 어느 갈래로 가든 필요하므로 먼저 모은다.
        # 키에 source를 넣는다 — 같은 발사체가 GT와 UAV 양쪽에 나오고,
        # 섞으면 UAV가 본 발사체가 GT가 본 박격포에 붙는다.
        # setdefault가 아니라 이른 시각으로 갱신한다. 입력 순서가 시각
        # 순서라는 보장이 없다(파일이 UAV → ground_truth 순으로 읽힌다).
        if kind == "projectile":
            key = (source, subject)
            if key not in first_seen or ts < first_seen[key][0]:
                first_seen[key] = (ts, ecef)
        else:
            candidates[(source, ts)].append((subject, ecef))

        raw = row["predicate"]
        p = parse(raw)
        if p is None:
            tally.unparsed[raw] = tally.unparsed.get(raw, 0) + 1
        elif p.predicate:
            obj, obj_type, evidence = _object_of(p, layout, uuid_map,
                                                 control_points, tally)
            obs.append(Obs(subject, p.predicate, obj, obj_type, ts,
                           row["source"], "observed", evidence))
            tally.relation_rows += 1
            continue          # 관계가 된 행은 위치 테이블로 가지 않는다

        positions.append({"subject": subject, "kind": kind,
                          "latitude": row["latitude"],
                          "longitude": row["longitude"],
                          "timestamp": ts, "source": row["source"]})
        tally.position_rows += 1

    derived, unresolved = fired_by(first_seen, candidates, munition_map) \
        if munition_map else ([], [])
    return collapse(obs + derived), positions, tally, unresolved


def _ecef_of(row) -> tuple[float, float, float]:
    """위경도를 ECEF 미터로. fired_by가 math.dist로 거리를 재므로 도 단위를
    그대로 넘기면 200m 임계가 아무 의미가 없어진다."""
    return Coord(float(row["latitude"]), float(row["longitude"]),
                 0.0).to_ecef()


def _object_of(p, layout, uuid_map, control_points, tally):
    if p.object_kind == "coord":
        result = snap(_ecef(p.object_raw), layout,
                      control_points=control_points)
        tally.snap_hits[result.object_type] = \
            tally.snap_hits.get(result.object_type, 0) + 1
        return (result.object_id, result.object_type,
                f"snap {result.distance_m:.1f}m")
    if p.object_kind == "uuid":
        marking = to_marking(p.object_raw, uuid_map)
        if marking is None:
            return p.object_raw, "uuid", "uuid 미해석"
        kind = "waypoint" if p.predicate == "moves_to" else "entity"
        return marking, kind, "uuid 해석"
    return p.object_raw, "entity", "predicate 원문"


def write_all(out_dir, relations, positions, tally, unresolved) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "relations.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["subject", "predicate", "object", "object_type",
                    "t_start", "t_end", "source", "confidence", "evidence"])
        for r in relations:
            w.writerow([r.subject, r.predicate, r.object, r.object_type,
                        r.t_start, r.t_end, r.source, r.confidence,
                        r.evidence])

    with open(out / "positions.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["subject", "kind", "latitude", "longitude",
                                "timestamp", "source"])
        w.writeheader()
        w.writerows(positions)

    lines = [
        "# STKG A단계 추출 보고", "",
        f"- 입력 행: {tally.total:,}",
        f"- 관계 기여 행(축약 전): {tally.relation_rows:,}",
        f"- 관계 구간: {len(relations):,}",
        f"- 위치 행: {tally.position_rows:,}",
        f"- 제외: {tally.dropped:,}",
        f"- 격리(1970 epoch): {tally.quarantined:,}", "",
        "## 좌표 스냅", "",
    ]
    total_snap = sum(tally.snap_hits.values()) or 1
    for kind, n in sorted(tally.snap_hits.items()):
        lines.append(f"- {kind}: {n:,} ({n / total_snap:.1%})")
    lines += ["", "## 미확정 fired_by", ""]
    lines += [f"- {u}" for u in unresolved] or ["- 없음"]
    lines += ["", "## 파싱 실패 술어", ""]
    lines += [f"- {n:,}행  `{raw[:120]}`"
              for raw, n in sorted(tally.unparsed.items(),
                                   key=lambda x: -x[1])] or ["- 없음"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd new_VTMAK && python -m pytest tests/test_stkg_export.py -v`
Expected: PASS — 10 passed

- [ ] **Step 5: Run the whole suite to check nothing regressed**

Run: `cd new_VTMAK && python -m pytest tests/ -q`
Expected: 새 테스트 전부 통과. 기존 실패 5건(`test_gates`·`test_roster`·`test_spec` ×2·`test_writer`)은 A단계와 무관한 선행 실패이므로 그대로여야 한다. **6건 이상 실패하면 멈추고 원인을 찾는다.**

- [ ] **Step 6: Commit**

```bash
git add new_VTMAK/vtmak/stkg/export.py new_VTMAK/tests/test_stkg_export.py
git commit -m "feat(stkg): 관계·위치 테이블 조립과 회계 검사

모든 입력 행이 관계·위치·제외·격리 중 정확히 한 갈래로 가고, 합이 안 맞으면
실패한다. 파싱 실패는 행을 버리는 사유가 아니라 위치는 살리고 원문을 보고한다."
```

---

### Task 8: `scripts/06_stkg_export.py` — CLI와 실데이터 실측

**Files:**
- Create: `new_VTMAK/scripts/06_stkg_export.py`
- Modify: `new_VTMAK/RUNBOOK.md` (실행 절차에 06 추가)

**Interfaces:**
- Consumes: `vtmak.stkg.export.build`/`write_all`, `vtmak.stkg.resolve.load_uuid_map`, `vtmak.stkg.derive.load_munition_map`, `vtmak.geometry.BattlefieldLayout`
- Produces: `build/stkg/relations.csv`, `build/stkg/positions.csv`, `build/stkg/report.md`

- [ ] **Step 1: Write the script**

`new_VTMAK/scripts/06_stkg_export.py`:

```python
"""시뮬레이터 CSV → STKG 관계 테이블 + 위치 테이블 (A단계).

재시뮬이 필요 없다. build/csv/*.csv만 읽는다.
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Windows 기본 콘솔은 cp949라 보고의 '—' 같은 문자에서 죽는다.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from vtmak.geometry import BattlefieldLayout                 # noqa: E402
from vtmak.stkg.derive import load_munition_map              # noqa: E402
from vtmak.stkg.export import build, write_all               # noqa: E402
from vtmak.stkg.resolve import load_uuid_map                 # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-dir", default=str(ROOT / "build" / "csv"))
    ap.add_argument("--out", default=str(ROOT / "build" / "stkg"))
    ap.add_argument("--oob", default="",
                    help="CSV와 짝이 되는 .oob. 없으면 uuid를 해석하지 않는다")
    args = ap.parse_args()

    paths = sorted(glob.glob(str(Path(args.csv_dir) / "*_dataset.csv")))
    if not paths:
        print(f"{args.csv_dir}에 *_dataset.csv 없음")
        return 1

    rows = []
    for p in paths:
        with open(p, encoding="utf-8", newline="") as fh:
            rows.extend(csv.DictReader(fh))
    print(f"입력 {len(paths)}개 파일 · {len(rows):,}행")

    layout = BattlefieldLayout.load(ROOT / "config" / "battlefield_layout.json")
    uuid_map = load_uuid_map(args.oob) if args.oob else {}
    if not uuid_map:
        print("  uuid 표 없음 — Move-To Waypoint / Target-entity task의 "
              "uuid는 원문을 유지한다(--oob로 짝이 되는 .oob를 줄 것)")
    munition_map = load_munition_map(ROOT / "config" / "munition_map.csv")

    relations, positions, tally, unresolved = build(
        rows, layout, uuid_map, munition_map)
    write_all(args.out, relations, positions, tally, unresolved)

    accounted = (tally.relation_rows + tally.position_rows
                 + tally.dropped + tally.quarantined)
    print(f"관계 구간 {len(relations):,} (기여 행 {tally.relation_rows:,}) · "
          f"위치 {tally.position_rows:,} · 제외 {tally.dropped:,} · "
          f"격리 {tally.quarantined:,}")
    if accounted != tally.total:
        print(f"회계 불일치: {accounted:,} != {tally.total:,} — 행이 "
              f"조용히 사라졌다")
        return 1
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it on the real data**

Run: `cd new_VTMAK && python scripts/06_stkg_export.py`
Expected: 회계 일치, 종료 코드 0. 입력 **130,523행**
(GT 126,718 + UAV 1 1,227 + UAV 2 1,281 + UAV 3 609 + UAV 4 688).

기대 분해 — 실측에서 유도한 값이다. 크게 어긋나면 멈추고 원인을 찾는다.

```
제외        5,072행   Force 2,586 + Observer 1,624 + GlobalEnv 862
격리            0행   1970 epoch 없음
관계 기여   95,020행   Move to 62,064 + Follow-Entity 31,920 + FFE 1,035 + find_cover 1
위치       30,431행   None 35,503 중 제외분을 뺀 나머지 + 발사체 113
```

`fired_by`는 GROUND_TRUTH 4건이 관계로, UAV 2의 3건이 미확정으로 나와야 한다.

- [ ] **Step 3: Verify the output by hand**

```bash
cd new_VTMAK
head -3 build/stkg/relations.csv
cat build/stkg/report.md
python -c "
import csv,collections
rs=list(csv.DictReader(open('build/stkg/relations.csv',encoding='utf-8')))
print('관계 구간',len(rs))
print('술어별',dict(collections.Counter(r['predicate'] for r in rs)))
print('object 빈 행',sum(1 for r in rs if not r['object']))
print('object_type별',dict(collections.Counter(r['object_type'] for r in rs)))
"
```

확인할 것:
- `object` 빈 행이 **0건**이어야 한다. 이 작업의 목적 자체다.
- 제외 대상(`1 Force`·`Observer 1`·`GlobalEnv 1`)이 `relations.csv`·
  `positions.csv` 어디에도 없어야 한다.
- `report.md`의 스냅 비율이 **`location` 100%** 여야 한다. `coord` 폴백이
  하나라도 있으면 좌표계가 어긋난 것이니 멈추고 원인을 찾는다.
- 술어는 `moves_to` · `follows` · `fires_at` · `takes_cover_from` ·
  `fired_by` 5종만 나온다. `engages`·`suppresses`는 이번 CSV에 재료가 없다.
- `fired_by` 미확정에 UAV 2의 `M933HE 1/2/3`이 사유와 함께 올라와 있어야 한다.
- 파싱 실패 술어가 **0건**이어야 한다. 어휘 6종을 전부 다루도록 만들었다.

그리고 스펙 §12의 통합 검증 하나를 여기서 마저 돌린다 — `object_type=entity`
인 모든 `object`가 실제 `.oob`의 marking에 존재하는가.

```bash
cd new_VTMAK && python -c "
import csv,re
oob=open('build/scnx/battle.oob',encoding='utf-8').read() if False else None
import zipfile
with zipfile.ZipFile('build/scnx/battle.scnx') as z:
    oob=z.read('battle.oob').decode('utf-8','replace')
marks=set(re.findall(r'\(marking-text \"([^\"]*)\"',oob))
rs=list(csv.DictReader(open('build/stkg/relations.csv',encoding='utf-8')))
ents={r['object'] for r in rs if r['object_type']=='entity'}
missing=sorted(ents-marks)
print('entity object 고유',len(ents),'· .oob에 없는 것',len(missing))
print(missing[:20])
"
```

17:22 CSV는 현재 빌드와 정확히 일치하므로 **없는 것이 0건이어야 한다.**
하나라도 나오면 멈추고 원인을 찾는다.

- [ ] **Step 4: Record the measured numbers in RUNBOOK**

`RUNBOOK.md`의 실행 절차에 한 줄 추가:

```
python scripts/06_stkg_export.py   # CSV → STKG 관계·위치 테이블 (A단계)
```

그리고 Step 3에서 실제로 나온 숫자(관계 구간 수, 술어별 분포, 스냅 비율)를
같은 절에 적는다. 계획서의 기대치가 아니라 **실제 출력**을 적는다.

- [ ] **Step 5: Commit**

```bash
git add new_VTMAK/scripts/06_stkg_export.py new_VTMAK/RUNBOOK.md
git commit -m "feat(stkg): CSV → STKG 테이블 추출 스크립트

build/csv/*.csv를 읽어 relations.csv·positions.csv·report.md를 낸다.
재시뮬 불필요. 회계가 안 맞으면 종료 코드 1로 실패한다."
```

---

## 완료 기준

- [ ] `python -m pytest tests/test_stkg_*.py -q` 전부 통과
- [ ] `python -m pytest tests/ -q` 실패가 기존 5건에서 늘지 않음
- [ ] `python scripts/06_stkg_export.py` 종료 코드 0 (회계 일치)
- [ ] `relations.csv`의 `object` 빈 행 0건
- [ ] `object_type=entity`인 `object` 중 `.oob`에 없는 것 0건
- [ ] 좌표 스냅 `coord` 폴백 0건, 파싱 실패 술어 0건
- [ ] `report.md`에 스냅 비율·미확정 `fired_by`·파싱 실패 술어가 적혀 있음

## A단계가 끝나도 남는 것

계획 밖이지만 기록해 둔다. 완료 보고에 함께 적을 것.

- **GT↔UAV 시간대 불일치** (GT 08:09~08:16, UAV 22:00~22:07, 겹침 0초).
  관계 테이블이 좋아져도 관측 성능은 못 낸다. 다만 길이가 431초 대 424초로
  거의 같아져 오프셋 정렬 여지가 생겼다. C단계 몫이다.
- **`fires_at`의 object가 아직 위치뿐**이다. 엔티티 표적은 B단계에서
  `fire-at-target` 저작이 들어가야 생긴다. 이번 CSV의 `engages` 재료
  (`Target-entity task`)는 0건이다.
- **`suppresses` 0건.** `provide_suppressive_fire_loc`이 이번 CSV에 안 나온다.
  PLN에는 25개 저작돼 있는데 내보내기에 안 잡히는 것이라, 왜인지는 C단계에서
  확인한다.
- **`find_cover` 1건뿐.** PLN에 25개 저작돼 있는데 실행이 1회다. 반응행동이
  거의 발동하지 않았다는 뜻이라, 시나리오 쪽 문제일 수 있다.
- **이동 불가 10기 문제 여전.** 박격포·대공화기·M901에 이동 태스크가 남아
  있고 VR-Forces가 버린다. B단계에서 처리한다.
