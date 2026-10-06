# STLogic 진행 현황 (Progress)

> 이 문서는 **살아있는 문서**입니다. 작업이 진행될 때마다 계속 갱신합니다.
> 최종 갱신: 2026-07-16

---

## 1. 프로젝트 한 줄 요약

**STLogic** — 전장 시공간 지식 그래프(STKG)에서 시간 논리 규칙(TLogic)에 **공간 맥락
(거리·거리변화량)**을 결합해, 설명 가능하면서도 변별력 높은 link forecasting을 수행.
목표 학회: IMETI 2026 (10/30~11/03, Taipei).

기존 TLogic의 한계: 하나의 시간 규칙이 수십~수백 개의 동일 confidence 후보를 생성 →
변별력 저하. STLogic은 규칙별 Gaussian 공간 분포로 후보를 재순위화해 이를 보완.

---

## 2. 현재 상태 요약 (2026-07-16)

| 단계 | 상태 |
|---|---|
| TLogic 환경 세팅 | ✅ 완료 (`tlogic` conda env, Python 3.10) |
| 백마고지 데이터셋 파악 | ✅ 완료 (100만+ triple, 75섹터) |
| STKG → TLogic 변환기 | ✅ 완료 (`convert_battlefield.py`) |
| TLogic baseline 확보 | ✅ 완료 (**MRR 0.546**, 유효값) |
| STLogic 공간 scorer | ✅ 구현 완료 (재순위화 ②③ + backoff ① + 부대중심점) |
| STLogic ablation | ✅ 완료 — **best MRR 0.5891 (baseline 0.5464 대비 +4.3%p, Hits@10 +12.7%p)** |
| **비교군 실험** | 🟡 **선정 완료·실행 전** — inductive 프로토콜 결정이 선행 블로커 (§6) |
| 논문 필수(case study·다중seed) | ⬜ 미착수 (싸고 급함) |
| 논문 작성 | ⬜ 미착수 |

---

## 3. 데이터셋 현황

### 원천 (관측 STKG)
- 위치: `dataset/백마고지 데이터셋/battlefield_hill395_large/`
- 규모: **1,005,101 triple, 75섹터** (train 50 / dev 12 / test 13), 사전 분할.
- 구성: 섹터별 `observations.jsonl`(시간별 관측=observation index, 좌표·velocity·state
  포함) + `stkg.nt`(landmark 좌표) + `manifest.json` + `labels/`(A/B 융합 정답, STLogic엔 미사용).
- ontology: 관계 13종, state 11종. `n_robots=2` → kg A/B 멀티소스(같은 장면 2번 관측).
- ※ 상위 폴더의 `stkg.nt` / `observations.jsonl` 단독 파일은 sec_dev_0000 **샘플**일 뿐.

### 변환 결과 (TLogic 입력)
- 위치: `STLogic/data/battlefield_hill395/`
- 포맷: `head \t relation \t tail \t timestamp \t location(E,N)` **5컬럼**
  (baseline TLogic은 앞 4컬럼만 읽고 location 무시 → TLogic·STLogic 공용 파일).
- 규모: 엔티티 5,876 / 관계 10 / 타임스탬프 6,777 / 엣지 116,680
  (train 77,850 · valid 18,620 · test 20,210) / landmark 600.
- 관계 10종: emplacedAt, firesAt, follows, movesToward, near, occupies, partOf,
  reinforces, screens, supports.
- 부속: `entity2id/relation2id/ts2id.json`, `landmarks.tsv`, `stats.yaml`.

### VR-Forces (VTMAK) 데이터 — ver2.0, 2026-09-14 투입
- 원천: `STLogic/dataset/VR-Forces/` — `UAV1~5_ver2.0.csv`, `ground_truth_ver2.0.csv`
  (68열, 1Hz, 약 1.0GB). 시나리오 자산은 `STKG_Experiments/VR-Forces/`.
- **premade 5컬럼 변환**: `tools/convert_vrforces.py` → `data/VR-Forces/`
  (`subject,predicate,object,timestamp,location="(lat, lon)"`). 사람이 읽는 중간
  산출물이라 grapher가 파싱하지 않는 괄호 형식을 의도적으로 유지.
- **TLogic/STLogic 데이터셋**: `tools/build_vrforces_dataset.py` →
  `data/VR-Forces_{ground_truth,uav}_s10/`. 좌표는 **local ENU 미터**(lat/lon 도를
  그대로 쓰면 거리 7% 왜곡·방위는 더 크게 틀어짐). landmark 좌표는
  `VR-Forces/config/battlefield_layout.json`, 엔티티 타입·부대는
  `VR-Forces/build/registry/master_entities.csv`에서 가져온다(하이픈 제거로 323/323 매칭).
- GT 규모(stride 10s): 틱 173(train 121 / valid 25 / test 27), 엔티티 341,
  **관계 4종**, landmark 18, 엣지 train 29,885 / valid 5,691 / test 5,170.

#### ⚠️ 이 데이터의 성질 (방법론을 좌우함)
- 엣지 496,639개인데 **distinct triple은 522개** — Data Logger가 tick마다 '수행 중인
  task'를 찍어 같은 사실이 934배 중복된다. 1Hz 원본에서 **실제 object 전이는 158건뿐**
  (전부 `move to`; Fire-Weapon·FFE·Provide-Suppressive-Fire-Loc은 전이 0건).
- 전이 158건은 **146 subject에 고루** 퍼져 있다(1회 139명, 상위 5명 점유 9.5%).
  LOC 전이 그래프는 24쌍. 즉 편중 문제는 없다.
- 단일 장면이라 **inductive 설정이 사라졌다**. hill395의 "임베딩 모델 실행 불가" 논지는
  이 데이터엔 적용되지 않는 대신, 임베딩 비교군이 드디어 돌아간다(§6-0(나) 해소).
- UAV는 부분 관측: 개별 33~60%, 합집합 216/333, **117개는 아무 UAV도 못 봄**.
  전이 시점 기준 실시간 관측은 1/158(1%), 마지막 관측 후 경과 중앙 31틱·최대 609틱.

---

## 4. Baseline 현황

**TLogic baseline** (train 50섹터 학습 → test 13섹터 평가, inductive):

| 지표 | 값 |
|---|---|
| MRR | **0.546** |
| Hits@1 | 0.516 |
| Hits@3 | 0.548 |
| Hits@10 | 0.612 |

- 실행: `learn.py -d battlefield_hill395 -l 1 2 3 -n 200 -p 8 -s 12` → `apply.py -w 0` → `evaluate.py`
- 규칙: 111개 (길이1=16, 길이2=10, 길이3=85).
- test 쿼리 11,118개는 후보 없음(규칙 미발화) — 이 부분은 STLogic도 개선 대상 아님.
- ⚠️ 정정: 초기 측정치 0.625는 ts id가 uint16 한계를 넘겨(OFFSET=100000) `get_walks`에서
  timestamp가 손상된 무효값이었음. 변환기를 **연속 rank ts id**(max 6776 < 65535)로 고쳐
  재측정한 위 값이 유효 baseline.

---

## 5. 자산 위치 맵

| 항목 | 경로 |
|---|---|
| TLogic 원본(참조) | `STKG_Experiments/TLogic/` |
| STLogic 작업 폴더 | `STKG_Experiments/STLogic/` |
| TLogic/STLogic 소스 | `STLogic/mycode/` (learn/apply/evaluate/grapher/temporal_walk/...) |
| **변환기** | `STLogic/tools/convert_battlefield.py` |
| 변환 데이터 | `STLogic/data/battlefield_hill395/` |
| 규칙/후보 출력 | `STLogic/output/battlefield_hill395/` |
| 변환기 설계 스펙 (영/한) | `STLogic/docs/superpowers/specs/2026-07-16-...-design.md` / `.ko.md` |
| **STLogic 연구내용 (프로포저용)** | `STLogic/docs/STLogic_연구내용.md` |
| 이 진행문서 | `STLogic/docs/PROGRESS.md` |
| conda 환경 | `tlogic` (Python 3.10, numpy/pandas/joblib) |
| 실행 파이썬 | `C:/Users/user/anaconda3/envs/tlogic/python.exe` |

---

## 6. 다음 단계 (TODO)

> STLogic 방법 구현·ablation은 **완료**. 이후는 **비교/엄밀성/논문화**가 핵심.

### 6-0. 먼저 결정할 것 (블로커)
- **(가) 기여 스토리 재정의**: 원 제안서는 "공간 재순위화" 중심이나 실험 결과 재순위화는 미미(+0.4%p),
  **진짜 이득은 ① 공간 backoff 후보생성 + 부대 중심점**(+4.3%p, Hits@10 +12.7%p). 논문 핵심 기여를
  "규칙 실패 쿼리를 프레임 불변 공간서명으로 되살리는 spatial candidate generation"으로 재프레이밍 필요.
- **(나) inductive 프로토콜 결정 — 비교군 전체를 좌우** ⚠️:
  우리 데이터는 엔티티를 섹터별 네임스페이싱 → **test 엔티티 전부 미지(완전 inductive)**.
  → 임베딩 모델(RE-Net/CyGNet/TiRGN/STSE)은 test 엔티티 임베딩이 없어 **실행 불가/완전 실패**.
  TLogic/STLogic은 변수 규칙+위치 특징이라 정체성 비의존이라 OK.
  - (A) inductive 유지 → "기존 임베딩 STKG는 미지 전장 전이 불가, STLogic만 가능"을 **기여로**
  - (B) transductive 변형 데이터셋 추가(엔티티 공유) → 임베딩에 공정한 무대, 별도 표로 보고
  - (C) inductive 가능 baseline만(xERTE/TITer)으로 교체
  - 추천: **A를 메인 + STSE/임베딩엔 B 보조** ("inductive 독보 + transductive 무대서도 경쟁력")

### 6-1. 비교군 실험 (선정 완료, 실행 남음)
- ※ **비교군 확정 필요**: 실험계획 PDF(RE-Net/CyGNet/TiRGN/STSE) vs PPT(CounTRuCoLa/C-TLogic) **불일치**.
- **규칙 기반** (1순위, inductive OK):
  - TLogic ✅ 완료 (직접 부모, 가장 공정한 비교, 0.546).
  - CounTRuCoLa: 코드 있음 `github.com/JuliaGast/counttrucola` (CPU). 단 **TGB 2.0 커스텀 데이터셋 변환** 필요,
    c/f-rules는 엔티티 상수 → inductive 전이 불가(변수 규칙만 작동).
  - C-TLogic: 독립 공개 코드 불명확 → 보류/재구현 리스크.
- **STKG(STSE)** (2순위): 임베딩 기반 → 프로토콜 이슈, 좌표 입력 필요.
- **임베딩 TKG(RE-Net/CyGNet/TiRGN)** (3순위): `nec-research/TKG-Forecasting-Evaluation` 통합 프레임워크
  활용 가능(CEN/CyGNet/RE-GCN/RE-NET/TANGO/TLogic/xERTE 등), GPU 필요, 프로토콜 이슈.

### 6-2. 논문 필수 (싸고 급함, 신경망 불필요)
- **설명가능성 case study**: 동일 규칙 다수 후보에서 STLogic이 공간 근거와 함께 정답을 올리는 실사례.
- **다중 seed 반복**: 현재 seed=12 단일 → 평균±표준편차, 섹터별 분산.
- **비-공간 backoff 대조군**(빈도/랜덤): backoff 이득이 "공간" 덕임을 증명.

### 6-3. 방법 완결·강화 (선택)
- 잔존 3,146 no-cand: `stkg.nt`에서 대대→연대 계층 emit → supports/reinforces 공간화.
- σ 자동 게이팅 실증 + 관계별 이득 분해.
- 도메인 일반성: 공개 STKG(ICEWS05-ST 등)에 STLogic 적용 → frame-invariance 실증.
- 노이즈 강건성(CEP·멀티소스·20% dangling), 하이퍼파라미터 민감도(α, f_min, top_k, window).

---

## 7. 작업 로그

### 2026-07-16
- `tlogic` conda 환경 제거 후 재생성(Python 3.10.20), 의존성 설치, import·스모크테스트 통과.
- 백마고지 데이터셋 구조 분석: `battlefield_hill395_large`(75섹터, 100만 triple, ontology, 사전분할) 발견.
- 변환 설계 확정: 5컬럼(+location) 포맷, 섹터별 네임스페이싱, 시간 오프셋, A/B 병합.
- 설계 스펙 문서화(영문 + 한국어판).
- `convert_battlefield.py` 구현 → 전체 변환(엔티티 5,876 / 엣지 116,680).
- 순정 TLogic end-to-end 실행 → **baseline MRR 0.625** 확보(5컬럼 호환성 검증).
- STLogic 공간 scorer 설계 확정: 좌표계 불변성 원리 → 상대 극-운동학 (d, Δd, β) 규칙별 Gaussian
  + 분산 자동 게이팅 + 스트리밍 누적. 연구내용 문서화(`docs/STLogic_연구내용.md`).
- ⚠️ 변환기 버그 수정: ts id uint16 초과 → 연속 rank id(max 6776). 유효 baseline MRR 0.546.
- STLogic 공간 scorer 구현 완료: `spatial_context.py`(신규) + grapher/rule_learning/learn/
  rule_application/apply 연결. 유닛테스트 통과. 규칙 111개 중 90개에 (μ,σ) 부착.
- **1차 ablation(test)**: off 0.5464 / dist 0.5467 / dist_dd 0.5443 / dist_dd_bearing 0.5457 (MRR).
  회귀 통과(off=baseline). 그러나 **공간 효과 사실상 없음**(dist Hits@10만 0.612→0.629). 원인
  추정: 후보없음 27% 희석, 규칙 σ 과대(변별력 약), 평균결합 희석. → 진단 필요.
- **진단**: 답변가능 72.5% 중 정답 rank-1 이미 72.5%(헤드룸 없음), 거리 σ/μ=0.44(뭉툭),
  방위 cosb σ≈균일(노이즈). 그러나 **정답이 rank-1이 아닌 hard 7,857건에서 dist가 MRR
  0.152→0.199 (+4.7%p, 상대 +31%)** — 애매한 구간에서 공간이 실제로 작동함 확인.
- **②③ 실험**(dist 기준): 타입조건부(②) 효과 없음(hard MRR 0.1985 무변화, 가설 기각);
  tie게이팅(③, fm0.5)은 aggregate엔 유리(easy 보호)하나 hard 이득은 감소(+4.7→+4.2%p) = 트레이드오프.
  최선 dist+type+gate agg MRR **0.5464→0.5502(+0.38%p)** — 실재하나 드라마틱 아님.
  결론: **재순위화는 천장 근접.** 드라마틱은 ①(후보없음 27% 공간 backoff 생성)에서.
  실험 스크립트: scratchpad(run_ablation/run_exp2/diag_hard).
- **① 공간 backoff 실험**: 규칙 미발화 쿼리에 관계별 공간서명으로 후보 생성. no-cand
  11,118→8,987(2,131건 회복, 평균 rank~3), **MRR 0.5464→0.5627(+1.63%p, ②③의 4배)**,
  Hits@10 0.612→0.664(+5.3%p). 부작용 없음(빈 쿼리만 채움, 재순위화와 stack).
  best=dist+type+gate+backoff. 남은 여지: 위치 없는 subject 커버리지(8,987 잔존).
  실험: scratchpad/run_exp1.sh. 코드: apply.py --backoff, spatial_context.fit_relation_spatial/backoff_candidates.
- **잔존 no-cand 진단**: 8,987 중 98.9%가 partOf/supports/reinforces(대상=부대, 좌표 없음).
- **① 부대 중심점 확장**: 부대 위치=구성원 재귀 centroid(build_unit_members, 계층 재귀). test
  부대 커버 위해 all_idx 멤버십 사용, **leave-one-out**(후보를 상대 부대 centroid에서 제외)로
  유출 제거 → 검증됨(0.5856 vs LOO 0.5854 동일). partOf/_partOf 5,400+ 회복.
  **no-cand 11,118→3,146, best MRR 0.5891, Hits@10 0.612→0.739(+12.7%p).**
  잔존 3,146=supports/reinforces(연대, 변환데이터에 대대→연대 계층 없음). 실험 scratchpad/run_exp1b.sh.
- **비교군 조사**: 규칙 기반 우선 방침. CounTRuCoLa 코드 존재(`JuliaGast/counttrucola`, CPU, TGB 변환 필요),
  C-TLogic 코드 불명확. 임베딩 baseline은 `nec-research/TKG-Forecasting-Evaluation` 통합 프레임 활용 가능.
  **핵심 발견: 우리 inductive(섹터별 네임스페이싱) 설계상 임베딩 모델은 test 엔티티 임베딩이 없어 실행 불가**
  → 비교군 착수 전 inductive 프로토콜(A/B/C) 결정 필요(§6-0). 진행 보류, 사용자 결정 대기.

### 2026-09-14 — VR-Forces ver2.0 투입, fixed-horizon 평가로 전환
- **문제 진단**: tick 단위 `(s,r,?,t)` 평가는 성립하지 않는다. persistence(직전 답 복사)가
  MRR 0.9997 — 공간이든 무엇이든 올릴 자리가 없다. transition만 평가하면 시간 분할 시
  test 전이가 2~3건이라 통계가 안 나온다.
- **해결**: 예측 대상은 원래대로 `(s,r,?,t)`로 두되 **forecasting horizon Δ**를 도입.
  쿼리는 실제 시각 t에 그대로 두고, 모델이 볼 수 있는 것은 `t-Δ`까지로 자른다.
  `apply.py --horizon`(단위: 틱). 누수 지점 셋 — 창 컷오프·공간 기준 시각·시간 근접성
  점수 — 에 **모두** `obs_ts = ts - horizon`을 적용. `--horizon 0`은 순정과 동일 경로.
- **평가기 신설** `mycode/evaluate_horizon.py`: aggregate + **hard 부분집합**(관측 시점과
  답이 달라진 쿼리) + **클러스터 부트스트랩 CI**(전이 1건이 최대 Δ개의 상관된 쿼리를
  낳으므로 독립 단위는 쿼리가 아니라 전이).

**TLogic baseline (GT, stride 10s, `-l 1 2 3 -w 3`, 규칙 22개, test 쿼리 10,340)**

| horizon | persistence H@1 | TLogic MRR (all) | hard n | **hard MRR** | hard 클러스터 | hard MRR 95% CI |
|---|---:|---:|---:|---:|---:|---|
| 0s    | 1.0000 | 0.9994 | 0 | — | 0 | — |
| 30s   | 0.9983 | 0.9977 | 12 | 0.0029 | 5 | [0.0029, 0.0029] |
| 60s   | 0.9965 | 0.9960 | 24 | 0.0029 | 5 | [0.0029, 0.0029] |
| 120s  | 0.9930 | 0.9927 | 48 | 0.0029 | 5 | [0.0029, 0.0029] |
| 300s  | 0.9677 | 0.9653 | 230 | 0.0029 | 27 | [0.0029, 0.0029] |
| 600s  | 0.8584 | **0.8358** | 1,170 | **0.0110** | 134 | [0.0079, 0.0147] |

- **horizon이 길어질수록 헤드룸이 열린다**: hard 비율 0% → 11.3%, 600s에서 hard 쿼리
  1,170건 / 독립 클러스터 134개로 통계가 성립한다.
- **600s에서 TLogic은 persistence보다 못하다**(0.8358 < 0.8584). 시간 규칙이 학습한 최상위
  규칙이 `move to(X,Y,t) :- move to(X,Y,t')` conf 0.98 — persistence 그 자체라, 답이 바뀌는
  구간에서 오히려 해가 된다.
- **핵심 진단 — 병목은 재순위화가 아니라 후보 생성이다**: 600s hard 쿼리 1,170건 중
  **98.4%(1,151건)에서 정답이 후보 목록에 아예 없다**. 후보 개수 중앙값 2개.
  hill395에서 이득이 ①backoff·centroid(후보 생성)에서 나왔던 것과 같은 구조이고, 정도는
  훨씬 심하다. 답 후보가 landmark 18개뿐이라 공간 기반 생성기는 승산이 크다.
- 따라서 STLogic 실험은 거리·접근율·heading을 **재순위화 항이 아니라 후보 생성기**로
  놓는 설계가 1순위다.

#### 실행 중 고친 버그 (모두 잠복 상태였음)
- `grapher.py`: id JSON을 인코딩 지정 없이 열어 Windows 기본 cp949로 읽음 → 비ASCII
  엔티티명(한글 LOC)에서 즉사. hill395는 전부 ASCII라 드러나지 않았다.
- `rule_application.save_candidates`: 점수가 numpy `float32`라 `json.dump`가 중간에
  예외를 내고 **14바이트짜리 잘린 파일**을 남김. 조용한 데이터 손실이라 특히 위험.
- `apply.py`: `np.product` → `np.prod` (numpy 2.x에서 제거됨). `TLogic/`은 순정 보존.
- 후보 파일명에 horizon이 없어 스윕이 서로 덮어씀 → 파일명에 `_h<N>` 추가.
- `-w 0`(과거 전체)은 길이-3 규칙 조인이 28GiB를 요구하며 터진다. 단일 장면이라 tail이
  landmark 18개로 수렴해 워크가 팬아웃하기 때문. 유계 창(`-w 3`)으로 회피.

### 2026-09-21 — Final test after validation freeze (VR-Forces)

프로토콜: `K`·`λ`·`Norm(F_r)` 통계를 **valid에서만** 결정하고 test는 1회만 열었다.
고정값 `K = 10`, `λ = 0.1`(convex), horizon 60틱(600초), test 쿼리 10,340.

**① Candidate Recall@K**

| K | TLogic | STLogic | 차이 |
|---|---:|---:|---:|
| 1 | 0.5094 | 0.5094 | +0.0000 |
| 3 | 0.5441 | 0.5531 | +0.0090 |
| **10** | 0.6332 | **0.6795** | **+0.0463** |
| 20 | 0.7094 | 0.7557 | +0.0463 |

**② Spatial Recovery Rate** — TLogic 후보에 정답이 없던 1,486건 중 **479건(32.23%)** 복구.

**③ Fusion curve** — **average tie-handling 기준 (공식)**

| 모델 | ALL MRR | HARD MRR | H@1 | CR@10 |
|---|---:|---:|---:|---:|
| TLogic | 0.7695 | 0.0110 | 0.7475 | 0.6332 |
| **STLogic-Conservative λ=0.1** | **0.7815** | **0.1162** | 0.7475 | 0.6795 |
| STLogic-Fusion λ=0.3 | 0.7826 | 0.1205 | 0.7495 | 0.6795 |
| STLogic-Fusion λ=0.5 | 0.6736 | 0.1322 | 0.6062 | 0.6795 |
| STLogic-Fusion λ=0.7 | 0.6624 | 0.1495 | 0.6065 | 0.6795 |
| STLogic-Fusion λ=0.9 | 0.6265 | 0.1497 | 0.5640 | 0.6752 |
| Spatial-only λ=1.0 | 0.5844 | **0.1524** | 0.5059 | 0.6470 |

```
Δ ALL  MRR = +0.0120     0.7695 → 0.7815
Δ HARD MRR = +0.1052     0.0110 → 0.1162   (10.6배)
H@1        = 0.7475 → 0.7475              쉬운 쿼리 불변
```

**⚠️ 평가 규약 변경 이력** — 이 표를 처음 낼 때는 tie handling이 `best`였고 ALL MRR이
TLogic 0.8358 / STLogic 0.8478이었다. 이후 primary를 `average`로 통일하면서 ALL이
0.0663 내려갔다. **HARD는 0.0110 / 0.1162로 전혀 변하지 않았고 Δ도 불변이다**(+0.0120 /
+0.1052) — 결론은 그대로이고 절대값만 규약을 따라 이동했다. `best` 수치는 폐기하지 않고
규약 변경 전 기록으로 남긴다. ALL에서만 차이가 나는 이유는 persistence 쿼리(88%)에서
TLogic 후보에 동점이 많고 `best`가 이를 낙관적으로 처리하기 때문이다.

**④ 동점 처리 민감도 (hard MRR)** — `E_S` 전환으로 인공물 소멸.

| | best | average | worst |
|---|---:|---:|---:|
| TLogic | 0.0110 | 0.0110 | 0.0083 |
| **STLogic λ=0.1** | **0.1162** | **0.1162** | **0.1162** |
| Spatial-only λ=1.0 | 0.1524 | 0.1524 | 0.1524 |

**⑤ hard MRR 95% 클러스터 부트스트랩 CI** (클러스터 134개) — **비중첩**.

```
TLogic         [0.0079, 0.0147]
STLogic λ=0.1  [0.0827, 0.1564]
```

**⚠️ 프로토콜 기록** — test에서 `λ=0.3`이 ALL MRR 0.8489로 `λ=0.1`(0.8478)보다 근소하게
높았으나 **선택하지 않았다.** λ는 valid에서 결정했고 차이는 +0.0011로 무의미하며,
test를 보고 고르면 test-set driven selection이 된다.

**CR@1·H@1 불변**은 Conservative의 정의와 일치하는 동작이다. λ=0.1에서 주입 후보는
`0.1·E_S ≤ 0.1`이고 persistence 후보는 `0.9·0.98 ≈ 0.88`이라 1위를 넘을 수 없다.
개선은 전부 2위 이하에서 일어난다 — *기존 temporal top-1 예측을 보존하면서 TLogic이
놓친 정답을 하위 rank에 복구한다.*

### Case Study — Spatial Recovery 479건 분석 (2026-09-21)

대표 사례를 고르기 전에 **479건 전체를 먼저 집계**했다. 그 결과가 STLogic의 작동
메커니즘 해석을 수정했다.

