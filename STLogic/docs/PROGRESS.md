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

## STLogic 최종 결과 (battlefield_hill395, test, baseline 0.5464 대비)
| config | MRR | Hits@1 | Hits@3 | Hits@10 | no-cand |
|---|---|---|---|---|---|
| baseline TLogic | 0.5464 | 0.5156 | 0.5482 | 0.6117 | 11,118 |
| 재순위화 ②③ | 0.5502 | 0.5151 | 0.5559 | 0.6308 | 11,118 |
| + backoff(기하) | 0.5627 | 0.5198 | 0.5687 | 0.6644 | 8,987 |
| + 부대centroid(off+bo) | 0.5854 | 0.5290 | 0.5856 | 0.7200 | 3,146 |
| **best 전부결합** | **0.5891** | 0.5286 | 0.5933 | **0.7390** | 3,146 |
