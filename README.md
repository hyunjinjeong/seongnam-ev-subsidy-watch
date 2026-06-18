# seongnam-ev-subsidy-watch

성남시 전기차 보조금 공고를 감시해 텔레그램으로 알림. (변화 감지 15분 / 일일 보고서 08:00 KST)

## 텔레그램 셋업 (처음 쓰는 경우)

1. 텔레그램 앱 설치·가입.
2. `@BotFather` → `/newbot` → 봇 이름·username 입력 → **봇 토큰** 발급.
3. 발급된 `t.me/<봇>` 링크 열어 **`/start`** 한 번 누르기.
4. chat_id 확인:
   ```bash
   TELEGRAM_BOT_TOKEN=<토큰> uv run python check.py --get-chat-id
   ```
5. 테스트 전송(휴대폰 수신 확인):
   ```bash
   TELEGRAM_BOT_TOKEN=<토큰> TELEGRAM_CHAT_ID=<챗ID> uv run python check.py --test-telegram
   ```
6. GitHub 레포 `Settings → Secrets and variables → Actions`에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 등록.

## 로컬 실행

```bash
uv sync
uv run playwright install chromium
uv run python check.py --mode change --dry-run   # 전송 없이 현황 출력
```

## 동작

- `check-change.yml`: 15분마다 성남시 `비고+공고파일` 변화 시 알림.
- `daily-report.yml`: 매일 08:00 KST 현황(잔여대수+전일대비) 보고서. `workflow_dispatch`로 즉시 실행해 검증 가능.
- 상태는 `state/seongnam.json`에 커밋되어 유지.
