# 원문 어휘 → VR-Forces task 매핑 확대 설계

작성일 2026-08-05. 대상 `new_VTMAK/vtmak/scnx/plan.py`, `new_VTMAK/config/`.

## 1. 문제

시뮬레이션을 돌려 뽑은 GT의 술어가 다섯 종뿐이다 — `move to`, `follow entity`,
`fired by`, `FFE on location`, `find cover`. 원문을 이벤트로 바꾸고 task까지
매핑하는데도 그렇다.

원인이 둘이다. 이 설계가 다루는 것은 **A**뿐이다.

**A. 원문의 2/3이 `noop`으로 버려진다.** `build/events/battle.jsonl` 3,000건 중
task가 되는 것은 746건이다(`moveTo` 571 · `directFireAt` 77 · `hitBy` 77 ·
`indirectFireAt` 21). 나머지 2,254건은 `pattern_map.csv`에서 전부 noop이다.

**B. 저작한 task도 GT에 안 찍힌다.** `.pln`에 `fire-at-target` 26개,
`provide_suppressive_fire_loc` 51개가 들어 있는데 GT의 `event` 열에는 없다.
Data Logger가 tick마다 '지금 수행 중인 task'를 찍는 구조라 **오래 도는 task만
표본을 남긴다.** `find_cover`가 557,069행 중 1행인 것이 그 증거다. B는 별개
문제이고 여기서 고치지 않는다 — 다만 이 설계의 기대치를 정할 때 쓴다.

## 2. 무엇을 넣고 무엇을 넣지 않는가

`config/VR-Forces_task_list.xlsx`의 실행 가능 task 21종을 원문 어휘와 대조했다.
넣을 수 있는 것은 셋이다.

| 새 task | 근거 이벤트 | 건수 | GT 가시성 |
|---|---|---:|---|
| `wait-duration` | `stopAt` "…에 정지한다" 102 + `stayAt` "…에 잔류한다" 77 | 179 | 높음(60초 점유) |
| `find_firing_position` | 상태전이 `사격 준비 대기 → 사격 준비` | 21 | 낮음(짧은 스크립트 task) |
| `set-aiming-point` (방향 조준) | `aimAt` "포신 정렬 후 간접사격 준비" | 21 | 낮음 |

기존 `find_cover`는 유지한다. **task type 7종 → 10종, 근거 이벤트 +221건.**

### 넣지 않는 것과 그 이유

- **`set-target`** — `engAttacker` 118건이 근거가 되지만 뺀다. 이 요청은 "이걸
  교전하라"고 **지정만** 하고 실제 사격은 자동교전 로직이 한다. `AIEnabled`가
  끄는 것 중 하나가 자동사격이므로(매뉴얼 34.3), AI Off 상태에서는 지정만 되고
  아무 일도 일어나지 않을 가능성이 크다. 실측 근거는 없고 구조상의 판단이다.
- **`set spot reporting request`** — 원문에 발견 보고 문장이 없다.
- **`move along` · `animated movement task` · `place ied` · `throwgrenade` ·
  `embark`/`disembark`** — 카탈로그에 템플릿이 있어도 원문이 그 행동을 서술하지
  않는다. 넣으면 없는 사실을 지어내는 것이 된다. 특히 `embark`는
  후보로 검토했으나, `적재 대기`(13건)는 보급 트럭의 **화물** 적재 대기이고
  탑승할 객체가 원문에 없다.
- **`ffe on entity` · `ffe on target` · `move to`(waypoint)** — 이 시나리오의
  사격 표적은 `EN-FP-001`(적 자주포 사격진지) 같은 **정적 객체**라 객체 uuid가
  없다. 통제점을 늘리면 가능하지만 이번 범위 밖이다.

### 상태전이를 대부분 쓰지 않는 이유

`stateChange` 계열 1,294건 중 **1,226건은 이미 task를 내는 이벤트와 같은 시각·
같은 객체에 붙어 있다.** 서사가 같은 순간을 상태로 한 번 더 말하는 것이라, task를
또 붙이면 중복이다.

```
127  기동 → 후퇴            같은 시각 같은 객체에 moveTo 있음
124  기동 → 방어            같은 시각 같은 객체에 moveTo 있음
 76  기동 또는 사격 준비 → 사격  같은 시각 같은 객체에 directFireAt 있음
 51  기동 또는 사격 가능 → 제압  같은 시각 같은 객체에 hitBy 있음
```

짝이 없는 전이는 4종 68건이다 — `대기→사격 준비 대기`(21) ·
`사격 준비 대기→사격 준비`(21) · `정상→피격 지역`(21) · `대기→적재 대기`(13).
이 중 task가 되는 것은 `사격 준비 대기→사격 준비` 하나다. `정상→피격 지역`은
피동이라 행위가 아니고, `대기→적재 대기`는 위에 적은 이유로 뺀다.

