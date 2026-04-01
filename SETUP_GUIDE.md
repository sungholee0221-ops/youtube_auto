# YouTube 자동화 시스템 — 서버 맥북 설치 가이드

---

## 1. 사전 준비 (한 번만)

### Homebrew 설치
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Python 3.11+ 및 FFmpeg 설치
```bash
brew install python ffmpeg
```

### FFmpeg 경로 확인
```bash
which ffmpeg
# 보통 /usr/local/bin/ffmpeg 또는 /opt/homebrew/bin/ffmpeg
```

### 한글 폰트 설치 (썸네일용)
```bash
brew install --cask nanum-font
```

---

## 2. 프로젝트 설치

```bash
cd ~
git clone <레포 주소> youtube_auto
cd youtube_auto
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. 환경 설정 (.env)

```bash
cp .env.example .env   # 없으면 .env 직접 생성
```

| 항목 | 설명 |
|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_KEY` | Supabase anon key |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `GOOGLE_TTS_API_KEY` | Google TTS API 키 |
| `FFMPEG_PATH` | FFmpeg 경로 (`which ffmpeg` 결과) |
| `OUTPUT_DIR_RAIN` | 출력 경로 (예: `/Users/xxx/youtube_auto/b4_upload`) |
| `OUTPUT_DIR_DINO` | 위와 동일 |
| `OUTPUT_DIR_HISTORY` | 위와 동일 |

---

## 4. 소스 파일 배치

### 채널1 (비소리) — channel1_source/
```
channel1_source/
  pexels-rain-forest-01.mp4      ← 빗소리 영상 (Pexels)
  freesound-rain-heavy-01.mp3    ← 빗소리 오디오 (Freesound)
  ...
```

Supabase 등록:
```bash
source venv/bin/activate
python3 scripts/register_rain_videos.py        # 등록
python3 scripts/register_rain_videos.py --list # 목록 확인
```

### 채널2 (공룡) — channel2_source/
```
channel2_source/
  dino_opening.mp4               ← 오프닝 영상+음성 (~5초)
  52weeks_dinosaurs.csv          ← 52주 주제 목록
  w01_dino_source/
    week01_tyrannosaurus-rex.json   ← 스크립트 (씬별 narration_kr, duration_sec)
    week01_S01_Tyrannosaurus.png
    week01_S02_Tyrannosaurus.png
    ...
  w02_dino_source/
    ...
```

### 채널3 (역사) — channel3_source/
```
channel3_source/
  history_opening.mp4            ← 오프닝 영상+음성 (~5초)
  52weeks_history.csv            ← 52주 주제 목록
  w01_his_source/
    week01_Dawn of Civilization.json  ← 스크립트 (씬별 narration_kr)
    Week01_S01_Dawn of the First Cities.png
    ...
  w02_his_source/
    ...
```

> **⚠️ 미디어 파일(mp4, png, mp3)은 git 제외** → Google Drive로 각 머신에 복사

---

## 5. Supabase 설정 (한 번만)

### 5-1. weekly_schedule 테이블 생성 (SQL Editor에서 실행)
```sql
CREATE TABLE IF NOT EXISTS weekly_schedule (
    id          SERIAL PRIMARY KEY,
    channel     TEXT    NOT NULL,
    week_num    INTEGER NOT NULL,
    folder_name TEXT    NOT NULL,
    title_kr    TEXT,
    is_used     BOOLEAN DEFAULT FALSE,
    UNIQUE(channel, week_num)
);
```

### 5-2. 주차 데이터 등록 (터미널에서 실행)
소스 폴더가 실제로 존재하는 주차만 자동 등록됨:
```bash
source venv/bin/activate
python3 scripts/setup_weekly_schedule.py        # 등록
python3 scripts/setup_weekly_schedule.py --list # 목록 확인
```

새 주차 소스 폴더 추가 후 재실행하면 신규 주차만 추가 등록됨.

---

## 6. 동작 테스트

