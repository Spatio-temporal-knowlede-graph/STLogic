# 원문 어휘 → VR-Forces task 매핑 확대 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 원문이 서술하지만 지금 버려지는 문장 221건을 VR-Forces task로 저작해 `.pln`의 task type을 7종에서 10종으로 늘린다.

**Architecture:** `plan.py`에 하드코딩된 세 개의 표(`LABEL_CANDIDATES`·`REF_FIELD`·`FIRE_KIND`)가 `task_catalog.csv`의 33종 행동 중 8종만 도달 가능하게 막고 있다. 이 셋을 `config/task_kinds.csv` 한 장으로 빼서 매핑 추가를 CSV 두 줄짜리 작업으로 만든 뒤, 그 위에 새 매핑 셋(`wait-duration`·`방향 조준`·`find_firing_position`)을 얹는다.

**Tech Stack:** Python 3.13, pytest, CSV(UTF-8/CRLF) 설정 파일, VR-Forces `.scnx`(S-expression + zip)

**설계 문서:** `docs/superpowers/specs/2026-08-05-task-mapping-expansion-design.md`

## Global Constraints

- 작업 디렉터리는 `C:\Users\user\OneDrive\문서\Cybermarine system lab\STKG\STKG_Experiments\new_VTMAK`다. 이 문서의 모든 상대 경로는 여기 기준이다.
- 콘솔이 cp949라 한글 출력이 죽는다. 모든 명령 앞에 `PYTHONIOENCODING=utf-8`을 붙인다(Bash). PowerShell이면 `$env:PYTHONIOENCODING='utf-8'`을 먼저 실행한다.
- `config/*.csv`는 **UTF-8(BOM 없음) · CRLF**다. 손으로 편집하지 말고 Python `csv` 모듈로 읽고 쓴다(`lineterminator="\r\n"`). 따옴표 이스케이프를 손으로 하면 반드시 틀린다.
- **`Path.read_text()`로 읽어서 다시 쓰지 않는다.** 유니버설 개행이라 CRLF를 `\n`으로 바꿔 읽고, 그대로 쓰면 **기존 행 전부의 줄바꿈이 LF로 뭉개진다.** Task 3에서 실제로 걸렸다. 읽기는 `p.read_bytes().decode("utf-8-sig")`에 `io.StringIO(..., newline="")`, 쓰기는 `csv.DictWriter(..., lineterminator="\r\n")`로 전체를 왕복시킨다. 아래 Task 3의 스크립트 예시 중 `read_text`를 쓰는 것들은 이 규칙 이전에 쓰인 것이라 그대로 따라 하면 안 된다.
- CSV를 고친 뒤에는 바이트로 확인한다: `raw.count(b"\r\n")`과 `raw.count(b"\n")`이 같고 BOM이 없어야 한다.
- **커밋할 때 `git add -A`를 쓰지 않는다.** 작업 트리에 무관한 진행 중 변경이 쌓여 있다. 각 Task가 지정한 파일만 `git add <path>`로 담는다.
- 폴백을 만들지 않는다. 설정이 없거나 키가 빠지면 조용히 noop이 되는 대신 예외나 게이트 차단으로 드러나야 한다. 이 저장소의 기존 원칙이다.
- 주석과 문서는 한국어로 쓴다. 기존 파일의 밀도와 어조를 따른다 — 무엇을 하는지가 아니라 **왜 그런지**를 적는다.
- 새 문법을 확인 없이 지어내지 않는다. S-expression은 `campaign/campaign.pln`·`yewon_test/`·`config/task_catalog.csv`에서 수확한다. 확인 못 한 값은 `# VERIFY-ON-TARGET`으로 표시한다.
- 기존 테스트 중 `tests/test_roster.py::test_preserves_every_engagement_kind`는 **이 작업 전부터 실패한다.** 새로 깨진 것이 아니다. 다른 테스트가 깨지면 그건 이 작업 탓이다.
- **테스트와 파이프라인이 보는 명부가 다르다.** `scripts/02_parse_events.py`는 명부 감축을 하지 않아 328객체를 낸다. `tests/test_spec.py::_build()`는 `roster.json`으로 200객체까지 줄인다. 그래서 같은 매핑이라도 테스트가 세는 건수가 04가 세는 건수보다 적다(실측: `stopAt` 56 vs 102, `aimAt` 13 vs 21, 사격 준비 전이 13 vs 21). **테스트에 건수를 못 박지 않는다.** 04 출력의 건수는 사람이 눈으로 확인하는 값이지 테스트 단언이 아니다.
- 임시 스크립트는 저장소 안(`scratch/` 등)에 만들지 않는다. 세션 스크래치패드 디렉터리에 만들고 쓰고 나면 지운다. 저장소에 남으면 다음 `git add`에 딸려 들어간다.
- `pytest` 통과 개수(`208 passed` 등)는 **참고값**이다. 못 박아야 하는 것은 "실패가 `test_preserves_every_engagement_kind` 하나뿐"이라는 사실이다.

---

## 파일 구조

| 파일 | 책임 | Task |
|---|---|---|
| `config/task_kinds.csv` | **신규.** task_kind → 참조 필드 · 사거리 종류 · 행동 후보 | 1 |
| `vtmak/scnx/catalog.py` | `TaskKinds` 로더 추가. 기존 `TaskCatalog`·`DisCatalog`와 같은 자리 | 1 |
| `vtmak/scnx/plan.py` | 세 코드 표 제거, `TaskKinds` 사용. 참조 없는 kind 허용. `next_fire_target` 해석 | 1, 3, 5 |
| `vtmak/scnx/spec.py` | `build_spec`이 `TaskKinds`를 받아 `build_entity_plan`에 넘김 | 1 |
| `scripts/04_compile_scnx.py` | `TaskKinds` 로드 | 1 |
| `vtmak/parser.py` | `PatternMap`이 상태전이를 읽음. 메서드 이름 변경 | 2 |
| `config/pattern_map.csv` | `stopAt`·`stayAt`·`aimAt` 매핑 변경, `state_transition` 행 추가 | 2, 3, 4, 5 |
| `config/task_catalog.csv` | `대기` 3행 · `방향 조준` 3행 · `사격위치 탐색` 1행 추가 | 3, 4, 5 |
| `vtmak/geometry.py` | `bearing_elevation()` 추가 | 4 |
| `tests/test_task_kinds.py` | **신규.** `TaskKinds` 로더 단위 테스트 | 1 |
| `tests/test_parser.py` | 상태전이 읽기 테스트 추가 | 2 |
| `tests/test_spec.py` | 새 매핑 3종의 저작 결과 테스트 추가 | 3, 4, 5 |
| `tests/test_geometry.py` | `bearing_elevation` 테스트 추가 | 4 |
| `README.md` · `RUNBOOK.md` | 새 매핑과 측정 라운드 절차 | 6 |

---

## Task 1: `task_kinds.csv`로 코드 표 세 개를 뺀다

동작을 바꾸지 않는 리팩터링이다. **기존 테스트가 전부 그대로 통과해야 하고, 저작 결과가 달라지면 안 된다.** 그것이 이 Task의 합격 기준이다.

**Files:**
- Create: `config/task_kinds.csv`
- Create: `tests/test_task_kinds.py`
- Modify: `vtmak/scnx/catalog.py` (끝에 `TaskKind`·`TaskKinds` 추가)
- Modify: `vtmak/scnx/plan.py:33-61` (세 표 제거), `:93-200` (배선)
- Modify: `vtmak/scnx/spec.py:146-151, 183-186` (파라미터 통과)
- Modify: `scripts/04_compile_scnx.py`
- Modify: `tests/test_spec.py`, `tests/test_writer.py`, `tests/test_fixed_objects.py`, `tests/test_roster.py` (build_spec 호출부)

**Interfaces:**
- Consumes: `vtmak.norm.norm`, `vtmak.scnx.catalog._rows`
- Produces:
  - `TaskKind(task_kind: str, ref_kind: str, ref_field: str, fire_kind: str, labels: tuple[str, ...], note: str)` — frozen dataclass
  - `TaskKinds.load(path) -> TaskKinds`
  - `TaskKinds.get(task_kind: str, ref_kind: str) -> TaskKind | None`
  - `TaskKinds.ref_field(task_kind: str) -> str`
  - `TaskKinds.fire_kind(task_kind: str) -> str`
  - `TaskKinds.known(task_kind: str) -> bool`
  - `build_entity_plan(events, entity, pattern_map, catalog, kinds, ranges, ctx, fire_distance, suppression=None)` — `kinds`가 5번째 위치 인자로 삽입됨
  - `build_spec(events, registry, layout, pattern_map, catalog, kinds, dis, ranges, scenario_id, seed="", fixed=None)` — `kinds`가 6번째 위치 인자로 삽입됨

---

- [ ] **Step 1: `config/task_kinds.csv`를 만든다**

기존 세 표를 그대로 옮긴 것이다. 값을 새로 정하지 않는다 — `plan.py:33-61`을 열어 한 줄씩 대조한다.

다음 스크립트를 실행한다(CRLF·따옴표를 손으로 쓰지 않기 위해서다).

