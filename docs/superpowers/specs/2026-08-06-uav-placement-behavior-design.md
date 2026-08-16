# UAV 배치·행동 재설계 — 희소 술어 포착과 전 객체 관측

2026-08-06 · `new_VTMAK`

관련 문서: [파이프라인 설계](2026-08-02-new-vtmak-scnx-pipeline-design.md) ·
[task 매핑 확대](2026-08-05-task-mapping-expansion-design.md) ·
[운영 가이드](../../../new_VTMAK/RUNBOOK.md)

---

## 1. 요구

1. GT 술어 분포에서 `FFE-on-Location` · `find_cover` · `fired_by`처럼 희소한
   술어를 UAV가 잘 포착하도록 배치한다.
2. 모든 객체가 하나 이상의 UAV에 관측되도록 한다.

## 2. 진단 — 병목은 거리가 아니라 시간이다

측정 대상은 `build/stkg/*_20260804_155849_annotated.csv`다. GT 이벤트 행
(`predicate != none`)을 분모로, 같은 `(시각, 주체, 술어)`가 UAV CSV에 있으면
포착으로 센 재현율:

| 술어 | GT 행 | UAV 포착 | 재현율 |
|---|---:|---:|---:|
| `move to` | 106,550 | 1,337 | 1.25% |
| `Follow-Entity` | 72,885 | 0 | **0.00%** |
| `fired_by` | 2,960 | 16 | 0.54% |
| `FFE-on-Location` | 2,174 | 242 | 11.13% |
| `find_cover` | 1 | 0 | **0.00%** |

### 2.1 거리 가설은 기각됐다

거리대별 재현율에 단조성이 없다. `move to`는 0–500 m에서 1.4%, 2–2.5 km에서
4.2%로 **멀리서 더 잘 잡힌다**. 미관측 주체 169개 중 **166개가 2 km 안에 들어온
적이 있고**, 최근접 57 m까지 붙었던 `FRSNP001`도 한 행도 남기지 않았다.

2026-08-05 세션에서 세웠던 "모든 객체를 어느 UAV로부터 2 km 안에 둔다"는 규칙은
**폐기한다.** 그 규칙은 관측 성공/실패를 설명하지 못한다.

### 2.2 실제 병목 — 관측의 시간 점유율

UAV가 무언가를 기록한 시각은 전체 683개 중 **88 / 71 / 28 / 25개**(4~13%)뿐이다.
그런데 기록이 있는 순간에는 한 번에 **최대 35~70개 객체**를 본다. 기록은 1~2초
간격의 짧은 버스트로 뭉치고 버스트 사이는 최대 119초 공백이다.

즉 센서의 순간 시야는 넓은데 그 순간이 드물다. 공간이 아니라 시간 문제다.

### 2.3 원인 둘

**(a) 짐벌이 거의 수직 아래를 본다.** `battle.oob`의 UAV 4대 전부:

```
(aiming-elevation -1.396263)   ← -80.0°
(aiming-mode 3)                ← Scan
(scanning-left True)
```

지면 위 약 70~75 m에서 -80°로 내려보며 방위만 훑는다. `campaign.oob` 원본은
`-0.785`(-45°) / `aiming-mode 0`이었고, GUI에서 Scan을 적용할 때 -80°가 들어갔다.
생성기가 내보내는 Set은 `(aiming-mode 3)`뿐이라 각도를 되돌리지 않는다.

**(b) 관측 보고 Set이 빠져 있다.** `build/scnx/battle.scnx` 안의 `.pln`에는
`set-aiming-point` 19 · `set-speed` 17 · `set-aim-sensor` 4가 있고
**`set-spot-reporting-request`는 0건**이다. `campaign.pln`에는 UAV 4대분 4건이
있다.

### 2.4 구조적 결과

적 보병 `EN-INF` 100개 중 99개, `EN-SA` 15개 중 14개가 통째로 미관측이다.
`Follow-Entity` 주체 113개가 정확히 이 둘(99+14)이라 재현율이 0%다.

### 2.5 배치도 나쁘다

UAV 1·2는 300 m 간격으로 아군 포병진지 위, UAV 3·4는 350 m 간격으로
남측고지관측소 위에 있다. 4대가 두 곳에 뭉쳐 있고, 이벤트가 몰린 세 곳
(적포병진지 · 적북측접근로 · 중앙 킬존)은 아무도 보지 않는다.

## 3. 설계

### 3.1 campaign의 UAV 플랜을 수확한다

`campaign.pln`의 UAV 플랜은 두 조각이다. 문법을 새로 만들지 않고 그대로 쓴다.

```
(Set (set-data-request-type "set-spot-reporting-request")
     (spot-reporting-turned-on 2) (use-global-receivers True)
     (spot-reporting-receivers ))
(Task (task-type "orbit_object") (subtask False)
      (allow-task-visualizations True) (script-id "orbit_object")
   (variables (DtRwBoolean (clockwise False))
              (DtRwReal   (radius 1000.000000))
              (DtRwReal   (scriptedtask_version 1.000000))
              (DtRwObjectName (target "VRF_UUID:…"))))
```

