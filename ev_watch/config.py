# ev_watch/config.py
from zoneinfo import ZoneInfo

URL = "https://ev.or.kr/nportal/buySupprt/initSubsidyPaymentCheckAction.do"
GYEONGGI_CODE = "4100"   # 경기도
SEONGNAM_CODE = "4113"   # 성남시
KST = ZoneInfo("Asia/Seoul")
STATE_PATH = "state/seongnam.json"
CONSECUTIVE_FAILURE_THRESHOLD = 3
# 숫자 셀 분해 순서 (표 헤더 기준): 전체 / (우선순위) / (법인·기관) / (택시) / (일반)
NUMBER_KEYS = ["전체", "우선순위", "법인기관", "택시", "일반"]