```python
# scratch/write_task_kinds.py 로 저장 후 실행, 끝나면 지운다
import csv, io
from pathlib import Path

HEADER = ["task_kind", "ref_kind", "참조_필드", "사거리_종류", "행동_후보", "비고"]
ROWS = [
    ["move", "COORD", "dst", "", "좌표로 이동|통제점으로 이동", ""],
    ["move", "ENTITY", "dst", "", "좌표로 이동|통제점으로 이동", ""],
    ["move_slow", "COORD", "dst", "", "좌표로 이동|통제점으로 이동",
     "저속 보급 기동 — plan.py가 set-speed를 앞에 붙인다"],
    ["fire_direct", "ENTITY", "target", "direct", "대상 직접사격|대상 자동무장 사격", ""],
    ["fire_direct", "COORD", "target", "direct", "대상 직접사격", ""],
    ["fire_indirect", "COORD", "target", "indirect", "좌표 대상 간접사격", ""],
    ["fire_indirect", "ENTITY", "target", "indirect",
     "Entity 대상 간접사격|좌표 대상 간접사격", ""],
    ["aim", "ENTITY", "target", "indirect", "객체 조준", ""],
    ["aim", "COORD", "target", "indirect", "객체 조준", ""],
    ["suppress", "ENTITY", "target", "direct", "제압사격", "표적 좌표만 필요(uuid 불필요)"],
    ["suppress", "COORD", "target", "direct", "제압사격", ""],
    ["take_cover", "ENTITY", "source_obj", "", "피격 후 엄폐", "Threat = 피격 원천 객체"],
    ["follow", "ENTITY", "unit_leader", "", "대형 추종 이동", "부대 선두를 추종"],
]
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\r\n")
w.writerow(HEADER)
w.writerows(ROWS)
Path("config/task_kinds.csv").write_bytes(buf.getvalue().encode("utf-8"))
print("rows", len(ROWS))
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_task_kinds.py`를 새로 만든다.

```python
"""task_kinds.csv — plan.py의 코드 표 세 개를 대체한 사전."""
from pathlib import Path

import pytest

from vtmak.scnx.catalog import TaskKinds

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config"


@pytest.fixture(scope="module")
def kinds():
    return TaskKinds.load(CFG / "task_kinds.csv")


def test_ref_kind_selects_a_different_label_list(kinds):
    """같은 kind라도 참조가 객체냐 좌표냐에 따라 후보가 갈린다."""
    assert kinds.get("fire_direct", "ENTITY").labels == (
        "대상 직접사격", "대상 자동무장 사격")
    assert kinds.get("fire_direct", "COORD").labels == ("대상 직접사격",)


def test_ref_field_and_fire_kind_are_per_task_kind(kinds):
    assert kinds.ref_field("take_cover") == "source_obj"
    assert kinds.ref_field("follow") == "unit_leader"
    assert kinds.ref_field("move") == "dst"
    assert kinds.fire_kind("fire_indirect") == "indirect"
    assert kinds.fire_kind("move") == ""


def test_unknown_kind_is_not_silently_empty(kinds):
    """조용히 빈 값을 주면 왜 task가 안 나오는지 .scnx를 열기 전엔 모른다."""
    assert kinds.get("없는kind", "ENTITY") is None
    assert not kinds.known("없는kind")
    with pytest.raises(KeyError, match="없는kind"):
        kinds.ref_field("없는kind")


def test_conflicting_rows_are_an_error(tmp_path):
    """같은 kind의 두 행이 참조 필드를 다르게 적으면 어느 쪽이 맞는지 알 수 없다."""
    p = tmp_path / "task_kinds.csv"
    p.write_text(
        "task_kind,ref_kind,참조_필드,사거리_종류,행동_후보,비고\r\n"
        "move,COORD,dst,,좌표로 이동,\r\n"
        "move,ENTITY,target,,좌표로 이동,\r\n",
        encoding="utf-8", newline="")
    with pytest.raises(ValueError, match="참조_필드"):
        TaskKinds.load(p)


def test_wildcard_ref_kind_matches_anything(tmp_path):
    p = tmp_path / "task_kinds.csv"
    p.write_text(
        "task_kind,ref_kind,참조_필드,사거리_종류,행동_후보,비고\r\n"
        "wait,*,,,대기,참조 대상 없음\r\n",
        encoding="utf-8", newline="")
    k = TaskKinds.load(p)
    assert k.get("wait", "COORD").labels == ("대기",)
    assert k.get("wait", "ENTITY").labels == ("대기",)
    assert k.ref_field("wait") == ""
```

- [ ] **Step 3: 테스트가 실패하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_task_kinds.py -v`
Expected: FAIL — `ImportError: cannot import name 'TaskKinds' from 'vtmak.scnx.catalog'`

- [ ] **Step 4: `TaskKinds`를 구현한다**

`vtmak/scnx/catalog.py` 맨 끝에 붙인다.

```python
@dataclass(frozen=True)
class TaskKind:
    task_kind: str
    ref_kind: str            # COORD | ENTITY | * (무관)
    ref_field: str           # Event의 필드 이름. 빈 값 = 참조 대상 없음
    fire_kind: str           # direct | indirect | 빈 값(사거리 검사 안 함)
    labels: tuple[str, ...]  # task_catalog '행동' 이름, 우선순위 순
    note: str