campaign에서는 4대 모두 엔티티 `E2`를 반경 1,000 m로 선회한다.

### 3.2 선회 중심 — 이미 저작 중인 지명 4곳

희소 술어의 최대밀집 격자가 이미 저작 중인 정적 표적과 겹친다.

| UAV | 선회 중심 지명 | 정적 표적 | 근거 | 중심과의 거리 |
|---|---|---|---|---:|
| 1 | `LOC_적포병진지` | `EN-FP-001` | `fired_by` 78% (2,303행) | 14 m |
| 2 | `LOC_아군포병진지` | `FR-FP-001` | `FFE-on-Location` 69% (1,500행) | 22 m |
| 3 | `LOC_적북측접근로` | `EN-RT-001` | `Follow-Entity` 56% (40,788행) + `find_cover` 100% | 4 m |
| 4 | `LOC_중앙킬존` | `OBJ-009` | 광역 보완 | — |

관측 반경 R을 가정한 커버리지. 자유 좌표 최적해보다 낫다.

| R | 지명 4곳 | (참고) 자유 최적 4점 | Follow | FFE | fired_by | find_cover |
|---:|---:|---:|---:|---:|---:|---:|
| 750 m | **326/345 (94%)** | 285 (83%) | 100% | 100% | 92% | 100% |
| 1,000 m | 333/345 (97%) | 343 (99%) | 100% | 100% | 99% | 100% |
| 1,250 m | **345/345 (100%)** | 345 (100%) | 100% | 100% | 100% | 100% |

새 객체를 만들지 않는다. 선회 중심은 파이프라인이 이미 저작하는 **통제점**이다.

### 3.3 확정 수치

선회 반경 1,000 m(campaign 실적값) · 고도 400 m AGL · 초기 위치는 선회 중심
정북 1,000 m(결정론).

| UAV | 중심 위경도 | 지면 | 고도 MSL | 초기 위경도 | 이동량 |
|---|---|---:|---:|---|---:|
| 1 | `21.36728, -157.73174` | 5.3 m | 405.3 m | `21.37627, -157.73174` | 2,629 m |
| 2 | `21.39530, -157.73726` | 1.0 m | 401.0 m | `21.40428, -157.73726` | 849 m |
| 3 | `21.37133, -157.74174` | 37.1 m | 437.1 m | `21.38031, -157.74174` | 1,397 m |
| 4 | `21.38376, -157.74492` | 39.2 m | 439.2 m | `21.39274, -157.74492` | 1,482 m |

짐벌은 반경·고도가 같아 4대 공통이다.

```
aiming-elevation  -0.380506   = -atan(400 / 1000) = -21.80°
aiming-azimuth    -1.570796   = -90° (기체 좌현 = 반시계 선회의 안쪽)
aiming-mode       0           고정 조준
scanning-left     False
```

### 3.4 짐벌은 Set이 아니라 `.oob`에 쓴다

`set-aim-sensor`에 azimuth/elevation을 얹는 문법은 정본을 확인하지 못했다.
대신 `fixed.py`가 복제하는 `.oob` raw 레코드의 `sensor-gimbal-controller` PSR
필드를 직접 치환한다. 필드명은 `campaign.oob`·`battle.oob`에서 읽어 확인한
것이라 추측이 없다. 기존 `센서 스캔` 행은 없앤다.

### 3.5 비행이 버는 것

선회하면 관측 방위가 계속 바뀌어 지형 차폐가 풀린다. UAV 3 담당 구역
(적북측접근로, 지면 37.1 m)에서 `EN-INF` 99개 전부가 미관측인 것은 정지 관측의
한계와 맞아떨어진다. 정지 고정 조준으로는 한 방향에서 가려진 것이 끝까지
가려진다.

`orbit_object`는 scripted task다(`script-id`). campaign이 같은 VR-Forces 설치에서
쓰고 있으므로 스크립트는 있다.

### 3.6 '항상 고정' 원칙의 개정

`fixed_objects.json`은 지금까지 "이동 태스크를 붙이지 않는다"를 원칙으로 삼았고
`spec.build_fixed_plans`가 Set 외의 Plan 요소를 예외로 막았다. 이 원칙을
**"원문 규모와 무관하게 같은 배치를 갖는다"** 로 개정한다.

- 좌표·고도·짐벌은 원문이 아니라 `fixed_objects.json`이 정한다. 명부를 줄여도
  값이 변하지 않는다 — 기존 불변식은 그대로 산다.
- 선회는 결정적이다. 같은 config면 같은 `.scnx` 바이트가 나온다.
- `FIXED_PLAN_ELEMENTS`에 `Task`를 추가하되, 붙일 수 있는 행동은 여전히
  `task_catalog`에 있는 것만이다.

## 4. 구현