### 확인했으나 손대지 않는 것

`noTask` 77건("이후 EN-INF-001에는 일반 이동·사격 task를 부여하지 않는다")은
파서가 읽기만 하고 어디서도 쓰이지 않는다. 그러나 **그 시각 이후 해당 객체의
이동·사격 이벤트가 0건**이라 원문이 이미 일관적이다. 준수 로직을 넣어도 바뀌는
것이 없으므로 넣지 않는다. 회귀 방지 검사로만 의미가 있다.

## 3. 구조 — 코드 표 세 개를 config 한 장으로

task_kind 하나를 늘리려면 지금은 다섯 곳을 같이 고쳐야 하고 그중 셋이 코드다.

```
config/pattern_map.csv                원문 → task_kind          데이터
vtmak/scnx/plan.py  LABEL_CANDIDATES  task_kind → 행동 후보     코드  ← 병목
vtmak/scnx/plan.py  REF_FIELD         task_kind → 참조 필드     코드
vtmak/scnx/plan.py  FIRE_KIND         task_kind → 사거리 종류   코드
config/task_catalog.csv               (그룹, 행동) → PLN        데이터
```

`task_catalog.csv`는 이미 33종 행동 / 17종 task type을 담고 있는데
`LABEL_CANDIDATES`가 그중 8종만 도달 가능하게 막고 있다. **이번 작업의 대부분은
새 S-expression 저작이 아니라 배선이다.**

세 코드 표를 `config/task_kinds.csv` 한 장으로 뺀다.

| 열 | 뜻 |
|---|---|
| `task_kind` | `pattern_map.csv`의 `task_kind`와 같은 값 |
| `ref_kind` | `COORD` \| `ENTITY` \| `*`(무관) — `LABEL_CANDIDATES` 키의 둘째 자리 |
| `참조_필드` | Event의 어느 필드에서 대상을 가져오는가. 비면 참조 없음 |
| `사거리_종류` | `direct` \| `indirect` \| 빈칸(검사 안 함) |
| `행동_후보` | `task_catalog.csv`의 '행동' 이름, `\|`로 구분한 우선순위 순 |
| `비고` | 판단 근거 |

발췌다. 기존 8종(`move` · `move_slow` · `fire_direct` · `fire_indirect` · `aim` ·
`suppress` · `take_cover` · `follow`)은 `LABEL_CANDIDATES`의 (kind, ref_kind)
조합을 그대로 옮긴다.

```csv
task_kind,ref_kind,참조_필드,사거리_종류,행동_후보,비고
move,COORD,dst,,좌표로 이동|통제점으로 이동,
move,ENTITY,dst,,좌표로 이동|통제점으로 이동,
fire_direct,ENTITY,target,direct,대상 직접사격|대상 자동무장 사격,
wait,*,,,대기,참조 대상 없음
aim_dir,COORD,target,indirect,방향 조준,
find_fp,COORD,next_fire_target,,사격위치 탐색,후속 사격 문장의 표적
```

**주의 — 위 `find_fp` 행을 그대로 복사하지 말 것.** `사거리_종류`는 반드시
**빈칸**이어야 한다. `indirect`로 두면 `_one()`의 사거리 검사가
`fire_distance[event_id]`를 찾는데 상태전이 이벤트는 이 dict에 없어 21건
전부 "교전 거리 미산출"로 떨어지고 G3의 C3.5가 `BLOCK`을 낸다 — 조용히
task 21개가 통째로 사라진다. 이유는 §4(b)에 있다.

또한 위 발췌의 `aim_dir`은 **설계 당시의 이름이고 실제 구현과 다르다.**
구현은 새 kind를 만들지 않고 기존 `aim` kind를 `ref_kind=COORD`로 재사용한다
(§4(c) 참고) — 새 kind를 만들면 기존 `aim`(ENTITY 대상 객체 조준)이
`LABEL_CANDIDATES`/`task_kinds.csv`에서 도달 불가능한 채로 남기 때문이다.

폴백은 두지 않는다. 파일이 없거나 task_kind가 빠지면 명확히 실패한다 — 조용히
noop이 되면 왜 task가 안 나오는지 `.scnx`를 열어보기 전엔 알 수 없다.

이후 매핑 추가는 **CSV 두 줄**(`pattern_map` 1줄 + `task_kinds` 1줄)이 된다.

### 곁들여 필요한 코드 변경