class TaskKinds:
    """task_kind → 참조 필드 · 사거리 종류 · 행동 후보.

    예전에는 plan.py에 LABEL_CANDIDATES·REF_FIELD·FIRE_KIND 세 개의 dict로
    박혀 있었다. 그래서 매핑 하나를 늘리려면 CSV 두 장과 코드 세 곳을 같이
    고쳐야 했고, task_catalog에 템플릿이 있는 행동 33종 중 8종만 도달 가능했다.

    참조_필드와 사거리_종류는 task_kind 하나에 하나뿐이다(ref_kind별로 갈리지
    않는다). 여러 행에 다르게 적혀 있으면 어느 쪽이 맞는지 알 수 없으므로
    로드 시점에 예외로 세운다.
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], TaskKind] = {}
        self._ref: dict[str, str] = {}
        self._fire: dict[str, str] = {}

    @classmethod
    def load(cls, path) -> "TaskKinds":
        k = cls()
        for r in _rows(Path(path)):
            kind = r["task_kind"].strip()
            if not kind:
                continue
            t = TaskKind(
                kind,
                r["ref_kind"].strip() or "*",
                r["참조_필드"].strip(),
                r["사거리_종류"].strip(),
                tuple(x.strip() for x in r["행동_후보"].split("|") if x.strip()),
                (r.get("비고") or "").strip(),
            )
            for field, store in (("참조_필드", (t.ref_field, k._ref)),
                                 ("사거리_종류", (t.fire_kind, k._fire))):
                value, table = store
                if kind in table and table[kind] != value:
                    raise ValueError(
                        f"task_kinds.csv: {kind}의 {field}가 행마다 다르다 "
                        f"({table[kind]!r} vs {value!r})")
                table[kind] = value
            k._by_key[(kind, t.ref_kind)] = t
        return k

    def known(self, task_kind: str) -> bool:
        return task_kind in self._ref

    def get(self, task_kind: str, ref_kind: str) -> TaskKind | None:
        return (self._by_key.get((task_kind, ref_kind))
                or self._by_key.get((task_kind, "*")))

    def ref_field(self, task_kind: str) -> str:
        if task_kind not in self._ref:
            raise KeyError(f"task_kinds.csv에 없는 task_kind: {task_kind}")
        return self._ref[task_kind]

    def fire_kind(self, task_kind: str) -> str:
        if task_kind not in self._fire:
            raise KeyError(f"task_kinds.csv에 없는 task_kind: {task_kind}")
        return self._fire[task_kind]
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_task_kinds.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: `plan.py`에서 세 표를 지우고 `TaskKinds`를 쓴다**

`vtmak/scnx/plan.py`에서 `LABEL_CANDIDATES`(33-48행), `FIRE_KIND`(51-52행), `REF_FIELD`(55-58행)를 **지우고** 다음으로 바꾼다.

```python
# (task_kind, ref_kind) → 행동 후보, 참조 필드, 사거리 종류는 이제
# config/task_kinds.csv에 있다. 여기에 표를 두면 매핑 하나를 늘릴 때마다
# CSV 두 장과 코드 세 곳을 같이 고쳐야 하고, 실제로 그래서 task_catalog의
# 행동 33종 중 8종만 도달 가능한 상태로 굳어 있었다.
```

이어 함수 넷의 시그니처와 본문을 바꾼다.

```python
def build_entity_plan(events: list[Event], entity: EntityDef,
                      pattern_map: PatternMap, catalog: TaskCatalog,
                      kinds: TaskKinds,
                      ranges: WeaponRanges, ctx: PlanContext,
                      fire_distance: dict[str, float],
                      suppression: set[str] | None = None) -> list[PlanStep]:
    suppression = suppression or set()
    steps: list[PlanStep] = []
    ordered = sorted(events, key=lambda x: (x.time_s, x.event_id))
    for e in ordered:
        kind = pattern_map.task_kind_of(e)
        if kind in ("", "noop"):
            continue
        if kind == "fire_direct" and e.event_id in suppression:
            kind = "suppress"
        steps.extend(_one(e, entity, kind, catalog, kinds, ranges, ctx,
                          fire_distance, ordered))
    return steps


def _resolve_ref(e: Event, kind: str, ctx: PlanContext,
                 kinds: TaskKinds) -> str:
    field = kinds.ref_field(kind)
    if field == "unit_leader":
        return ctx.unit_leader(e.actor) or ""
    return getattr(e, field, "") or e.dst or e.target


def _pick_template(kind: str, ref_kind: str, type_group: str,
                   catalog: TaskCatalog, kinds: TaskKinds):
    spec = kinds.get(kind, ref_kind)
    if spec is None:
        return None, None
    for label in spec.labels:
        t = catalog.get(type_group, label)
        if t is not None:
            return t, label
    return None, None
```

`_one`은 시그니처만 바꾼다. 본문의 `FIRE_KIND.get(kind)`는 `kinds.fire_kind(kind) or None`로, `_resolve_ref(e, kind, ctx)`는 `_resolve_ref(e, kind, ctx, kinds)`로, `_pick_template(kind, ref_kind, entity.type_group, catalog)`는 끝에 `, kinds`를 더한다. `move_slow` 분기의 재귀 호출 `_one(e, entity, "move", catalog, ranges, ctx, fire_distance)`도 새 시그니처에 맞춘다.

```python
def _one(e: Event, entity: EntityDef, kind: str, catalog: TaskCatalog,
         kinds: TaskKinds, ranges: WeaponRanges, ctx: PlanContext,
         fire_distance: dict[str, float],
         actor_events: list[Event]) -> list[PlanStep]:
    step = PlanStep(e.event_id, e.time_s, e.template, kind, None, None)
    if not kinds.known(kind):
        step.issues.append(f"task_kinds.csv에 없는 task_kind: {kind}")
        return [step]
    ref = _resolve_ref(e, kind, ctx, kinds)
    if not ref:
        if kind == "follow":
            return _one(e, entity, "move", catalog, kinds, ranges, ctx,
                        fire_distance, actor_events)
        step.issues.append("참조 대상 없음")
        return [step]
    ...
```

`actor_events`는 Task 5에서 쓴다. 지금은 받아만 두고 쓰지 않는다.

`import` 줄에 `TaskKinds`를 더한다.

```python
from .catalog import TaskCatalog, TaskKinds
```

- [ ] **Step 7: `spec.py`가 `TaskKinds`를 통과시킨다**

`vtmak/scnx/spec.py`:

```python
from .catalog import DisCatalog, TaskCatalog, TaskKinds
```

```python
def build_spec(events: list[Event], registry: dict[str, EntityDef],
               layout: BattlefieldLayout, pattern_map: PatternMap,
               catalog: TaskCatalog, kinds: TaskKinds,
               dis: DisCatalog, ranges: WeaponRanges,
               scenario_id: str, seed: str = "",
               fixed: list[FixedObject] | None = None) -> ScnxSpec:
```

`build_entity_plan` 호출부:

```python
        spec.entity_plans[oid] = build_entity_plan(
            by_actor[oid], d, pattern_map, catalog, kinds, ranges, ctx,
            fire_distance, suppression)
```

- [ ] **Step 8: 호출부 다섯 곳을 고친다**

`scripts/04_compile_scnx.py`:

```python
from vtmak.scnx.catalog import DisCatalog, TaskCatalog, TaskKinds
```

```python
    spec = build_spec(events, registry, layout, pmap,
                      TaskCatalog.load(CFG / "task_catalog.csv"),
                      TaskKinds.load(CFG / "task_kinds.csv"),
                      dis, ranges,
                      scenario_id="battle", fixed=fixed)
```

`tests/test_spec.py`·`tests/test_writer.py`·`tests/test_fixed_objects.py`도 같은 자리에 `TaskKinds.load(cfg / "task_kinds.csv")`를 6번째 인자로 넣고 import를 더한다. `tests/test_roster.py`는 `build_spec`을 부르지 않으면 손대지 않는다 — 먼저 `grep -n "build_spec" tests/test_roster.py`로 확인한다.

- [ ] **Step 9: 전체 테스트로 동작이 안 바뀐 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: `1 failed, 208 passed` — 실패는 `test_preserves_every_engagement_kind` 하나뿐이어야 한다(Global Constraints의 기존 실패). 다른 게 깨졌으면 표를 잘못 옮긴 것이다. `plan.py`의 삭제한 세 dict를 git에서 꺼내(`git show HEAD:vtmak/scnx/plan.py`) 한 줄씩 대조한다.

- [ ] **Step 10: 커밋**

```bash
git add config/task_kinds.csv tests/test_task_kinds.py vtmak/scnx/catalog.py vtmak/scnx/plan.py vtmak/scnx/spec.py scripts/04_compile_scnx.py tests/test_spec.py tests/test_writer.py tests/test_fixed_objects.py
git commit -m "refactor(scnx): plan.py의 매핑 표 3개를 config/task_kinds.csv로"
```

---

## Task 2: `PatternMap`이 상태전이를 읽는다

**Files:**
- Modify: `vtmak/parser.py:114-140` (`PatternMap`), `:170-180` (`parse_scenario`)
- Modify: `vtmak/scnx/plan.py` (호출부 1곳)
- Modify: `tests/test_parser.py`
- Modify: `tests/test_spec.py`, `tests/test_writer.py`, `tests/test_fixed_objects.py`, `tests/test_roster.py` (`task_kind(` 호출부)

**Interfaces:**
- Consumes: Task 1의 변경 없음
- Produces:
  - `PatternMap.predicate_of(template: str, action_label: str, state_from: str, state_to: str) -> str`
  - `PatternMap.task_kind_of(event: Event) -> str`
  - 옛 이름 `predicate()`·`task_kind()`는 **삭제한다.** 남겨 두면 상태 인자를 안 넘긴 호출부가 조용히 다른 답을 받는다. 지우면 `AttributeError`로 즉시 드러난다.
  - `pattern_map.csv`의 `kind` 열에 `state_transition` 추가. `key`는 `<이전 상태>><다음 상태>` 형식(구분자 `>`)

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_parser.py` 끝에 붙인다.

```python
def test_state_transition_row_overrides_the_template_row(tmp_path):
    """상태전이는 template보다 구체적이라 우선한다.

    stateChange 1,294건 중 1,226건은 같은 시각 같은 객체에 이미 task를 내는
    이벤트가 붙어 있다(2026-08-05 실측). 그래서 template 단위로 task를 주면
    중복이다. 짝이 없는 전이만 골라 쓰려면 전이 단위 키가 있어야 한다.
    """
    p = tmp_path / "pattern_map.csv"
    p.write_text(
        "key,kind,predicate,task_kind,note\n"
        "stateChange,template,stateChangedTo,noop,\n"
        "사격 준비 대기>사격 준비,state_transition,preparesFiringPosition,find_fp,\n",
        encoding="utf-8", newline="")
    pm = PatternMap.load(p)

    hit = Event(event_id="E1", time_s=0, line_no=1, predicate="",
                template="stateChange", actor="FR-MORT-001",
                state_from="사격 준비 대기", state_to="사격 준비")
    miss = Event(event_id="E2", time_s=0, line_no=1, predicate="",
                 template="stateChange", actor="FR-INF-001",
                 state_from="기동", state_to="후퇴")

    assert pm.task_kind_of(hit) == "find_fp"
    assert pm.task_kind_of(miss) == "noop"
    assert pm.predicate_of("stateChange", "", "사격 준비 대기", "사격 준비") \
        == "preparesFiringPosition"
    assert pm.predicate_of("stateChange", "", "기동", "후퇴") == "stateChangedTo"


def test_move_action_still_wins_over_template(tmp_path):
    """기존 move_action 우선순위가 그대로여야 한다(회귀 방지)."""
    p = tmp_path / "pattern_map.csv"
    p.write_text(
        "key,kind,predicate,task_kind,note\n"
        "moveTo,template,moveTo,move,\n"
        "공격 대형 이동,move_action,approach,follow,\n",
        encoding="utf-8", newline="")
    pm = PatternMap.load(p)
    e = Event(event_id="E1", time_s=0, line_no=1, predicate="",
              template="moveTo", actor="FR-INF-001",
              action_label="공격 대형 이동")
    assert pm.task_kind_of(e) == "follow"
    assert pm.predicate_of("moveTo", "공격 대형 이동", "", "") == "approach"
```

`tests/test_parser.py` 상단 import에 `Event`를 더한다: `from vtmak.parser import Event, PatternMap, parse_scenario` (기존 import 줄을 확인하고 맞춘다).

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_parser.py -k state_transition -v`
Expected: FAIL — `AttributeError: 'PatternMap' object has no attribute 'task_kind_of'`

- [ ] **Step 3: `PatternMap`을 고친다**

`vtmak/parser.py`의 `PatternMap` 전체를 바꾼다.

```python
class PatternMap:
    """원문 문장 종류 → 술어 + task_kind.

    키가 셋이고 구체적인 쪽이 이긴다.
      state_transition  '<이전>><다음>'  상태전이. 가장 구체적이다
      move_action       이동 행동 이름    moveTo 안에서 갈린다
      template          문장 템플릿 이름  기본값
    """

    def __init__(self) -> None:
        self._tmpl: dict[str, tuple[str, str]] = {}
        self._move: dict[str, tuple[str, str]] = {}
        self._trans: dict[tuple[str, str], tuple[str, str]] = {}

    @classmethod
    def load(cls, path) -> "PatternMap":
        pm = cls()
        with open(Path(path), encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key, kind = row["key"].strip(), row["kind"].strip()
                val = (row["predicate"].strip(), row["task_kind"].strip())
                if kind == "template":
                    pm._tmpl[key] = val
                elif kind == "move_action":
                    pm._move[key] = val
                elif kind == "state_transition":
                    if ">" not in key:
                        raise ValueError(
                            "state_transition 키는 '<이전 상태>><다음 상태>' "
                            f"형식이어야 한다: {key!r}")
                    a, b = key.split(">", 1)
                    pm._trans[(a.strip(), b.strip())] = val
        return pm

    def _row(self, template: str, action_label: str,
             state_from: str, state_to: str) -> tuple[str, str] | None:
        hit = self._trans.get((state_from, state_to))
        if hit is not None:
            return hit
        if template == "moveTo" and action_label in self._move:
            return self._move[action_label]
        return self._tmpl.get(template)

    def predicate_of(self, template: str, action_label: str = "",
                     state_from: str = "", state_to: str = "") -> str:
        row = self._row(template, action_label, state_from, state_to)
        return row[0] if row else ""

    def task_kind_of(self, event) -> str:
        """Event를 통째로 받는다.

        인자를 옵션으로 늘리면 state_from/state_to를 안 넘긴 호출부가 조용히
        다른 답을 받는다. 호출부가 여섯 곳뿐이라 한 번에 바꾼다.
        """
        row = self._row(event.template, event.action_label,
                        event.state_from, event.state_to)
        return row[1] if row else "noop"
```

- [ ] **Step 4: `parse_scenario`의 호출부를 고친다**

`vtmak/parser.py:169-175` 부근. `act` 다음 줄에 상태를 뽑고 `predicate=`를 바꾼다.

```python
            act = (g.get("act") or "").strip()
            s_from = (g.get("s0") or "").strip()
            s_to = (g.get("s1") or "").strip()
            res.events.append(Event(
                event_id=f"E{seq:05d}",
                time_s=carry_time,
                line_no=line_no,
                template=name,
                predicate=pattern_map.predicate_of(name, act, s_from, s_to),
```

아래쪽에 이미 `state_from=`·`state_to=`를 채우는 줄이 있다. 같은 `g.get("s0")`·`g.get("s1")`을 두 번 계산하지 말고 `s_from`·`s_to`를 쓰도록 함께 고친다. 먼저 `sed -n '176,200p' vtmak/parser.py`로 현재 모양을 확인한다.

- [ ] **Step 5: 나머지 호출부 다섯 곳을 고친다**

`vtmak/scnx/plan.py`의 `pattern_map.task_kind(e.template, e.action_label)`를 `pattern_map.task_kind_of(e)`로 바꾼다(Task 1 Step 6에서 이미 그렇게 썼다면 이 단계는 확인만).

테스트 넷의 `pm.task_kind(e.template, e.action_label)`를 `pm.task_kind_of(e)`로 바꾼다.

Run: `grep -rn "task_kind(\|\.predicate(" --include=*.py .` — `def ` 정의를 뺀 결과가 **0건**이어야 한다.

- [ ] **Step 6: 테스트가 통과하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: `1 failed, 213 passed`(참고값, 실제 기준선) — 기존 실패 하나만 남는다.

- [ ] **Step 7: 커밋**

```bash
git add vtmak/parser.py vtmak/scnx/plan.py tests/test_parser.py tests/test_spec.py tests/test_writer.py tests/test_fixed_objects.py tests/test_roster.py
git commit -m "feat(parser): pattern_map에 state_transition 키 종류 추가"
```

---

## Task 3: `wait-duration` — 정지·잔류 179건

**Files:**
- Modify: `config/pattern_map.csv` (2행)
- Modify: `config/task_kinds.csv` (1행)
- Modify: `config/task_catalog.csv` (3행)
- Modify: `vtmak/scnx/plan.py` (`_one`에서 참조 없는 kind 허용)
- Modify: `tests/test_spec.py`

**Interfaces:**
- Consumes: Task 1의 `TaskKinds`, Task 2의 `task_kind_of`
- Produces: task_kind `wait` — 참조 필드 없음, 사거리 검사 없음, 행동 `대기`

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_spec.py` 끝에 붙인다.

```python
def test_stop_and_stay_become_wait_tasks(spec):
    """'정지한다'·'잔류한다'는 원문이 서술한 행위다. 버리지 않는다."""
    waits = [(oid, s) for oid, steps in spec.entity_plans.items()
             for s in steps if s.task_kind == "wait"]
    assert waits, "wait task가 하나도 없다"
    for _, s in waits:
        assert s.template in ("stopAt", "stayAt"), s.template
        assert s.pln is not None, s.event_id
        assert '(task-type "wait-duration")' in s.pln
        assert "(seconds-to-wait" in s.pln


def test_wait_task_has_no_placeholder_left(spec):
    """참조 대상이 없는 kind라 치환할 자리도 없어야 한다."""
    for steps in spec.entity_plans.values():
        for s in steps:
            if s.task_kind != "wait":
                continue
            for tok in ("TARGET_UUID", "ENTITY_UUID", "CONTROL_POINT_UUID",
                        "X Y Z", "SX SY SZ"):
                assert tok not in s.pln, (s.event_id, tok)
            assert s.refs == [], s.event_id
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py -k wait -v`
Expected: FAIL — `AssertionError: wait task가 하나도 없다`

- [ ] **Step 3: `pattern_map.csv`의 두 행을 고친다**

`stopAt`·`stayAt`의 `task_kind`를 `noop`에서 `wait`로 바꾸고 `note`를 갱신한다. `predicate` 열은 건드리지 않는다(각각 `stopAt`·`occupy` 유지 — 후처리 STKG가 쓰는 값이다).

```python
# scratch/edit_pattern_map.py
import csv, io
from pathlib import Path
p = Path("config/pattern_map.csv")
rows = list(csv.DictReader(io.StringIO(p.read_text(encoding="utf-8-sig"))))
EDIT = {
    "stopAt": ("wait", "정지 — wait-duration 60초"),
    "stayAt": ("wait", "피격 후 잔류 — wait-duration 60초"),
}
for r in rows:
    if r["kind"] == "template" and r["key"] in EDIT:
        r["task_kind"], r["note"] = EDIT[r["key"]]
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
w.writeheader(); w.writerows(rows)
p.write_bytes(buf.getvalue().encode("utf-8"))
print("ok")
```

- [ ] **Step 4: `task_kinds.csv`에 `wait` 행을 더한다**

`take_cover` 행 뒤에 넣는다. Step 3과 같은 방식(csv 모듈)으로 append 한다.

```
wait,*,,,대기,참조 대상 없음 — 정지·잔류 표현
```

- [ ] **Step 5: `task_catalog.csv`에 `대기` 3행을 더한다**

PLN은 `campaign/campaign.pln`에서 그대로 수확한 것이다(그 파일에 277개 들어 있는 VR-Forces 저작 리터럴이라 추측이 없다). 다음을 실행해 확인한 뒤 붙인다.

```bash
PYTHONIOENCODING=utf-8 python -c "
import re
pln=open('campaign/campaign.pln',encoding='utf-8',errors='replace').read()
print(pln.count('(task-type \"wait-duration\")'), 'occurrences')
"
```
Expected: `277 occurrences`

```python
# scratch/add_wait_rows.py
import csv, io
from pathlib import Path

PLN = ('(Task (task-type "wait-duration") (subtask False) '
       '(allow-task-visualizations True) (seconds-to-wait 60.000000))')
NOTE = ("campaign.pln에서 수확(277개). 원문 '정지한다'·'잔류한다'. "
        "참조 대상이 없어 치환 자리가 없다. 60초는 이 칸의 리터럴이라 "
        "코드 수정 없이 바꾼다 — 플랜은 순서 큐라 대기만큼 뒤가 밀린다.")
GROUPS = ["보병 - 소총(M4 계열)", "보병 - RPG 계열", "차량/장갑차 - M2HB 계열"]

p = Path("config/task_catalog.csv")
text = p.read_text(encoding="utf-8-sig")
if not text.endswith(("\r\n", "\n")):
    text += "\r\n"
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\r\n")
for g in GROUPS:
    w.writerow([g, "대기", "Task", "wait-duration", PLN, "seconds-to-wait", NOTE])
p.write_bytes((text + buf.getvalue()).encode("utf-8"))
print("rows now", sum(1 for _ in csv.DictReader(io.StringIO(
    p.read_text(encoding="utf-8-sig")))))
```

그룹 셋은 실측에서 나온 것이다 — `stopAt`은 보병-소총 52 · 차량 28 · 보병-RPG 22, `stayAt`은 보병-소총 51 · 차량 26. 공통 폴백은 두지 않는다. 다른 원문에서 넷째 그룹이 `stopAt`을 내면 G3의 C3.5가 `BLOCK`으로 막고, 그때 행을 추가하면 된다.

- [ ] **Step 6: `_one`이 참조 없는 kind를 통과시킨다**

`vtmak/scnx/plan.py`의 `_one`에서 참조 해석 앞에 분기를 넣는다.

```python
    if not kinds.ref_field(kind):
        # 참조 대상이 없는 kind(wait). 치환할 자리가 없으므로 템플릿을
        # 고르고 바로 끝낸다. 사거리 검사도 대상이 없다.
        tmpl, label = _pick_template(kind, "*", entity.type_group,
                                     catalog, kinds)
        if tmpl is None:
            step.issues.append(
                f"템플릿 없음: kind={kind} type_group={entity.type_group}")
            return [step]
        step.action_label = label
        if tmpl.task_or_request_type in entity.unsupported_tasks:
            step.issues.append(
                f"{entity.entity_class}에 {tmpl.task_or_request_type} "
                "컨트롤러 없음 — VR-Forces 실측(vrfSim.log)")
            step.skip_reason = SKIP_UNSUPPORTED
            return [step]
        step.pln = tmpl.pln.strip()
        return [step]

    ref = _resolve_ref(e, kind, ctx, kinds)
```

이 분기는 `if not kinds.known(kind): ...` 바로 다음, `ref = _resolve_ref(...)` 바로 앞에 온다.

- [ ] **Step 7: 테스트가 통과하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py -k wait -v`
Expected: PASS (2 passed)

- [ ] **Step 8: 전체 테스트와 실제 저작으로 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: `1 failed, 212 passed`

Run:
```bash
PYTHONIOENCODING=utf-8 python scripts/04_compile_scnx.py 2>&1 | tail -3
PYTHONIOENCODING=utf-8 python -c "
import re, zipfile
from collections import Counter
pln=zipfile.ZipFile('build/scnx/battle.scnx').read('battle.pln').decode('utf-8','replace')
print(Counter(re.findall(r'\(task-type \"([^\"]*)\"', pln)).most_common())
print('balanced', pln.count('(')==pln.count(')'))
"
```
Expected: `wait-duration`이 약 179개 나오고 괄호가 맞는다. 정확히 179가 아닐 수 있다 — 명부 감축과 `unsupported_tasks`로 빠지는 것이 있다. 100개 미만이면 매핑이 안 걸린 것이니 `pattern_map.csv`를 다시 본다.

- [ ] **Step 9: 커밋**

```bash
git add config/pattern_map.csv config/task_kinds.csv config/task_catalog.csv vtmak/scnx/plan.py tests/test_spec.py
git commit -m "feat(plan): 정지·잔류를 wait-duration으로 저작"
```

---

## Task 4: `set-aiming-point` 방향 조준 — 포신 정렬 21건

`aimAt` 표적 21건이 전부 정적 객체(`EN-FP-001` 등)라 객체 조준(`aiming-type 1`)은 쓸 수 없다. 방위·고각을 계산해 넣는 방향 조준(`aiming-type 2`)을 쓴다. 원문 "포신 정렬"과 의미도 더 정확히 맞는다.

**설계 문서와의 차이:** 스펙은 새 kind 이름을 `aim_dir`로 적었다. 실제로는 **기존 `aim` kind를 그대로 쓴다** — `TaskKinds`가 이미 `(kind, ref_kind)`로 후보를 가르므로 `aim,COORD` 행의 행동을 `방향 조준`으로 바꾸면 된다. 새 이름을 만들면 도달 불가능한 `aim` kind가 하나 남는다.

**Files:**
- Modify: `vtmak/geometry.py` (`bearing_elevation` 추가)
- Modify: `vtmak/scnx/plan.py` (`_fill`에 방위·고각 치환)
- Modify: `config/pattern_map.csv` (1행), `config/task_kinds.csv` (1행), `config/task_catalog.csv` (3행)
- Modify: `tests/test_geometry.py`, `tests/test_spec.py`

**Interfaces:**
- Consumes: Task 1의 `TaskKinds`, `vtmak.geometry.Coord`·`ground_distance`
- Produces: `geometry.bearing_elevation(a: Coord, b: Coord) -> tuple[float, float]` — (방위 라디안 0~2π, 고각 라디안 -π/2~π/2)

---

- [ ] **Step 1: 실패하는 기하 테스트를 쓴다**

`tests/test_geometry.py` 끝에 붙인다.

```python
import math

from vtmak.geometry import Coord, bearing_elevation


def test_bearing_is_zero_due_north_and_grows_clockwise():
    here = Coord(21.39, -157.74, 0.0)
    north = Coord(21.40, -157.74, 0.0)
    east = Coord(21.39, -157.73, 0.0)
    south = Coord(21.38, -157.74, 0.0)

    assert bearing_elevation(here, north)[0] == pytest.approx(0.0, abs=1e-3)
    assert bearing_elevation(here, east)[0] == pytest.approx(math.pi / 2,
                                                             abs=1e-3)
    assert bearing_elevation(here, south)[0] == pytest.approx(math.pi,
                                                              abs=1e-3)


def test_bearing_stays_in_zero_to_two_pi():
    here = Coord(21.39, -157.74, 0.0)
    west = Coord(21.39, -157.75, 0.0)
    az, _ = bearing_elevation(here, west)
    assert 0.0 <= az < 2 * math.pi
    assert az == pytest.approx(3 * math.pi / 2, abs=1e-3)


def test_elevation_is_positive_when_target_is_higher():
    low = Coord(21.39, -157.74, 0.0)
    high = Coord(21.39, -157.74, 100.0)
    far_high = Coord(21.40, -157.74, 100.0)

    assert bearing_elevation(low, high)[1] > 0
    assert bearing_elevation(high, low)[1] < 0
    # 멀수록 같은 고도차의 고각은 작아진다
    assert bearing_elevation(low, far_high)[1] < bearing_elevation(low, high)[1]


def test_same_point_is_flat_and_north():
    p = Coord(21.39, -157.74, 50.0)
    assert bearing_elevation(p, p) == (0.0, 0.0)
```

`tests/test_geometry.py` 상단에 `import pytest`가 없으면 더한다.

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_geometry.py -k bearing -v`
Expected: FAIL — `ImportError: cannot import name 'bearing_elevation'`

- [ ] **Step 3: `bearing_elevation`을 구현한다**

`vtmak/geometry.py`의 `ground_distance` 바로 뒤에 붙인다.

```python
def bearing_elevation(a: Coord, b: Coord) -> tuple[float, float]:
    """a에서 b를 볼 때의 방위·고각(라디안).

    방위는 진북 0, 시계 방향으로 증가하며 0 이상 2π 미만이다. 고각은 수평이
    0이고 올려다보면 양수다.

    거리는 ground_distance(ECEF 직선거리)를 쓰지 않는다. 그건 고도차를
    포함하므로 고각 계산에 넣으면 자기 참조가 된다. 수평 성분만 _deg_scales로
    미터로 바꿔 쓴다 — 위도별 도-미터 환산이 이미 거기 있다.

    # VERIFY-ON-TARGET: VR-Forces의 aiming-azimuth가 진북 기준 시계 방향
    # 라디안이라는 것은 확인하지 못했다. 틀리면 포신 방향만 어긋나고
    # task 자체는 돈다.
    """
    lat_m, lon_m = _deg_scales((a.lat + b.lat) / 2.0)
    north = (b.lat - a.lat) * lat_m
    east = (b.lon - a.lon) * lon_m
    flat = math.hypot(north, east)
    if flat == 0.0 and b.alt == a.alt:
        return (0.0, 0.0)
    az = math.atan2(east, north) % (2 * math.pi)
    el = math.atan2(b.alt - a.alt, flat) if flat else math.copysign(
        math.pi / 2, b.alt - a.alt)
    return (az, el)
```

- [ ] **Step 4: 기하 테스트가 통과하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_geometry.py -k "bearing or elevation or flat" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 실패하는 저작 테스트를 쓴다**

`tests/test_spec.py`의 기존 `test_aim_produces_no_task`를 **지우고**(더 이상 참이 아니다) 대신 붙인다.

```python
def test_aim_becomes_a_direction_aiming_set(spec):
    """'포신 정렬'은 원문이 서술한 행위다. 표적이 정적 지점이라 객체 조준
    대신 방위·고각을 계산해 넣는 방향 조준(aiming-type 2)을 쓴다."""
    aims = [s for steps in spec.entity_plans.values() for s in steps
            if s.task_kind == "aim"]
    assert aims, "aim task가 하나도 없다"
    for s in aims:
        assert s.template == "aimAt", s.template
        assert s.pln is not None, s.event_id
        assert '(set-data-request-type "set-aiming-point")' in s.pln
        assert "(aiming-type 2)" in s.pln
        assert "AZIMUTH_RAD" not in s.pln and "ELEVATION_RAD" not in s.pln


def test_aim_angles_are_real_radians(spec):
    """치환이 됐는지만이 아니라 값이 말이 되는지 본다."""
    import math
    import re
    seen = 0
    for steps in spec.entity_plans.values():
        for s in steps:
            if s.task_kind != "aim":
                continue
            az = float(re.search(r"\(aiming-azimuth ([-\d.]+)\)", s.pln).group(1))
            el = float(re.search(r"\(aiming-elevation ([-\d.]+)\)", s.pln).group(1))
            assert 0.0 <= az < 2 * math.pi, az
            assert -math.pi / 2 <= el <= math.pi / 2, el
            seen += 1
    assert seen, "검사한 aim task가 없다"
    # 전부 0이면 사수·표적 좌표가 같은 자리로 풀린 것이다
    assert any(
        float(re.search(r"\(aiming-azimuth ([-\d.]+)\)", s.pln).group(1)) != 0.0
        for steps in spec.entity_plans.values() for s in steps
        if s.task_kind == "aim")
```

`tests/test_spec.py` 상단에 `import re`가 이미 있다(1행). `import math`는 함수 안에서 한다.

- [ ] **Step 6: 테스트가 실패하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py -k aim -v`
Expected: FAIL — `AssertionError: aim task가 하나도 없다`

- [ ] **Step 7: 설정 세 장을 고친다**

`config/pattern_map.csv` — `aimAt` 행의 `task_kind`를 `noop`에서 `aim`으로, `note`를 다음으로 바꾼다(Task 3 Step 3과 같은 스크립트 방식).

```
포신 정렬 — 방향 조준(aiming-type 2). 표적이 정적 지점이라 객체 조준을 못 쓴다. 사거리는 G0가 별도로 검사
```

`config/task_kinds.csv` — `aim,COORD` 행의 `행동_후보`를 `객체 조준`에서 `방향 조준`으로 바꾼다. `aim,ENTITY` 행은 `객체 조준` 그대로 둔다(이 원문에는 안 걸리지만 다른 원문에서 객체 표적이 오면 그쪽이 맞다).

`config/task_catalog.csv` — `방향 조준` 3행을 더한다. 기존 `차량/장갑차 - M2HB 계열` 행을 복제하고 무기명만 바꾼 것이다. 무기명은 `plan.with_weapon`이 객체의 실제 무기로 치환하므로 기본값일 뿐이다.

```python
# scratch/add_aim_rows.py
import csv, io
from pathlib import Path

TMPL = ('(Set (set-data-request-type "set-aiming-point") '
        '(aiming-point 0.0 0.0 0.0) (target-object "") '
        '(aiming-azimuth AZIMUTH_RAD) (aiming-elevation ELEVATION_RAD) '
        '(aiming-type 2) (weapon "{w}"))')
NOTE = ("차량 그룹의 '방향 조준' 행을 복제. 원문 '포신 정렬 후 간접사격 준비'. "
        "aimAt 표적 21건이 전부 정적 객체라 객체 조준(aiming-type 1)을 못 쓴다. "
        "# VERIFY-ON-TARGET: 방위 기준(진북/시계 방향)은 확인 못 함.")
ROWS = [
    ("포병 - 155mm 자주포", "Indirect-Fire-Gun:M107-155mm"),
    ("포병 - 박격포(m9333he 계열)", "Indirect-Fire-Gun:m9333he"),
    ("미사일 발사대 - Patriot", "Patriot Missile Launcher"),
]

p = Path("config/task_catalog.csv")
# read_text()는 유니버설 개행이라 CRLF를 \n으로 바꿔 읽는다. 그대로 다시 쓰면
# 기존 77행의 줄바꿈이 통째로 LF로 뭉개진다(Task 3에서 실제로 걸렸다).
# 읽기도 쓰기도 csv 모듈로 왕복시켜 CRLF를 유지한다.
rows = list(csv.DictReader(io.StringIO(
    p.read_bytes().decode("utf-8-sig"), newline="")))
cols = list(rows[0].keys())
for group, weapon in ROWS:
    rows.append({
        cols[0]: group, cols[1]: "방향 조준", cols[2]: "Set",
        cols[3]: "set-aiming-point", cols[4]: TMPL.format(w=weapon),
        cols[5]: "AZIMUTH_RAD; ELEVATION_RAD", cols[6]: NOTE,
    })
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\r\n")
w.writeheader()
w.writerows(rows)
p.write_bytes(buf.getvalue().encode("utf-8"))
print("rows", len(rows))
```

쓰고 나면 바이트로 확인한다 — bare LF가 0이어야 한다.

```bash
PYTHONIOENCODING=utf-8 python -c "
raw=open('config/task_catalog.csv','rb').read()
crlf=raw.count(b'\r\n'); print('CRLF',crlf,'bare-LF',raw.count(b'\n')-crlf,'BOM',raw[:3]==b'\xef\xbb\xbf')
"
```

- [ ] **Step 8: `_fill`이 방위·고각을 치환한다**

`vtmak/scnx/plan.py`의 `_fill`에 처리를 더한다. 지금은 `self_coord`만 받으므로 시그니처는 그대로 쓸 수 있다 — 사수 좌표는 `self_coord`, 표적 좌표는 `ctx.coord_of(ref)`다.

`import` 줄을 바꾼다.

```python
from ..geometry import Coord, bearing_elevation
```

`_fill`의 `if "X Y Z" in out:` 블록 **뒤에** 붙인다.

```python
    if "AZIMUTH_RAD" in out or "ELEVATION_RAD" in out:
        if self_coord is None:
            raise ValueError("방향 조준에 사수 좌표가 없다")
        az, el = bearing_elevation(self_coord, ctx.coord_of(ref))
        out = out.replace("AZIMUTH_RAD", f"{az:.6f}")
        out = out.replace("ELEVATION_RAD", f"{el:.6f}")
```

docstring의 치환 목록에도 한 줄 더한다.

```
    AZIMUTH_RAD / ELEVATION_RAD = 이 객체에서 참조 대상을 볼 때의 방위·고각
```

- [ ] **Step 9: 테스트가 통과하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py -k aim -v`
Expected: PASS (2 passed)

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: `1 failed, 215 passed` — 지운 `test_aim_produces_no_task` 만큼 줄고 새 테스트만큼 는다.

- [ ] **Step 10: 커밋**

```bash
git add vtmak/geometry.py vtmak/scnx/plan.py config/pattern_map.csv config/task_kinds.csv config/task_catalog.csv tests/test_geometry.py tests/test_spec.py
git commit -m "feat(plan): 포신 정렬을 방향 조준(set-aiming-point)으로 저작"
```

---

## Task 5: `find_firing_position` — 사격 준비 전이 21건

**Files:**
- Modify: `vtmak/scnx/plan.py` (`next_fire_target` 해석)
- Modify: `config/pattern_map.csv` (1행 추가), `config/task_kinds.csv` (1행 추가), `config/task_catalog.csv` (1행 추가)
- Modify: `tests/test_spec.py`

**Interfaces:**
- Consumes: Task 1의 `TaskKinds`, Task 2의 `state_transition`
- Produces: task_kind `find_fp` — 참조 필드 `next_fire_target`(가상 필드, `_resolve_ref`가 해석), **사거리 검사 없음(빈칸)**, 행동 `사격위치 탐색`

---

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_spec.py` 끝에 붙인다.

```python
def test_firing_prep_becomes_find_firing_position(spec):
    """'사격 준비 대기 → 사격 준비'는 짝이 없는 전이다.

    stateChange 1,294건 중 1,226건은 같은 시각 같은 객체에 이미 task를 내는
    이벤트가 붙어 있어 중복이다. 이 전이는 짝이 없어 task가 될 수 있다.
    """
    preps = [s for steps in spec.entity_plans.values() for s in steps
             if s.task_kind == "find_fp"]
    assert preps, "find_fp task가 하나도 없다"
    for s in preps:
        assert s.template == "stateChange", s.template
        assert s.pln is not None, s.event_id
        assert '(task-type "find_firing_position")' in s.pln
        assert "TARGET_UUID" not in s.pln, s.event_id
        assert s.refs, s.event_id


# 파이프라인 전체(명부 감축 없음, 328객체)에서 나오는 통제점. 사격 준비
# 전이가 참조하는 정적 표적 7종이다(2026-08-05 실측).
FIRE_PREP_LOCATIONS = {
    "LOC_중앙킬존", "LOC_적포병진지", "LOC_적박격포진지", "LOC_적북측접근로",
    "LOC_남측제1방어선", "LOC_아군포병진지", "LOC_아군박격포진지",
}


def test_find_firing_position_threat_is_a_control_point(spec):
    """위협 대상이 정적 지점이라 통제점 uuid로 풀린다.

    2026-08-03에 통제점을 뺀 것은 배치 지명 29개를 전부 찍어 로딩이 느려졌기
    때문이다. 여기서 생기는 것은 실제로 조준·사격 대상이 되는 곳뿐이다.

    개수를 못 박지 않는다. 이 테스트의 _build()는 roster.json으로 명부를
    200객체로 줄이는데(파이프라인 02는 감축하지 않는다 — 328객체), 그래서
    여기서 보이는 통제점은 전체의 부분집합이다. 못 박으면 roster.json을
    건드릴 때마다 깨진다. 전체 7종은 04를 돌려 확인한다.
    """
    ctl = {c.uuid: c.ref_id for c in spec.control_objects}
    assert ctl, "통제점이 하나도 없다"
    for steps in spec.entity_plans.values():
        for s in steps:
            if s.task_kind != "find_fp":
                continue
            assert s.refs[0] in ctl, (s.event_id, s.refs)
    # 통제점이 사격 준비 표적 말고 다른 데서 새면 여기서 잡힌다.
    assert set(ctl.values()) <= FIRE_PREP_LOCATIONS, sorted(ctl.values())
```

- [ ] **Step 2: 테스트가 실패하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py -k firing_prep -v`
Expected: FAIL — `AssertionError: find_fp task가 하나도 없다`

- [ ] **Step 3: 설정 세 장을 고친다**

`config/pattern_map.csv` — 행 하나를 **추가**한다(기존 `stateChange` template 행은 `noop`으로 그대로 둔다).

```
key                        kind              predicate               task_kind  note
사격 준비 대기>사격 준비      state_transition  preparesFiringPosition  find_fp    짝 없는 전이. 같은 시각 같은 객체에 task 이벤트가 없다(2026-08-05 실측)
```

`config/task_kinds.csv` — 행 하나를 추가한다.

```
find_fp,COORD,next_fire_target,,사격위치 탐색,후속 사격 문장의 표적을 위협으로 쓴다. 사거리 검사 안 함 — 사격이 아니라 위치 탐색이다
```

**사거리_종류를 비우는 것이 중요하다.** 설계 문서 §4(b)는 `indirect`로 두어
"최소사거리 미달로 사격이 빠지면 준비도 같이 빠지게" 하려 했는데, 그렇게 하면
task가 하나도 안 나온다. `_one`의 사거리 검사는 `fire_distance[e.event_id]`를
찾는데, 이 dict는 `engagement_pairs`가 사격 이벤트에서만 만든다 — 2026-08-05
실측으로 119건 전부 `directFireAt`(77)·`aimAt`(21)·`indirectFireAt`(21)이고
`사격 준비` 전이 21건은 **하나도 없다**. `indirect`로 두면 21건 전부
"교전 거리 미산출"로 떨어지고, `skip_reason`이 안 붙어 G3의 C3.5가 `BLOCK`을
낸다.

부작용은 받아들인다. 뒤따르는 간접사격이 최소사거리 미달로 빠져도 사격위치
탐색은 남는다 — 객체가 자리를 잡고 쏘지 않을 뿐이라 해롭지 않다.

`config/task_catalog.csv` — `미사일 발사대 - Patriot` 그룹의 `사격위치 탐색` 행 하나를 추가한다. 기존 `포병 - 155mm 자주포` 행을 **글자 그대로 복제**한다(무기가 안 들어가는 템플릿이다).

```python
# scratch/add_find_fp_row.py
import csv, io
from pathlib import Path

p = Path("config/task_catalog.csv")
# read_text()는 CRLF를 \n으로 바꿔 읽는다. 그대로 다시 쓰면 기존 행의 줄바꿈이
# 통째로 LF가 된다(Task 3에서 실제로 걸렸다). csv 모듈로 왕복시킨다.
rows = list(csv.DictReader(io.StringIO(
    p.read_bytes().decode("utf-8-sig"), newline="")))
src = next(r for r in rows
           if r["행동"] == "사격위치 탐색"
           and r["객체_타입_그룹"] == "포병 - 155mm 자주포")
new = dict(src)
new["객체_타입_그룹"] = "미사일 발사대 - Patriot"
new["비고"] = (src["비고"] + " / 포병 155mm 행을 복제(무기 무관). "
               "Patriot 2건이 사격 준비 전이를 낸다.")
rows.append(new)
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()),
                   lineterminator="\r\n")
w.writeheader()
w.writerows(rows)
p.write_bytes(buf.getvalue().encode("utf-8"))
print("rows", len(rows))
```

쓰고 나면 바이트로 확인한다 — bare LF가 0이어야 한다.

```bash
PYTHONIOENCODING=utf-8 python -c "
raw=open('config/task_catalog.csv','rb').read()
crlf=raw.count(b'\r\n'); print('CRLF',crlf,'bare-LF',raw.count(b'\n')-crlf,'BOM',raw[:3]==b'\xef\xbb\xbf')
"
```

- [ ] **Step 4: `next_fire_target`을 해석한다**

`vtmak/scnx/plan.py`에 상수와 해석을 더한다. `_resolve_ref` 바로 위에 붙인다.

```python
# '후속 사격 문장'으로 볼 템플릿. 사격 준비 상태가 된 객체의 위협 대상은
# 그 객체가 곧이어 쏘는 표적이다. 2026-08-05 실측: 사격 준비 전이 21건
# 전부 이 세 템플릿 중 하나로 표적이 잡힌다(실패 0).
FIRE_REF_TEMPLATES = ("indirectFireAt", "aimAt", "engAttacker")
```

`_resolve_ref`를 바꾼다.

```python
def _resolve_ref(e: Event, kind: str, ctx: PlanContext, kinds: TaskKinds,
                 actor_events: list[Event]) -> str:
    field = kinds.ref_field(kind)
    if field == "unit_leader":
        return ctx.unit_leader(e.actor) or ""
    if field == "next_fire_target":
        # actor_events는 (time_s, event_id)로 정렬돼 들어온다.
        for x in actor_events:
            if x.time_s >= e.time_s and x.template in FIRE_REF_TEMPLATES \
                    and x.target:
                return x.target
        return ""
    return getattr(e, field, "") or e.dst or e.target
```

`_one`의 호출부에 `actor_events`를 넘긴다.

```python
    ref = _resolve_ref(e, kind, ctx, kinds, actor_events)
```

- [ ] **Step 5: 테스트가 통과하는 것을 확인한다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py -k "firing_prep or control_point" -v`
Expected: PASS (2 passed)

테스트가 보는 통제점은 명부 감축(200객체) 때문에 전체의 부분집합이다 —
실측 5개다. 전체 7개는 Task 6 Step 4에서 04를 돌려 확인한다. 실제 목록을
보려면:

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0,'.')
from tests.test_spec import _build
s=_build()
print(sorted(c.ref_id for c in s.control_objects))
"
```
Expected: `FIRE_PREP_LOCATIONS`의 부분집합. 여기 없는 지명이 나오면 통제점이
사격 준비 표적 말고 다른 경로에서도 새고 있다는 뜻이다.

- [ ] **Step 6: 전체 테스트**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: `1 failed, 217 passed`

`tests/test_writer.py::test_oob_contains_every_entity`와 `test_omp_lists_every_object`는 `len(spec.entities) + len(spec.control_objects)`로 세므로 통제점이 생겨도 통과한다. 깨지면 그 테스트가 통제점을 안 세고 있는 것이니 먼저 읽어 본다.

- [ ] **Step 7: 커밋**

```bash
git add vtmak/scnx/plan.py config/pattern_map.csv config/task_kinds.csv config/task_catalog.csv tests/test_spec.py
git commit -m "feat(plan): 사격 준비 전이를 find_firing_position으로 저작"
```

---

## Task 6: 재저작 · 회귀 방지 · 문서

**Files:**
- Modify: `tests/test_spec.py` (`noTask` 회귀 방지)
- Modify: `tests/test_writer.py` (코드 표가 안 돌아왔는지)
- Modify: `README.md`, `RUNBOOK.md`
- Run: `scripts/02_parse_events.py`, `scripts/04_compile_scnx.py`

**Interfaces:**
- Consumes: Task 1~5 전부
- Produces: 없음 (검증과 문서)

---

- [ ] **Step 1: 회귀 방지 테스트 둘을 쓴다**

`tests/test_spec.py`에 붙인다.

```python
def test_no_task_objects_get_no_move_or_fire_after_that_line(spec):
    """원문이 'task를 부여하지 않는다'고 적은 객체를 지키고 있는가.

    2026-08-05 실측으로 그 시각 이후 이동·사격 이벤트가 0건이라 지금은
    강제 로직이 없어도 지켜진다. 원문이 바뀌어 어긋나면 여기서 잡는다.
    """
    import json
    from pathlib import Path
    jsonl = Path(__file__).resolve().parents[1] / "build" / "events" / "battle.jsonl"
    if not jsonl.exists():
        pytest.skip("build/events/battle.jsonl 없음 — 02를 먼저 실행")
    rows = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l]
    cutoff = {}
    for r in rows:
        if r["template"] == "noTask":
            cutoff.setdefault(r["actor"], r["time_s"])
    assert cutoff, "noTask 이벤트가 하나도 없다 — 원문이 바뀐 것이다"
    bad = [(oid, s.event_id, s.task_kind) for oid, steps in spec.entity_plans.items()
           if oid in cutoff
           for s in steps
           if s.time_s > cutoff[oid]
           and s.task_kind in ("move", "move_slow", "follow",
                               "fire_direct", "fire_indirect", "suppress")]
    assert bad == [], bad[:5]
```

`tests/test_writer.py`에 붙인다.

```python
def test_mapping_tables_stay_out_of_the_code():
    """매핑 표가 코드로 돌아오면 config/task_kinds.csv가 정본이 아니게 된다."""
    src = (ROOT / "vtmak" / "scnx" / "plan.py").read_text(encoding="utf-8")
    for name in ("LABEL_CANDIDATES", "REF_FIELD", "FIRE_KIND"):
        assert f"{name}:" not in src and f"{name} =" not in src, name
```

- [ ] **Step 2: 테스트를 돌린다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_spec.py::test_no_task_objects_get_no_move_or_fire_after_that_line tests/test_writer.py::test_mapping_tables_stay_out_of_the_code -v`
Expected: PASS (2 passed)

- [ ] **Step 3: 02를 다시 돌린다**

`pattern_map.csv`의 `predicate` 열이 바뀌었으므로(`preparesFiringPosition` 추가) 이벤트를 다시 뽑는다.

Run: `PYTHONIOENCODING=utf-8 python scripts/02_parse_events.py 2>&1 | tail -5`

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "
import json
from collections import Counter
rows=[json.loads(l) for l in open('build/events/battle.jsonl',encoding='utf-8') if l.strip()]
print(len(rows), 'events')
print(Counter(r['predicate'] for r in rows).most_common(8))
"
```
Expected: 3,000건이 그대로 나오고 `preparesFiringPosition`이 21건 보인다.

- [ ] **Step 4: 04를 다시 돌리고 산출물을 센다**

```bash
PYTHONIOENCODING=utf-8 python scripts/04_compile_scnx.py 2>&1 | tail -4
PYTHONIOENCODING=utf-8 python -c "
import re, zipfile
from collections import Counter
z=zipfile.ZipFile('build/scnx/battle.scnx')
pln=z.read('battle.pln').decode('utf-8','replace')
oob=z.read('battle.oob').decode('utf-8','replace')
print('Task :', Counter(re.findall(r'\(task-type \"([^\"]*)\"', pln)).most_common())
print('Set  :', Counter(re.findall(r'\(set-data-request-type \"([^\"]*)\"', pln)).most_common())
print('objects', oob.count('(local-vrf-object'), '| AIEnabled True', oob.count('AIEnabled True'))
print('balanced', pln.count('(')==pln.count(')'))
"
```
Expected: task type이 10종 나온다 — `move-to-location-task` · `follow-entity` · `fire-at-target` · `provide_suppressive_fire_loc` · `ffe-on-location` · `find_cover` · **`wait-duration`** · **`find_firing_position`**, Set은 `set-speed` · **`set-aiming-point`** · `set-aim-sensor`. `AIEnabled True`는 0이어야 한다. 괄호가 맞아야 한다.

10종이 안 나오면 어느 매핑이 빠졌는지 `05`의 감사표로 본다.

Run: `PYTHONIOENCODING=utf-8 python scripts/05_data_postprocessing.py 2>&1 | tail -10` — 입력 CSV가 없으면 건너뛴다.

- [ ] **Step 5: `README.md`를 갱신한다**

"AI Enabled = No 는 task를 막지 않는다" 절 **앞에** 새 절을 넣는다.

```markdown
### 매핑을 늘리는 자리는 CSV 두 줄이다

예전에는 task_kind 하나를 늘리려면 `pattern_map.csv`·`task_catalog.csv`와
`plan.py`의 표 세 개(`LABEL_CANDIDATES`·`REF_FIELD`·`FIRE_KIND`)를 같이
고쳐야 했다. 그래서 `task_catalog.csv`에 템플릿이 있는 행동 33종 중 8종만
도달 가능한 상태로 굳어 있었다.

세 표는 `config/task_kinds.csv`로 나왔다(2026-08-05). 이제 매핑 추가는
`pattern_map.csv` 한 줄 + `task_kinds.csv` 한 줄이다. 폴백은 없다 — 어느
쪽이 비면 G3가 막는다.

| 열 | 뜻 |
|---|---|
| `task_kind` | `pattern_map.csv`의 같은 이름 |
| `ref_kind` | `COORD` \| `ENTITY` \| `*` — 참조 대상 종류별로 후보가 갈린다 |
| `참조_필드` | Event의 어느 필드에서 대상을 가져오는가. 비면 참조 없음(`wait`) |
| `사거리_종류` | `direct` \| `indirect` \| 빈칸 |
| `행동_후보` | `task_catalog.csv`의 '행동', `\|`로 구분한 우선순위 순 |

`참조_필드`에 `next_fire_target`을 쓰면 그 객체가 곧이어 쏘는 표적을 가져온다
(`find_firing_position`의 위협 대상).

### 원문 어휘에서 뽑은 task 3종 (2026-08-05)

| 새 task | 원문 근거 | 건수 |
|---|---|---:|
| `wait-duration` | `stopAt` "…에 정지한다" · `stayAt` "…에 잔류한다" | 179 |
| `set-aiming-point` (방향 조준) | `aimAt` "포신 정렬 후 간접사격 준비" | 21 |
| `find_firing_position` | 상태전이 `사격 준비 대기 → 사격 준비` | 21 |

`.pln`의 task type이 7종에서 10종이 됐다.

**상태전이를 대부분 쓰지 않는 이유가 있다.** `stateChange` 계열 1,294건 중
1,226건은 이미 task를 내는 이벤트와 **같은 시각·같은 객체**에 붙어 있다 —
서사가 같은 순간을 상태로 한 번 더 말하는 것이라 task를 또 붙이면 중복이다.
짝이 없는 전이는 4종 68건이고 그중 행위인 것은 `사격 준비 대기 → 사격 준비`
하나다.

**`set-target`은 일부러 뺐다.** `engAttacker` 118건이 근거가 되지만, 이
요청은 "이걸 교전하라"고 지정만 하고 실제 사격은 자동교전 로직이 한다.
`AIEnabled`가 끄는 것이 바로 그 자동사격이므로 AI Off에서는 지정만 되고
아무 일도 일어나지 않을 가능성이 크다(실측 없음, 구조상의 판단).

**통제점 7개가 생겼다.** `find_firing_position`의 위협 대상이 정적 객체라
uuid가 필요하다. 2026-08-03에 통제점을 뺀 것은 배치 지명 29개를 전부 찍어
로딩이 느려졌기 때문이고, 여기 7개는 실제로 조준·사격 대상이 되는 곳뿐이다.
로딩 영향은 측정하지 않았다.
```

- [ ] **Step 5b: 이번 작업으로 틀리게 된 기존 서술을 정정한다**

구현 중에 드러난 것들이다. 넷 다 실제로 지금 문서에 남아 있는 틀린 문장이므로
찾아서 고친다. 문장을 지우지 말고 **왜 바뀌었는지**를 남긴다.

1. **`README.md`의 "ZPU-4와 M901은 … 플랜이 빈다".** M901 Patriot Launcher는
   더 이상 플랜이 비지 않는다 — `unsupported_tasks`가
   `move-to-location-task;ffe-on-location`이라 `set-aiming-point`는 막히지 않고,
   `aim`이 방향 조준 task를 준다. 이제 플랜이 비는 것은 ZPU-4뿐이다.
   `tests/test_spec.py::test_empty_plans_are_only_towed_equipment`가 그 목록을
   못 박고 있으니 문서와 테스트가 같은 말을 하는지 확인한다.

2. **설계 문서 `docs/superpowers/specs/2026-08-05-task-mapping-expansion-design.md`
   §4(b)의 "사거리 종류를 `indirect`로 둔다".** 틀렸다. 그렇게 두면
   `find_firing_position` 21건이 전부 "교전 거리 미산출"로 떨어진다 —
   `fire_distance`는 사격 이벤트에서만 만들어져 상태전이 event_id가 없기 때문이다.
   실제 구현은 사거리 검사를 하지 않는다. 그 문단을 실제 동작과 근거로 바꾼다.

3. **`README.md`의 "감사표(`05_data_postprocessing.py`)".** `05`는
   `vtmak/scnx/audit.py`를 import하지 않는다. `build_rows`를 부르는 것은
   `tests/test_audit.py`뿐이다. 감사표가 실제로 어디서 나오는지 확인해서 바로잡거나,
   확인이 안 되면 "현재 어느 스크립트도 audit.py를 쓰지 않는다"를 사실대로 적는다.
   `grep -rn "audit" scripts/`로 먼저 확인할 것.

4. **`docs/superpowers/plans/2026-08-05-task-mapping-expansion.md`의 낡은 통과 개수.**
   Task 2 Step 6이 `210 passed`로 적혀 있는데 실제 기준선은 213이었다. 이 계획서의
   `Expected:` 줄에 박힌 개수들을 실제 값으로 맞추거나, 참고값임을 명시한다
   (Global Constraints에 이미 적혀 있으니 개수만 손봐도 된다).

- [ ] **Step 6: `RUNBOOK.md`를 갱신한다**

"AI Enabled = No로 두는 것이 정상이다" 문단 뒤에 붙인다.

```markdown
**새 task를 매핑하려면 CSV 두 줄이다.** `config/pattern_map.csv`에 원문
문장 종류 → `task_kind` 한 줄, `config/task_kinds.csv`에 그 `task_kind`의
참조 필드·사거리 종류·행동 후보 한 줄. 행동 이름은 `config/task_catalog.csv`에
있어야 한다 — 없으면 G3의 C3.5가 `BLOCK`으로 막는다(조용히 안 빠진다).

상태전이로 매핑하려면 `pattern_map.csv`의 `kind`를 `state_transition`으로,
`key`를 `<이전 상태>><다음 상태>`로 쓴다. 다만 상태전이 대부분은 같은 시각
같은 객체의 task 이벤트와 중복이다 — 붙이기 전에 짝이 있는지 확인한다.

**새 task 종류를 넣은 다음에는 측정 라운드를 돈다.** 1차 저작 → VR-Forces
실행 → `vrfSim.log`에서 `No controller`가 난 (모델, task) 조합을 모아
`config/entity_class_map.csv`의 `unsupported_tasks`에 적는다 → 재저작.
1차 런은 오류가 많은 것이 정상이다. 실패 후보는 견인 박격포·ZPU 계열의
`find_firing_position`과 Patriot 계열이다.

**통제점이 7개 생겼다(2026-08-05).** 로딩이 눈에 띄게 느려지면
`config/pattern_map.csv`의 `사격 준비 대기>사격 준비` 행을 `noop`으로 되돌리면
통제점도 같이 사라진다.
```

- [ ] **Step 7: 전체 테스트를 마지막으로 돌린다**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: `1 failed, 219 passed` — 실패는 `test_preserves_every_engagement_kind` 하나뿐

Run: `python -m flake8 vtmak scripts tests | wc -l` — Task 1 전과 견줘 늘지 않아야 한다. 먼저 기준선을 `git stash` 없이 알고 싶으면 `git show HEAD~5:vtmak/scnx/plan.py > /tmp/base.py && python -m flake8 /tmp/base.py | wc -l`로 파일별로 견준다.

- [ ] **Step 8: 커밋**

```bash
git add tests/test_spec.py tests/test_writer.py README.md RUNBOOK.md
git commit -m "docs: 매핑 확대 결과와 측정 라운드 절차"
```

- [ ] **Step 9: 측정 라운드를 사람에게 넘긴다**

`build/scnx/battle.scnx`를 VR-Forces에서 열고 실행한 뒤 `vrfSim.log`를 받아야 다음이 정해진다. 아래를 보고한다.

- `.pln`의 task type 종수와 각 건수 (Step 4의 출력)
- 통제점 7개로 로딩 시간이 달라졌는지
- `No controller` 오류가 난 (모델, task) 조합 — `entity_class_map.csv`에 적을 것
- `wait-duration` 60초가 시나리오 진행을 얼마나 늦추는지

---

## 자체 검토

**스펙 커버리지**

| 스펙 절 | 담당 Task |
|---|---|
| §3 코드 표 세 개 → `task_kinds.csv` | 1 |
| §3 `_one()`이 참조 없는 kind 허용 | 3 Step 6 |
| §3 `PatternMap`이 Event를 받음 | 2 |
| §3 `_resolve_ref`가 이벤트 목록을 받음 | 1 Step 6(배선), 5 Step 4(사용) |
| §3 `geometry.bearing_elevation` | 4 |
| §4(a) `wait-duration` | 3 |
| §4(b) `find_firing_position` + 통제점 7개 | 5 |
| §4(c) `set-aiming-point` 방향 조준 | 4 |
| §5 AI Enabled 무관 | 문서에만 반영 (6 Step 5) |
| §6 게이트·감사 | 3·4·5의 전체 테스트 실행, 6 Step 4의 05 실행 |
| §6 새 테스트 6종 | 1·3·4·5·6에 분산 |
| §6 측정 라운드 | 6 Step 9 |
| §7 기대치 | 6 Step 4의 실측으로 확인 |

빠진 것 없음. 스펙 §2의 "넣지 않는 것"은 구현할 것이 없어 문서(6 Step 5)에만 남긴다.

**설계와 다르게 한 것 하나** — 스펙은 새 kind 이름을 `aim_dir`로 적었으나 기존 `aim`을 쓴다. `TaskKinds`가 `(kind, ref_kind)`로 후보를 가르므로 `aim,COORD`의 행동만 바꾸면 되고, 새 이름을 만들면 도달 불가능한 `aim` kind가 하나 남는다. Task 4 머리말에 적어 두었다.

**플레이스홀더** — 없음. 모든 코드 단계에 실제 코드가 있다.

**타입 정합성** — `TaskKinds.get/ref_field/fire_kind/known`이 Task 1에서 정의되고 3·4·5에서 같은 이름으로 쓰인다. `build_entity_plan`·`build_spec`의 `kinds` 위치(각각 5번째·6번째)가 Task 1의 Interfaces와 호출부 수정이 일치한다. `_one`의 `actor_events`는 Task 1에서 받아 두고 Task 5에서 쓴다. `bearing_elevation`의 반환 `(az, el)`이 Task 4의 테스트·`_fill` 양쪽에서 같다.