### 4.1 `config/task_catalog.csv`

`무인기 - 짐벌 센서` 그룹의 행을 교체한다.

| 행동 | Plan 요소 | type | 치환 파라미터 |
|---|---|---|---|
| `관측 보고 켜기` | `Set` | `set-spot-reporting-request` | 없음 |
| `선회 감시` | `Task` | `orbit_object` | `RADIUS_M` · `ORBIT_TARGET_UUID` |

`센서 스캔` 행은 삭제한다(§3.4).

### 4.2 `config/fixed_objects.json`

```json
{
  "source_dir": "campaign",
  "markings": ["UAV 1", "UAV 2", "UAV 3", "UAV 4"],
  "orbit_centers": {
    "UAV 1": "LOC_적포병진지",
    "UAV 2": "LOC_아군포병진지",
    "UAV 3": "LOC_적북측접근로",
    "UAV 4": "LOC_중앙킬존"
  },
  "orbit":  { "radius_m": 1000.0, "clockwise": false, "start_bearing_deg": 0.0 },
  "flight": { "altitude_agl_m": 400.0 },
  "gimbal": { "aiming_mode": 0, "azimuth_rad": -1.570796, "scanning_left": false },
  "plan":   { "type_group": "무인기 - 짐벌 센서",
              "actions": ["관측 보고 켜기", "선회 감시"] }
}
```

`aiming_elevation`은 적지 않는다 — `-atan(altitude_agl_m / radius_m)`으로
계산한다. 고도나 반경을 고치면 각도가 저절로 따라오게 하기 위해서다.

### 4.3 `vtmak/scnx/fixed.py`

- `load_fixed(config_path, root, layout)` — 지명 해석에 `BattlefieldLayout`이
  필요하므로 인자를 하나 받는다.
- `FixedObject`에 `orbit_center_loc` · `orbit_radius_m` · `orbit_clockwise`를
  더한다.
- 초기 좌표를 계산한다: 선회 중심에서 `start_bearing_deg` 방향으로
  `radius_m`, 고도는 `지면 + altitude_agl_m`.
- 복제한 raw 레코드를 치환한다 — `(position …)` 전부, `(ordered-altitude …)`,
  `(DtRwReal OrderedAltitude … publish)`, 짐벌 4필드.

### 4.4 `vtmak/scnx/spec.py`

- `FIXED_PLAN_ELEMENTS = {"Set", "Task"}`.
- `build_fixed_plans(fixed, catalog, orbit_uuid_of)` — `RADIUS_M`과
  `ORBIT_TARGET_UUID`를 치환한다. 치환 후에도 괄호 균형을 검사한다.
- `build_spec` — 선회 중심 지명을 `ctx.referenced_locs`에 넣어 통제점이
  저작되게 하고, 그 uuid를 `orbit_uuid_of`로 넘긴다.

### 4.5 테스트

- 좌표·고도가 선회 중심과 config에서 계산된 값인가
- 짐벌 4필드가 raw에 실제로 치환됐는가, `-1.396263`이 남아 있지 않은가
- 플랜에 `orbit_object`와 `set-spot-reporting-request`가 둘 다 있는가
- `ORBIT_TARGET_UUID`가 실제 저작된 통제점의 uuid인가
- 명부 규모를 바꿔도 UAV 배치가 그대로인가(기존 테스트 유지)
- `task_catalog`에 없는 행동은 여전히 예외인가

## 5. 위험

1. **`orbit_object`의 `target`이 통제점을 받는지 미검증이다.** 변수 데이터 타입은
   `simulationobject`이고 campaign은 엔티티(`E2`)를 썼다. 1차 실행에서
   `vrfSim.log`를 본다. 안 되면 campaign의 `E2` 레코드를 복제한 중립 앵커 4개를
   `fixed_objects`에 더한다(§4.2의 config 확장으로 끝난다).
2. **선회 대상이 파괴되면** 어떻게 되는지 모른다. 통제점은 파괴되지 않으므로
   위험 1을 통과하면 같이 해소된다.
3. **UAV 1이 2,629 m 이동**해 전장 남단으로 내려간다. 같은 Ala Moana 지형이라
   좌표는 유효하지만 인스턴스화는 1차 실행에서 확인한다.

## 6. 성공 기준 — 1차 측정 라운드

측정 절차는 RUNBOOK "측정 라운드"를 따른다. 저작 → VR-Forces 실행 →
`05_data_postprocessing.py` → 재현율 표 재생성.

- 관측 주체 **176/345 → ≥326/345**
- `Follow-Entity` **0% 탈출**(지금 72,885행 전부 미포착)
- `find_cover` 1건 포착
- `fired_by` 0.54% → **≥10%**
- `FFE-on-Location` 11.13% → **≥50%**

목표에 못 미치면 순서대로 조정한다: 선회 반경 → 고도 → 짐벌 방위각. 셋 다
`fixed_objects.json` 한 줄이고 코드를 고치지 않는다.