> We first analyzed all 479 spatially recovered cases and then selected
> representative examples reflecting the dominant recovery patterns.

**① 관계별 recovery** — 복구는 `move to` 한 관계에만 일어난다.

| relation | missing | recovered | SRR_r |
|---|---:|---:|---:|
| `move to` | 576 | **479** | **83.2%** |
| `_move to` (역) | 616 | 0 | 0.0% |
| `Fire-Weapon` | 147 | 0 | 0.0% |
| `_Fire-Weapon` (역) | 147 | 0 | 0.0% |

전체 SRR 32.23%는 사실상 **"`move to`에서 83.2%, 나머지 0%"의 가중평균**이다. 역관계는
object가 엔티티인데 공간 모델이 정방향으로 적합돼 있고, `Fire-Weapon`은 두 분포가 겹쳐
`F_r ≈ 0`이라 문턱을 넘지 못한다.

**② 정답의 공간 순위 / ③ 최종 순위**

```
C_S 내 정답 순위   1위 9.2% · 2~3위 45.5% · 4~10위 45.3%
STLogic 최종 순위  1위 0.0% · 2~3위 19.4% · 4~10위 80.6%
```

**④ 정답 vs 최상위 경쟁 오답** (raw 미터)

| | 정답 Q1/중앙/Q3 | 오답 Q1/중앙/Q3 |
|---|---|---|
| `F_r` | 0.314 / 0.470 / 0.516 | 0.534 / 0.545 / 0.561 |
| `d` | 877 / 954 / 1,057 m | 650 / 809 / 858 m |

**정답의 `F_r`이 경쟁 오답보다 큰 경우는 44/479 = 9.2%뿐이다.** 즉 복구는 정확한 식별이
아니라 relation-compatible top-K 주입 덕분이다.

**⑤ position source** — registry 310 (64.7%) · direct 169 (35.3%).

#### 메커니즘 진단 — 왜 정답이 더 먼가

학습된 `move to` Gaussian (L=1,057 m, τ=1 s):

```
positive  μ = (d̃ 0.853, ṽ −0.0006)  σ = (0.328, 0.0011)  n = 16,390   → d 중심 901 m ± 346 m
negative  μ = (d̃ 1.163, ṽ −0.0003)  σ = (0.590, 0.0010)  n = 129,076  → d 중심 1,229 m ± 623 m
```

모델은 "정답은 더 가까운 쪽"(901 vs 1,229 m)을 올바르게 학습했다. 그런데 recovered
케이스의 정답은 중앙 954 m로 positive 중심보다 멀고, 경쟁 오답(809 m)이 오히려 중심에
가깝다. `corr(Δd, ΔF) = −0.732`.

**결정적 증거 — 정답은 단 한 건도 최근접 landmark가 아니다.**

| 거리순 정답 순위 (후보 15개) | 건수 |
|---|---:|
| 1위 | **0 (0.0%)** |
| 2~3위 | 0 (0.0%) |
| 4~7위 | 432 (90.2%) |
| 8위+ | 47 (9.8%) |

600초 동안 실제 이동거리는 중앙 658 m로, 정답까지 954 m 중 **69%만 좁힌다**. 즉 관측
시점에 정답은 아직 도달하지 않은 중간 거리의 목적지다. `[d]`가 틀린 것이 아니라
**현재 거리만으로 미래 목적지를 식별할 정보가 원리적으로 부족하다.**

> Spatial context was substantially more effective for **candidate recovery** than for
> fine-grained destination discrimination. For `move to`, 83.2% of missing destinations
> were recovered, whereas only 9.2% of recovered truths received the highest spatial
> compatibility score, and **none was the nearest landmark** (90.2% ranked 4th–7th by
> distance). Units traversed only 69% of the distance to their true destination within
> the 600 s horizon.

**기여 구조 수정**

```
TLogic → Relation-compatible Spatial Candidate Recovery (주된 효과)
       → Conservative Spatial Reranking (제한적 보정)
```

메인 모델 λ=0.1에서 **최종 1위가 0건**이라는 사실이 "제한적 보정"을 직접 뒷받침한다.

**⚠️ `F_r > 0` 문턱의 효과는 주장하지 않는다.** `|O_vis(move to)| = 15`에 `K = 10`이라
후보 풀이 좁아, threshold-없음 ablation 없이는 문턱의 기여가 분리되지 않는다. 방법
설명 수준으로만 기술한다.

#### 대표 3건 (479건 분포에 근거해 기계적으로 선별)

| | Query | GT | TLogic 최상위 (S_T) | 정답 d / F_r / C_S 순위 | 최종 |
|---|---|---|---|---|---:|
| **A. Typical Recovery** | ENINF098, 13:46:42 | LOC_적북측접근로 | LOC_동측측방접근로 (1.000) | 975 m / 0.440 / 4위 | 5위 |
| **B. Successful Discrimination** | FRSNP005, 13:49:42 | LOC_중앙킬존남측 | LOC_적북측접근로 (1.000) | 840 m / 0.542 / **1위** | **2위** |
| **C. Recovery Limitation** | FRSNP002, 13:46:42 | LOC_목표A남측 | LOC_적북측접근로 (1.000) | 1,050 m / 0.347 / 8위 | 8위 |

- **A** — 전체 중앙값에 가장 가까운 사례. 정답이 경쟁 후보보다 203 m 멀고 `F_r`도 낮지만
  (0.440 vs 0.562) 후보군에는 들어온다. 식별이 아니라 복구라는 주된 작동 방식.
- **B** — 공간 순위 1위인 **9.2%** 사례. 정답이 195 m 더 먼데도 `F_r`이 높다(0.542 vs
  0.501) — 학습 positive 중심 901 m에 840 m가 더 가깝기 때문. *This pattern occurred in
  9.2% of recovered cases.*
- **C** — 경쟁 후보 `LOC_적북측접근로`가 **temporal 1위(S_T=1.000)이자 공간 1위(F_r=0.900)**
  다. λ=0.1에서 정답이 얻는 `0.1·E_S`로는 `0.9·1.000`을 넘을 수 없다. **이 한 사례가
  H@1이 불변이고 H@10·HARD MRR만 개선되는 이유를 설명한다.**

*(B의 선별 기준 주의: "F_r(정답) > F_r(최상위 경쟁)"과 "공간 순위 1위"는 정의상 동일한
조건이다 — 최상위 경쟁을 `C_S` 1위로 정의했기 때문. 44건 모두 공간 순위 1위였다.)*

**Discussion limitation**

> STLogic is effective at recovering plausible future destinations that temporal rule
> grounding misses, but current spatial features provide limited fine-grained
> discrimination among multiple relation-compatible destinations.

전체 479건은 `scratchpad/recovery_cases.csv`에 있다.

---

### RQ1 Multi-seed 재현성 (5 seeds, 2026-09-21)

hyperparameter는 고정하고 seed만 바꾼다 — robustness check이지 hyperparameter
search가 아니다. master seed에서 구성요소 seed를 유도한다.

```
master ∈ {12, 13, 14, 15, 16}
  tlogic_seed   = master           TLogic random walk
  negative_seed = master + 1000    hard / relation-compatible negative sampling
  thinning_seed = master + 2000    GT-Sparse-δ (RQ2 확장용, 예약)
```

seed마다 **규칙 학습 → hard negative 재생성 → spatial model 재적합 → STLogic 적용 →
test 평가** 전체를 다시 돈다.

| 지표 | TLogic | STLogic |
|---|---|---|
| ALL MRR | 0.7691 ± 0.0008 | **0.7820 ± 0.0003** |
| H@1 | 0.7475 ± 0.0000 | 0.7475 ± 0.0000 |
| H@10 | 0.8391 ± 0.0015 | **0.8859 ± 0.0001** |
| HARD MRR | 0.0094 ± 0.0032 | **0.1219 ± 0.0014** |
| CR@10 | — | 0.6792 ± 0.0001 |
| SRR (%) | — | 32.40 ± 0.68 |

**seed별 Δ가 핵심이다** — 같은 seed 안에서 두 모델이 동일한 규칙 집합을 공유하므로
짝지은 비교가 되고, "개선이 seed마다 유지되는가"에 직접 답한다.

| seed | Δ ALL | Δ HARD |
|---|---:|---:|
| 12 | +0.0127 | +0.1118 |
| 13 | +0.0126 | +0.1113 |
| 14 | +0.0138 | +0.1162 |
| 15 | +0.0126 | +0.1113 |
| 16 | +0.0127 | +0.1119 |

```
Δ ALL   = +0.0129 ± 0.0005
Δ HARD  = +0.1125 ± 0.0019        표준편차가 평균의 1.7%
```

seed별 hard MRR 95% CI가 거의 겹친다(`[0.083, 0.166]` 근방). 부수 통계:
learned rules 21.4 ± 0.8 · spatial positive samples 18,298 ± 0 ·
no-candidate queries 294 ± 0 · hard clusters 134 ± 0. 뒤의 셋이 seed와 무관하게
고정된 것은 정상이다 — 샘플 대상 사실과 hard 정의는 데이터가 정하고 seed는 negative
추출에만 관여한다.

**TLogic HARD의 변동(±0.0032)이 STLogic(±0.0014)보다 크다.** seed 14에서 0.0029까지
떨어지는데, 어떤 규칙이 뽑히느냐에 따라 hard 쿼리를 우연히 맞히는 정도가 흔들린다.
절대값이 작아 상대 변동이 커 보이는 것이고 **STLogic 쪽이 더 안정적이다.**

**단일 seed 값과의 차이** — 앞 절의 Δ HARD +0.1052는 seed 12 단일 실행값이고
multi-seed의 seed 12는 +0.1118이다. 원인은 **negative sampling seed**다: 앞 절은
`rng_seed=0`, multi-seed는 `negative_seed = master + 1000 = 1012`를 쓴다. TLogic 쪽
HARD는 두 경우 모두 0.0110으로 동일하므로 차이는 전부 spatial model 쪽에서 온다.

**재현성 확인** — `learn.py -s 12`를 두 번 실행해 규칙 파일을 비교한 결과 규칙 22개가
**내용까지 완전히 동일**했다. TLogic rule learning은 결정론적이다
(`np.random.seed(seed)`를 각 워커에서 호출하고 관계 분배가 고정). 따라서 "동일 seed =
동일 run"이 성립하며 "5 random seeds"라는 표현을 쓸 수 있다.

**공식 수치는 5-seed 평균 +0.1125 ± 0.0019를 쓴다.**

---

### RQ2 준비 — 관측 조건 분리 (2026-09-21)

RQ2는 retraining 실험이 아니라 **observation robustness 실험**이다. 모델·하이퍼파라미터를
전혀 바꾸지 않고 입력 조건만 바꾼다.

```
Query / Label      ←  -d          (GT)
Visible edges      ←  --history   (조건별)
Spatial positions  ←  --source    (조건별)
```

`apply.py --history` 신설. 생략하면 `history = -d`로 기존 동작과 동일하며,
**회귀 확인: `--history GT`가 생략 시와 후보 파일 완전 일치(쿼리 10,340).**

UAV 데이터셋은 `build_vrforces_dataset.py --reuse-ids`로 **GT와 같은 id 공간**에
빌드한다. UAV가 못 본 엔티티도 맵에 남기고 엣지·위치만 없앤다 — 삭제하면 부분 관측이
아니라 다른 KG가 된다.

| Condition | Temporal history | Spatial history | Entity coverage | Spatial obs. density | Median staleness | p90 staleness |
|---|---|---|---:|---:|---:|---:|
| GT-Full | GT | GT | 333 / 333 | 96.6% | 0 s | 1 s |
| **GT-Sparse-δ** | **GT 그대로** | UAV-like thinned GT | **333 / 333** | 18.0% | 670 s | 956 s |
| UAV | UAV | UAV | 216 / 333 | 18.0% | 670 s | 956 s |

`GT-Sparse-δ`는 temporal facts를 건드리지 않는다. 그래야 `GT-Full → GT-Sparse-δ`가
**공간 관측 희소화 효과만** 나타낸다.

**⚠️ thinning 규칙을 한 번 고쳤다.** 처음에는 UAV 관측 간격의 경험 분포에서 간격을
추출했는데, UAV 간격의 **90%가 1초**라 1 Hz 주기가 그대로 재생산되고 staleness가 GT와
같은 0~1초에 머물렀다. UAV를 GT와 가르는 것은 간격의 주변분포가 아니라 **버스트 구조**
— 보이는 동안은 1 Hz, 안 보이면 통째로 빔 — 다. 그래서 **UAV 엔티티의 관측 시각 마스크를
통째로 이식**하는 방식으로 바꿨고, 그때서야 staleness가 UAV와 일치했다(670 s / p90 956 s).

> Sparse spatial observations were generated by transferring empirical UAV
> observation masks rather than independently sampling inter-observation intervals,
> because UAV observations exhibit bursty visibility patterns rather than uniformly
> sparse sampling.

seed=0 고정, donor 패턴 216개, 위치 관측 566,433 → 105,532.

---

### RQ2 결과 — Partial Observation Robustness (test, 재학습 없음)

`K=10 · λ=0.1 · φ=[d, v_d] · Δ=600 s · average tie-handling`. spatial model은 GT
train에서 적합한 것 그대로, 조건마다 바뀌는 것은 **입력뿐**이다.

| Condition | TLogic ALL | STLogic ALL | Δ ALL | TLogic HARD | STLogic HARD | **Δ HARD** |
|---|---:|---:|---:|---:|---:|---:|
| GT-Full | 0.7695 | 0.7815 | +0.0120 | 0.0110 | 0.1162 | **+0.1052** |
| GT-Sparse-δ | 0.7695 | 0.7786 | +0.0091 | 0.0110 | 0.1053 | **+0.0943** |
| GT-T / UAV-S | 0.7695 | 0.7786 | +0.0091 | 0.0110 | 0.1177 | **+0.1067** |
| UAV | 0.3008 | 0.2929 | −0.0079 | 0.1290 | 0.1754 | **+0.0464** |

**⚠️ HARD 절대값을 조건 간에 비교하지 않는다.** 관측 그래프가 바뀌면 candidate set·
발화 규칙 수·후보 경쟁 구조가 함께 달라진다. `TLogic HARD 0.0110 → 0.1290`은 모델이
좋아진 것이 아니라 후보 집합이 거의 빈 상태에서 순위 기준선이 이동한 것이다. 조건
비교는 **조건 내 Δ**로만 한다.

**3단 분해**

```
GT-Full     → GT-Sparse-δ     Δ HARD +0.1052 → +0.0943   spatial staleness effect
GT-Sparse-δ → GT-T / UAV-S    Δ HARD +0.0943 → +0.1067   spatial coverage reduction
GT-T / UAV-S → UAV            Δ HARD +0.1067 → +0.0464   temporal history loss
```

공간 관측이 UAV 수준으로 떨어져도(엔티티 333 → 216, 공간점수 가능 48.6% → 22.7%)
이득이 줄지 않는다 — `GT-T / UAV-S`의 +0.1067은 `GT-Full`의 +0.1052와 같은 수준이다.
이득이 깎이는 것은 **temporal history가 12%로 줄 때뿐**이다(엣지 81,492 → 9,690,
10,340 쿼리 중 8,838건에서 TLogic 무후보).

> Within the tested decomposition, the dominant source of degradation was
> temporal-history loss rather than spatial sparsity or spatial coverage loss.

**stale position 실제 오차** — GT-Sparse-δ가 사용한 위치와 같은 시각의 실제 GT 위치 차이:

| staleness | median error | n |
|---|---:|---:|
| 0 ~ 60 s | 0 m | 766 |
| 60 ~ 300 s | 36 m | 189 |
| **300 ~ 900 s** | **241 m** | 1,467 |
| 900 s ~ | 432 m | 519 |

전체 중앙 55 m · p90 602 m · 최대 1,563 m. 주력 구간의 241 m는 장면 척도
`L = 1,057 m`의 23%다. 즉 `P(e, obs)`가 at-or-before로 값을 돌려주어 *계산만 가능했던*
것이 아니라, **위치가 실질적으로 틀린 상태에서도 이득이 유지됐다.**

> STLogic maintained most of its hard-query gain even when stale spatial
> observations induced substantial position errors.

**결론**

```
RQ1:  spatial context improves TLogic
RQ2:  the gain is robust to spatial sparsity and spatial coverage loss,
      but weakens under severe temporal-history loss
```

STLogic은 TLogic을 대체하는 것이 아니라 temporal reasoning을 spatial context로
보완하는 구조이므로, temporal history가 빈약해지면 함께 영향을 받는 것이 설계와 일관된다.

---

### RQ1 Ablation (test, K=10 · λ=0.1 · **average tie-handling**)

| Method | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | CR@10 | SRR |
|---|---:|---:|---:|---:|---:|---:|---:|
| Persistence | 0.7733 | **0.7518** | **0.7959** | 0.8354 | 0.0029 | 0.6343 | — |
| TLogic | 0.7695 | 0.7475 | 0.7795 | 0.8398 | 0.0110 | 0.6332 | — |
| + Random Candidates | 0.7758 | 0.7475 | 0.7795 | 0.8782 | 0.0660 | 0.6705 | 26.72% |
| + Spatial `[d]` | **0.7816** | 0.7475 | 0.7891 | **0.8887** | **0.1177** | **0.6820** | **33.98%** |
| **+ Spatial `[d, v_d]`** | 0.7815 | 0.7475 | 0.7885 | 0.8862 | 0.1162 | 0.6795 | 32.23% |

> **All ranking metrics use average rank for tied candidates. This convention was
> fixed after identifying optimistic bias from best-case tie handling, particularly
> in random candidate augmentation.**

hard MRR 95% CI (클러스터 134): TLogic [0.0079, 0.0147] · `[d]` [0.0851, 0.1553] ·
`[d, v_d]` [0.0827, 0.1564].

**⚠️ Persistence 해석 정정** — `best` 기준에서는 Persistence가 ALL 0.8588로 전부를
이겼으나, 규약 통일 후에는 **0.7733으로 STLogic(0.7815)보다 낮다.** Persistence는
후보가 1개라 동점이 없을 것 같지만, 후보가 없는 쿼리에서 빈도 baseline으로 대체되고
거기에 동점이 많아 `best`가 크게 유리했다. 통일된 규약에서는:

```
ALL   STLogic 0.7815 > Random 0.7758 > Persistence 0.7733 > TLogic 0.7695
HARD  STLogic 0.1162 ≫ Random 0.0660 > TLogic 0.0110 > Persistence 0.0029
```

다만 ALL 차이는 작고(+0.0082) **H@1은 Persistence가 0.7518로 더 높다.** "모든 지표에서
우수"라고 쓸 수 없다. 실질적 개선은 **H@10 0.8398 → 0.8887**과 HARD에서 나타난다.

`[d]`와 `[d, v_d]`는 통계적으로 구분되지 않는다(CI 완전 중첩). valid 기준 선택 원칙에
따라 `[d, v_d]`를 유지한다.

최종 feature `[d, v_d]`는 **validation에서 선택**했다. test에서는 `[d]`가 근소하게
높았으나(0.1177 vs 0.1162, CI 완전 중첩) 사후 재선택하지 않았다. valid 동일 조건:

| | ALL MRR | HARD MRR | CR@10 | SRR |
|---|---:|---:|---:|---:|
| + Spatial `[d]` | 0.7798 | 0.1611 | 0.6499 | 44.21% |
| **+ Spatial `[d, v_d]`** | **0.7804** | **0.1645** | **0.6500** | **44.25%** |

**증강 자체가 아니라 공간이 기여한다** — 동일하게 후보를 늘리는 무작위 증강 대비
hard MRR **1.76배**(0.0660 → 0.1162), SRR 26.72% → 32.23%(valid 29.15% → 44.25%).
무작위 증강도 CR@10을 0.6332 → 0.6705로 올리므로 "후보를 늘리면 좋아지는 몫"은 실재하며,
공간은 그 위에 추가로 기여한다.

**⚠️ `v_d`의 기여는 제한적이다.** 과거 공간 단독 진단에서 `[d]` 0.2814 → `[d, v_d]`
0.5310(+89%)이었으나, TLogic과 결합한 최종 파이프라인에서는 valid 0.1611 → 0.1645에
그친다. 조건이 다르다(공간 단독 + 전이 클러스터 분할 vs 결합 + 시간 분할).
**feature의 판별력과 end-to-end 기여는 다를 수 있다**는 것이 이 대비의 내용이며,
"거리 변화율이 성능을 크게 향상시킨다"고 주장하지 않는다.

**Persistence 해석** — ALL에서는 `Persistence > STLogic > TLogic`, HARD에서는
`STLogic ≫ TLogic > Persistence`다. "모든 baseline보다 우수하다"고 쓸 수 없다.
전체 query에서 persistence가 가장 높은 것은 데이터의 강한 상태 지속성(변화 158건)
때문이고, 상태 전이가 일어난 hard query에서는 persistence와 TLogic이 모두 붕괴한다.
`hard`는 결과를 보고 만든 부분집합이 아니라 **horizon 평가 설계 당시 정의한
diagnostic subset**이다(2026-09-14 기록 참조).

**진행 중 고친 평가 버그** — `calculate_rank`가 후보 dict를 **삽입 순서**로 읽는다
(정렬되어 있다고 가정하는 TLogic 원본 관례). 직접 만든 증강 dict를 정렬하지 않아
한 차례 무효 수치가 나왔다. `evaluate_stlogic.rank_of`와 `apply_stlogic`에서 정렬을
강제했다.

---

## STLogic 최종 결과 (battlefield_hill395, test, baseline 0.5464 대비)
| config | MRR | Hits@1 | Hits@3 | Hits@10 | no-cand |
|---|---|---|---|---|---|
| baseline TLogic | 0.5464 | 0.5156 | 0.5482 | 0.6117 | 11,118 |
| 재순위화 ②③ | 0.5502 | 0.5151 | 0.5559 | 0.6308 | 11,118 |
| + backoff(기하) | 0.5627 | 0.5198 | 0.5687 | 0.6644 | 8,987 |
| + 부대centroid(off+bo) | 0.5854 | 0.5290 | 0.5856 | 0.7200 | 3,146 |
| **best 전부결합** | **0.5891** | 0.5286 | 0.5933 | **0.7390** | 3,146 |

---

## 외부 baseline 비교 — CyGNet (2026-09-21)

### 공정성 조건을 코드가 아니라 evaluator 로 통일했다

각 모델의 자체 MRR 코드를 쓰지 않는다. 모델은 **쿼리별 점수 벡터만** 뱉고, 순위는
전부 `evaluate_horizon` / `evaluate_stlogic` 가 매긴다. 그래야 split·쿼리 집합·
horizon·filtered setting·tie handling·HARD 정의·cluster bootstrap 이 정의상 같아진다.
`CyGNet/run_vrforces.py` 가 그 덤프를 만든다.

`tools/export_for_baselines.py` 로 RE-Net/CyGNet/TiRGN 공통 포맷(`s r o t 0` +
`stat.txt`)으로 내보냈다. entities 341 · relations 4 · timestamps 173 ·
train 29,885 / valid 5,691 / test 5,170. **forward quadruple 만** 쓴다 — 세 모델 모두
역관계를 내부에서 만든다.

**두 가지를 고쳐야 수치가 성립했다.**

1. **쿼리 집합이 절반이었다.** `Grapher.test_idx` 는 test.txt 5,170행 뒤에 역
   quadruple 5,170행을 붙여 **10,340**이다. 처음에 object 모델 덤프만 넣었더니
   나머지 절반이 `evaluate_horizon` 의 빈도 baseline 으로 조용히 백오프했고, 두 시스템이
   섞인 값이 CyGNet 점수로 찍혔다. CyGNet `subject` 모델도 학습해 이어 붙여 고쳤다.
   행 `N+i` 는 `(o_i, r_i + num_r, ?, t_i)` 이므로 subject 모델이 정확히 그 질문이다.

2. **horizon 이 적용되지 않았다.** CyGNet `test.py` 는 historical vocabulary 를
   **train 전체 틱의 합집합**으로 고정한다. 우리 프로토콜은 `ts <= t - 60` 이다.
   쿼리 시각별로 사전을 다시 쌓도록 바꿨다. 비용: HARD 0.2882 → **0.2025**.

   학습은 CyGNet 고유의 1-step 방식 그대로 둔다. TLogic 이 규칙을 train 그래프
   전체에서 배우는 것과 같은 취급이다 — horizon 은 추론 프로토콜의 성질이며 모든
   모델에 동일하게 적용된다.

### 결과 (horizon 60틱 · filtered · average ties · 10,340 쿼리 · 5 seeds)

| model | ALL MRR | HARD MRR | HARD H@10 | HARD 95% CI |
|---|---|---|---|---|
| Persistence | 0.7733 | 0.0029 | 0.0000 | [0.0029, 0.0029] |
| Vocab-obs | 0.7733 | 0.0029 | 0.0000 | [0.0029, 0.0029] |
| **CyGNet** | **0.8135 ± 0.0218** | **0.1994 ± 0.0079** | **0.4921 ± 0.0108** | [0.1646, 0.2431] |
| TLogic | 0.7691 ± 0.0009 | 0.0094 ± 0.0036 | 0.0130 ± 0.0073 | [0.0079, 0.0147] |
| STLogic | 0.7816 ± 0.0003 | 0.1183 ± 0.0014 | 0.4154 ± 0.0000 | [0.0839, 0.1605] |
| _Vocab-train_ | _0.8662_ | _0.4338_ | _0.5453_ | _[0.3401, 0.5405]_ |

`Vocab-obs` = 후보를 obs 까지 누적된 `(s,r)` 목적지로 두고 최근순 정렬(학습 없음).
`Vocab-train` 은 obs 컷을 적용하지 않는다 — **프로토콜 위반이며 참고선일 뿐** 비교
대상이 아니다.