1. **`_one()`이 참조 없는 kind를 허용해야 한다.** 지금은 `ref`가 비면 무조건
   "참조 대상 없음"으로 끝낸다. `참조_필드`가 빈 kind(`wait`)는 그대로 통과시킨다.
2. **`PatternMap.task_kind()`가 Event를 받는다.** 상태전이를 읽으려면
   `state_from`·`state_to`가 필요하다. 인자를 옵션으로 더하면 안 넘긴 호출부가
   조용히 다른 답을 받는다. 호출부가 6곳(테스트 4곳 포함)뿐이라 한 번에 바꾼다.
3. **`_resolve_ref()`가 그 객체의 이벤트 목록을 받는다.** `next_fire_target`을
   풀려면 필요하다. `build_entity_plan`이 이미 정렬된 목록을 갖고 있다.
4. **`geometry.bearing_elevation(a, b)`** 신규 — 방위·고각(라디안).

## 4. 새 매핑 3종

### (a) `wait-duration` — 179건

```
pattern_map    stopAt,template,stopAt,wait
               stayAt,template,occupy,wait
task_kinds     wait,*,,,대기
task_catalog   '대기' 행 신규 — 보병-소총 · 보병-RPG · 차량/장갑차
```

PLN은 `campaign/campaign.pln`에서 그대로 수확한다. 그 파일에 277개 들어 있는
VR-Forces 저작 리터럴이라 추측이 없다.

```
(Task (task-type "wait-duration") (subtask False)
      (allow-task-visualizations True) (seconds-to-wait 60.000000))
```

60초는 카탈로그 행의 리터럴이므로 코드 수정 없이 바꿀 수 있다. VR-Forces 플랜은
순서 큐라 대기만큼 뒤가 밀린다. 60초는 짧아 영향이 작다고 본다.

대상 그룹은 실측에서 나온 셋뿐이다 — `stopAt`은 보병-소총 52 · 차량 28 ·
보병-RPG 22, `stayAt`은 보병-소총 51 · 차량 26.

공통 폴백은 두지 않는다. 다른 원문에서 넷째 그룹이 `stopAt`을 내면
`_pick_template`이 템플릿을 못 찾고 G3의 C3.5가 `BLOCK`으로 막는다. 그때 카탈로그
행을 추가하면 된다 — 조용히 빠지지 않는 쪽이 낫다. `사격위치 탐색`·`방향 조준`도
같다.

### (b) `find_firing_position` — 21건

```
pattern_map    사격 준비 대기>사격 준비,state_transition,preparesFiringPosition,find_fp
task_kinds     find_fp,COORD,next_fire_target,,사격위치 탐색
task_catalog   '사격위치 탐색' — 미사일 발사대 그룹 1행 추가(무기 무관이라 복제)
```

`Threat`은 **그 객체의 후속 사격 문장의 표적**이다. 21건 전부 연결된다(실패 0).
대상 그룹은 포병 155mm 10 · 포병 박격포 9 · 미사일 발사대 2.

표적이 정적 지점이라 `ctx.ref_uuid`가 통제점 uuid를 할당한다. **이 경로는 이미
구현돼 있어 코드 변경이 없다.** 통제점 7개가 생긴다.

```
LOC_중앙킬존 · LOC_적포병진지 · LOC_적박격포진지 · LOC_적북측접근로
LOC_남측제1방어선 · LOC_아군포병진지 · LOC_아군박격포진지
```

2026-08-03에 통제점을 뺀 것은 배치 지명 29개를 전부 찍어 로딩이 느려졌기
때문이다. 7개는 그와 규모가 다르다. **로딩 영향은 측정하지 않았다** — 측정
라운드에서 확인한다.

사거리_종류는 비워 사거리 검사를 하지 않는다. 처음에는 `indirect`로 두어
"최소사거리 미달로 사격이 빠지면 준비도 같이 빠지게" 하려 했는데, 그렇게
두면 `find_firing_position` 21건이 전부 "교전 거리 미산출"로 떨어진다.
`_one`의 사거리 검사는 `fire_distance[e.event_id]`를 찾는데, 이 dict는
`engagement_pairs`가 사격 이벤트에서만 만든다 — 2026-08-05 실측으로 119건
전부 `directFireAt`(77)·`aimAt`(21)·`indirectFireAt`(21)이고 `사격 준비`
전이(상태전이 이벤트) 21건은 하나도 없다. `indirect`로 두면 21건 전부
"교전 거리 미산출"로 떨어지고 `skip_reason`이 안 붙어 G3의 C3.5가 `BLOCK`을
낸다 — 사격이 아니라 위치 탐색이니 애초에 사거리 검사 대상이 아니다.

