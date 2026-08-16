# 전장 STKG → TLogic 변환기 — 설계 스펙 (단순화 버전)

- 날짜: 2026-07-16
- 작성자: 김예원 (사이버마린시스템 연구실)
- 상태: 초안 (검토 대기)
- 관련 연구: STLogic (공간 인지형 시간 논리 규칙, IMETI 2026)

## 1. 목적

자체 구축한 백마고지(Hill-395) 관측 STKG를, **위치(location) 컬럼 하나가 추가된
TLogic 형식**의 평면(flat) 데이터셋으로 변환한다. STLogic 구현의 첫 번째 구체적
산출물이다.

## 2. 출력 형식 (핵심)

`STLogic/data/battlefield_hill395/`, TLogic 데이터셋 레이아웃을 그대로 따름:

```
train.txt  valid.txt  test.txt      # 탭 구분 5개 컬럼 (아래 참조)
entity2id.json  relation2id.json  ts2id.json
landmarks.tsv                       # landmark_name \t easting \t northing
stats.yaml                          # 요약 통계
```

`{train,valid,test}.txt`의 각 행:
```
head <TAB> relation <TAB> tail <TAB> timestamp <TAB> location
```
- `head` — 관측된 엔티티 (섹터별 네임스페이싱, 4.2 참조). 탭이 없는 문자열.
- `relation` — 해당 관측 `relations[]`의 predicate.
- `tail`  — `target_ref` (엔티티 / 지형지물 / 부대), 네임스페이싱된 문자열.
- `timestamp` — 네임스페이싱된 시간 토큰 (4.3 참조); ts2id가 전역 정수 id로 매핑.
- `location` — 해당 시각에서 **head 엔티티의 좌표**를 `easting,northing` 형태로
  (단일 필드, 예: `301356.19,4239394.54`).

### 하위 호환성 (검증 완료)
`grapher.map_to_idx`는 `x[0..3]`(subject/relation/object/timestamp)만 읽고 그 이후
컬럼은 무시한다. 따라서 동일한 5컬럼 파일이 다음 둘 다에 그대로 입력된다:
- **baseline TLogic** (원본 그대로) — 평범한 4컬럼 쿼드러플로 보고 location은 무시;
- **STLogic** — grapher가 `x[4]`를 읽어 head 좌표를 얻음.
별도의 positions sidecar도, 데이터 파일 두 벌도 필요 없다.

## 3. 원천 데이터

`dataset/백마고지 데이터셋/battlefield_hill395_large/` — 75개 섹터, 사전 분할
(`splits/{train,dev,test}.txt`), ontology는 `ontology/relations.yaml`(13개 predicate).
섹터별: `observations.jsonl`(주 소스), `stkg.nt`(landmark 좌표), `manifest.json`.

## 4. 변환 규칙

### 4.1 엣지 (v1 = relations만)
각 관측 `o`(엔티티 `e`, 시각 `t`, 위치 `loc`)에 대해, `o.relations[]`의 각 `rel`마다:
```
(head=e, relation=rel.predicate, tail=rel.target_ref, timestamp=t, location=loc)
```
- 엣지의 소스는 `observations.jsonl`의 `relations[]`(시간 정보 있음)이며,
  `stkg.nt`(시간 정보가 집계되어 사라짐)가 아니다.
- `location`은 항상 **head의 관측 좌표**다 (행 자체가 head의 관측에서 생성되므로
  반드시 존재한다).
- 중복 행(같은 head/rel/tail/ts)은 제거한다 (첫 location 유지).
- ontology(`relations.yaml`)에 없는 predicate → 즉시 오류(fail fast).

v1에서 **의도적으로 제외**(추후 쉬운 토글, 단순화를 위해 제외):
`state`를 `hasState` 엣지로 만드는 것, `events[]` 참여, 관측 confidence,
A/B 멀티소스 융합(`labels/`는 무시).

### 4.2 섹터별 네임스페이싱 (섹터 간 누수 차단)
각 노드 문자열은 소속 섹터를 접두어로 붙여 섹터 간 노드 공유를 없앤다:
`sec_train_0000/ent_A_0001`, `sec_train_0000/lm_crest_0_0`. 섹터는 서로 독립된
장면이고 엔티티가 disjoint하므로, 어떤 temporal walk나 규칙 grounding도 섹터
경계를 넘을 수 없다 — TLogic 코드를 건드리지 않고 **구조적으로** 보장된다.

### 4.3 타임스탬프
- 섹터 내: 고유 `time` 값을 정렬 → 로컬 tick `0..T-1`.
- 전역 id = `sector_index * OFFSET + local_tick` (OFFSET=100000, 어떤 window ω보다도
  훨씬 큼; window 누수에 대한 2차 안전장치). `sector_index`는 train→dev→test 순으로
  모든 섹터를 열거.