**CyGNet 이 ALL·HARD 모두에서 STLogic 을 앞선다.** 감추지 말고 그대로 써야 한다.
CI 가 [0.1646, 0.2431] 대 [0.0839, 0.1605] 로 사실상 겹치지 않는다.

### HARD 는 방향이 전부다

| model | forward (목적어 예측) | inverse (주어 예측) |
|---|---|---|
| CyGNet | 0.3635 ± 0.0156 | 0.0353 ± 0.0017 |
| STLogic | 0.2337 ± 0.0029 | 0.0029 ± 0.0000 |
| TLogic | 0.0158 ± 0.0072 | 0.0029 ± 0.0000 |
| _Vocab-train_ | _0.5466_ | _0.3210_ |

CyGNet 의 HARD H@10 이 정확히 0.4921(≈0.5)인 것은 우연이 아니다. forward 585건을
**전부** top-10 에 넣고(중앙 순위 2) inverse 585건은 **하나도** 못 넣는다.
STLogic 도 inverse 에서는 persistence 수준이다.

### CyGNet 의 우위가 어디서 오는가 — 데이터셋의 문제다

forward HARD 585건 중 **319건(54.5%)** 은 정답 triple `(s, r, o)` 가 `train.txt` 에
존재한다. 마지막 train 관측은 쿼리보다 **26~36틱** 전 — 즉 `(t-60, t]` 라는 horizon
금지 구간 안이지만, **train 코퍼스 안**이다. 모든 모델이 train 전체로 학습하므로
이것은 규약 위반이 아니라 이 데이터셋의 성질이다. 구분되는 triple 이 522개뿐이라
"train split 을 외운다"가 사실상 "정답지를 외운다"에 가깝다.

- obs 에서 정직하게 자른 `(s,r)` 이력에는 HARD 정답이 **사실상 없다** (MRR 0.0029,
  중앙 순위 341 = 후보에 부재).
- obs 컷 없이 train 전체의 `(s,r)` 목적지를 최근순으로 놓기만 해도 forward HARD
  0.5466 — **학습 없이 CyGNet(0.3635)을 넘는다.**

그러므로 CyGNet 의 이득은 공간 추론이나 시간 추론이 아니라 **주어 조건부 후보 집합의
기억**에서 온다. STLogic 의 진단("병목은 후보 coverage 가 아니라 후보 내용")은 맞았고,
CyGNet 은 그 병목을 공간 feature 없이 더 싸게 푼다.

### 관련 — 스펙과 구현의 불일치

`apply_stlogic.Augmenter._domain` 은 **relation 단위**(`by_rel`)로만 쌓인다. 따라서
`move to` 질의는 주어가 누구든 landmark 18개 전부가 후보다. 스펙 수정 ②는
`O_vis` 를 **subject-conditional** 로 하라고 했다. 이 간극이 지금 성능 차이의
직접 원인은 아니다 — STLogic 의 후보 집합에는 정답이 들어 있다(`move to` SRR 83.2%).
문제는 후보 생성이 아니라 **순위**다. 그래도 스펙/구현 불일치이므로 기록해 둔다.

---

## ⚠️ 재현성 결함 — `scene_scale` 의 L 이 프로세스마다 달랐다 (2026-09-21)

multi-seed 로 기록해 둔 STLogic HARD 0.1219 ± 0.0014 가 **재현되지 않았다**. 같은
seed, 같은 TLogic 후보 파일, 같은 코드에서 0.1274 가 나왔고 프로세스를 바꿔도,
실행 순서를 바꿔도 소수점 12자리까지 안정적이었다. evaluator 두 경로
(`evaluate_stlogic.evaluate` vs `evaluate_horizon`)를 같은 dict 에 통과시켜 비교한
결과 **1,170건 중 0건**이 달랐으므로 지표 코드의 문제가 아니었다.

원인은 `spatial.scene_scale` 이다.

```python
for e in provider.entities_with_position(at):   # <- set 을 순회
```

`entities_with_position` 은 **문자열 set** 을 돌려준다. Python 은 PYTHONHASHSEED 를
프로세스마다 무작위화하므로 set 순회 순서가 매번 달라지고, `random.Random(0)` 로
샘플링해도 **뽑히는 점 쌍이 달라진다.** 측정된 L: 1002.8 / 1007.6 / 1003.5 / 1021.1
(그리고 기록된 run 에서는 1057).

**그리고 L 은 중립이 아니다.** docstring 은 "한 데이터셋 안에서 랭킹을 바꾸지 않는다,
소수 4자리까지 동일"이라고 주장했지만 거짓이다. seed 12 고정, L 만 바꿔 측정:

| L | ALL MRR | HARD MRR |
|---|---|---|
| 1002.8 | 0.7828 | 0.1279 |
| 1007.6 | 0.7827 | 0.1272 |
| 1021.1 | 0.7823 | 0.1233 |
| 1057.0 | 0.7815 | 0.1167 |

HARD 가 **0.0112** 흔들린다. 보고하던 seed 간 표준편차 ±0.0011 의 **10배**다. 즉
"5-seed ± 0.0011" 은 실제 불확실성을 한 자릿수 과소평가하고 있었다.

**수정**: 샘플링 전에 정렬한다(`sorted(...)`). L 이 1037.2161 로 고정되고 프로세스를
바꿔도 동일하다. `tests/test_spatial.py` 17건 통과.

**영향**: 위 비교표의 STLogic 수치(HARD **0.1183 ± 0.0014**)가 수정 후 값이다.
이전에 기록한 0.1219 ± 0.0014 는 폐기한다. TLogic 수치는 영향 없다(0.7691/0.0094로
기록치와 정확히 일치).

---

## 외부 baseline — RE-Net / TiRGN 포팅 (2026-09-21)

### 환경

`stkgdgl` = python 3.10 + torch 2.3.0+cpu + dgl 2.2.1 + numpy 1.26.4 + torchdata 0.7.1.
세 개의 핀이 강제된다. dgl 2.2.1 은 graphbolt DLL 을 torch 2.3.0 까지만 배포하므로
torch 2.4.1 은 import 단계에서 죽고, torch 2.3.0 은 numpy<2 를 요구하며, dgl 은
torchdata 0.8 에서 제거된 `torchdata.datapipes` 를 쓴다. GPU 는 쓸 수 없다 —
RTX 5060 은 sm_120 이라 torch>=2.7 이 필요한데 그 조합의 DGL 휠이 없다. 데이터가
작아 문제되지 않는다.

### 두 저장소가 그냥은 돌지 않는다 — 고친 것

| 저장소 | 증상 | 조치 |
|---|---|---|
| 공통 | `dgl.DGLGraph()` + `add_nodes`/`add_edges` 가 dgl 1.0 에서 삭제됨 | `dgl.graph((src,dst), num_nodes=n)` |
| 공통 | `in_degrees(range(n))` 가 range 를 안 받음 | `in_degrees()` |
| RE-Net | `Aggregator`/`utils` 안에서 `.cuda()` 를 **무조건** 호출(자체 `use_cuda` 플래그 밖) — 18곳 | `cpu_shim.py`: CUDA 장치가 없을 때만 `.cuda()` 를 항등함수로. 있으면 아무 것도 하지 않음 |
| RE-Net | shim 이 닿지 않는 모듈 레벨 `torch.cuda.current_device()` 2곳 | `torch.cuda.is_available()` 로 감쌈 |
| RE-Net | **Windows 에서 `np.asarray` 의 기본 정수가 int32**(리눅스는 int64) → `cross_entropy` 가 "expected scalar type Long but found Int". 첫 validation 에서야 터진다 | `load_quadruples` 에 `dtype=np.int64` 명시 |
| TiRGN | `args.gpu = -1` 을 `.to()` 에 그대로 넘김 → "Device index must not be negative" | CPU 일 때 `args.gpu = torch.device("cpu")`. 체크포인트 파일명이 만들어진 뒤에 치환 |
| TiRGN | `load_data` 의 데이터셋 화이트리스트 | `VRFORCES` 등록 |

### horizon 을 어디에 넣는가 — 구조마다 다르다

- **CyGNet** — copy vocabulary 를 쿼리 시각마다 `ts <= t-60` 합집합으로 다시 쌓는다.
- **RE-Net** — 엔티티의 현재 틱 사실을 히스토리로 밀어 넣는 flush 를 pending 큐에
  붙잡아 두고 `t-60` 이 따라잡은 뒤에야 승격시킨다. rolling `history_len` 상한을
  **승격 시점에** 적용해야 "존재하는 마지막 10블록"이 아니라 "볼 자격이 있는 마지막
  10블록"이 남는다.
- **TiRGN** — 두 곳이다. ① 그래프 스냅샷 창을 상대 위치가 아니라 절대 틱
  (`ticks <= t-60`)으로 지정하고 test ground truth 로 전진시키지 않는다.
  ② history vocabulary 를 `<= t-60` 으로 자른다(`get_history.py --horizon`).
  native 와 horizon 어휘는 `history/` 와 `history_h60/` 로 분리해, **학습은 native,
  평가만 horizon** — CyGNet 과 같은 취급이다.

### 정렬 검증

TiRGN 자체 filtered 수치(MRR 0.793803 / H@1 0.731238 / H@3 0.842650 / H@10 0.886267)가
우리 evaluator 에서 **0.7938 / 0.7312 / 0.8426 / 0.8863 으로 정확히 재현**됐다.
TiRGN 은 스냅샷마다 `[forward; inverse]` 를 뱉고 Grapher 는 `[전체 forward; 전체
inverse]` 라 행 매핑이 어긋나기 쉬운데, 이 일치가 매핑이 맞다는 확인이 된다.

### ⚠️ 1-step-ahead 는 이 데이터에서 퇴화한다

TiRGN 을 native 설정(horizon 없음, 슬라이딩 창이 test ground truth 를 먹음)으로
돌리면 **HARD MRR 0.9971**, ALL MRR 0.9816 이 나온다. TiRGN 이 뛰어나서가 아니라
`t-1` 의 답이 거의 언제나 `t` 의 답이기 때문이다(틱 단위 persistence MRR 0.9997,
2026-09-14 기록). horizon 60 을 걸면 0.9971 → 0.1599 로 떨어진다.

**이것이 fixed-horizon 프로토콜의 가장 명확한 근거다.** 1-step-ahead 로 평가하면
이 데이터셋에서는 어떤 모델도 persistence 와 구분되지 않는다.

---

## 외부 baseline 최종 비교 (2026-09-22)

horizon 60틱(600 s) · filtered · average ties · 10,340 쿼리 · 단일 evaluator.
CyGNet 은 5 seed, TiRGN/RE-Net 은 단일 run(학습 비용). `*` 는 obs 컷을 적용하지 않은
**참고선**이며 비교 대상이 아니다.

| model | seeds | ALL MRR | HARD MRR | HARD H@10 | HARD 95% CI |
|---|---|---|---|---|---|
| Persistence | – | 0.7733 | 0.0029 | 0.0000 | [0.0029, 0.0029] |
| Vocab-obs | – | 0.7733 | 0.0029 | 0.0000 | [0.0029, 0.0029] |
| TLogic | 5 | 0.7691 ± 0.0009 | 0.0094 ± 0.0036 | 0.0130 | [0.0079, 0.0147] |
| **STLogic** | 5 | 0.7816 ± 0.0003 | 0.1184 ± 0.0015 | 0.4152 | [0.0841, 0.1609] |
| CyGNet | 5 | **0.8135 ± 0.0218** | 0.1994 ± 0.0079 | 0.4921 | [0.1646, 0.2431] |
| TiRGN | 1 | 0.7938 | 0.1599 | 0.4299 | [0.1174, 0.2081] |
| **RE-Net** | 1 | 0.7653 | **0.2413** | 0.4154 | [0.1922, 0.2979] |
| _Vocab-train_* | – | _0.8662_ | _0.4338_ | _0.5453_ | _[0.3401, 0.5405]_ |
| _CyGNet-1step_* | 1 | _0.8151_ | _0.4381_ | _0.6410_ | _[0.3586, 0.5255]_ |
| _TiRGN-1step_* | 1 | _0.9816_ | _0.9971_ | _0.9983_ | _[0.9942, 0.9994]_ |
| _RE-Net-native_* | 1 | _0.7643_ | _0.2622_ | _0.4154_ | _[0.2083, 0.3261]_ |

RE-Net 은 best checkpoint epoch 13/20 에서 멈췄다. CPU 에서 validation 한 번이
한 시간 가까이 걸려 남은 7 epoch 이 비현실적이었다. validation MRR 기준 모델 선택은
이미 끝난 상태이므로 유효한 결과지만, **더 학습하면 올라갈 여지가 있다**고 적어 둔다.

### 있는 그대로 — 외부 baseline 세 개가 모두 STLogic 을 앞선다

HARD 에서 RE-Net 0.2413 > CyGNet 0.1994 > TiRGN 0.1599 > **STLogic 0.1184** > TLogic
0.0094. RE-Net 과 STLogic 의 CI 는 겹치지 않는다([0.1922, 0.2979] vs [0.0841, 0.1609]).
ALL 에서도 CyGNet·TiRGN 이 STLogic 보다 높다. 숨기지 말고 써야 한다.

STLogic 이 TLogic 대비 HARD 를 12.6배(0.0094 → 0.1184) 올린 것은 사실이고 그 자체가
결과지만, **"기존 TKG forecasting 모델보다 우수하다"고는 쓸 수 없다.**

### 방향별로 보면 STLogic 의 한계가 정확히 보인다

| model | forward (목적어) | inverse (주어) |
|---|---|---|
| STLogic | 0.2338 ± 0.0031 | **0.0029** ← persistence 바닥 |
| CyGNet | 0.3635 ± 0.0156 | 0.0353 |
| TiRGN | 0.2894 | 0.0305 |
| RE-Net | 0.4319 | 0.0507 |

**STLogic 은 inverse 방향에서 persistence 와 완전히 동일하다(0.0029).** 공간 증거가
"이 부대는 어디로 가는가"에는 기여하지만 "거기로 가는 것은 누구인가"에는 전혀
기여하지 못한다. `_domain` 이 relation 단위라 inverse 관계(`_move to`)의 후보 풀이
주어 조건부가 아닌 것과 같은 뿌리다. 세 baseline 은 작지만 0 이 아니다.

### 참고선이 말해 주는 것

- **TiRGN-1step 0.9971** — horizon 없이 1-step-ahead 로 평가하면 HARD 조차 거의 만점이다.
  `t-1` 의 답이 곧 `t` 의 답이기 때문. **fixed-horizon 프로토콜의 정당화.**
- **CyGNet-1step 0.4381 → CyGNet 0.1994** — CyGNet 의 원래 설정은 금지 구간의 최신성에
  크게 기대고 있었다. horizon 을 걸면 절반 이하로 떨어진다.
- **RE-Net-native 0.2622 → RE-Net 0.2413** — RE-Net 의 자기예측 유사 이력은 이득이
  거의 없다. 즉 RE-Net 은 native 설정에서도 사실상 프로토콜을 크게 어기지 않는다.
- **Vocab-train 0.4338** — 학습 없이 train 전체의 `(s,r)` 목적지를 최근순으로 놓기만
  해도 어떤 학습 모델보다 높다. 이 벤치마크에서 모두가 실제로 쓰고 있는 신호가
  무엇인지 보여 준다(구분되는 triple 522개).

### 남은 작업
- STSE — 저장소를 찾지 못해 보류. 현재 base 환경은 Python 3.13 + torch CPU 이고
  DGL 은 py3.12 까지만 지원한다. `stkgdgl`(py3.10 + torch 2.4 cpu + dgl 2.2.1) 환경을
  따로 만들어 진행한다. 두 저장소는 dgl 0.5 API(`dgl.DGLGraph()` + `add_nodes`)를
  쓰므로 `dgl.graph(...)` 로 바꾸는 소규모 포팅이 필요하다(utils.py / get_history_graph.py
  두 곳). 나머지 API(`update_all`, `dgl.batch`, `max_nodes`, `NID/EID`)는 2.x 에 그대로 있다.
- STSE — 저장소를 찾지 못해 보류.
- GPU: RTX 5060(sm_120)이 있으나 설치된 torch 는 CPU 전용이다. 데이터가 작아
  (엔티티 341, 관계 4) CPU 로 충분하다 — CyGNet 30 epoch 이 양방향 합쳐 약 2분.

---

## 방법론 재구성 진단 (2026-09-22)

baseline 비교 결과를 받아 "무엇을 고치면 오르는가"를 추측이 아니라 측정으로 정렬했다.

### ① 공간 분기가 역관계에 **전혀** 도달하지 않는다 — 최대 결함

```
relation_domain 키 : {'move to': 15, 'FFE-on-Location': 7,
                     'Fire-Weapon': 26, 'Provide-Suppressive-Fire-Loc': 2}
Grapher 관계 이름  : [... 4개 정방향 ..., '_FFE-on-Location', '_Fire-Weapon',
                     '_Provide-Suppressive-Fire-Loc', '_move to']
inverse HARD 200건 중 후보 풀이 비어 있는 경우: 200 (100%)
```

`Augmenter._domain` 은 `stkg.get_facts()`(CSV 정방향 사실)로 `by_rel` 을 만든다.
역관계 이름은 키 자체가 없어 `relation_domain('_move to')` 가 빈 집합이고,
`spatial.build_samples` 도 정방향 이름만 학습하므로 `model.score('_move to', ·)` 는
None 이다. **C_S 주입도, C_T 재순위화도 일어나지 않는다.**

결과: 시도한 **모든** fusion 변형에서 inverse HARD = 0.0029 = persistence 바닥.
쿼리 집합의 절반(hard 1,170건 중 585건)이 공간 정보를 한 톨도 받지 못하고 있다.

feature 는 대칭이라(`d(s,o) = d(o,s)`) 새 연구가 아니라 **구현 완성**이다.

### ② fusion 이 주입 후보를 rank 2 아래로 고정한다

```
주입 후보 점수 상한 = λ·E_S ≤ 0.100   (E_S ≤ 1)
C_T 에 정답이 없는 forward HARD 566건 중
  S_T > λ/(1-λ)=0.111 인 C_T 후보가 있는 경우: 566 (100.0%)
  그 후보 개수: 중앙 1 · 평균 1.00 · 최대 1
```

`apply_stlogic.augment` 는 `pairs[oid] = (0.0, ...)` 로 C_S 전용 후보에 `S_T = 0` 을
준다. 그래서 주입 후보의 최종 순위 하한이 **정확히 2** 로 고정된다. HARD 의 정의상
그 1개는 '바뀌기 전 옛 정답' 즉 반드시 오답이다 — **현재 설계는 hard query 마다
오답을 1위로 보장한다.** 관측된 `HARD H@1 = 0.0000` 이 우연이 아닌 이유다.

다만 이것만 고쳐서 얻는 폭은 작다.

| fusion | ALL MRR | HARD MRR | HARD H@1 | fwd | inv |
|---|---|---|---|---|---|
| current `(1-λ)S_T + λE_S`, 주입 S_T=0 | 0.7818 | 0.1191 | 0.0000 | 0.2353 | 0.0029 |
| backoff (주입 S_T = C_T 최솟값) | 0.5912 | 0.1579 | 0.0427 | 0.3128 | 0.0029 |
| RRF (순위 기반) | 0.7792 | 0.1242 | 0.0077 | 0.2455 | 0.0029 |
| spatial only | 0.5853 | 0.1590 | 0.0427 | 0.3150 | 0.0029 |

**단일 λ 로 ALL 과 HARD 를 동시에 잡을 수 없다**는 것이 핵심이다. 공간 분기 단독의
HARD 상한도 0.1590 으로 CyGNet(0.1994)·RE-Net(0.2413)에 못 미친다 — 즉 fusion 은
주된 병목이 아니다.

### ③ 적응 게이트는 지금 상태로는 작동하지 않는다

가설: "1위 시간 후보에 대한 E_S 가 낮으면 답이 바뀐 것" → λ 를 질의별로 조절.

```
HARD  n=1170  평균 -0.2712  중앙 +0.0000  E_S=0 비율 50.0%
easy  n=8876  평균 +0.0003  중앙 +0.0000  E_S=0 비율 50.0%
AUC = 0.5616
```

양쪽 모두 **정확히 50%** 가 `E_S = 0` 이다 — 역관계 절반이 통째로 신호가 없기
때문이다. 게이트를 걸면 ALL↔HARD 를 같은 곡선 위에서 맞바꿀 뿐이다
(P20 에서 ALL 0.6553 / HARD 0.1498). **①을 고친 뒤 다시 볼 것.**

### ④ heading·도착예측 feature 는 **더 나쁘다** (가설 반증)

"속도 벡터를 600초 외삽해 도착 위치를 예측하면 낫다"는 가설을 forward HARD
`move to` 585건에서 직접 쟀다.

| feature | MRR | H@1 | H@3 | 중앙순위 |
|---|---|---|---|---|
| **F_r (현재 모델)** | **0.3467** | **0.0889** | **0.4718** | **4.0** |
| d (가까운 순) | 0.1846 | 0.0000 | 0.0000 | 5.0 |
| d(도착예측, 후보) | 0.1227 | 0.0017 | 0.0051 | 8.0 |
| cos(heading) | 0.0809 | 0.0000 | 0.0051 | 13.0 |
| cos + d(도착예측) | 0.0960 | 0.0000 | 0.0051 | 11.0 |

부대가 직선으로 가지 않고 600초는 순간 헤딩이 의미를 갖기엔 너무 길다.
**현재 `φ = [d̃, ṽ_d]` + 판별적 가우시안을 교체하지 말 것.** 원거리 순위(0.1846)
대비 0.3467 로, 학습된 모델이 실제로 일을 하고 있다.

### ⑤ 주어 조건부 후보 풀 — 아직 안 쓰는 가장 큰 신호

| | relation 단위 풀 | subject 조건부 풀 | 정답 포함률 |
|---|---:|---:|---:|
| forward HARD | 중앙 15 | **중앙 2** | 54.5% |
| inverse HARD | 중앙 0 (부재) | 중앙 39 | 54.5% |

정방향에서 풀이 15 → 2 로 줄면서 절반 이상이 정답을 담는다. 이것이 세 baseline 이
모두 가지고 STLogic 만 없는 것(CyGNet 의 copy vocabulary, RE-Net·TiRGN 의 엔티티별
표현)이다. 단, 풀은 **학습 코퍼스**에서 유도해야 한다 — obs 에서 자른 주어 조건부
이력은 HARD 정답을 사실상 담지 않는다(MRR 0.0029). CyGNet 의 copy vocabulary 가
train 고정인 것과 같은 취급이므로 프로토콜 위반이 아니다.

### 우선순위

1. **공간 분기의 역관계 확장** — `by_rel` 에 `_r` 키 생성(역관계의 domain 은 주어 집합),
   `build_samples` 에 역관계 포함. 예상 HARD 0.119 → 0.23~0.31.
2. **주어 조건부 후보 사전** — `O_train(s, r)` 을 C_S 생성의 1차 풀로, 그 안에서 `F_r` 로 순위.
3. **fusion 을 공통 척도로** — 주입 후보에 `S_T = 0` 을 주지 말 것. RRF 는 +0.005 HARD / −0.003 ALL 로 공짜에 가깝다.
4. **적응 게이트 재시도** — 1 이후.
5. **하지 말 것** — heading/도착예측 feature 교체.

---

## SSTKG — baseline 으로 쓸 수 없다 (2026-09-22)

저장소: `SSTKG/` (WWW 2024, Yang·Salim·Xue, arXiv 2402.12132). 총 607줄.

**과제가 다르다.** SSTKG 의 엔티티는 POI(상점)이고 각 엔티티는 **수치 시계열**
(SafeGraph `spend_patterns.csv` 의 일별 매출)을 갖는다. 모델은 그 시계열의 공변동에서
엔티티 간 **영향력 행렬 I** 를 학습해 가중 방향 그래프를 만들고, static/dynamic-out/
dynamic-in 임베딩을 얻는다. 출력은 **미래 시계열 값 예측**과 공간 추천이다.

- **관계 어휘가 없다.** 간선은 타입 없는 실수 가중치다.
- `(s, r, ?, t)` 질의도, 엔티티 순위 평가도, MRR/Hits 코드도 저장소에 없다.
- 입력은 `(시계열, category, placekey)` 3종이며 우리 4-tuple 과 대응이 없다.

**게다가 공개 코드가 실행 불가다.**

| 위치 | 문제 |
|---|---|
| `KG_construction.construct_kg` | `train_model()` 호출 — 정의도 import 도 없음(`construction_model` 만 import) |
| `KG_training.SSTKG.psi` | `@staticmethod psi(combined_input)` 인데 `self.psi(static_emb, temporal_records)` 로 2인자 호출 |
| 같은 곳 | `psi` 가 호출마다 `nn.Linear` 를 새로 만든다 — 학습되지 않고 등록도 안 되는 파라미터 |
| `SSTKG.forward` | `out_emb = out_emb = ...` |
| `SSTKG.save_state` | 존재하지 않는 `self.influence_matrices` 참조 |
| `KG_construction` | `nx.write_gpickle`/`read_gpickle` — networkx 3.0 에서 제거됨 |
| `example/*` | `jina`, `tensorflow`, `placekey`, `umap` 의존 · main 진입점 없음 |

**결론**: 재현이 아니라 우리가 새로 구현하는 것이 된다. 그렇게 얻은 숫자는 SSTKG 가
아니라 우리의 과제 매핑에 귀속되므로 baseline 으로 제시하면 안 된다. STSE 와 같은
취급 — **related work 로 인용하되 비교 대상에서 제외**하고, 이유(과제 불일치: 수치
시계열 회귀 vs 관계형 링크 예측)를 한 문장으로 명시한다.

