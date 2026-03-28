# 스케줄 설정

## cron 등록
```bash
bash scheduler/setup_cron.sh
```

## 스케줄
| 채널 | 요일 | 시간 | cron |
|------|------|------|------|
| 채널1 비소리 | 수요일 | 자정 | `0 0 * * 3` |
| 채널2 공룡 | 금요일 | 자정 | `0 0 * * 5` |
| 채널3 역사 | 월요일 | 자정 | `0 0 * * 1` |

## 수동 실행
```bash
cd /path/to/youtube-automation
python3 channel1_rain/run.py
python3 channel2_dino/run.py
python3 channel3_history/run.py
```

## 테스트 (1분 영상)
```bash
VIDEO_DURATION=60 python3 channel1_rain/run.py
DINO_IMAGE_COUNT=5 python3 channel2_dino/run.py
```

## 로그 확인
```bash
ls -la logs/
tail -f logs/channel1_rain_*.log
```
