# Cloud Run Jobs 이전 설계

작성일: 2026-06-19

## 배경 / 문제

성남시 전기차 보조금 공고 감시 작업은 현재 GitHub Actions의 `schedule` 트리거로
15분마다(변화 감지) + 매일 08:00 KST(일일 현황) 실행한다. 그러나 GitHub Actions의
`schedule`은 best-effort라 짧은 주기 cron이 40분~2시간까지 밀리거나 건너뛰어진다
(깃헙 내부 디스패치 큐 과부하, 정각 집중). 유료 플랜에도 타이밍 SLA가 없고
self-hosted runner로도 해결되지 않는 구조적 문제다.

→ **신뢰성 있는 스케줄러를 가진 플랫폼으로 이전한다.**

## 목표

- 15분 주기 / 매일 1회 스케줄이 **밀리지 않고** 실행된다.
- 기존 Python + Playwright(Chromium) 코드를 **거의 그대로** 재사용한다(JS 암호화
  페이지 복호화에 실제 브라우저가 필요하므로 경량 함수 플랫폼은 불가).
- 실질 비용 **$0**(무료 한도 내), 청구 안전장치 포함.

## 제약 (고정)

- **실제 Chromium 브라우저 필요** — ev.or.kr 페이지는 `pnp4web` JS 암호화라
  브라우저가 페이지 JS를 실행해야 데이터가 보인다.
- **외부 네트워크 호출** — `ev.or.kr`, `api.telegram.org` (둘 다 구글 외부).
- **상태 영속화** — diff 감지와 전일 대비 계산을 위해 `seongnam.json` 상태를
  실행 간 보존해야 한다.

## 채택한 접근법: Google Cloud Run Jobs + Cloud Scheduler

Firebase(Spark)는 무료 플랜에서 구글 외부 네트워크 호출이 막혀 불가하고, Blaze로
올리면 Functions 2세대는 사실상 Cloud Run이다. Functions 런타임(특히 Python)에
Chromium을 번들링하는 것보다 컨테이너로 포장해 Cloud Run에 올리는 편이 깔끔하다.
스케줄러 엔진(Cloud Scheduler)은 Firebase 스케줄 함수와 동일하므로 신뢰성 손해는 없다.

### 아키텍처

```
Cloud Scheduler (cron 2개)
   ├─ */15 * * * *      → Cloud Run Job 실행 (args override: --mode change)
   └─ 0 23 * * * (UTC)  → 같은 Job 실행      (args override: --mode daily)
                  │
            Cloud Run Job  "ev-watch"  (Docker 이미지)
              · 베이스: mcr.microsoft.com/playwright/python (Chromium + OS deps 내장)
              · 엔트리: python check.py --mode <change|daily>
              · 스크랩: ev.or.kr (Chromium)
              · 상태:  GCS 버킷의 seongnam.json 읽기/쓰기
              · 시크릿: Secret Manager → 환경변수 주입
              · 알림:  Telegram sendMessage
```

- **Cloud Run Job 1개**에 실행 시 args override(`--mode change` / `--mode daily`)만
  바꿔 두 모드를 돌린다. 이미지/코드 단일 유지.
- **Cloud Scheduler 2개**가 Cloud Run Admin API(`run.googleapis.com .../jobs/JOB:run`)를
  OIDC 인증으로 호출해 Job 실행을 트리거한다.

## 컴포넌트 / 변경 사항

### 1. Dockerfile (신규)
- 베이스 이미지: `mcr.microsoft.com/playwright/python:<version>` — Chromium과
  OS 라이브러리가 내장되어 `playwright install` 단계가 불필요.
- `uv` 또는 `pip`로 의존성 설치(playwright, httpx, google-cloud-storage).
- 엔트리포인트: `python check.py`. args는 Cloud Run Job 실행 시 주입.

### 2. `ev_watch/state.py` (수정 — 분기 추가)
- 환경변수 `STATE_BUCKET`이 설정되면 GCS에서 `STATE_PATH`(객체 키) 읽기/쓰기.
- 미설정이면 기존 로컬 파일 동작 유지 → 기존 테스트가 그대로 통과.
- `load_state` / `save_state`의 인터페이스(시그니처, 반환 형태)는 불변. 저장 백엔드만
  내부에서 분기. 핵심 로직(`compute_change_hash`, `report_numbers`,
  `compute_deltas`)은 손대지 않는다.

### 3. deploy 스크립트 (신규, 예: `deploy/setup.sh`)
다음 `gcloud` 작업을 묶는다(idempotent 지향):
- 필요한 API 활성화: run, cloudscheduler, cloudbuild, secretmanager, storage,
  artifactregistry.
- GCS 버킷 생성(`gs://<project>-ev-watch-state`), 객체 키 `seongnam.json`.
- Secret Manager에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 등록.
- 이미지 빌드 & 푸시(Cloud Build → Artifact Registry).
- Cloud Run Job `ev-watch` 생성/갱신: 리전 `asia-northeast3`,
  시크릿을 환경변수로 매핑, `STATE_BUCKET` env 설정, 메모리/타임아웃 적정값.
- 전용 서비스 계정 + 최소 IAM(GCS 읽기/쓰기, Secret 접근, Job 실행).
- Cloud Scheduler 2개 생성: `*/15 * * * *`(--mode change),
  `0 23 * * *`(--mode daily). OIDC로 Job 실행 호출.

### 4. GitHub Actions
- `check-change.yml`, `daily-report.yml`의 `schedule` 트리거 제거.
- 수동 점검용으로 `workflow_dispatch`만 남길지 여부는 구현 시 결정(기본: 폐기).

### 5. README 갱신
- 새 아키텍처, 배포/재배포 방법, 사용자 1회 셋업 절차, 운영 중단 방법.

## 사용자 1회 셋업 (로그인/결제 필요 — 자동화 불가)

1. GCP 프로젝트 생성 + **결제 활성화**(카드 등록).
2. `gcloud` CLI 설치 후 `gcloud auth login`.
3. **예산 알림 $1** 설정(청구 안전장치, 콘솔).
4. 프로젝트 ID 공유 → 이후 deploy 스크립트 실행.

## 비용

실사용량 하루 ~96회 × ~30초. Cloud Run(요청·vCPU·메모리), Cloud Scheduler(무료 3개),
GCS(수 KB 객체), Secret Manager 모두 무료 한도를 크게 밑돈다 → 실질 $0~$1 미만/월.
예산 알림이 만일의 안전장치.

## 결정 사항 요약

- 리전: `asia-northeast3`(서울).
- Job 단일 + args override로 두 모드.
- 상태: GCS(`STATE_BUCKET` env로 분기, 로컬 폴백 유지).
- 시크릿: Secret Manager.
- 스케줄 신뢰성·diff·연속실패·startup 로직은 기존 그대로.

## 비목표 (YAGNI)

- GitHub Actions와의 이중 운영(혼란만 가중). 이전 후 schedule 폐기.
- 멀티 지역/멀티 차종 일반화. 성남시 단일 대상 유지.
- 별도 대시보드/웹 UI. Telegram 알림으로 충분.