**대신 할 수 있는 정직한 것**: SSTKG 의 *공간 표현 방식*(위경도 → 단위구 3D →
UMAP 축소 임베딩을 엔티티 표현에 concat)을 STLogic 의 ablation 한 줄로 넣는 것.
과제는 우리 것으로 고정하고 **공간 표현만 바꿔** 비교하므로 공정하고, 이름도
"SSTKG-style spatial embedding" 으로 쓰면 오해가 없다.

---

## 전장 도메인 특화 — 자산은 많지만 대부분 작동하지 않는다 (2026-09-22)

`VR-Forces/config/` 에 `weapon_ranges.csv`, `engagement_doctrine.json`,
`entity_class_map.csv`, `task_catalog.csv` 등이 있고 `master_entities.csv` 에
`force`(RED/BLUE/NEUTRAL) · `unit`(36개) · `entity_class` · `role` 이 있다.
지금 STLogic 은 이 파일을 **위치 조회에만** 쓴다. 각각을 제약으로 걸어 재봤다.

### 작동하지 않는 것 (측정)

| 도메인 신호 | 측정 | 판정 |
|---|---|---|
| `weapon_ranges.csv` | 교전 3,109건 중 사수 사거리 안 **0.4%**. 실제 교전거리 Q1/중앙/Q3 = 1423/1514/**1716** m | 시뮬레이션이 이 표를 따르지 않는다. 하드 제약 불가 |
| force 제약 (move to) | LOC 은 전부 `NEUTRAL` → 정보량 0 | 무의미 |
| force 제약 (Fire-Weapon) | 100% 교차 진영(3,109건)이지만 **inverse HARD `_Fire-Weapon` 이 0건** | HARD 부분집합을 건드리지 못함 |
| unit(편성) 조건부 풀 | 크기 중앙 152 · 정답 잔존 58.5% (엔티티 조건부는 39 / 54.5%) | 4배 큰 풀에 잔존 +4%p. 비효율 |
| 교리 `target_priority` | 실제 교전의 표적 type_group 이 **2종**뿐, 사수는 3108/3109 가 단일 타입 | 타입 분류가 퇴화해 정보 없음 |
| "이미 접근 중" 필터 | 풀 20으로 줄지만 **정답 잔존 0.0%** | 아래 참조 |

### 가장 중요한 발견 — Δ=600 s 에서 미래의 이동 주체는 아직 움직이지 않는다

`obs = t − 600 s` 시점에 목적지 L 로 거리가 줄고 있는 엔티티만 남기면 후보는 323 → 20
으로 줄지만 **정답이 남는 비율이 0.0%** 다. 즉 시각 t 에 L 에 가 있을 부대는 obs 에
아직 L 쪽으로 출발조차 하지 않았다. 이동 명령이 `(obs, t]` 구간에서 하달된다.

이것이 heading(0.0809)·도착예측(0.1227) feature 가 실패한 이유이자, 역방향이
persistence 바닥(0.0029)에 머무는 이유다. **Δ=600 s 에서 목적지를 결정하는 것은
관측 가능한 물리가 아니라 지휘 의도다.**

### 유일하게 살아남은 도메인 신호 — 타입 조건부 목적지 사전

| 주어 type_group | 이동 | 목적지 종수 | 최빈 목적지 비중 |
|---|---:|---:|---:|
| 보병 - 소총(M4 계열) | 24,638 | 9 | 30.4% |
| 보병 - RPG 계열 | 6,240 | 7 | 53.2% |
| 차량/장갑차 - M2HB 계열 | 5,786 | 7 | 49.9% |
| 포병 - 155mm 자주포 | 772 | 7 | 42.5% |

전체 목적지 15종 → 타입별 7~9종, 최빈 30~53%. 실재하는 신호지만
**엔티티 조건부(15 → 2, 잔존 54.5%)가 더 날카로워** 단독 가치는 낮다.
다만 학습 때 못 본 엔티티에는 타입 사전이 backoff 로 쓸모가 있다.

### 그래서 도메인 특화는 어디로 가야 하는가

기하·운동학은 한계에 도달했다(F_r 0.3467 이 이미 상한 근처). 남은 불확실성은
**임무 배정**이며, 이는 phase 조건부 tasking 패턴으로만 줄일 수 있다.
`engagement_doctrine.json` 의 phase(접근/조준/간접사격/직접사격/철수)는 존재하지만
**시나리오 task 스크립트(`task_catalog.csv`, `derive_rules.csv`, `pattern_map.csv`)를
직접 쓰면 정답지를 읽는 것**이 되므로 금지다. 학습 구간에서 phase 를 **추정**해
"phase p 에서 타입 T·위치 P 인 부대는 목표 O 로 배정된다"는 템플릿을 귀납하는 것만이
정당한 경로다.

---

## 데이터가 부족한 것인가 — 아니다, 학습곡선이 거꾸로다 (2026-09-22)

"시뮬레이터로 시나리오를 더 만들면 나아지는가"를 측정으로 답했다.

### ① 공간 모델 학습곡선 (forward HARD 'move to' 585건 · 후보 풀 15)

| 학습 표본 | positive | negative | MRR | H@1 | H@3 |
|---:|---:|---:|---:|---:|---:|
| 10% | 1,387 | 11,084 | **0.6242** | **0.3966** | **0.8085** |
| 25% | 4,205 | 33,604 | 0.5902 | 0.3624 | 0.7846 |
| 50% | 8,903 | 71,152 | 0.5121 | 0.2462 | 0.7949 |
| 100% | 18,298 | 146,176 | 0.3318 | 0.0752 | 0.4718 |

**표본을 늘릴수록 단조 감소한다.** 데이터 양은 병목이 아니다. 같은 성격의 데이터를
더 넣으면 오히려 나빠진다.

### ② 원인 — 학습 positive 의 73.5%가 persistence 다

```
학습 사실 18,790 = 전이 3,306 (17.6%) + 유지 13,803 (73.5%) + 이력없음 1,681
```

`build_samples` 는 "시각 t 에 (s, move to, o) 가 성립한다"는 모든 사실을 positive 로
쓴다. 그런데 그 중 73.5%는 **t−600s 의 답과 t 의 답이 같은** 사실, 즉 "목적지는 이미
향하던 그곳"이라는 persistence 사례다. 100%로 적합한 가우시안은 이 덩어리로 끌려간다.

| positive 집합 | d Q1/중앙/Q3 | v_d 중앙 | d<50m 비율 |
|---|---|---:|---:|
| 초반 10% | 700 / 1151 / 1317 m | −1.006 m/s | 0.0% |
| 전체 100% | 595 / **987** / 1161 m | **−0.452** m/s | 1.4% |
| 전이만 | 449 / 794 / 1336 m | −0.796 m/s | 0.0% |
| 유지만 | 634 / 990 / 1142 m | −0.450 m/s | 1.8% |

HARD 는 정의상 **답이 바뀌는** 질의인데 학습 분포는 답이 안 바뀌는 사례가 지배한다.
**학습 분포와 평가 분포가 어긋나 있다.**

### ③ 무료 수정 — positive 를 전이로 제한

| 학습 positive | MRR | H@1 | H@3 | 중앙순위 |
|---|---:|---:|---:|---:|
| 전체 100% (현재) | 0.3347 | 0.0803 | 0.4718 | 4.0 |
| **전이만, 100% 구간** | **0.4272** | **0.1179** | **0.7350** | **3.0** |
| 초반 10% (참고) | 0.6204 | 0.3915 | 0.8068 | 2.0 |

데이터를 한 줄도 추가하지 않고 **+0.093**. 초반 10%가 더 높은 것은 그 구간이 전이가
많을 뿐 아니라 **원거리 기동**(d 중앙 1151 m)이라 HARD 질의의 기하와 더 닮아서다.

### ④ 지금 split 은 암기를 보상한다

```
전체 엣지 81,492 · 구분되는 triple 1,032  (중복도 79배)
test triple 460 중 train 에 이미 있는 것 426 (92.6%)
test 엔티티 중 train 미등장 0 / 248
test 질의 10,340건 중 정답 triple 이 train 에 존재 9,514 (92.0%)
```

같은 시나리오를 시간으로만 자른 split 이라 **미등장 엔티티가 하나도 없다.**
`Vocab-train` 이 학습 없이 HARD 0.4338 을 내고 CyGNet·RE-Net 이 STLogic 을 앞서는
이유가 여기 있다 — 벤치마크가 일반화가 아니라 암기를 보상한다.

### 결론 — 무엇을 더 만들어야 하는가

- **같은 성격의 시나리오를 더 뽑는 것은 의미가 없다.** 학습곡선이 음의 기울기이고,
  전이/유지 비율(17.6 : 73.5)이 시나리오 수에 무관하게 재생산된다.
- 관계 종류가 안 늘어난다는 우려는 맞지만 **문제가 아니다.** HARD 부분집합은 이미
  전부 `move to` 이고(inverse `_Fire-Weapon` HARD 0건), 병목은 관계 다양성이 아니다.
- 의미 있는 생성 방향은 둘이다.
  1. **교차 시나리오 split** — 배치·부대 구성·지형이 다른 시나리오를 만들어
     train/test 를 시나리오 단위로 가른다. 미등장 엔티티가 생기면 암기 경로가
     무너지고(CyGNet copy vocabulary, RE-Net·TiRGN 엔티티 임베딩 전부) 관계 수준
     정규화로 전이 가능한 `F_r` 만 남는다. **STLogic 의 dataset-agnostic 설계가
     비로소 이득이 되는 체제.** `battlefield_hill395`(엔티티 5,876 · 관계 10)가
     이미 두 번째 시나리오로 존재한다.
  2. **기동 밀도가 높은 시나리오** — 부대가 목표에 도착해 머무는 구간이 아니라
     계속 재배치되는 구간. 전이/유지 비율을 바꾸는 것이 표본 수를 늘리는 것보다
     직접적이다.

---

## 검토 지적 4건 검증 — 전부 사실로 확인 (2026-09-22)

### ① 학습 데이터가 테스트 관측 마감 이후까지 존재한다

```
train 13:21:42 ~ 13:42:12 (121) | valid 13:42:22 ~ 13:46:32 (25) | test 13:46:42 ~ 13:51:02 (27)
test 관측 마감 13:36:12 ~ 13:40:52
학습 종료(13:42:12) > 관측 마감 인 테스트 시점: 27 / 27
가장 이른 마감(13:36:12) 이후의 학습 시점: 34 / 121 (28.1%)
가장 늦은 마감(13:40:52) 이후의 학습 시점: 8
```

**27개 테스트 시점 전부**가 해당한다. 추론 이력은 잘랐지만 규칙·공간 분포·엔티티별
목적지 사전에는 마감 이후 정보가 들어간다. 이는 모든 TKG 모델이 train split 전체로
학습하는 관례와 일치하므로 **모델 간 비교는 여전히 공정**하지만, 방법론 문서의
**"모델은 t−600s 까지만 본다"는 실시간 forecasting 주장은 성립하지 않는다.**
두 조건은 별개이며, 문서를 후자에 맞게 고쳐야 한다.

`Vocab-train` HARD 0.4338 의 해석도 보류한다. 이 값이 memory signal 인지, 마감 이후
학습 사실의 유출인지 분리되지 않았다.

### ② horizon 이 실제로 600초가 아니다

```
tick 간격 중앙 10 s · 최대 20 s · 10초 아닌 간격 4개
ts_id − 60 의 실제 초: 중앙 620 · 최소 610 · 최대 630   (의도 600)
```

`apply_stlogic.py` 가 `tsid2epoch.get(ts - horizon)` 으로 **ID 에서 60을 뺀다.**
간격이 균일하지 않아 610~630 s 가 된다. 성능의 주원인은 아니지만 프로토콜 정확성에
필요한 수정이다. 실제 초 기준 cutoff 로 바꾸고 기존 설정은 별도 조건으로 남긴다.

### ③ 분산 하한의 `+1` 이 스케일 불변성을 깬다 — L 민감도의 기전

`spatial.py:132` `sd = max(표본sd, VAR_FLOOR * (|mu| + 1.0))`, `VAR_FLOOR = 1e-3`.

| relation | side | dim | mu | sd | floor | |
|---|---|---:|---:|---:|---:|---|
| move to | neg | 1 | −0.000348 | **0.001000** | 0.001000 | **하한에 걸림** |
| move to | pos | 1 | −0.000618 | 0.001132 | 0.001001 | 거의 걸림 |
| Provide-Suppressive-Fire-Loc | pos | 1 | 0.000000 | **0.001000** | 0.001000 | **하한에 걸림** |
| Provide-Suppressive-Fire-Loc | neg | 1 | 0.000000 | **0.001000** | 0.001000 | **하한에 걸림** |

정규화된 `v_d` 는 크기가 1e-3 안팎인데 `+1` 때문에 floor 가 `|mu|` 와 무관하게 사실상
`1e-3` 으로 고정된다. **판별 차원 전체와 같은 규모의 하한**이다. L 이 커지면
정규화된 v 는 작아지는데 floor 는 그대로라 더 강하게 눌린다.

이것이 앞서 측정만 하고 기전을 못 찾았던 L 민감도(HARD 0.1279@L=1003 →
0.1167@L=1057)의 원인이다. **"정규화 때문에 나빠졌다"가 아니라 "정규화와 분산 하한의
상호작용 때문"**이며, 하한을 스케일 불변 형태(`VAR_FLOOR * |mu|` 또는 feature 별
절대 하한)로 바꾸면 해소될 가능성이 크다. 통제 실험 필요.

### ④ `E_S = 0` 이 `F = 0` 이 아니다 — 복구 후보의 49%가 음수 증거를 받는다

`fit_norm_stats` 는 `spatial_scores()` 값만 모으는데 그 함수는 **F > 0 만** 돌려준다.
따라서 수집 표본이 전부 양수이고 `mu > 0` 이다.

```
Norm 통계 (valid): move to mu 0.4515 · Fire-Weapon mu 0.7493 · FFE-on-Location mu 4.6349
=> E_S = 0 이 되는 지점은 F = 0 이 아니라 F = mu
F>0 로 '복구된' 후보 43,602개 중 최종 E_S < 0 인 것: 21,350 (49.0%)
```

**후보 생성 단계의 "양의 공간 증거"와 결합 단계의 "양의 증거"가 서로 다른 것을
가리킨다.** 절반이 생성 기준으로는 양성인데 결합 기준으로는 음성으로 뒤집힌다.
`F = 0` 을 고정 기준점으로 쓰거나, 정규화 통계를 F 부호와 무관한 표본에서 추정해야
의미가 일치한다.

### 받아들이는 수정 — 역관계 기대치

이전 기록에서 "역관계 확장 시 HARD 0.119 → 0.23~0.31" 이라고 적었다. 이는
**역방향이 정방향 수준을 낸다고 가정한 것이고 근거가 없다.** 거리 특징은 대칭이지만
후보 수(정방향 15 vs 역방향 323)와 negative 분포가 다르다. 기대치를 철회하고,
역관계는 **별도의 학습 표본·평가**로 구성한 뒤 측정으로 답한다.

---

## 깊은 결합(rule-conditioned spatial context)을 VR-Forces 에서 처음 켜 봤다 (2026-09-22)

`spatial_context.py`(283줄)는 제안된 구조 — **규칙별 공간 context model** — 를 이미
구현하고 있다. 규칙의 grounding 인스턴스에서 `d / dd / cos(bearing)` 가우시안을 적합해
`rules.json` 에 함께 저장하고(`rule_learning.py:126-142`), 추론 때
`score = score_12(...) * spatial_fit` 로 **Noisy-OR 이전에** 곱한다. hill395 용으로
만들고 VR-Forces 에서는 계속 `sp-off` 였다. 이번에 처음 켰다.

학습은 이미 되어 있었다 — 기존 `*_s12_rules.json` 에 규칙 22개 중 20개가 `spatial`
키를 갖고 있고, 표본도 충분하다(`d`/`dd` 규칙당 n 중앙 436, 18/20 규칙이 n≥10;
`cosb` 만 10규칙·6개가 n≥10).

### 결과 (seed 12 · horizon 60 · average ties · 10,340 쿼리)

| 경로 | ALL MRR | H@1 | H@3 | H@10 | HARD MRR |
|---|---:|---:|---:|---:|---:|
| `sp-off` (TLogic) | 0.7695 | 0.7475 | 0.7795 | 0.8398 | 0.0110 |
| `sp-dist` | **0.8034** | 0.7624 | 0.8420 | 0.8447 | 0.0097 |
| `sp-dist_dd` | 0.8034 | 0.7624 | 0.8420 | 0.8447 | 0.0097 |
| `sp-dist_dd_bearing` | 0.8034 | 0.7624 | 0.8420 | 0.8447 | 0.0097 |
| `sp-dist_dd --backoff` | 0.8034 | 0.7624 | 0.8420 | 0.8447 | 0.0097 |
| (참고) 얕은 결합 `apply_stlogic` | 0.7816 | — | — | — | **0.1184** |

### ⚠️ ALL 상승은 재순위화가 아니라 **동점 해소**다

동점 처리 규약을 바꿔 보면 드러난다.

| 규약 | `sp-off` ALL MRR | `sp-dist` ALL MRR |
|---|---:|---:|
| best | **0.8358** | 0.8034 |
| average | 0.7695 | **0.8034** |
| worst | 0.6679 | 0.8034 |

```
최대 동점 블록 크기:  sp-off  평균 14.78 · 블록>1 인 쿼리 44.0%
                     sp-dist 평균  1.01 · 블록>1 인 쿼리  0.9%
```

TLogic 은 **쿼리의 44%에서 평균 15개짜리 동일 신뢰도 블록**을 만들고, 정답은 대개 그
블록 안에 있다(그래서 `best` 가 0.8358). 공간 적합도를 곱하면 블록이 거의 완전히
풀린다(평균 1.01). `sp-dist` 가 규약에 무관하게 0.8034 로 고정되는 이유다.

따라서 정직한 비교 대상은 `best`(=최적 동점 해소, 도달 불가)가 아니라
**`average`(=무작위 동점 해소의 기댓값)**다. 그 기준에서 **+0.0339 는 무작위 대비
실질 이득**이며, 공간 증거가 동점 블록 안에서 우연보다 잘 고른다는 뜻이다.
다만 "재순위화로 성능을 올렸다"가 아니라 **"동점을 해소했다"**고 써야 한다.

### `dd` 와 `cos(bearing)` 는 기여가 없다

`dist` 와 `dist_dd` 는 **10,046개 쿼리에서 점수가 다른데 지표는 소수 4자리까지
동일**하다. `bearing` 도 마찬가지. 앞서 φ 에서 `v_d` 가 "핵심 성능 원천은 아니다"라고
적은 것과 일관되며, 여기서는 아예 순위를 바꾸지 못한다.

### `--backoff` 는 VR-Forces 에서 완전한 no-op 이다

`dist_dd` 와 `dist_dd_bo` 가 **0개 쿼리에서 차이**나고 무후보 쿼리도 294로 동일하다.
원인은 `apply.py:78-88`:

```python
sec = name.split("/")[0] if "/" in name else None
```

후보 풀을 **엔티티 이름의 "sector" 접두사**로 만든다. hill395 는 `sec_dev_0000/…`
형태라 동작하지만 VR-Forces 는 `ENBTR60001` 이라 `/` 가 없어 `id2sector` 가 비고
`backoff_for` 가 항상 `{}` 를 돌려준다. **일반 경로에 숨은 데이터셋 종속 가정**이다.

### 결론 — 두 경로는 상호 보완적이고, 어느 쪽도 단독으로는 부족하다

| | ALL | HARD | 메커니즘 |
|---|---:|---:|---|
| 깊은 결합 | **+0.0339** | −0.0013 | C_T 내부 동점 해소 |
| 얕은 결합 | +0.0121 | **+0.1074** | 없는 정답 주입 (C_S) |

깊은 결합은 규칙이 만든 후보를 잘 정렬하지만 **없는 정답을 만들어내지 못한다**
(hard query 의 98.4%가 C_T 에 정답 부재). 얕은 결합은 주입하지만 `S_T=0` 때문에
순위 하한이 2로 고정된다.

**제안된 파이프라인이 성립하려면 두 가지가 같이 있어야 한다**: 규칙별 공간 조건으로
Noisy-OR 이전에 점수를 곱하고, **동시에** 공간 기반 후보 생성을 같은 프레임 안에서
수행해야 한다. 후자는 `backoff_candidates` 가 자리는 잡고 있으나 후보 풀 구성이
sector 의존이라 VR-Forces 에서 못 쓴다 — `spatial.relation_domain(r, obs)` 로
교체하면 된다.

---

## 만료 게이트 — "다음 답이 무엇인가" 대신 "지금 답이 언제 만료되는가" (2026-09-22)

### 동기

`C_T` 에 정답이 없는 forward HARD 566건 **전부**에서 `S_T > λ/(1−λ)` 인 후보가 정확히
1개 있고, 그것이 '옛 답'이며 HARD 정의상 반드시 오답이다. 주입 후보는 영원히 2위다.
λ 를 키우는 것은 앞서 실패했다(ALL 붕괴). 그렇다면 그 **한 후보만** 끌어내려야 한다.

### 만료는 obs 시점에 예측 가능하다 — 그것도 아주 잘

주어와 '옛 답' 사이의 obs 시점 거리 `d` 로 HARD/easy 를 가른 AUC:

| 부분집합 | d | v_d | dwell |
|---|---:|---:|---:|
| **forward** | **0.9478** | (역방향 강함) | 0.6678 |
| inverse | 0.5955 | 0.3563 | 0.2849 |
| 전체 | 0.7769 | 0.2057 | 0.4957 |

```
forward:  HARD 의 d 중앙 133 m  vs  easy 810 m
          HARD 의 v_d 중앙 −1.4 m/s (빠르게 접근 = 도착 직전)
```

**부대가 현재 목적지에 도착해 있으면 그 목적지는 곧 바뀐다.** 누수는 없다 — `d` 는
obs 시점 위치로만 계산하고 '옛 답'도 obs 이전 사실이다.

이 한 줄이 그동안의 측정을 전부 설명한다. 공간 정보는 **"다음 답이 무엇인가"에는
약하고(후보 순위 F_r 0.35) "지금 답이 언제 만료되는가"에는 강하다(0.95)**.
heading·도착예측 외삽이 실패한 것도, 후보는 복구되는데 순위가 안 오르는 것도 같은
이유다.

### 게이트 적용 결과 (valid 에서만 적합, test 적용)

```
π(q) = P(답이 바뀐다 | d, v_d)                  ← valid 로지스틱
S(o) = (1−λ)·S_T(o)·(1 − π·[o 가 옛 답]) + λ·E_S(o)
```

| 모드 | ALL MRR | HARD MRR | HARD H@1 | fwd | inv |
|---|---:|---:|---:|---:|---:|
| current | 0.7818 | 0.1188 | 0.0000 | 0.2347 | 0.0029 |
| **expiry** | 0.7684 | **0.1381** | **0.0188** | **0.2734** | 0.0029 |
| _oracle_ (π=정답) | _0.7871_ | _0.1662_ | _0.0513_ | _0.3296_ | _0.0029_ |

- **HARD H@1 이 처음으로 0 을 벗어났다** (0.0000 → 0.0188). 구조적 상한이 풀렸다는 증거.
- HARD +0.0193, ALL −0.0134. 오탐이 정상적인 persistence 답을 깎기 때문이다.
- **oracle 에서는 ALL 이 오히려 오른다**(0.7871 > 0.7818). 즉 ALL 손실은 게이트의
  원리 때문이 아니라 **정확도 부족** 때문이다. 게이트를 개선할 여지가 그대로 있다.

### 그러나 scoring 만으로는 부족하다 — oracle 상한이 말해 준다

**완벽한 게이트로도 HARD 0.1662 가 천장이다.** CyGNet(0.1994)·RE-Net(0.2413)에 못 미친다.
이유는 남은 두 구멍이다.

1. **inverse 가 여전히 0.0029** — 게이트를 걸든 말든 공간 분기가 없으니 변화 없음.
   질의의 절반이 그대로 방치된다.
2. **`C_S` 내부 순위가 약하다** — 복구된 정답이 `C_S` 안에서 1위인 경우가 9.2% 뿐.
   막는 후보를 치워도 그 자리를 옳게 채우지 못한다.

forward oracle(0.3296)을 inverse 도 낸다고 가정하면 HARD ≈ 0.33 으로 RE-Net 을 넘는다.
**즉 지금 가장 큰 단일 레버는 여전히 inverse 구현이고, 만료 게이트는 그다음이다.**

### 즉시 개선 가능한 점

게이트를 **forward/inverse 를 합쳐서** 적합했다(AUC 0.948 과 0.596 을 섞음). test 에서
π 는 HARD 평균 0.561 · easy 0.115 로 분리가 무뎌졌다. **방향별로 따로 적합**하면
forward 쪽이 날카로워진다. 현재 수치는 그 개선 이전 값이다.

---

## 역관계 공간 분기 구현 + 만료 게이트 — 누적 결과 (2026-09-22)

### 구현

`spatial.with_inverses(facts)` 추가. `relation_domain()`·`build_samples()` 가
`(sub, rel, obj, t)` 에 대해 일반적이므로 `(obj, _r, sub, t)` 를 먹이면 역관계도
자기 후보 풀과 자기 모델을 갖는다. `Augmenter._domain` 도 이를 쓰도록 수정.
테스트 33건 통과.

```
후보 풀 — 이전:  {FFE 7, Fire-Weapon 26, Provide 2, move to 15}
후보 풀 — 이후:  위 + {_FFE 14, _Fire-Weapon 26, _Provide 7, _move to 312}
모델 관계 8종 (이전 4종) · _move to 표본 pos 16,390 / neg 621,080
```

만료 게이트는 **방향별로 따로 적합**했다(이전엔 합쳐서 적합해 무뎌졌다).

```
forward π: HARD 평균 0.865 · easy 0.070      <- 합쳐 적합했을 때 0.561 / 0.115
inverse π: HARD 평균 0.313 · easy 0.152
```

### 누적 결과 (seed 12 · horizon 60 · average ties)

| 구성 | ALL MRR | HARD MRR | HARD H@1 | fwd | inv |
|---|---:|---:|---:|---:|---:|
| TLogic | 0.7695 | 0.0110 | 0.0000 | 0.0158 | 0.0029 |
| A0 기존 STLogic | 0.7818 | 0.1191 | 0.0000 | 0.2353 | 0.0029 |
| A1 +inverse | **0.8563** | 0.1190 | 0.0000 | 0.2351 | 0.0029 |
| **A2 +expiry(방향별)** | **0.8456** | **0.1534** | **0.0282** | **0.3039** | 0.0029 |
| _A3 게이트 oracle_ | _0.8617_ | _0.1665_ | _0.0513_ | _0.3301_ | _0.0029_ |
| — CyGNet | 0.8135 | 0.1994 | — | 0.3635 | 0.0353 |
| — RE-Net | 0.7653 | 0.2413 | — | 0.4319 | 0.0507 |
| — TiRGN | 0.7938 | 0.1599 | — | 0.2894 | 0.0305 |

**ALL 0.8456 은 모든 baseline 을 앞선다**(직전 최고 CyGNet 0.8135).
HARD 0.1534 는 TiRGN(0.1599) 수준, CyGNet·RE-Net 에는 아직 못 미친다.

### 역관계는 ALL 만 올리고 HARD 는 못 올린다 — 이유가 확인됐다

단계별로 쪼개 보면 후보 누락이 아니라 **순위 실패**, 그것도 무작위보다 나쁘다.

| | forward HARD | inverse HARD |
|---|---:|---:|
| ① 후보 도메인에 정답 존재 | 100.0% (풀 15) | 100.0% (풀 312) |
| ② 공간 특징 계산 가능 | 100.0% | 100.0% |
| ③ **F_r 순위 중앙** | **4 / 15** (무작위 8) | **197 / 312** (무작위 **156**) |
| TopK=10 포함 | 99.1% | **0.0%** |
| TopK=50 포함 | 100.0% | **0.0%** |

**K 를 키워도 소용없다.** `_move to` 의 positive 는 "그 LOC 로 가고 있는 부대"의 기하로
적합되는데, inverse HARD 의 정답은 obs 에 **아직 그 LOC 쪽으로 출발하지도 않은** 부대다
(앞선 측정: 정답이 '접근 중'인 비율 0.0%). 그래서 모델이 정답을 **적극적으로 낮게**
매긴다 — 무작위보다 나쁜 이유다.

즉 **역관계 실패는 구현 누락이 아니라 Δ=600 s 에서 특징의 한계**다.
이전에 적었던 기대치(HARD 0.23~0.31)는 이미 철회했고, 이 측정이 그 철회를 기전으로
확인한다.

### 한 문장으로

> 공간 정보는 **"지금 누가 어디 있나"** 를 잘 알고(→ ALL +0.064, 역관계 easy 질의),
> 그래서 **"지금 답이 곧 만료된다"** 도 잘 안다(→ forward HARD +0.069, H@1 이 처음으로 0 탈출).
> 그러나 **"다음에 무엇이/누가 올까"** 는 모른다(→ inverse HARD 무작위 이하).

오늘의 두 변경으로 ALL +0.0638, HARD +0.0343. 남은 격차는 전부 inverse 이며,
그것은 현재 특징 집합으로는 닫히지 않는다.

---

## Phase 0 — 평가 프로토콜 수정 (2026-09-22)

구조 개선보다 먼저. 기존 수치는 모델 간 **진단**으로는 유효하지만 새 구조를 고르는
근거로 쓰면 프로토콜 수정 후 전부 다시 돌려야 하기 때문이다.

### 0-1. 정확한 초 단위 cutoff

`apply.py --horizon N` 은 **tick id 를 뺀다.** 균일 격자에서만 의도한 간격과 같은데
VR-Forces 에는 20 초 간격이 4곳 있어 `--horizon 60` 이 실제로는 **610~630 초**였다.

`--horizon-seconds 600` 신설. 가시 집합을 정확히
`{t : epoch(t) <= epoch(q) − 600}` 으로 정의한다.

```
obs tick = max{k : epoch(k) <= epoch(q) − Δ}       (위치 조회용, inclusive)
get_window_edges 에 넘기는 값 = obs tick + 1        (t < bound 이므로)
```

두 값을 나눈 이유: 위치는 obs 에서 읽고 `get_window_edges` 는 `t < bound` 로 거르므로,
같은 수를 넘기면 엣지 창이 위치 창보다 한 틱 좁아진다.

**회귀 확인**: `--horizon 60`(tick 경로) 결과가 패치 전과 완전히 동일
(ALL 0.7695 / HARD 0.0110 / H@1 0.7475 / H@3 0.7795 / H@10 0.8398).

`apply_stlogic.py` 도 `Augmenter.observation_epoch()` 로 동일하게 처리.
`evaluate_horizon.py` 에도 `--horizon-seconds` 추가.

### ⚠️ 평가자와 생성자의 cutoff 가 어긋나면 HARD 정의가 바뀐다

초 단위로 만든 후보를 tick 기준 평가자에 넣었더니 **TLogic HARD 가 0.0110 → 0.1055**
로 뛰었다. 성능 향상이 아니라, 평가자가 "아직 안 바뀐 답"이라고 부르는 시점보다
모델이 더 최신 사실을 이미 봤기 때문이다. **반드시 같은 cutoff 를 써야 한다.**

맞춘 뒤의 값:

| 프로토콜 | ALL MRR | HARD MRR | HARD n |
|---|---:|---:|---:|
| tick 60 / tick 평가 (기존) | 0.7695 | 0.0110 | 1,170 |
| **600 s / 600 s 평가** | **0.7870** | **0.0316** | **1,022** |

cutoff 가 ~20 초 최신화되면서 **HARD 부분집합 크기 자체가 1,170 → 1,022 로 줄었다.**
두 프로토콜의 수치는 서로 비교 불가이며, **모든 기존 수치를 새 프로토콜로 재생산해야
한다.**

### 0-2. train/test embargo

요구: `train_end <= min(test query 의 t_obs)`.

현재 split 의 위반 규모:

```
valid 최소 obs 13:32:22 → train 이 그보다 뒤인 tick 57개 (121 중 47%)
test  최소 obs 13:36:42 → train 이 그보다 뒤인 tick 31개 (26%)
```

**이중 embargo(valid 에도 적용)는 불가능하다.** 시나리오가 1,760 초뿐이라 train 이
20~32 틱만 남는다(현재 121). 따라서 **단일 embargo + 보정은 train 꼬리에서** 취한다.

`build_vrforces_dataset.py --embargo 600 --test-ticks 27` 신설.
산출 `data/VR-Forces_gt_s10_emb600` · `split_meta.json`:

```
학습     tick   0~ 76   13:21:42~13:34:32
보정     tick  77~ 89   13:34:42~13:36:42     ← Norm·게이트는 여기서만
embargo  tick  90~145   13:36:52~13:46:32     ← valid.txt 에 담기되 학습·평가 안 함
평가     tick 146~172   13:46:42~13:51:02

train_end(13:36:42) <= min test cutoff(13:36:42)  ✓  (빌더가 assert)
엣지: train 22,637 · embargo 12,939 · test 5,170
```

**valid.txt 의 의미가 바뀌었다.** 더 이상 validation split 이 아니라 **embargo 블록**
이다. 학습에 쓰면 안 되지만 데이터셋에는 남겨야 한다 — 뒤쪽 test 질의의 cutoff 가 이
구간 안에 떨어지므로 추론 시 증거로는 보여야 한다. `split_meta.json` 이 역할을 기록한다.

따라서 `fit_norm_stats(..., g.valid_idx)` 를 **train 꼬리(`calib_ticks`)로 바꿔야
한다.** docstring 을 고쳤고 호출부 교체가 남았다.

### 남은 작업

- [ ] `evaluate_stlogic.py` 에 `--horizon-seconds`
- [ ] 보정 rows 를 `split_meta.calib_ticks` 에서 뽑는 헬퍼
- [ ] embargo 데이터셋으로 Phase 1 재측정 (Persistence / TLogic / 현행 STLogic)

### 0-3. `learn.py` 의 빈 범위 버그 (embargo 에서 드러남)

embargo train 구간(tick 0~89)에는 `Provide-Suppressive-Fire-Loc` 이 없어 관계가
**8종 → 6종**으로 줄었다. 그러자 `-p 8` 에서

```python
num_relations = len(all_relations) // num_processes   # 6 // 8 == 0
relations_idx = range(i*0, (i+1)*0)                   # 모든 워커가 빈 범위
```

가 되어 **규칙 0개가 학습됐는데 오류는 나지 않았다.** `max(1, ...)` 로 수정.
관계 수 ≥ 프로세스 수인 기존 경우에는 값이 그대로라 회귀 없음 —
기존 데이터셋 `-p 8` 이 여전히 규칙 22개(확인함).

embargo 데이터셋: 규칙 19개(spatial 보유 18), 공간 학습 사실 11,542(기존 18,790의 61%).

---

## Phase 1 — 수정 프로토콜에서 기준선 재측정 (2026-09-22)

`VR-Forces_gt_s10_emb600` · 600 s exact cutoff · embargo · 10,340 질의 · average ties.
보정은 train 꼬리 tick 77~89(6,356 rows). valid.txt(embargo)는 어디에도 쓰지 않음.

| model | ALL | H@1 | H@3 | H@10 | **HARD** | HARD H@1 | fwd | inv |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Persistence | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0029 | 0.0029 |
| Vocab-obs | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0029 | 0.0029 |
| TLogic | 0.7842 | 0.7617 | 0.7953 | 0.8619 | **0.0029** | 0.0000 | 0.0029 | 0.0029 |
| **STLogic(현행)** | **0.7973** | 0.7617 | 0.8164 | **0.9041** | **0.1355** | 0.0000 | **0.2681** | 0.0029 |
| _Vocab-train_* | _0.7102_ | _0.6937_ | _0.7286_ | _0.7395_ | _0.0029_ | — | _0.0029_ | _0.0029_ |

HARD n = 1,022. cluster CI — STLogic **[0.0953, 0.1817]**, 나머지 전부 [0.0029, 0.0029].

### ① Vocab-train 이 무너졌다 — 0.4338 → 0.0029

가장 알고 싶었던 수치다. 학습 없는 "이 부대가 가 본 곳" 사전이

```
HARD   0.4338  →  0.0029   (모든 학습 모델을 앞서던 것이 persistence 바닥으로)
ALL    0.8662  →  0.7102   (전체 최고에서 전체 최저로)
```

**기존 transductive split 이 training-time memory 를 크게 보상하고 있었다는 직접
증거다.** embargo 로 학습 상한이 13:36:42 로 내려가자 "가 본 곳" 정보가 test 시점
기준 최소 56 틱 낡은 것이 되어 아무 값도 못 한다.

### ② TLogic 도 HARD 에서 바닥으로 내려갔다 — 0.0110 → 0.0029

그리고 **TLogic 후보에 정답이 없는 hard query 가 1,022 / 1,022 = 100%** 다
(수정 전 98.4%). 즉 정직한 프로토콜에서 시간 규칙은 hard query 에 **후보조차
만들지 못한다.**

### ③ 그 결과 STLogic 만 바닥 위에 있다

Persistence · Vocab-obs · TLogic · Vocab-train 이 전부 정확히 0.0029 인데
STLogic 만 0.1355 이고 CI 가 겹치지 않는다. SRR 은 32.2% → **42.7%** 로 올랐다.

수정 전에는 "STLogic 이 TLogic 을 12배 올리지만 외부 baseline 에 밀린다"였는데,
수정 후에는 **"정직한 프로토콜에서 hard query 에 유효한 후보를 만드는 유일한 방법"**
이 됐다. 다만 **외부 baseline 3종을 아직 이 프로토콜로 재실행하지 않았으므로 그
비교는 미정이다.**

### 유지된 결론 / 바뀐 결론

| | 수정 전 | 수정 후 |
|---|---|---|
| TLogic 후보 누락 | 98.4% | **100%** (유지·심화) |
| forward-inverse 불균형 | 0.2347 / 0.0029 | **0.2681 / 0.0029** (유지) |
| HARD H@1 = 0 (rank-2 상한) | 그대로 | **그대로** |
| Vocab-train 우위 | 0.4338 | **0.0029 — 소멸** |
| TLogic HARD 기여 | 0.0110 | **0.0029 — 소멸** |

### 남은 작업 (Phase 1 완결용)
- [ ] CyGNet / RE-Net / TiRGN 을 embargo 데이터셋으로 재실행
- [ ] multi-seed 재실행

---

## Phase 1 완결 — 외부 baseline 을 수정 프로토콜로 재실행 (2026-09-23)

확장 데이터셋(+파생 공간 관계)은 탐색으로 남기고, **`VR-Forces_gt_s10_emb600` +
exact 600 s cutoff + embargo** 에 고정한 뒤 외부 baseline 3종을 같은 조건으로 돌린다.

### 공정한 비교를 위해 만든 것

embargo 프로토콜은 범주가 셋인데 이 모델들은 둘뿐이다. embargo 블록을 train.txt 에
넣으면 **금지된 사실로 학습**하고, 빼면 **STLogic 이 쓰는 증거를 못 보게** 된다
(마지막 test 틱의 cutoff 는 embargo 창 안에 떨어진다). 그래서 파일을 넷으로 나눴다.

`tools/export_embargo_baselines.py`:

```
train.txt      학습 가능       tick  0~ 76   19,459
valid.txt      학습 가능       tick 77~ 89    3,178   (이들의 validation)
evidence.txt   학습 불가       tick 90~145   12,939   증거로만
test.txt       질의            tick146~172    5,170
vocab.txt      train+valid+evidence          35,576   어휘 구축용
horizon_map.txt  tick -> 그 tick 의 질의가 볼 수 있는 마지막 tick (정확한 초 기준)
```

- **CyGNet** — `get_historical_vocabulary.py` 가 copy vocabulary 를 `vocab.txt` 에서
  만들고, gradient 는 `train.txt` 에서만 받도록 분리. `run_vrforces.py` 는
  `horizon_map.txt` 로 cutoff.
- **TiRGN** — `get_history.py` 의 history vocabulary 를 `vocab.txt` 로. 원래는
  `train+valid+test` 를 합쳐 읽었는데, **test.txt 는 고정 horizon 에서 거의 모든
  질의에게 미래 데이터**다. `main.py` 의 스냅샷 창도 `horizon_map` 사용.
- **RE-Net** — `data/VRFEMB/get_history_graph.py` 신설. `History.advance()` 가 tick
  뺄셈 대신 `horizon_map` 을 쓰고, embargo 블록을 **질의 행 없이 history 에만 흘려
  넣는** `absorb()` 를 추가(train → valid → evidence → test 순).

### ✅ CyGNet — 5 seed 완료

30 epoch · batch 1024 · time_stamp 1 · seed 12~16.

| seed | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD 95% CI |
|---|---:|---:|---:|---:|---:|---|
| 12 | 0.7189 | 0.6419 | 0.7862 | 0.8372 | 0.1156 | [0.0858, 0.1485] |
| 13 | 0.7144 | 0.6313 | 0.7833 | 0.8388 | 0.1173 | [0.0822, 0.1571] |
| 14 | 0.7119 | 0.6219 | 0.7750 | 0.8416 | 0.1031 | [0.0706, 0.1397] |
| 15 | 0.7322 | 0.6566 | 0.7852 | 0.8316 | 0.1262 | [0.0967, 0.1575] |
| 16 | 0.6989 | 0.5989 | 0.7888 | 0.8558 | 0.1394 | [0.0978, 0.1880] |
| **평균 ± 표준편차** | **0.7153 ± 0.0108** | | | 0.8410 | **0.1203 ± 0.0121** | |

**HARD H@1 은 5 seed 전부 0.0000.** STLogic 과 같은 증상 — 옛 답이 1위를 점유한다.

수정 전 프로토콜에서 CyGNet 은 ALL 0.8135 / HARD 0.1994 였다. embargo 로
**ALL −0.098, HARD −0.079** 떨어졌다. 즉 **임베딩 모델도 embargo 에 무너진다** —
Vocab-train 만의 현상이 아니다.

STLogic(ALL 0.7973 / HARD 0.1355)과 비교하면 두 지표 모두 STLogic 이 앞선다.
다만 HARD 차이(0.1355 vs 0.1203±0.0121)는 CI 가 겹치므로 **유의하다고 말할 수 없다.**

### ⚠️ TiRGN — 덤프 버그 발견 후 재실행 중

첫 실행 결과가 ALL 0.1014 / HARD 0.1348 로 나왔는데, **HARD 가 ALL 보다 높은** 기이한
값이었다. 원인은 성능이 아니라 덤프였다.

```
wrote tirgn_emb.json  (6356 queries, horizon=600)
```

**6,356 = 3,178 × 2 = valid 크기.** `test()` 안에서 `args.dump` 를 검사하는데 이
함수는 학습 루프 안의 validation 라운드에서도 호출되므로, **먼저 끝난 validation 이
파일을 써버렸다.** `test()` 에 `do_dump` 게이트를 추가하고 진짜 test 호출 2곳에서만
True 를 넘기도록 고친 뒤 재학습 중.

### ⏳ RE-Net — 전처리·pretrain 완료, 본 학습 중

```
전처리   horizon_map 173 ticks · train_graphs 77 snapshots
         evidence absorbed 12,939 facts (evidence only)
         test 5,170 rows, 100% non-empty history
pretrain 20 epoch, loss 131.62
train    10 epoch 예정 (기본 20 에서 축소 -- 이전 데이터셋에서 CPU 15시간 소요)
```

계산 예산 때문에 epoch 을 줄였으므로 **RE-Net 에 불리한 조건임을 논문에 명시해야 한다.**
DGL 이 이 GPU(sm_120)를 지원하지 않아 CPU 로만 돌릴 수 있다.

### TiRGN 덤프 버그 — 두 겹이었다

**(1) 검증 라운드가 덤프를 가로챘다.** `test()` 안에서 `args.dump` 를 검사하는데 이
함수는 학습 루프의 validation 라운드에서도 호출된다. 먼저 끝난 validation 이 파일을
써버려 **6,356행(= 3,178 × 2, valid 크기)** 이 test 인 척 저장됐다. 그대로 평가하면
ALL 0.1014 / HARD 0.1348 — **HARD 가 ALL 보다 높은** 값이 나와 발견했다(정상적인
모델이라면 persistence 가 통하는 easy 질의에서 더 잘해야 한다).

호출부에 `do_dump` 플래그를 넘기는 방식은 실패했다(여전히 6,356). 더 견고하게
**`mode` 문자열로 게이트**했다 — validation 은 `mode="train"`, 진짜 test 만
`mode="test"` 를 넘긴다.

```python
if args.dump and mode == "test":
```

**(2) history 파일이 test 틱에 없었다.** history vocabulary 를 `vocab.txt`(tick
0~145)로 바꾸자 `tail_history_146.npz` 부터가 만들어지지 않았다. TiRGN 은 **질의 틱
이름**으로 파일을 찾는데, 고정 horizon 에서 그 틱이 봐야 할 내용은 **cutoff 틱**의
누적 상태다. 누적이 단조이므로 `horizon_map[T]` 틱의 파일을 T 이름으로 복사하면
정확히 일치한다(test tick 146~172 ← cutoff tick 89~113, 54개 파일).

원본 `get_history.py` 는 `train+valid+test` 를 합쳐 읽었는데, **고정 horizon 에서
test.txt 는 거의 모든 질의에게 미래 데이터**다. 이것도 같이 고쳤다.

### ✅ TiRGN — 수정 후 결과

덤프 10,340행 정상. 30 epoch · history-rate 0.3 · history-len 9 · CPU.

| | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@1 | HARD H@3 | HARD H@10 | HARD 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| TiRGN | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.0000 | 0.1292 | 0.1477 | [0.0414, 0.1303] |

수정 전 프로토콜에서는 ALL 0.7938 / HARD 0.1599 였다. embargo 로 **ALL −0.203,
HARD −0.076**. CyGNet 보다 낙폭이 크다.

**HARD H@1 은 여기서도 0.0000** — Persistence, TLogic, CyGNet(5 seed 전부), STLogic 과
동일하다. 즉 **어떤 모델도 hard query 를 1위로 맞히지 못한다.** 옛 답이 1위를
점유하는 구조적 문제이며 특정 방법의 약점이 아니다.

---

## Ablation Study — STLogic 내부 구성요소의 기여 (2026-09-23)

`VR-Forces_gt_s10_emb600` · exact 600 s cutoff + embargo · 10,340 질의 · HARD 1,022 ·
average ties · seed 12.

구성 정의:

```
TLogic                        규칙 후보 C_T, 시간 점수 S_T 만
+ Spatial Context             C_T 는 그대로, 점수만 (1-λ)S_T + λE_S 로 재정렬
+ Spatial Candidate Recovery  C_S 주입, C_T 점수는 원본 유지
STLogic Full                  둘 다
```

| Method | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@1 | HARD H@3 | HARD H@10 | SRR% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TLogic | 0.7842 | 0.7617 | 0.7953 | 0.8619 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | — |
| + Spatial Context | 0.7842 | 0.7617 | 0.7953 | 0.8619 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | — |
| **+ Spatial Candidate Recovery** | **0.7971** | 0.7617 | **0.8162** | **0.9038** | **0.1340** | 0.0000 | **0.2123** | **0.4237** | **42.4** |
| **STLogic Full** | 0.7971 | 0.7617 | 0.8162 | 0.9038 | 0.1340 | 0.0000 | 0.2123 | 0.4237 | 42.4 |

HARD 95% CI — TLogic·Context [0.0029, 0.0029] · Recovery·Full [0.0935, 0.1800].

### ⚠️ Spatial Context 의 기여가 정확히 0 이다

`+ Spatial Context` 행이 **TLogic 과 소수 4자리까지 동일**하다. 재정렬이 순위를 단
한 건도 바꾸지 못했다.

원인은 설계 그대로다. `E_S = 2·Norm(F_r) − 1` 은 **공간 증거가 없으면 정확히 0** 이
되도록 중심화돼 있는데, `C_T` 후보의 약 80%가 공간 증거를 갖지 못한다. 그러면
`(1−λ)S_T + λ·0` 은 `S_T` 의 단조 변환이라 순위가 보존된다. 증거가 있는 소수 후보만
움직이는데 그것으로는 순위가 안 바뀐다.

**따라서 현재 STLogic 의 이득은 전부 후보 생성(Recovery)에서 나온다.**
"규칙이 만든 후보를 더 잘 구분한다"는 주장은 이 구조에서는 **성립하지 않는다.**
앞서 깊은 결합(규칙별 spatial context, Noisy-OR 이전 곱셈)이 ALL 을 올린 것은 동점
해소였고, 그것도 구 프로토콜 측정이다 — 신 프로토콜 미검증.

### SRR 이 없으면 Recovery 의 기여가 안 보인다

MRR 만 보면 `+0.131` 이지만, 실제로 일어난 일은
**규칙 후보에 정답이 없는 1,022건(=HARD 전부) 중 42.4% 를 후보로 되찾은 것**이다.
되찾은 뒤에도 순위가 2~10위에 머물러(HARD H@1 = 0, H@3 0.2123, H@10 0.4237)
MRR 기여가 희석된다. **Candidate Recall 계열 지표를 반드시 같이 실어야 한다.**

---

## 실험 1. Forecasting 성능 — 외부 baseline vs STLogic (2026-09-23)

전역 관측 `ground_truth_ver2.0.csv` · `VR-Forces_gt_s10_emb600` ·
**exact 600 s cutoff + embargo** · 10,340 질의 · HARD 1,022 · average ties ·
filtered · **단일 evaluator** (외부 모델은 점수 벡터만 덤프, 순위는 전부 우리가 매김).

| Model | ALL MRR | H@1 | H@3 | H@10 | **HARD MRR** | HARD H@1 | fwd HARD | inv HARD | HARD 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Persistence | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0029 | 0.0029 | [0.0029, 0.0029] |
| Vocab-obs | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0029 | 0.0029 | [0.0029, 0.0029] |
| TLogic | 0.7842 | 0.7617 | 0.7953 | 0.8619 | 0.0029 | 0.0000 | 0.0029 | 0.0029 | [0.0029, 0.0029] |
| CyGNet (5 seed 평균) | 0.7153 | 0.6301 | 0.7837 | 0.8410 | 0.1203 | 0.0000 | 0.2317 | 0.0090 | seed 별 아래 |
| ± 표준편차 | 0.0108 | 0.0194 | 0.0047 | 0.0081 | 0.0121 | 0.0000 | 0.0241 | 0.0011 | |
| TiRGN | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.0000 | 0.1525 | 0.0153 | [0.0414, 0.1303] |
| RE-Net | — | — | — | — | — | — | — | — | 미완 (아래) |
| **STLogic** | **0.7972** | 0.7617 | **0.8162** | **0.9039** | **0.1346** | 0.0000 | **0.2663** | 0.0029 | [0.0945, 0.1807] |
| _Vocab-train_* | _0.7102_ | _0.6937_ | _0.7286_ | _0.7395_ | _0.0029_ | — | _0.0029_ | _0.0029_ | [0.0029, 0.0029] |

CyGNet seed 별 HARD: s12 0.1156 · s13 0.1173 · s14 0.1031 · s15 0.1262 · s16 0.1394

### 읽는 법

**① STLogic 이 ALL·HARD 양쪽에서 1위다.** ALL 0.7972 로 모든 baseline 을 앞서고,
HARD 0.1346 으로도 최고다.

**② 다만 HARD 에서 CyGNet 과의 차이는 유의하지 않다.**
STLogic [0.0945, 0.1807] 과 CyGNet 평균 0.1203 (seed 범위 0.1031~0.1394) 이 겹친다.
**"STLogic 이 hard query 에서 우월하다"고 주장할 수 없다.** 말할 수 있는 것은
*"STLogic 과 CyGNet 만 바닥 위에 있고, 나머지는 persistence 와 구분되지 않는다"* 다.

**③ ALL 에서는 차이가 크다.** STLogic 0.7972 vs CyGNet 0.7153 (−0.082),
TiRGN 0.5905 (−0.207). 임베딩 모델들은 embargo 후 **easy 질의(persistence 로 풀리는
것)마저 놓친다** — 학습 구간이 짧아지고 test 와 멀어졌기 때문이다.

**④ HARD H@1 은 전 모델 0.0000.** Persistence·TLogic·CyGNet(5 seed)·TiRGN·STLogic
모두. 어떤 방법도 hard query 를 1위로 맞히지 못한다. 옛 답이 1위를 점유하는 구조적
한계이며 특정 방법의 약점이 아니다. **논문에 반드시 명시할 것.**

**⑤ inverse 는 전 모델이 약하다.** STLogic 0.0029, CyGNet 0.0090, TiRGN 0.0153.
STLogic 이 가장 낮다 — 공간 특징이 역방향에서 무작위보다 나쁘기 때문(F_r 순위 중앙
197/312). 다만 **0.009~0.015 도 사실상 바닥**이라, 이 과제가 현재 방법론 전반에서
풀리지 않는다는 쪽이 더 정확한 서술이다.

### ❌ RE-Net — 미완

전처리·pretrain·본 학습까지 진행했으나 덤프 단계에서 실패했다.

```
KeyError: 89   at utils.py:269  global_emb[tt]
```

`global_emb` 는 **학습에서 본 틱(0~76)에 대해서만** 채워지는데, 고정 horizon 에서
test 질의의 cutoff 는 tick 89~113 이라 그 키가 없다. embargo 로 학습 구간과 test
관측 구간이 분리되면서 드러난 문제로, RE-Net 의 global model 을 embargo 구간까지
확장해 채워야 한다(구조 변경 필요).

부수적 제약도 있다 — DGL 이 이 GPU(sm_120)를 지원하지 않아 CPU 전용이고, 본 학습을
기본 20 epoch 에서 **10 epoch 으로 축소**했다(이전 데이터셋에서 CPU 15시간 소요).
재개하더라도 **RE-Net 에 불리한 조건임을 명시해야 한다.**

---

## 실험 2. Partial Observation Robustness — 미실시

`UAV*.csv` 기반 부분 관측 조건에서 관측 품질이 떨어져도 공간 분기의 이득이 유지되는지
보는 실험. **아직 새 프로토콜로 돌리지 않았다.**

필요한 표 (관측 조건 × 모델):

| Observation | Model | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@1 | HARD H@3 | HARD H@10 |
|---|---|---|---|---|---|---|---|---|---|
| GT-Full / GT-Sparse / UAV | TLogic · CyGNet · TiRGN · RE-Net · STLogic | | | | | | | | |

그리고 **GT → UAV 감소량**을 따로 내야 실험 질문에 직접 답한다 — 절대 MRR 보다
"관측이 나빠질 때 얼마나 버티는가"가 핵심이기 때문이다.

| Model | GT HARD MRR | UAV HARD MRR | 감소량 |
|---|---|---|---|

### 준비 상태

- ✅ 데이터셋 `VR-Forces_uav_s10`, `VR-Forces_uavall_s10` 존재 (train 3,558 / test 649)
- ✅ `--history` 로 질의는 GT, 증거는 UAV 를 쓰는 실행 경로 있음
- ❌ **embargo 프로토콜로 재빌드 안 됨** — `build_vrforces_dataset.py --embargo` 를
  UAV observer 로 다시 돌려야 한다
- ❌ 외부 baseline 을 UAV 조건에서 돌린 적 없음

---

## 현재 상태 요약 (2026-09-23)

| 항목 | 상태 |
|---|---|
| 프로토콜 (exact 600 s cutoff + embargo) | ✅ 확정·검증 |
| Ablation Study | ✅ 완료 — **이득은 전부 Candidate Recovery 에서 나온다** |
| 실험 1 · Persistence / Vocab / TLogic / STLogic | ✅ 완료 |
| 실험 1 · CyGNet | ✅ 완료 (5 seed) |
| 실험 1 · TiRGN | ✅ 완료 (덤프 버그 2건 수정 후) |
| 실험 1 · RE-Net | ❌ `global_emb` KeyError — 구조 변경 필요 |
| 실험 2 · Partial Observation | ❌ 미실시 |
| Multi-seed (STLogic) | ❌ 미실시 (CyGNet 만 5 seed) |

### 지금 말할 수 있는 것

1. **프로토콜을 고치면 암기 기준선이 무너진다** — Vocab-train HARD 0.4338 → 0.0029.
2. **시간 규칙만으로는 hard query 에 후보조차 못 만든다** — 누락률 100% (1,022/1,022).
3. **STLogic 의 이득은 후보 생성에서 나온다** — Spatial Context 재정렬 기여 정확히 0,
   Recovery 가 SRR 42.4% 로 정답을 되찾는다.
4. **ALL 에서는 STLogic 이 명확히 1위**, HARD 에서는 **CyGNet 과 통계적으로 동등**.
5. **HARD H@1 은 전 모델 0** — 이 과제의 공통 한계.

### 다음 순서

1. RE-Net `global_emb` 확장 (embargo 구간까지)
2. 실험 2 — UAV 데이터셋을 embargo 프로토콜로 재빌드 후 전 모델 실행
3. STLogic multi-seed (5 seed)
4. 규칙별 spatial context(깊은 결합)를 신 프로토콜에서 검증 — 현재 Context 기여가
   0 이므로, 이 구조가 그 구멍을 메우는지가 핵심 질문

---

## 실험 1 표 갱신 — HARD Hits@k 추가 (2026-09-23)

앞선 실험 1 표는 HARD 에서 **H@1 만** 싣고 H@3 / H@10 을 빠뜨렸다. 보완한 전체 표:

| Model | ALL MRR | H@1 | H@3 | H@10 | **HARD MRR** | HARD H@1 | HARD H@3 | HARD H@10 | fwd | inv |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Persistence | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| Vocab-obs | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| TLogic | 0.7842 | 0.7617 | 0.7953 | 0.8619 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| CyGNet (5seed 평균) | 0.7153 | 0.6301 | 0.7837 | 0.8410 | 0.1203 | 0.0000 | 0.1957 | 0.4186 | 0.2317 | 0.0090 |
| ± 표준편차 | 0.0108 | 0.0194 | 0.0047 | 0.0081 | 0.0121 | 0.0000 | **0.0342** | **0.0393** | 0.0241 | 0.0011 |
| TiRGN | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.0000 | 0.1292 | 0.1477 | 0.1525 | 0.0153 |
| RE-Net | — | — | — | — | — | — | — | — | — | — |
| **STLogic** | **0.7971** | 0.7617 | **0.8162** | **0.9039** | **0.1344** | 0.0000 | **0.2114** | **0.4247** | **0.2658** | 0.0029 |
| _Vocab-train_* | _0.7102_ | _0.6937_ | _0.7286_ | _0.7395_ | _0.0029_ | — | _0.0000_ | _0.0000_ | _0.0029_ | _0.0029_ |

HARD 95% CI — STLogic [0.0942, 0.1801] · TiRGN [0.0414, 0.1303] ·
Persistence/Vocab/TLogic [0.0029, 0.0029].

### Hits@k 를 보태니 드러나는 것

**① HARD H@10 에서 STLogic 과 CyGNet 은 사실상 동률이다.**
0.4247 vs 0.4186 ± 0.0393 — 차이 0.006 이 표준편차의 1/6 이다.
**"정답을 상위 10 안에 넣는 능력"은 둘이 같다.**

**② 차이는 H@3 에서만 조금 난다.** 0.2114 vs 0.1957 ± 0.0342 — 역시 표준편차 안이다.
즉 HARD 어느 지표에서도 STLogic 의 우위를 주장할 수 없다.

**③ TiRGN 은 H@10 에서 확연히 뒤진다** (0.1477 vs 0.42 대). MRR 차이(0.0839 vs 0.12~0.13)
보다 H@10 격차가 더 크다 — TiRGN 은 **정답을 후보 상위권에 아예 못 넣는다.**

**④ Persistence·TLogic·Vocab 계열은 HARD 전 지표가 0.0000 이다.**
MRR 0.0029 는 "가끔 낮은 순위로 맞힌다"가 아니라 **상위 10 안에 단 한 번도 없다**는 뜻.
1/341 ≈ 0.0029 는 후보에 없을 때의 기본값이다.

**⑤ 그래서 실험 1 의 정직한 결론은 두 갈래다.**

- **ALL 에서는 STLogic 이 명확히 1위** (0.7971 vs CyGNet 0.7153, TiRGN 0.5905).
  embargo 후 임베딩 모델은 persistence 로 풀리는 easy 질의마저 놓친다.
- **HARD 에서는 STLogic ≈ CyGNet** (MRR·H@3·H@10 모두 CI/표준편차 안).
  말할 수 있는 것은 *"공간 분기와 copy-vocabulary 라는 서로 다른 두 메커니즘이
  비슷한 수준으로 후보를 되찾고, 나머지는 바닥에 있다"* 이다.

### 참고 — ablation 의 `STLogic Full` 과 0.0004 차이

ablation 표의 Full(HARD 0.1340 / H@3 0.2123 / H@10 0.4237)은 점수식을 직접 재구성한
값이고, 실험 1 의 STLogic(0.1344 / 0.2114 / 0.4247)은 `Augmenter.augment()` 를 그대로
호출한 값이다. 주입 후보 처리에서 미세하게 달라 소수 3자리에서 갈린다.
**논문 수치는 `augment()` 경로(실험 1)를 쓴다.**

---

## ✅ RE-Net 완료 — 실험 1 최종표 (2026-09-23)

### 막고 있던 것을 고쳤다

`run_vrforces.py` 가 `global_emb[89]` 에서 KeyError 로 죽었다. 추적하니 두 곳이 전부
**학습 가능 구간(tick 0~76)만** 보고 있었다.

```
get_history_graph.py   train_graphs 를 train.txt 의 틱으로만 생성   → 77 snapshots
pretrain.py:93         global_emb 를 train_times_origin 으로만 생성 → 키 0~76
```

고정 horizon 에서 test 질의의 cutoff 는 **tick 89~113** 이라 그 키가 없다. embargo 로
학습 구간과 관측 구간이 분리되면서 드러난 문제다.

수정:
- 그래프 스냅샷을 **관측 가능 구간 전체(train+valid+evidence, tick 0~145)** 로 생성
  → 146 snapshots
- 그 스냅샷으로 `global_emb` 재계산 → 키 146개(0~145), 요구 cutoff 89~113 전부 포함
- `train.py` 는 `global_emb` 를 대입 1회 후 손대지 않는 **통과값**이므로 재학습 없이
  체크포인트에 갈아끼움. **gradient 는 여전히 train.txt 에서만** 나왔고, 늘어난 것은
  추론 시 관측 가능한 증거 범위뿐이다.
- CPU 실행을 위해 `cpu_shim` import (RTX 5060 은 sm_120, DGL 2.2.1 은 torch ≤2.3)

### 실험 1 최종표

`VR-Forces_gt_s10_emb600` · exact 600 s cutoff + embargo · 10,340 질의 · HARD 1,022 ·
average ties · filtered · 단일 evaluator.

| Model | ALL MRR | H@1 | H@3 | H@10 | **HARD MRR** | HARD H@1 | HARD H@3 | HARD H@10 | fwd | inv |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Persistence | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| Vocab-obs | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| TLogic | 0.7842 | 0.7617 | 0.7953 | 0.8619 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| CyGNet (5seed) | 0.7153 | 0.6301 | 0.7837 | 0.8410 | 0.1203 | 0.0000 | 0.1957 | 0.4186 | 0.2317 | 0.0090 |
| ± 표준편차 | 0.0108 | 0.0194 | 0.0047 | 0.0081 | 0.0121 | 0.0000 | 0.0342 | 0.0393 | 0.0241 | 0.0011 |
| TiRGN | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.0000 | 0.1292 | 0.1477 | 0.1525 | 0.0153 |
| **RE-Net** | 0.6541 | 0.5602 | 0.7140 | 0.8135 | **0.1666** | 0.0000 | **0.2436** | **0.4990** | **0.3138** | **0.0193** |
| **STLogic** | **0.7972** | 0.7617 | **0.8163** | **0.9038** | 0.1344 | 0.0000 | 0.2133 | 0.4237 | 0.2659 | 0.0029 |
| _Vocab-train_* | _0.7102_ | _0.6937_ | _0.7286_ | _0.7395_ | _0.0029_ | — | _0.0000_ | _0.0000_ | _0.0029_ | _0.0029_ |

HARD 95% CI — **RE-Net [0.1238, 0.2158]** · STLogic [0.0939, 0.1805] ·
TiRGN [0.0414, 0.1303] · Persistence/Vocab/TLogic [0.0029, 0.0029].

### ⚠️ 결론이 갈린다 — 지표마다 승자가 다르다

| | 1위 | 2위 | 3위 | 4위 |
|---|---|---|---|---|
| **ALL MRR** | **STLogic 0.7972** | CyGNet 0.7153 | RE-Net 0.6541 | TiRGN 0.5905 |
| **HARD MRR** | **RE-Net 0.1666** | STLogic 0.1344 | CyGNet 0.1203 | TiRGN 0.0839 |
| **HARD H@10** | **RE-Net 0.4990** | STLogic 0.4237 | CyGNet 0.4186 | TiRGN 0.1477 |

**STLogic 이 HARD 에서 1위가 아니다.** RE-Net 이 HARD MRR·H@3·H@10 전부 앞선다.
CI 는 겹치지만(RE-Net [0.1238, 0.2158] vs STLogic [0.0939, 0.1805]) 점추정이 뚜렷이
높고, **inverse 에서도 RE-Net 0.0193 > STLogic 0.0029** 다.

**그리고 RE-Net 은 불리한 조건이었다.** 계산 예산 때문에 pretrain 100→20 epoch,
본 학습 20→10 epoch 으로 줄였다. 예산을 채우면 격차가 더 벌어질 수 있다.

**반대로 ALL 에서는 STLogic 이 압도적이다** (RE-Net 대비 +0.143). RE-Net 은
persistence 로 풀리는 easy 질의를 크게 놓친다 — H@1 0.5602 vs STLogic 0.7617.

### 그래서 지금 정직하게 쓸 수 있는 문장

> 수정된 프로토콜에서 **STLogic 은 전체 질의(ALL)에서 가장 정확하고, 변화가 일어난
> 질의(HARD)에서는 RE-Net 이 가장 정확하다.** 두 모델은 서로 다른 것을 잘한다 —
> STLogic 은 지속되는 답을 유지하면서 일부 변화를 잡고, RE-Net 은 변화를 더 잘 잡는
> 대신 지속을 놓친다.

**"STLogic 이 hard query 에서 우월하다"는 주장은 철회해야 한다.**
남는 기여는 (1) 프로토콜 결함 진단, (2) 규칙 기반이 hard 에서 후보조차 못 만든다는
측정, (3) ALL 최고 성능, (4) 공간이 "무엇"보다 "언제"에 강하다는 기전 규명이다.

---

## 최종 제출 초록 (2026-09-30)

> Spatio-temporal knowledge graphs (STKGs) have been primarily studied for spatially-aware link prediction and completion. However, explainable forecasting of relations at future timestamps remains relatively underexplored. Embedding-based models often lack interpretability for their predictions. In contrast, temporal logical rule-based models such as TLogic provide rule-based explanations but do not incorporate spatial context, and the correct future answer may be missing from candidates derived from past temporal patterns. We propose STLogic, a framework for explainable link forecasting on battlefield STKGs that combines temporal logical reasoning with spatial candidate recovery. Following the TLogic framework, STLogic learns temporal logical rules from temporal random walks and applies the learned rules to generate answer candidates and temporal scores. In addition, STLogic extracts the distance between entities and the rate of change in distance at the observation timestamp as spatial features. The feature distributions of positive and negative candidates are modeled using Gaussian distributions to construct relation-specific spatial models. During inference, spatially plausible candidates that are not generated through temporal rule application are added to the candidate set, and temporal scores are combined with spatial compatibility scores to produce the final candidate ranking. To evaluate the proposed framework, we constructed a battlefield STKG using the VR-Forces simulation platform and conducted link forecasting experiments. Experimental results show that STLogic recovers correct answer candidates missed by temporal rules and achieves better overall predictive performance than the baseline models. Overall, STLogic integrates temporal logical reasoning with spatial candidate recovery, thereby alleviating the candidate-generation limitations of temporal rules and improving future link forecasting on battlefield STKGs.

### 초록이 본문에 지우는 의무

| 초록의 주장 | 본문 근거 | 상태 |
|---|---|---|
| relation-specific spatial model, 양성·음성 가우시안 | `spatial.py` `SpatialModel`, hard negative | ✅ 구현과 일치 |
| 규칙이 생성하지 못한 후보 추가, 시간 점수와 공간 적합도 결합 | `apply_stlogic.Augmenter.augment` | ✅ 구현과 일치 |
| recovers correct answer candidates missed by temporal rules | SRR 42.4 (ablation) / 42.7 (Phase 1) | ✅ 측정됨 |
| better **overall** predictive performance than baselines | ALL MRR 0.7972 1위 | ⚠️ 단일 seed — **multi-seed 필요** |
| **explainable** link forecasting | 없음 | ❌ **case study 필요** |
| 정답이 바뀐 질의에서 RE-Net 이 앞섬 | HARD 0.1666 vs 0.1344 | 본문에서 반드시 밝힐 것 |

"overall" 은 전체 질의(ALL) 기준으로만 쓴다. HARD 에서는 RE-Net 이 앞서므로 본문에서
이를 명시해야 초록과 모순되지 않는다.

## 남은 실험 계획 (2026-09-30)

| 순서 | 실험 | 목적 | 근거 |
|---|---|---|---|
| 1 | **STLogic multi-seed** (seed 12~16) | "better overall" 을 seed 분산까지 포함해 확정 | CyGNet 만 5 seed |
| 2 | **Horizon sweep** (Δ = 60 ~ 1200 s) | 600 s 선택 근거 | 발표 피드백 2 |
| 3 | **실험 2 · 부분 관측** (GT vs UAV) | 관측이 불완전해도 효과가 유지되는가 | 계획된 실험 2 |
| 4 | **위치 오차 강건성** (실측 오차 + 잡음 주입) | 다중 드론 위치 오차 대응 | 발표 피드백 1 |
| 5 | **설명 가능성 case study** | 초록의 "explainable" 근거 | 초록 의무 |
| 6 | 공개 데이터셋 (ICEWS/GDELT 좌표 복원) | 외부 타당성 | 발표 피드백 3 — 선택 |

---

## 실험 1 — STLogic / TLogic multi-seed (2026-09-30)

`VR-Forces_gt_s10_emb600` · exact 600 s cutoff + embargo · 10,340 질의 · HARD 1,022 ·
average ties. seed 가 바꾸는 것: learn.py 랜덤 워크(규칙 집합)와 공간 모델 음성
샘플링(`rng_seed = seed + 1000`).

| seed | 규칙 | TLogic ALL | TLogic HARD | STLogic ALL | STLogic HARD | HARD H@3 | HARD H@10 | SRR% | HARD 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 12 | 19 | 0.7842 | 0.0029 | 0.7972 | 0.1344 | 0.2123 | 0.4247 | 42.5 | [0.0943, 0.1804] |
| 13 | 21 | 0.7870 | 0.0316 | 0.7987 | 0.1501 | 0.2603 | 0.4276 | 39.3 | [0.1075, 0.1973] |
| 14 | 19 | 0.7842 | 0.0029 | 0.7971 | 0.1343 | 0.2114 | 0.4237 | 42.4 | [0.0936, 0.1802] |
| 15 | 18 | 0.7870 | 0.0316 | 0.7988 | 0.1512 | 0.2613 | 0.4276 | 39.3 | [0.1084, 0.1986] |
| 16 | 19 | 0.7870 | 0.0316 | 0.7987 | 0.1496 | 0.2593 | 0.4237 | 38.8 | [0.1073, 0.1967] |

### 평균 ± 표준편차 (n = 5)

| Model | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@1 | HARD H@3 | HARD H@10 | fwd | inv | SRR% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TLogic | 0.7859 ± 0.0014 | 0.7617 | 0.7987 | 0.8653 | 0.0201 ± 0.0141 | 0.0000 | 0.0346 | 0.0346 | 0.0374 | 0.0029 | — |
| **STLogic** | **0.7981 ± 0.0008** | 0.7622 | 0.8191 | 0.9039 | **0.1439 ± 0.0078** | 0.0047 | 0.2409 | 0.4254 | 0.2849 | 0.0029 | **40.4 ± 1.6** |
| CyGNet (5 seed) | 0.7153 ± 0.0108 | 0.6301 | 0.7837 | 0.8410 | 0.1203 ± 0.0121 | 0.0000 | 0.1957 | 0.4186 | 0.2317 | 0.0090 | — |
| RE-Net (1 run) | 0.6541 | 0.5602 | 0.7140 | 0.8135 | 0.1666 | 0.0000 | 0.2436 | 0.4990 | 0.3138 | 0.0193 | — |
| TiRGN (1 run) | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.0000 | 0.1292 | 0.1477 | 0.1525 | 0.0153 | — |

### 읽는 법

**① 초록의 "better overall performance" 가 seed 분산까지 포함해 확정됐다.**
STLogic ALL 0.7981 ± 0.0008 — 표준편차가 0.001 도 안 된다. 2위 CyGNet(0.7153 ± 0.0108)
과의 차이 0.083 은 양쪽 표준편차의 수십 배다.

**② seed 12 는 다섯 중 낮은 쪽이었다.** 규칙 집합이 두 무리로 갈린다 — seed 12·14 는
TLogic HARD 0.0029(규칙 후보에 정답 0건), seed 13·15·16 은 0.0316(일부 규칙이 정답을
낸다). 앞선 보고의 단일 seed 값(HARD 0.1344)은 평균 0.1439 보다 낮다.

**③ HARD 에서 STLogic 은 CyGNet 보다 높고 RE-Net 보다 낮다.**
- vs CyGNet: 평균 차 +0.024, seed 수준 표준오차 약 0.0064 로 seed 간 비교로는 분리된다.
  다만 한 run 안의 질의 표집 CI 는 여전히 겹친다 — "CyGNet 보다 높다"는 seed 평균 기준으로만 쓴다.
- vs RE-Net: RE-Net 단일 run 0.1666 이 STLogic 다섯 seed 의 최댓값(0.1512)보다 높다.
  RE-Net 은 예산 축소 조건이었으므로 실제 격차는 더 클 수 있다.

**④ HARD H@1 이 0 이 아니게 됐다.** STLogic 평균 0.0047 ± 0.0038 — seed 13·15·16 에서
정답이 1위로 올라오는 경우가 생긴다. 앞선 "전 모델 HARD H@1 = 0" 서술은 **seed 12
기준**이었으므로 "거의 0" 으로 고쳐 써야 한다.

**⑤ SRR 40.4 ± 1.6** — 초록의 "recovers correct answer candidates missed by temporal
rules" 를 뒷받침한다. 규칙이 정답을 일부 내는 seed(13·15·16)에서는 놓친 정답 풀이
달라져 SRR 이 약 39 로 조금 낮다.

**⑥ inverse 는 다섯 seed 모두 0.0029** — 공간 분기가 역방향에 기여하지 못한다는
결론은 seed 에 무관하다.

---

## `learn.py` 관계 분배 버그 두 번째 (2026-09-30)

Horizon sweep 데이터셋에서 `_move to` 규칙이 **0개**였다. inverse 질의 4,351건이 무후보.

```python
num_relations = max(1, len(all_relations) // num_processes)   # 8 // 6 = 1
num_rest_relations = len(all_relations) - (i + 1) * num_relations
if num_rest_relations >= num_relations:                       # 마지막 프로세스: 2 >= 1
    relations_idx = range(i * num_relations, (i + 1) * num_relations)   # 1개만
```

관계 8개를 `-p 6` 으로 돌리면 마지막 프로세스가 나머지 2개를 가져가지 않아, 관계 6·7
(`_Provide-Suppressive-Fire-Loc`, `_move to`)은 **아무도 맡지 않았다. 오류는 없었다.**
Phase 0-3 의 `max(1, ...)` 수정은 몫이 0 이 되는 경우만 막았고 이 경우는 못 막았다.

수정: 마지막 프로세스가 항상 나머지 전부를 맡도록.

```python
start = min(i * num_relations, n)
end = n if i == num_processes - 1 else min((i + 1) * num_relations, n)
```

(8, 6) · (6, 6) · (6, 8) · (16, 8) · (8, 8) · (3, 6) · (10, 4) 전부 누락·중복 없음 확인.

**메인 결과는 영향 없음.** `emb600` 은 학습 구간 관계가 6개라 `-p 6` 에서 나머지가 0 이고,
나머지가 없던 경우는 프로세스별 배정이 이전과 동일하다(multi-seed 포함).
`apply.py` 도 같은 구조지만 질의 수가 프로세스 수보다 훨씬 커서 나머지가 항상 몫보다
작으므로 안전하다.

---

## 실험 2 — Horizon sweep: 600 s 의 근거 (2026-09-30)

발표 피드백 2 — "600 s 로 처음부터 고정하지 말고 여러 horizon 결과로 근거를 보여라."

### 설계와 제약

Δ 마다 embargo 가 허용하는 **최대 학습 구간**을 쓴다(`VR-Forces_gt_s10_emb{Δ}`).
test 질의(tick 146~172, 10,340건)는 모든 Δ 에서 동일하고, HARD 정의만 Δ 에 따라
달라진다. 학습 구간이 Δ 마다 144~90 틱으로 달라지는 교란이 있다.

**Δ 상한이 약 700 s 다.** 처음에는 학습 구간을 가장 보수적인 Δ(900 s)에 맞춰 고정하려
했으나 불가능했다. 공간 모델은 학습 사실마다 Δ 초 전 기하를 읽어야 하므로 학습
구간이 Δ 보다 길어야 하고, embargo 는 학습 끝을 test 시작 − Δ 이전으로 묶는다.

```
test 시작 ≈ 1,500 s (시나리오 시작 기준)
조건 1 (embargo)   train_end ≤ 1,500 − Δ
조건 2 (공간 학습) train_span > Δ
→ 1,500 − Δ > Δ  →  Δ < 750 s
```

학습 틱 0~59 고정안은 Δ = 600·900 에서 공간 학습 표본이 0 이 되어 폐기했다.

### 결과 (seed 12)

| Δ (s) | 학습 틱 | HARD 수 | HARD 비율 | Persist ALL | TLogic ALL | TLogic HARD | STLogic ALL | STLogic HARD | STLogic HARD H@10 | SRR% | STLogic HARD 95% CI |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 30 | 144 | 12 | 0.1% | 0.9923 | 0.9956 | 0.0029 | 0.9954 | 0.0029 | 0.0000 | 0.0 | [0.0029, 0.0029] |
| 60 | 141 | 24 | 0.2% | 0.9864 | 0.9864 | 0.0029 | 0.9862 | 0.0029 | 0.0000 | 0.0 | [0.0029, 0.0029] |
| 120 | 136 | 48 | 0.5% | 0.9815 | 0.9891 | 0.0029 | 0.9889 | 0.0029 | 0.0000 | 0.0 | [0.0029, 0.0029] |
| 300 | 118 | 214 | 2.1% | 0.9468 | 0.9544 | 0.0053 | 0.9545 | 0.0122 | 0.0187 | 1.4 | [0.0029, 0.0305] |
| **600** | 90 | **1,022** | **9.9%** | 0.7849 | 0.7842 | 0.0029 | **0.7972** | **0.1344** | **0.4237** | **42.4** | [0.0937, 0.1806] |

### 600 s 를 고른 근거

1. **300 s 이하에서는 persistence 가 거의 완벽하다** — ALL 0.95~0.99. 모델 비교가
   persistence 복사 능력의 차이로 수렴한다.
2. **HARD 가 의미 있는 규모가 되는 첫 지점이 600 s 다** — 12 → 24 → 48 → 214 →
   1,022건(9.9%). 300 s 의 214건으로는 cluster CI 가 넓어 비교가 어렵다.
3. **이 시나리오에서 embargo 를 지키며 검증 가능한 최대 horizon 이 약 700 s 다.**

### ⚠️ 드러난 한계 — 공간 복구는 600 s 에서만 작동한다

300 s 에서 SRR 1.4% · STLogic HARD 0.0122 로 사실상 효과가 없고, 600 s 에서 SRR 42.4% 로
급격히 바뀐다. 즉 STLogic 의 이득은 horizon 에 강하게 의존한다. 가능한 설명:

- 짧은 horizon 의 공간 모델 양성 표본은 대부분 "지금 목적지로 가는 중" 의 기하라,
  곧 바뀔 **새** 목적지는 오답처럼 보인다(앞선 측정: 학습 양성의 73.5% 가 persistence).
- 600 s 에서는 관측 시점과 정답 시점 사이에 부대가 실제로 이동해, 관측 시점의 기하가
  다음 목적지와 연관된다.

**논문에서 "여러 horizon 에서 효과가 있다" 고 쓰면 안 된다.** 정확한 서술은 *"변화가
충분히 일어나는 horizon(이 시나리오에서 600 s)에서 효과가 나타나며, 짧은 horizon 은
persistence 가 지배한다"* 이다. 이 곡선 자체가 horizon 선택의 근거이자 한계다.

※ 이 sweep 은 `build_samples` 재현성 수정(음성 풀 정렬) 전에 돌렸다. 영향은 0.001 수준이라
추세 판단에는 무관하다.

### 도메인 일반화 (자동차 질문에 대한 답)

horizon 을 초 단위 절대값이 아니라 **"persistence 가 무너지고 HARD 가 충분해지는 지점"**
으로 정의하면 도메인에 맞게 옮겨진다. 이 시나리오에서는 그 지점이 600 s 였고, 이동이
빠른 도메인(차량)에서는 같은 기준으로 더 짧은 Δ 가 선택될 것이다. 장면 통과 시간
`T_cross = L / v̄`(여기서 L = 1,089 m)으로 정규화하는 방식도 가능하나 아직 검증하지 않았다.

---

## 실험 3 — 부분 관측 강건성 (2026-09-30)

`VR-Forces_gt_s10_emb600` · exact 600 s cutoff + embargo · seed 12~16 평균 · **재학습 없음**.
규칙·공간 모델·보정은 GT 학습 구간에서 한 번 만들고, 조건마다 추론 입력만 바꾼다.
질의와 정답은 항상 GT.

| 조건 | 시간 증거(규칙 grounding) | 공간 증거(위치) |
|---|---|---|
| GT-Full | GT | GT |
| GT-Sparse | GT | GT 궤적을 UAV 관측 마스크로 희소화 (`thin_positions`) |
| GT-T / UAV-S | GT | UAV 5대 로그 |
| UAV | UAV (`--history VR-Forces_uavall_s10`, 엣지 9,690 / GT 81,492) | UAV |

`VR-Forces_uavall_s10` 은 새 GT 데이터셋과 엔티티·관계·tick id 가 완전히 같아 그대로
증거로 쓸 수 있다. `-w 3` 에서는 증거 그래프의 학습 구간을 쓰지 않고 관측 cutoff 로만
거르므로 UAV 쪽 split 은 영향이 없다.

### 결과 (5 seed 평균)

| 조건 | 모델 | ALL | H@1 | H@3 | H@10 | HARD | HARD H@1 | HARD H@3 | HARD H@10 | SRR% |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GT-Full | TLogic | 0.7859 | 0.7617 | 0.7987 | 0.8653 | 0.0201 | 0.0000 | 0.0346 | 0.0346 | — |
| GT-Full | **STLogic** | **0.7981** | 0.7622 | 0.8191 | 0.9038 | **0.1437** | 0.0047 | 0.2411 | 0.4243 | 40.3 |
| GT-Sparse | TLogic | 0.7859 | 0.7617 | 0.7987 | 0.8653 | 0.0201 | 0.0000 | 0.0346 | 0.0346 | — |
| GT-Sparse | **STLogic** | 0.7917 | 0.7581 | 0.8135 | 0.8894 | **0.0981** | 0.0006 | 0.1849 | 0.2781 | 25.2 |
| GT-T / UAV-S | TLogic | 0.7859 | 0.7617 | 0.7987 | 0.8653 | 0.0201 | 0.0000 | 0.0346 | 0.0346 | — |
| GT-T / UAV-S | **STLogic** | 0.7856 | 0.7545 | 0.7987 | 0.8855 | **0.0535** | 0.0000 | 0.0346 | 0.2386 | 21.1 |
| UAV | TLogic | 0.2885 | 0.1852 | 0.3510 | 0.5746 | 0.1053 | 0.0000 | 0.1292 | 0.5000 | — |
| UAV | **STLogic** | 0.2953 | 0.1910 | 0.3374 | 0.5583 | **0.0922** | 0.0000 | 0.0235 | 0.5000 | — |

### 조건 내 이득 (STLogic − TLogic)과 GT-Full 대비 감소

| 조건 | Δ ALL | **Δ HARD** | STLogic HARD std | GT-Full 대비 HARD | GT-Full 대비 HARD H@10 |
|---|---:|---:|---:|---:|---:|
| GT-Full | +0.0122 | **+0.1235** | 0.0077 | — | — |
| GT-Sparse | +0.0059 | **+0.0779** | 0.0070 | −0.0456 | −0.1462 |
| GT-T / UAV-S | −0.0003 | **+0.0333** | 0.0083 | −0.0902 | −0.1857 |
| UAV | +0.0067 | **−0.0131** | 0.0000 | −0.0515 | +0.0757 |

### ⚠️ 이전 RQ2 결론을 철회한다

구 프로토콜 RQ2 는 *"이득은 공간 희소화·관측 대상 감소에 강건하다"* (GT-T/UAV-S +0.1067 ≈
GT-Full +0.1052) 였다. **수정 프로토콜에서는 성립하지 않는다.** 공간 관측이 나빠질수록
이득이 단계적으로 줄어든다:

```
GT-Full → GT-Sparse      HARD 이득 +0.1235 → +0.0779   관측 빈도 감소 (staleness)
GT-Sparse → GT-T/UAV-S   HARD 이득 +0.0779 → +0.0333   관측 대상 감소 (coverage)
GT-T/UAV-S → UAV         HARD 이득 +0.0333 → −0.0131   시간 증거 감소
```

그래도 **공간 관측을 UAV 수준으로 떨어뜨려도(GT-T/UAV-S) 시간 증거가 GT 인 한 이득은
양수로 남는다**(+0.0333, 5 seed 표준편차 0.0083 대비 4배). 이득이 사라지는 것은 시간 증거
까지 UAV 로 줄어든 경우다.

### UAV 조건 해석 — 빈도 backoff

UAV 증거로는 10,340 질의 중 **7,040건에서 규칙 후보가 없다.** 평가기는 이때 TLogic 에
관계별 빈도 후보(backoff)를 준다. UAV 조건 TLogic 의 HARD 0.1053 은 **규칙이 아니라
이 backoff 가 낸 값**이다.

처음 평가에서는 STLogic 이 빈 규칙 후보에 공간 후보를 넣는 순간 후보가 비지 않게 되어
이 backoff 를 **잃었다**(표의 `STLogic-noBO`: HARD 0.0612). 공정한 비교를 위해 STLogic 도
규칙 후보가 없을 때 같은 backoff 위에 공간 후보를 얹도록 했다(위 표의 `STLogic`).
GT 조건에서는 두 방식이 소수 4자리까지 같아 **메인 결과에는 영향이 없다**(GT 무후보 294건).

| UAV 조건 | ALL | HARD | HARD H@3 | HARD H@10 |
|---|---:|---:|---:|---:|
| TLogic (backoff 포함) | 0.2885 | 0.1053 | 0.1292 | 0.5000 |
| STLogic (backoff 위에 공간 후보) | 0.2953 | 0.0922 | 0.0235 | 0.5000 |
| STLogic-noBO (backoff 잃음) | 0.2747 | 0.0612 | 0.0705 | 0.2634 |

UAV 에서 STLogic 은 ALL 을 조금 올리지만 HARD 는 backoff 보다 조금 낮다 — 공간 후보가
backoff 가 맞힌 정답을 3위 밖으로 밀어낸다(HARD H@3 0.1292 → 0.0235).

**HARD 절대값을 조건 간에 비교하지 않는다.** UAV 는 후보 집합 구조가 달라(대부분 backoff)
기준선 자체가 다르다. 조건 비교는 조건 내 Δ 로만 한다.

### 재현성 수정 — `build_samples` 음성 풀 정렬

같은 설정에서 GT-Full HARD 가 multi-seed 평가와 0.001 가량 달랐다(seed 13: 0.1491 vs
0.1501). `relation_domain` 값이 문자열 집합이라 해시 순서가 프로세스마다 달라지고, 그
순서로 음성 샘플을 뽑아 공간 모델이 조금씩 바뀌었다. `scene_scale` 과 같은 유형이다.
`pool = sorted(...)` 로 고쳤다. 테스트 50건 통과. 이 표는 수정 후 재실행 값이다.

---

## 실험 4 — 위치 오차 강건성 (2026-09-30)

발표 피드백 1 — "여러 드론이 한 객체를 볼 때 촬영 각도·드론 위치에 따라 위치 오차가
생길 텐데 어떻게 해결할 것인가."

### 먼저 확인한 것 — 이 시뮬레이션의 UAV 관측 오차

| 대조 | 건수 | 중앙 | p90 | 최대 | 0 인 비율 |
|---|---:|---:|---:|---:|---:|
| UAV 위치 vs 같은 시각 GT 위치 | 151,789 | 0.522 m | 1.607 m | 21.281 m | 11.3% |
| 같은 (객체, 시각)을 본 드론들 사이 | 55,057 | 0.003 m | 0.225 m | 22.506 m | 45.5% |

UAV 로그의 위치는 장면 척도(L = 1,089 m)의 0.05% 수준 오차로, **사실상 참값**이다.
따라서 오차 영향은 합성 잡음으로 따로 측정했다.

### 설계

모델·보정은 깨끗한 GT 로 학습한 그대로 두고, 추론 시 **움직이는 개체의 관측 위치에만**
잡음을 넣는다(지명은 지도 좌표라 오차 없음). seed 12·13 평균.

- **independent** — 객체·관측 시각마다 독립 N(0, σ²)
- **common** — 같은 관측 시각의 모든 객체가 같은 오프셋 (한 드론이 여러 객체를 보는 상관 오차의 극단)

### 결과

| 방식 | σ (m) | σ / L | ALL | HARD | HARD H@10 | SRR% |
|---|---:|---:|---:|---:|---:|---:|
| (잡음 없음) | 0 | 0 | 0.7979 | 0.1417 | 0.4242 | 40.7 |
| independent | 5 | 0.005 | 0.7934 | 0.0965 | 0.3963 | 39.1 |
| independent | 10 | 0.009 | 0.7915 | 0.0792 | 0.3625 | 34.9 |
| independent | 25 | 0.023 | 0.7907 | 0.0718 | 0.3508 | 33.3 |
| independent | 50 | 0.046 | 0.7907 | 0.0709 | 0.3464 | 32.8 |
| independent | 100 | 0.092 | 0.7906 | 0.0693 | 0.3478 | 32.8 |
| independent | 200 | 0.184 | 0.7908 | 0.0701 | 0.3532 | 33.4 |
| common | 5 | 0.005 | 0.7918 | 0.0800 | 0.3684 | 35.3 |
| common | 10 | 0.009 | 0.7907 | 0.0709 | 0.3371 | 32.2 |
| common | 25 | 0.023 | 0.7893 | 0.0599 | 0.2906 | 27.2 |
| common | 50 | 0.046 | 0.7888 | 0.0548 | 0.2676 | 24.6 |
| common | 100 | 0.092 | 0.7887 | 0.0535 | 0.2583 | 23.7 |
| common | 200 | 0.184 | 0.7888 | 0.0532 | 0.2524 | 23.5 |
| TLogic (위치 미사용) | — | — | 0.7856 | 0.0173 | — | — |

### ⚠️ 예상과 다르다 — 아주 작은 오차에 크게 흔들린다

- **σ = 5 m (장면 척도의 0.5%) 만으로 HARD 가 0.1417 → 0.0965 (−32%)** 떨어진다.
  그 뒤 σ = 25~200 m 에서는 0.07 부근에서 평평하다.
- 공통 잡음이 상쇄되리라던 예상도 틀렸다. 오히려 독립 잡음보다 더 떨어진다.

**원인 추정 — 거리 변화율 `v_d` 가 1 초 간격 차분이다.** `features()` 는 가장 최근 두 관측
시각의 거리 차이를 시간 차로 나누는데, GT 는 1 Hz 라 두 시각이 1 초 떨어져 있다. 위치에
σ 의 잡음이 있으면 `v_d` 잡음은 약 √2·σ / 1 s — σ = 5 m 이면 약 7 m/s 로, 실제 접근 속도
(수 m/s 이하)를 덮어버린다. HARD 가 σ 에 무관하게 평평해지는 0.07 은 **`v_d` 가 무력해지고
거리 `d` 만 남은 수준**으로 보인다.

공통 잡음이 상쇄되지 않는 이유도 같다. 오프셋이 관측 시각마다 달라 두 시각 사이에서는
독립 잡음처럼 작용하고, `move to` 의 목적어인 **지명은 잡음이 없어** 주어 쪽 오프셋만 남는다.
상대 거리 특징의 상쇄는 **두 개체가 모두 같은 드론에 같은 시각 관측될 때**만 성립한다.

→ 가설 검증: `d` 만 쓰는 모델, 그리고 `v_d` 를 더 긴 간격(30 s, 60 s)으로 계산하는 모델을
같은 잡음에서 비교한다. 이 문제는 부분 관측의 GT-T/UAV-S 이득 감소(+0.1235 → +0.0333)와도
연결될 수 있다 — UAV 위치 오차는 중앙 0.5 m 지만 1 초 차분이면 `v_d` 잡음이 약 0.7 m/s 다.

---

## 실험 5 — 설명 가능성 (2026-09-30)

초록의 "explainable link forecasting" 근거. TLogic 의 `match_body_relations_complete`,
`get_walks_complete`, `verbalize_walk` 로 규칙 근거 경로를 복원하고, 공간 모델에서 공간
근거를 붙였다(seed 12).

### 정량 — 최종 1위 예측에 붙는 근거 (test 2,068건 표본)

| 근거 | 건수 | 비율 |
|---|---:|---:|
| 규칙 + 공간 근거 | 1,008 | 48.7% |
| 규칙 근거만 | 1,008 | 48.7% |
| 공간 근거만 | 26 | 1.3% |
| 근거 없음 (빈도 backoff) | 26 | 1.3% |

**최종 1위 예측의 98.7% 에 규칙 또는 공간 근거가 붙는다.** "규칙 근거만" 은 거의 전부
inverse 질의다 — 공간 모델이 정방향 관계에만 있어 역방향 후보에는 공간 근거가 없다.
forward·inverse 가 같은 사실의 양방향이라 두 줄의 건수가 같다.

### 사례 A — 공간이 복구한 HARD 질의

```
질의  (ENINF075, move to, ?, 13:46:42)  관측 시점 13:36:42
정답  LOC_북측예비방어선   관측 시점의 답  LOC_동측측방접근로   TLogic 후보에 정답 없음

1위  LOC_동측측방접근로 (규칙)  최종 0.8020
     규칙  move to(X0, X1, T) ← move to(X0, X1, T0)   신뢰도 0.988
     경로  ENINF075 → move to → LOC_동측측방접근로 @ 13:36:22
     공간  거리 102 m · 거리 변화율 −1.30 m/s · 로그우도비 −0.81
2위  LOC_북측예비방어선 (공간 추가)  최종 0.0357   ← 정답
     공간  거리 884 m · 거리 변화율 +1.14 m/s · 로그우도비 +0.50
     (정답 전형 978 m / −0.94 m/s · 오답 전형 1,262 m / −0.51 m/s)
```

이 사례 하나에 STLogic 의 작동과 한계가 모두 보인다.
- 규칙은 "지금 가는 곳에 계속 간다" 만 말한다. 정답은 규칙 후보에 없다.
- 공간 모델은 **옛 답에 로그우도비 −0.81** 을 준다 — 부대가 이미 102 m 까지 도착해
  목적지가 곧 바뀔 상황이다. 이것이 앞서 측정한 "만료 신호"다.
- 정답은 공간 후보로 복구돼 2위에 오지만, 규칙 점수(0.80)가 공간 점수(0.04)를 압도해
  옛 답을 끌어내리지 못한다. HARD H@1 이 거의 0 인 이유가 설명에 그대로 드러난다.

### 사례 B — 규칙이 맞힌 질의

```
질의  (FRAT008, move to, ?, 13:48:42)   정답 = 관측 시점의 답 = LOC_동측능선
1위  LOC_동측능선 (규칙)  최종 0.9087  ← 정답
     규칙  move to(X0, X1, T) ← move to(X0, X1, T0)   신뢰도 0.988
     공간  거리 698 m · 거리 변화율 −0.41 m/s · 로그우도비 +0.36 (접근 중, 정답 쪽)
```

규칙과 공간 근거가 같은 방향을 가리킨다.

### 사례 C — 실패한 HARD 질의 (역방향)

```
질의  (LOC_적북측접근로, _move to, ?, 13:47:32)   정답 ENINF096   STLogic 순위 341
1~3위  관측 시점에 그곳으로 가던 부대들 (규칙, 신뢰도 0.988)
공간  로그우도비 없음 (역방향 공간 모델 없음)
```

"누가 이곳으로 올 것인가" 에 대해 규칙은 지금 오던 부대만 제시하고, 공간 근거는 없다.
역방향 실패의 기전이 설명에서 바로 확인된다.

---

## 실험 1 최종값 — 재현성 수정 후 multi-seed 재실행 (2026-09-30)

`build_samples` 음성 풀 정렬 수정 후 같은 설정으로 재실행. 이제 같은 seed 는 실행마다
같은 값을 낸다. **논문 수치는 이 표를 쓴다.**

| seed | TLogic ALL | TLogic HARD | STLogic ALL | STLogic HARD | HARD H@3 | HARD H@10 | SRR% | HARD 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 12 | 0.7842 | 0.0029 | 0.7971 | 0.1342 | 0.2114 | 0.4237 | 42.4 | [0.0935, 0.1800] |
| 13 | 0.7870 | 0.0316 | 0.7986 | 0.1492 | 0.2603 | 0.4247 | 38.9 | [0.1067, 0.1964] |
| 14 | 0.7842 | 0.0029 | 0.7971 | 0.1343 | 0.2133 | 0.4237 | 42.4 | [0.0938, 0.1805] |
| 15 | 0.7870 | 0.0316 | 0.7987 | 0.1503 | 0.2603 | 0.4247 | 38.9 | [0.1077, 0.1978] |
| 16 | 0.7870 | 0.0316 | 0.7987 | 0.1503 | 0.2603 | 0.4247 | 38.9 | [0.1077, 0.1978] |

| Model | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@1 | HARD H@3 | HARD H@10 | fwd | inv | SRR% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TLogic (5 seed) | 0.7859 ± 0.0014 | 0.7617 | 0.7987 | 0.8653 | 0.0201 ± 0.0141 | 0.0000 | 0.0346 | 0.0346 | 0.0374 | 0.0029 | — |
| **STLogic (5 seed)** | **0.7981 ± 0.0008** | 0.7622 | 0.8191 | 0.9038 | **0.1437 ± 0.0077** | 0.0047 | 0.2411 | 0.4243 | 0.2844 | 0.0029 | **40.3 ± 1.7** |
| CyGNet (5 seed) | 0.7153 ± 0.0108 | 0.6301 | 0.7837 | 0.8410 | 0.1203 ± 0.0121 | 0.0000 | 0.1957 | 0.4186 | 0.2317 | 0.0090 | — |
| RE-Net (1 run) | 0.6541 | 0.5602 | 0.7140 | 0.8135 | 0.1666 | 0.0000 | 0.2436 | 0.4990 | 0.3138 | 0.0193 | — |
| TiRGN (1 run) | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.0000 | 0.1292 | 0.1477 | 0.1525 | 0.0153 | — |

수정 전(HARD 0.1439 ± 0.0078)과 차이 0.0002 — 결론 변화 없음.

### 실험 4 보강 — 원인 확인: 1 초 간격 거리 변화율 (2026-09-30)

같은 독립 잡음에서 `v_d` 계산 방식만 바꿔 비교했다. 각 변형으로 깨끗한 GT 에서 모델을 새로
학습. seed 12·13 평균.

**HARD MRR**

| 변형 | σ = 0 | σ = 5 m | σ = 25 m | σ = 100 m | σ = 5 m 하락 |
|---|---:|---:|---:|---:|---:|
| 현행 (최근 두 관측, 1 초 차분) | 0.1417 | 0.0965 | 0.0718 | 0.0693 | −32% |
| 거리만 (`v_d` 제거) | 0.1235 | 0.1235 | 0.1226 | 0.1185 | −0% |
| 30 초 차분 | 0.1405 | 0.1387 | 0.1246 | 0.1101 | −1% |
| **60 초 차분** | **0.1435** | **0.1426** | **0.1360** | **0.1244** | **−1%** |

**HARD H@10**

| 변형 | σ = 0 | σ = 5 m | σ = 25 m | σ = 100 m |
|---|---:|---:|---:|---:|
| 현행 (1 초 차분) | 0.4242 | 0.3963 | 0.3508 | 0.3478 |
| 거리만 | 0.4467 | 0.4462 | 0.4477 | 0.4325 |
| 30 초 차분 | 0.4344 | 0.4335 | 0.4452 | 0.4188 |
| 60 초 차분 | 0.4344 | 0.4335 | 0.4388 | 0.4477 |

**ALL MRR** — 모든 변형이 0.79~0.80 범위로 차이가 작다
(σ = 0: 현행 0.7979 · 거리만 0.7961 · 30 초 0.7978 · 60 초 0.7981).

### 결론

1. **가설 확인.** 위치 잡음에 약했던 원인은 `v_d` 의 1 초 차분이다. 거리만 쓰면 잡음에
   전혀 흔들리지 않는다(σ = 100 m 에서도 −4%).
2. **`v_d` 는 여전히 필요하다.** 거리만 쓰면 잡음이 없을 때 HARD 가 0.1417 → 0.1235 로
   낮다 — 접근·이탈 정보가 기여한다.
3. **60 초 차분이 둘 다 얻는다.** 잡음이 없을 때 현행과 같거나 조금 높고(0.1435),
   σ = 25 m 에서 0.1360 을 유지한다. 차분 간격을 늘리면 위치 잡음이 간격으로 나눠져
   약해진다(1 초 → 60 초로 60배).

### 발표 피드백 1 에 대한 답

> 드론 관측 위치 오차에 대해 STLogic 의 공간 특징 중 **거리는 본래 강건**하고, 약점이던
> **거리 변화율은 계산 간격을 60 초로 늘리면 강건해진다.** 위치 오차 σ = 25 m(장면 척도의
> 2.3%)에서도 HARD MRR 이 잡음이 없을 때의 95% 수준을 유지한다.

**다만 이는 방법 변경이다.** 채택하면 메인 결과·multi-seed·부분 관측·sweep 을 다시 돌려야
한다(외부 baseline 은 공간 특징을 쓰지 않아 영향 없음). 채택 여부는 결정 필요.

### 60 초 차분이 부분 관측에도 도움이 되는가 (2026-09-30)

실험 3 을 `v_d` 60 초 차분으로 다시 돌렸다(seed 12·13, 진단용). 비교는 같은 두 seed 의
1 초 차분 값.

| 조건 | TLogic HARD | STLogic HARD (1 초) | STLogic HARD (60 초) | 이득 (1 초) | **이득 (60 초)** | HARD H@10 (1 초 → 60 초) | ALL (1 초 → 60 초) |
|---|---:|---:|---:|---:|---:|---|---|
| GT-Full | 0.0173 | 0.1417 | 0.1435 | +0.124 | +0.126 | 0.4242 → 0.4345 | 0.7979 → 0.7981 |
| GT-Sparse | 0.0173 | 0.0966 | 0.1086 | +0.079 | +0.091 | 0.2760 → 0.2950 | 0.7916 → 0.7927 |
| GT-T / UAV-S | 0.0173 | 0.0527 | 0.0969 | +0.035 | **+0.080** | 0.2436 → 0.3405 | 0.7855 → 0.7899 |
| UAV | 0.1053 | 0.0922 | 0.0927 | −0.013 | −0.013 | 0.5000 → 0.5000 | 0.2952 → 0.3134 |

**UAV 위치를 쓰는 GT-T/UAV-S 에서 이득이 2.3 배가 된다.** UAV 위치의 실제 오차(중앙
0.5 m)가 1 초 차분에서 증폭되던 것이, 실험 3 에서 본 이득 감소(+0.124 → +0.035)의 상당
부분이었다. 60 초 차분이면 공간 관측을 UAV 로 바꿔도 이득의 64%(+0.080 / +0.126)가 남는다.

UAV 조건(시간 증거까지 UAV)은 60 초 차분으로도 HARD 이득이 음수다 — 이 조건의 한계는
공간 특징이 아니라 시간 증거 부족(무후보 7,040건)이다. ALL 은 0.2952 → 0.3134 로 오른다.

### 판단

60 초 차분은 **잡음이 없을 때 성능을 잃지 않고**(HARD 0.1417 → 0.1435, ALL 동일),
**위치 오차와 부분 관측 모두에서 강건성을 크게 높인다.** 방법의 기본값으로 채택할 근거가
충분하다. 채택하면 STLogic 을 쓰는 실험(메인, multi-seed, ablation, 부분 관측, horizon
sweep, 설명 사례)을 다시 돌려야 한다. 외부 baseline 은 공간 특징을 쓰지 않아 그대로다.

---

## TiRGN 메인 수치 정정 — test 스냅샷 창이 embargo 증거를 못 봤다 (2026-10-01)

TiRGN 은 test 때 두 가지를 증거로 쓴다: (1) 최근 스냅샷 창, (2) 누적 history 어휘.
(2) 는 `vocab.txt`(train + valid + embargo)로 만들었지만, (1) 은 원본 코드대로
`train_list + valid_list` — 즉 **tick 0~89** 에서만 꺼냈다. test 질의의 cutoff 는
tick 89~113 이라, 그 사이(embargo 구간 90~113)의 증거를 **STLogic 은 보는데 TiRGN 스냅샷
창은 보지 못했다.** 메인 표의 TiRGN 은 더 오래된 증거로 평가된 셈이다.

`main.py` 에 `--test-evidence DATASET` 을 추가했다. test 때 스냅샷 창과 history 어휘를 그
데이터셋의 `vocab.txt`(관측 가능한 전부)에서 만든다. 저장된 체크포인트로 test 만 다시
돌렸다(재학습 없음). 이름은 기존 `--test-history-len` 과 접두사가 겹치지 않게 정했다.

| TiRGN | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@3 | HARD H@10 | HARD 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 이전 (스냅샷 tick ≤ 89) | 0.5905 | 0.4552 | 0.6970 | 0.7614 | 0.0839 | 0.1292 | 0.1477 | [0.0414, 0.1303] |
| **정정 (embargo 증거 포함)** | **0.6716** | 0.5480 | 0.7659 | 0.8466 | **0.0866** | 0.1399 | 0.1517 | [0.0444, 0.1327] |

ALL 이 +0.081 오른다. **메인 표의 TiRGN 은 정정 값을 쓴다.** 순위는 바뀌지 않는다
(STLogic ALL 0.7981 > CyGNet 0.7153 > TiRGN 0.6716 > RE-Net 0.6541).

다른 baseline 은 해당 없음 — CyGNet 은 어휘가 `vocab.txt` 에서, RE-Net 은 history 에
`absorb()` 로 embargo 증거를 이미 넣었다.

---

## 실험 3 확장 — 외부 baseline 의 부분 관측 강건성 (2026-10-01)

외부 모델은 위치를 쓰지 않으므로 GT-Sparse·GT-T/UAV-S 에서는 GT-Full 과 같다. **UAV
조건(시간 증거까지 UAV)만** 새로 돌렸다. STLogic 과 같은 원칙으로 가중치는 GT 학습 그대로,
test 때 관측 가능한 증거만 UAV 로 바꿨다.

| 모델 | UAV 로 바꾼 test 증거 | 구현 |
|---|---|---|
| CyGNet | copy 어휘 | `config.py --test-vocab`, `run_vrforces.py` 가 최종 test 에만 다른 어휘 사용 |
| TiRGN | 스냅샷 창 + history 어휘 | `main.py --test-evidence` (아래 TiRGN 정정과 같은 옵션) |
| RE-Net | test history + 그래프 스냅샷 + global embedding | `renet_uav.py` 로 UAV 사실에서 재생성 |

UAV 관측 사실 4,845개(역방향 포함 9,690개 — STLogic 쪽 `--history uavall` 과 일치)를
`VRFEMB` id 공간으로 옮겨 `{CyGNet,TiRGN,RE-Net}/data/VRFEMB_UAV/vocab.txt` 에 두었다.

### 누수 하나를 잡았다 — RE-Net UAV history

처음 RE-Net UAV 전처리는 UAV 사실(tick 0~172)을 **전부** History 에 흘려 넣은 뒤 test 질의를
읽었다. History 는 진행한 시각만큼 공개 범위를 넓히므로, tick 172 까지 진행하면 tick 113
까지의 사실이 공개된다. 첫 test 질의(tick 146)의 cutoff 는 tick 89 다 — **최대 240 초 미래
정보**. GT 쪽은 embargo 증거가 tick 145 에서 끝나 이 문제가 없었다. 첫 test 틱 이전 사실
(4,196개)만 흘려 넣도록 고쳤다. 다른 경로(CyGNet 어휘 누적, TiRGN 창·어휘, STLogic 증거·위치)는
모두 cutoff 기준으로 걸러져 해당 없음을 확인했다.

### 결과

| 모델 | 증거 | ALL | H@1 | H@3 | H@10 | HARD | HARD H@1 | HARD H@3 | HARD H@10 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CyGNet (5 seed) | GT | 0.7153 | 0.6301 | 0.7837 | 0.8410 | 0.1203 | 0.0000 | 0.1957 | 0.4186 |
| CyGNet (5 seed) | UAV | 0.5609 | 0.4668 | 0.6592 | 0.7380 | 0.1186 | 0.0000 | 0.1898 | 0.4225 |
| TiRGN | GT | 0.6716 | 0.5480 | 0.7659 | 0.8466 | 0.0866 | 0.0000 | 0.1399 | 0.1517 |
| TiRGN | UAV | 0.2308 | 0.1726 | 0.2697 | 0.3260 | 0.1398 | 0.0646 | 0.2065 | 0.2446 |
| RE-Net | GT | 0.6541 | 0.5602 | 0.7140 | 0.8135 | 0.1666 | 0.0000 | 0.2436 | 0.4990 |
| RE-Net | UAV | 0.7074 | 0.6239 | 0.7685 | 0.8445 | 0.1671 | 0.0000 | 0.2211 | 0.5225 |

**GT → UAV 변화**

| 모델 | ALL | HARD | HARD H@10 |
|---|---:|---:|---:|
| CyGNet | −0.1543 | −0.0017 | +0.0039 |
| TiRGN | −0.4408 | +0.0532 | +0.0930 |
| RE-Net | +0.0533 | +0.0005 | +0.0235 |

### RE-Net 이 UAV 에서 ALL 이 오르는 이유 — 누수가 아니다

증거가 1/8 로 줄었는데 ALL 이 오르는 것을 확인했다. 이득은 전부 **UAV history 가 비어 있는
역방향 질의**에서 나온다.

| 부분집합 | n | GT MRR | UAV MRR |
|---|---:|---:|---:|
| forward | 5,170 | 0.8508 | 0.8509 |
| inverse | 5,170 | 0.4573 | 0.5639 |
| easy · UAV history 있음 | 5,880 | 0.6837 | 0.6813 |
| easy · UAV history 없음 | 3,144 | 0.8171 | **0.9967** |
| HARD | 1,022 | 0.1666 | 0.1671 |

- horizon 모드는 질의마다 history 를 덮어쓰고 내부 시각을 질의 시각으로 맞추므로, test 중
  캐시를 갱신하는 블록이 실행되지 않는다. global embedding 도 각 시점까지의 그래프만 쓴다.
- history 가 비면 RE-Net 은 `(대상 엔티티, 관계)` 의 **학습된 임베딩만으로** 예측한다. 학습
  구간에서 배운 "이 지명으로 가는 부대" 사전 지식이라 프로토콜상 합법이다.
- 역방향 질의에서는 이 사전 지식 경로가 history 경로보다 정확하다 — 지명마다 history 가 수많은
  부대로 붐벼 오히려 방해가 되는 것으로 보인다.

즉 **"RE-Net 이 UAV 에 강건하다"가 아니라 "RE-Net 의 history 경로가 역방향에서 손해였다"** 가
정확한 해석이다. HARD 는 변하지 않는다.

### 해석 주의

- **HARD 절대값을 조건 간에 비교하지 않는다.** TiRGN 의 UAV HARD 상승(+0.053, H@1 0.0646)은
  관측 시점 답이 UAV 에서 자주 안 보여 옛 답에 덜 고정되기 때문으로 보인다. TLogic 이 UAV 에서
  빈도 backoff 로 HARD 가 오른 것과 같은 유형이다.
- 조건 간 비교는 **같은 모델의 GT → UAV 변화**로만 한다.

---

## 거리 변화율 계산 간격 선택 — 검증 구간 기준 30 초 (2026-10-01)

test 에서 1·30·60 초만 비교해 고르면 test 에 맞춘 선택이 된다. 그래서 간격을 **검증 구간**
에서 골랐다.

- 검증 질의: 보정 구간(tick 77~89) 6,356건, HARD 1,039건. 규칙 후보는 같은 규칙으로
  `apply.py` 를 돌려 만들었다(`VR-Forces_gt_s10_emb600_calibq`, test.txt = 보정 틱).
- 공간 모델: 선택용은 fit 구간(tick 0~76)으로만 학습 → 검증 질의에게 표본 밖.
  test 민감도용은 학습 구간 전체(0~89).
- **선택 기준(결과를 보기 전에 정함)**: 검증 HARD MRR 을 잡음 없음과 σ = 25 m 에서 평균한 값.
  잡음 없을 때는 간격 간 차이가 0.003 이내라 그것만으로 고르면 사실상 우연에 맡기게 된다.

| W (s) | 검증 HARD (잡음 없음) | 검증 HARD (σ=25 m) | **기준** | test ALL | test HARD | test HARD H@10 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 (현행) | 0.1104 | 0.0770 | 0.0937 | 0.7978 | 0.1417 | 0.4242 |
| 10 | 0.1129 | 0.1033 | 0.1081 | 0.7975 | 0.1383 | 0.4305 |
| **30** | 0.1094 | 0.1092 | **0.1094** | 0.7977 | 0.1405 | 0.4344 |
| 60 | 0.1076 | 0.0968 | 0.1022 | 0.7980 | 0.1435 | 0.4345 |
| 120 | 0.1048 | 0.1037 | 0.1043 | 0.7983 | 0.1456 | 0.4335 |
| 300 | 0.1039 | 0.1041 | 0.1040 | 0.7983 | 0.1458 | 0.4227 |

(seed 12·13 평균)

**선택: W = 30 s.** test 에서는 60·120 초가 조금 더 높지만 미리 정한 검증 기준을 따른다.
30 초는 잡음 없을 때 현행과 같고(test HARD 0.1405 vs 0.1417), σ = 25 m 에서 test HARD
0.1246 으로 현행(0.0718)보다 크게 강건하다(앞선 진단).

**방법의 기본값을 30 초로 바꾼다.** STLogic 을 쓰는 실험은 이 값으로 다시 돌린다.

---

# 최종 결과 — 거리 변화율 30 초 간격 채택 후 재실행 (2026-10-01)

`spatial.VD_MIN_GAP = 30` (검증 구간 선택). `features()` 는 30 초 이상 떨어진 가장 최근
관측과 비교하고, 그런 관측이 없으면 가장 오래된 가용 관측으로 물러난다(관측 둘이면 기존과
동일). 테스트 2건 추가, 52건 통과. 공통 조건: `VR-Forces_gt_s10_emb600` · exact 600 s cutoff ·
embargo · test 10,340 질의 · HARD 1,022 · average ties · 단일 evaluator.
**이 절의 표가 논문용 최종값이다.** 앞선 1 초 간격 표들은 경위 기록으로 남긴다.

## 실험 1 — 예측 성능 비교

| Model | ALL MRR | H@1 | H@3 | H@10 | HARD MRR | HARD H@1 | HARD H@3 | HARD H@10 | fwd | inv |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Persistence | 0.7849 | 0.7617 | 0.8095 | 0.8538 | 0.0029 | 0.0000 | 0.0000 | 0.0000 | 0.0029 | 0.0029 |
| TLogic (5 seed) | 0.7859 ± 0.0014 | 0.7617 | 0.7987 | 0.8653 | 0.0201 ± 0.0141 | 0.0000 | 0.0346 | 0.0346 | 0.0374 | 0.0029 |
| CyGNet (5 seed) | 0.7153 ± 0.0108 | 0.6301 | 0.7837 | 0.8410 | 0.1203 ± 0.0121 | 0.0000 | 0.1957 | 0.4186 | 0.2317 | 0.0090 |
| TiRGN (1 run, 증거 정정) | 0.6716 | 0.5480 | 0.7659 | 0.8466 | 0.0866 | 0.0000 | 0.1399 | 0.1517 | — | — |
| RE-Net (1 run) | 0.6541 | 0.5602 | 0.7140 | 0.8135 | **0.1666** | 0.0000 | 0.2436 | **0.4990** | 0.3138 | 0.0193 |
| **STLogic (5 seed)** | **0.7979 ± 0.0005** | **0.7617** | **0.8196** | **0.9048** | 0.1417 ± 0.0048 | 0.0000 | **0.2460** | 0.4344 | 0.2804 | 0.0029 |

STLogic seed 별: HARD 0.1356 / 0.1454 / 0.1360 / 0.1456 / 0.1456 · SRR 41.4 ± 1.7.

- **ALL 1 위**, 2 위 CyGNet 대비 +0.083. seed 표준편차 0.0005.
- **HARD 는 RE-Net 1 위**(0.1666). STLogic 은 CyGNet 보다 높고(+0.021) RE-Net 보다 낮다.
  HARD H@3 은 STLogic 이 가장 높다(0.2460 vs RE-Net 0.2436).
- 1 초 간격 대비: HARD 0.1437 → 0.1417, ALL 0.7981 → 0.7979 — 정확도는 사실상 같다.

## Ablation (5 seed)

| Method | ALL | H@3 | H@10 | HARD | HARD H@3 | HARD H@10 | SRR% |
|---|---:|---:|---:|---:|---:|---:|---:|
| TLogic | 0.7859 | 0.7987 | 0.8653 | 0.0201 ± 0.0141 | 0.0346 | 0.0346 | — |
| + Spatial Context (재정렬만) | 0.7856 | 0.7987 | 0.8653 | 0.0174 ± 0.0118 | 0.0346 | 0.0346 | — |
| + Spatial Candidate Recovery | 0.7981 | 0.8196 | 0.9048 | **0.1444 ± 0.0070** | 0.2460 | 0.4344 | 41.4 |
| STLogic Full | 0.7979 | 0.8196 | 0.9048 | 0.1417 ± 0.0048 | 0.2460 | 0.4344 | 41.4 |

- **이득은 전부 후보 복구에서 나온다.**
- 공간 재정렬은 기여가 없고, 규칙이 정답을 일부 내는 seed(13·15·16)에서는 오히려 HARD 를
  조금 깎는다(0.0316 → 0.0271). 그래서 Recovery 단독(0.1444)이 Full(0.1417)보다 조금 높다.
  재정렬을 빼는 설계 단순화가 정당화된다 — 다만 초록이 "temporal scores are combined with
  spatial compatibility scores" 라고 썼으므로 본문에서는 결합을 유지하고 이 결과를 ablation 으로
  보고하는 편이 초록과 맞다.

## 실험 2 — Horizon sweep (seed 12)

| Δ | 학습 틱 | HARD 비율 | Persist ALL | TLogic HARD | STLogic ALL | STLogic HARD | HARD H@10 | SRR% |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 s | 144 | 0.1% | 0.9923 | 0.0029 | 0.9954 | 0.0029 | 0.0000 | 0.0 |
| 60 s | 141 | 0.2% | 0.9864 | 0.0029 | 0.9862 | 0.0029 | 0.0000 | 0.0 |
| 120 s | 136 | 0.5% | 0.9815 | 0.0029 | 0.9889 | 0.0029 | 0.0000 | 0.0 |
| 300 s | 118 | 2.1% | 0.9468 | 0.0053 | 0.9542 | 0.0122 | 0.0187 | 1.4 |
| **600 s** | 90 | **9.9%** | 0.7849 | 0.0029 | **0.7973** | **0.1356** | **0.4344** | **43.4** |

결론은 1 초 간격과 같다 — 300 s 이하는 persistence 가 지배하고, 공간 복구는 600 s 에서만
작동한다. embargo 를 지키며 검증 가능한 상한은 약 700 s.

## 실험 3 — 부분 관측 강건성 (5 seed, 재학습 없음)

**STLogic / TLogic**

| 조건 | TLogic HARD | STLogic ALL | STLogic HARD | STLogic HARD H@10 | **HARD 이득** | 이득 (1 초 간격) |
|---|---:|---:|---:|---:|---:|---:|
| GT-Full | 0.0201 | 0.7979 | 0.1417 | 0.4344 | **+0.1215** | +0.1235 |
| GT-Sparse | 0.0201 | 0.7927 | 0.1089 | 0.2975 | **+0.0887** | +0.0779 |
| GT-T / UAV-S | 0.0201 | 0.7899 | 0.0968 | 0.3626 | **+0.0766** | +0.0333 |
| UAV | 0.1053 | 0.3134 | 0.0927 | 0.5000 | −0.0126 | −0.0131 |

**30 초 간격으로 부분 관측 강건성이 크게 좋아졌다.** UAV 위치를 쓰는 GT-T/UAV-S 의 이득이
+0.033 → **+0.077**(GT-Full 이득의 63%)이다. 공간 관측이 희소하거나 UAV 로 바뀌어도 시간
증거가 GT 인 한 이득이 유지된다. 시간 증거까지 UAV 로 줄면(무후보 7,040건) HARD 이득은 사라지고
ALL 만 +0.025 오른다.

**외부 baseline (GT → UAV 변화)**

| 모델 | ALL (GT → UAV) | HARD (GT → UAV) |
|---|---|---|
| CyGNet (5 seed) | 0.7153 → 0.5609 (−0.154) | 0.1203 → 0.1186 (−0.002) |
| TiRGN | 0.6716 → 0.2308 (−0.441) | 0.0866 → 0.1398 (+0.053) |
| RE-Net | 0.6541 → 0.7074 (+0.053) | 0.1666 → 0.1671 (+0.001) |
| TLogic (5 seed) | 0.7859 → 0.2885 (−0.497) | 0.0201 → 0.1053 (빈도 backoff) |
| STLogic (5 seed) | 0.7979 → 0.3134 (−0.485) | 0.1417 → 0.0927 |

규칙 기반(TLogic·STLogic)은 시간 증거가 UAV 로 줄면 규칙 후보 자체가 사라져 ALL 이 크게
떨어진다. RE-Net 의 ALL 상승은 history 가 빈 역방향 질의에서 학습된 사전 지식 경로로 빠지기
때문이다(누수 아님 — 앞 절 참조). **"관측이 불완전해도 효과가 유지되는가"에 대한 답은
"공간 관측이 불완전한 경우는 유지되고, 시간 관측까지 불완전하면 규칙 기반 계열 전체가 약하다"**
이다.

## 실험 4 — 위치 오차 강건성 (seed 12·13)

| 잡음 | σ (m) | σ / L | ALL | HARD | HARD H@10 | 잡음 없음 대비 HARD |
|---|---:|---:|---:|---:|---:|---:|
| 없음 | 0 | 0 | 0.7978 | 0.1405 | 0.4344 | 100% |
| independent | 5 | 0.005 | 0.7976 | 0.1387 | 0.4335 | 99% |
| independent | 10 | 0.009 | 0.7971 | 0.1336 | 0.4359 | 95% |
| independent | 25 | 0.023 | 0.7962 | 0.1246 | 0.4452 | 89% |
| independent | 50 | 0.046 | 0.7957 | 0.1199 | 0.4477 | 85% |
| independent | 100 | 0.092 | 0.7945 | 0.1101 | 0.4188 | 78% |
| independent | 200 | 0.184 | 0.7921 | 0.0869 | 0.3782 | 62% |
| common | 25 | 0.023 | 0.7965 | 0.1274 | 0.4340 | 91% |
| common | 100 | 0.092 | 0.7939 | 0.1020 | 0.4022 | 73% |
| common | 200 | 0.184 | 0.7920 | 0.0820 | 0.3381 | 58% |
| TLogic (위치 미사용) | — | — | 0.7856 | 0.0173 | — | — |

1 초 간격에서는 σ = 5 m 만으로 HARD 가 −32% 였다. 30 초 간격에서는 **σ = 25 m(장면 척도의
2.3%)에서 89%, σ = 100 m(9.2%)에서도 78%** 를 유지하고, 모든 잡음 수준에서 TLogic 보다 크게
높다. 이 시나리오의 실제 UAV 관측 오차는 중앙 0.5 m 다.

## 실험 5 — 설명 가능성 (seed 12)

최종 1 위 예측의 근거(test 2,068건 표본): 규칙 + 공간 48.7% · 규칙만 48.7% · 공간만 1.3% ·
근거 없음 1.3%. **98.7% 에 근거가 붙는다.** 사례 A(공간이 복구한 HARD 질의 — 정답 2 위, 옛 답에
로그우도비 −0.77), B(규칙 적중 — 규칙과 공간 근거가 같은 방향), C(역방향 실패 — 공간 근거
없음)가 1 초 간격 때와 같은 양상으로 재현됐다.

## 최종 정리

**주장할 수 있는 것**
1. 정확한 cutoff 와 embargo 를 적용한 프로토콜에서 시간 규칙은 정답이 바뀌는 질의의 정답 후보를
   거의 만들지 못한다.
2. 공간 기반 후보 복구가 그 정답의 약 41% 를 되찾고, 전체 질의 정확도는 비교 모델 중 가장 높다
   (ALL 0.7979 ± 0.0005).
3. 600 s horizon 은 변화가 충분해지는 지점이라는 데이터 근거가 있다.
4. 공간 관측이 희소하거나 UAV 로 바뀌어도, 위치 오차가 장면 척도의 수 % 여도 이득이 대부분
   유지된다(30 초 간격 거리 변화율 덕분).
5. 예측의 98.7% 에 규칙 또는 공간 근거가 붙는다.

**한계로 밝힐 것**
1. 정답이 바뀐 질의의 MRR 은 RE-Net 이 더 높다(예산 축소 조건).
2. 역방향 질의에는 공간 분기가 기여하지 못한다.
3. 효과는 600 s horizon 에서만 나타난다(이 시나리오의 검증 상한 약 700 s).
4. 시간 증거까지 불완전하면(UAV) 규칙 기반 계열 전체가 약하다.
5. 공간 재정렬은 기여가 없고, 이득은 후보 복구에서만 나온다.
6. 단일 시뮬레이션 시나리오.