```bash
source venv/bin/activate

# 채널1 — 비소리
python3 channel1_rain/run.py

# 채널2 — 공룡
python3 channel2_dino/run.py

# 채널3 — 역사
python3 channel3_history/run.py
```

생성 파일 확인: `b4_upload/` 폴더

---

## 7. 크론 스케줄 등록

```bash
bash scheduler/setup_cron.sh
crontab -l   # 등록 확인
```

| 채널 | 실행 시간 |
|------|---------|
| 비소리 | 매주 월요일 자정 |
| 공룡   | 매주 화요일 자정 |
| 역사   | 매주 수요일 자정 |

> ⚠️ Mac이 잠들어 있으면 실행 안 됨 — 시스템 설정 → 배터리 → 전원 어댑터 연결 시 절전 방지 권장

---

## 8. 주간 업로드 워크플로우

```
월 자정  →  비소리 영상 자동 생성
화 자정  →  공룡 영상 자동 생성
수 자정  →  역사 영상 자동 생성
목/금    →  b4_upload/ 확인 → YouTube 업로드 → 파일 삭제
```

### 업로드 시 체크리스트 (txt 파일에 포함됨)
- 제목, 설명, 태그 → txt 파일에서 복사
- ⚠️ **세부정보 → 연령제한(고Advanced) → 변경된 콘텐츠 → YES** 반드시 체크

---

## 9. 채널별 영상 구조

| 채널 | 영상 구조 | 총 길이 |
|------|---------|--------|
| 비소리 | 15분 Pexels 영상 + 검은화면 + 빗소리 루프 | 3시간 |
| 공룡   | 오프닝(5초) + 이미지 슬라이드쇼 + TTS 나레이션 | ~10분 |
| 역사   | 오프닝(5초) + 슬라이드쇼 15분(페이드아웃) + 검은화면 50분 + TTS 나레이션 | ~65분 |

### 채널2 (공룡) 스크립트 작성 기준
- JSON 씬별 `duration_sec` 필수 — TTS 읽기 시간과 씬 표시 시간이 이 값으로 싱크됨
- 권장 분량: **1300~1500자** (TTS 약 10분)
- TTS가 씬 합계보다 길면 마지막 씬 자동 연장

### 채널3 (역사) 스크립트 작성 기준
- JSON 씬별 `duration_sec` 불필요 — 글자수 비율로 자동 배분
- 권장 분량: **2200~2500자** (TTS 약 15분)
- TTS 끝나면 나머지 50분은 검은화면 + 무음 (수면유도)

---

## 10. 소스 추가 워크플로우

매주 소스 파일(JSON + 이미지) 추가 시:
```
1. channel2_source/w02_dino_source/ 폴더 생성 후 JSON + PNG 복사
2. python3 scripts/setup_weekly_schedule.py   # 새 주차 자동 등록
3. 다음 화요일 자동 실행 또는 수동: python3 channel2_dino/run.py
```

---

## 11. 로그 확인

```bash
tail -f logs/cron_channel1.log
tail -f logs/cron_channel2.log
tail -f logs/cron_channel3.log
```

---

## 12. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: supabase` | venv 미활성화 | `source venv/bin/activate` |
| `사용 가능한 주차가 없습니다` | weekly_schedule 테이블 미등록 | `python3 scripts/setup_weekly_schedule.py` |
| JSON 파싱 오류 | 마크다운 코드블록 or Perplexity 링크 | `load_source_json()` 자동 전처리 — 로그 확인 |
| TTS 실패 | Google API 키 문제 | Supabase api_keys 테이블 확인 |
| 씬 싱크 불일치 (채널2) | JSON `duration_sec` 누락 | 각 씬에 `"duration_sec": 20` 형식으로 추가 |
| FFmpeg 오류 | 경로 불일치 | `.env`의 `FFMPEG_PATH` 수정 |
| 썸네일 한글 깨짐 | 나눔 폰트 미설치 | `brew install --cask nanum-font` |
| 크론 미실행 | Mac 절전 | 절전 방지 설정 또는 수동 실행 |
