#!/bin/bash
# YouTube 자동화 cron 스케줄 설정
# 사용법: bash scheduler/setup_cron.sh

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PROJECT_DIR}/venv/bin/python3"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "$LOG_DIR"

# 기존 youtube_auto 관련 cron 제거
crontab -l 2>/dev/null | grep -v "youtube_auto" > /tmp/cron_clean

# 채널 1: 비소리 — 매주 월요일 자정 (목/금 확인 후 업로드)
echo "0 0 * * 1 cd ${PROJECT_DIR} && ${PYTHON} channel1_rain/run.py >> ${LOG_DIR}/cron_channel1.log 2>&1" >> /tmp/cron_clean

# 채널 2: 공룡 — 매주 화요일 자정 (목/금 확인 후 업로드)
echo "0 0 * * 2 cd ${PROJECT_DIR} && ${PYTHON} channel2_dino/run.py >> ${LOG_DIR}/cron_channel2.log 2>&1" >> /tmp/cron_clean

# 채널 3: 역사 — 매주 수요일 자정 (목/금 확인 후 업로드)
echo "0 0 * * 3 cd ${PROJECT_DIR} && ${PYTHON} channel3_history/run.py >> ${LOG_DIR}/cron_channel3.log 2>&1" >> /tmp/cron_clean

crontab /tmp/cron_clean
rm /tmp/cron_clean

echo "=== cron 등록 완료 ==="
crontab -l | grep youtube_auto