- `timestamp` 컬럼 값 = 네임스페이싱 토큰 `"{sector}@{ISO}"` (섹터마다 고유; 원본
  1952-10-06 시각이 섹터 간에 충돌하는 문제를 방지).
- `ts2id.json`이 그 토큰 → 전역 id로 매핑. 섹터 내에서 상대적 Δt는 보존되므로
  TLogic의 `exp(-λ·Δt)` 감쇠가 왜곡되지 않는다.

### 4.4 분할 & id 매핑
- 50개 `sec_train_*` → train.txt, 12개 `sec_dev_*` → valid.txt, 13개 `sec_test_*` → test.txt.
- `entity2id` / `relation2id` / `ts2id`는 모든 split에 걸쳐 전역으로 구축(공유
  어휘; test에만 나오는 엔티티는 정상 — inductive forecasting).

### 4.5 지형지물(landmark) 좌표
`landmarks.tsv`는 네임스페이싱된 각 landmark → 정적 `easting,northing`을 나열하며,
`stkg.nt`(`geo:easting` / `geo:northing`)에서 파싱한다. STLogic은 tail이 landmark일
때 이를 사용한다(firesAt/movesToward/near/emplacedAt/occupies/screens → landmark).
엔티티 tail(follows)은 tail 자신의 행에 있는 location 컬럼에서 좌표를 회수한다.
부대 tail(partOf/supports/reinforces)은 좌표가 없으므로 → STLogic은 해당 엣지에
대해 confidence만 적용(fallback).

## 5. 구성요소 (`STLogic/tools/`)
- `convert_battlefield.py` — CLI: `--src`, `--dst`, `--offset 100000`.
- `sector_reader.py` — 섹터 하나 파싱(observations + landmark 좌표).
- `edge_builder.py` — 레코드 → 행 + landmark 테이블 (순수 함수, 유닛 테스트 가능).
- `id_space.py` — 전역 id 부여(네임스페이싱 + 오프셋), 결정적(deterministic).
- `writer.py` — txt 파일 + json 맵 + landmarks.tsv + stats.yaml 출력.

> 구현 참고: 이 규모에서는 위 5개 모듈이 과분할이라, 실제 구현은 함수로 잘 나눈
> **단일 스크립트** `convert_battlefield.py`로 통합했다(더 단순, 유지보수 용이).

## 6. 오류 처리
- ontology에 없는 predicate → 즉시 오류.
- 좌표가 없는 target을 가진 행 → 그래도 출력(유효한 시간 엣지); location 컬럼은
  target과 무관하게 항상 head 좌표를 담는다.
- 재현성을 위해 모든 곳에서 결정적 순서(섹터 정렬, 시각 정렬).

## 7. 검증
- 유닛: 3개 관측 픽스처에 `edge_builder` → 기대 5컬럼 행 + landmark 테이블.
  `id_space`: 두 섹터 간 엔티티 id 미공유 확인; ts 간격 ≥ OFFSET 확인.
- 통합: train 2 + test 1 섹터 변환 → 행 수 = Σ relations; 모든 행의 location이 두
  float로 파싱; id가 0부터 조밀.
- End-to-end (baseline 수치): 전체 변환 데이터에 순정 TLogic 실행
  (`learn.py -d battlefield_hill395 -l 1 2 3 -n 200 -p 8 -s 12` → apply → evaluate);
  코드 수정 없이(5번째 컬럼 무시) 동작하고 규칙 grounding이 한 섹터 안에 머무는지
  확인. 이것이 STLogic 비교용 TLogic baseline MRR/Hits@k가 된다.

## 8. 범위 밖 (YAGNI)
STLogic 공간 scorer(다음 스펙); A/B 융합; confidence 가중; state/event 엣지(v1 토글 off).

---

## 부록: 실제 실행 결과 (2026-07-16)

- 변환 규모: 엔티티 5,876 / 관계 10종 / 타임스탬프 6,777 / 엣지 116,680
  (train 77,850, valid 18,620, test 20,210) / landmark 600.
- 관계 10종: emplacedAt, firesAt, follows, movesToward, near, occupies, partOf,
  reinforces, screens, supports (ontology 13종 중 relations[]에 등장한 것).
- **TLogic baseline (test split, 13개 섹터)**: MRR 0.625, Hits@1 0.611,
  Hits@3 0.618, Hits@10 0.673.
- 순정 TLogic이 5컬럼 파일에서 learn→apply→evaluate 완주 → 하위 호환성 검증 완료.