부작용은 받아들인다. 뒤따르는 간접사격이 최소사거리 미달로 빠져도 사격위치
탐색은 남는다 — 객체가 자리를 잡고 쏘지 않을 뿐이라 해롭지 않다.

### (c) `set-aiming-point` 방향 조준 — 21건

```
pattern_map    aimAt,template,aimAt,aim_dir        (지금 noop)
task_kinds     aim_dir,COORD,target,indirect,방향 조준
task_catalog   '방향 조준' — 포병 155mm · 포병 박격포 · 미사일 발사대 3행 추가
```

기존 `방향 조준` 템플릿(차량 그룹, `aiming-type 2`)을 복제한다.

```
(Set (set-data-request-type "set-aiming-point") (aiming-point 0.0 0.0 0.0)
     (target-object "") (aiming-azimuth AZIMUTH_RAD)
     (aiming-elevation ELEVATION_RAD) (aiming-type 2) (weapon "…"))
```

`AZIMUTH_RAD`·`ELEVATION_RAD`는 사수→표적 좌표로 계산한다. 무기명은
`plan.with_weapon`이 객체의 실제 무기로 치환하므로 그룹별 값은 기본값일 뿐이다.

`aimAt` 표적 21건이 전부 정적 객체라 객체 조준(`aiming-type 1`)은 쓸 수 없다.
방향 조준이 원문 "포신 정렬"과 의미도 더 정확히 맞는다.

**`# VERIFY-ON-TARGET`** — `aiming-type 2` 문법은 카탈로그에 검증돼 있으나
방위 기준(진북/자북, 시계 방향)은 확인하지 못했다. 틀려도 포신 방향만 어긋나고
task 자체는 돈다.

## 5. AI Enabled와의 관계

2026-08-05에 생성기가 모든 객체를 `AIEnabled False`로 쓰게 바뀌었다. 새 task가
그것 때문에 안 도는 것 아닌가를 확인했고, **아니다.**

- `entity_class_map.csv`의 실패 기록은 전부 "컨트롤러 없음"이다 —
  `T-72 MBT find_cover 12/12 실패`인데 같은 '차량/장갑차' 그룹의 T-80·T-69는
  8/8 성공한다. AI 스위치라면 그룹 전체가 같이 실패했을 것이다. 모델의 플랫폼
  파일에 그 컴포넌트가 있느냐의 문제다.
- **직접 증거** — 2026-08-04 GT(그 런의 `.oob`는 `AIEnabled False` 332개)에
  `ENINF001`의 `find_cover` 행이 있다. AI Off 상태에서 실행됐다는 뜻이다.
- 매뉴얼 34.3 — AI Enabled는 충돌회피·자동사격·피격반응만 끈다. 328객체 중
  294객체가 AI Off로 오류 없이 task를 수행했다.

예외가 `set-target`이다(§2 참조). 그래서 뺐다.

## 6. 검증

### 게이트

G3는 그대로 쓴다. 새 task type이 C3 위반을 내지 않아야 한다. `방향 조준`의
무기는 기존 `test_every_task_weapon_exists_on_that_model`이 잡는다.

### 감사표(05)

`wait-duration`은 참조가 없어 `ref_id`가 빈다. 정상 값이다.

### 새 테스트

- `stopAt`·`stayAt`마다 `wait-duration`이 하나씩 나온다
- `find_firing_position`의 `Threat`이 통제점 uuid로 풀리고, 통제점이 정확히 7개다
- `aim_dir`의 방위·고각이 0이 아니고 라디안 범위 안이다
- `task_kinds.csv`를 지우면 폴백 없이 실패한다
- `LABEL_CANDIDATES`·`REF_FIELD`·`FIRE_KIND`가 코드에서 사라졌다(회귀 방지)
- `noTask` 대상 객체의 그 시각 이후 이동·사격 task가 0건이다(회귀 방지)

### 측정 라운드

저작 → VR-Forces 실행 → `vrfSim.log`의 `No controller` 수집 →
`entity_class_map.csv`의 `unsupported_tasks`에 기록 → 재저작. 1차 런은 오류가
많을 수 있다. 실패 후보는 견인 박격포·ZPU 계열의 `find_firing_position`과
Patriot 계열, 그리고 통제점 7개로 인한 로딩 지연이다.

## 7. 기대치

`.pln`의 task type은 7종에서 10종이 된다. GT 행 수로 보면 `wait-duration`이
대부분을 차지하고 `find_firing_position`·`set-aiming-point`는 짧은 task라 몇 행
남지 않는다(§1의 B). **GT 술어 종수는 늘지만 행 분포는 여전히 오래 도는 task에
치우친다.** 그것을 고치려면 B를 따로 다뤄야 한다.
