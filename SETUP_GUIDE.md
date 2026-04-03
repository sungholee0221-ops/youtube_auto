# YouTube 자동화 시스템 — 설치 및 운영 가이드

---

## 1. 사전 준비 (한 번만)

```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.11+ 및 FFmpeg
brew install python ffmpeg

# 한글 폰트 (썸네일용)
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

| 항목 | 설명 |
|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_KEY` | Supabase anon key |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `FFMPEG_PATH` | FFmpeg 경로 (`which ffmpeg` 결과) |
| `OUTPUT_DIR_RAIN` | 출력 경로 (예: `/Users/xxx/youtube_auto/b4_upload`) |
| `OUTPUT_DIR_DINO` | 위와 동일 |
| `OUTPUT_DIR_HISTORY` | 위와 동일 |

> Google TTS API 키는 Supabase `api_keys` 테이블에서 관리 (`.env` 아님)

---

## 4. 소스 파일 구조

### 채널1 (비소리) — channel1_source/

```
channel1_source/
  rain_video/
    pexelsource1_hd_1920_1080_30fps.mp4    ← 무음 영상 (Pexels)
    pexelsource2_hd_1920_1080_60fps.mp4
    pexelsource3_1920_1080_30fps.mp4
    Firefly source1.mp4                    ← 오디오 내장 영상 (Adobe Firefly)
    Fireflysource2.mp4                     ← 오디오 내장 영상
    Fireflysource3.mp4                     ← 무음 영상
  rain_audio/
    source1__bbrownmuse__rain-ambience.mp3          ← 빗소리 MP3 (무음 영상 전용)
    source2__sagamusix__rain-and-thunder-ambience.mp3
    source3__joncon_library__rain-ambience.mp3
```

**오디오 처리 방식:**
- 무음 영상 → `rain_audio` MP3 루프 (영상/오디오 독립 순환)
- 오디오 내장 영상 → 내장 오디오 추출 후 3시간 루프 (`rain_audio` 불필요)
- 영상/오디오 모두 소진 시 자동 리셋 후 재순환

Supabase 등록 (최초 1회 또는 파일 변경 시):
```bash
source venv/bin/activate
python3 -c "
from shared.supabase_client import get_client
sb = get_client()
# generated_files 테이블에 file_type='rain_video' 또는 'rain_audio'로 INSERT
# 자세한 내용은 Supabase 설정 섹션 참고
"
```

### 채널2 (공룡) — channel2_source/

```
channel2_source/
  dino_opening.mp4               ← 오프닝 영상+음성 (~5초)
  52weeks_dinosaurs.csv          ← 52주 주제 목록
  w01_dino_source/
    week01_tyrannosaurus-rex.json   ← 스크립트 JSON
    Week01_S01_Tyrannosaurus.png    ← 씬별 이미지 (씬 수만큼)
    Week01_S02_Tyrannosaurus.png
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
    week01_Dawn of Civilization.json   ← 스크립트 JSON
    Week01_S01_Dawn of the First Cities.png
    Week01_S02_Dawn of the First Cities.png
    ...
  w02_his_source/
    ...
```

> **미디어 파일(mp4, png, mp3)은 git 제외** → 각 머신에 직접 복사

---

## 5. Supabase 테이블 설정 (한 번만)

### 5-1. weekly_schedule (채널2·3 주차 관리)

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

주차 데이터 등록:
```bash
source venv/bin/activate
python3 scripts/setup_weekly_schedule.py        # 등록 (소스 폴더 존재 주차만)
python3 scripts/setup_weekly_schedule.py --list # 목록 확인
```

새 주차 소스 폴더 추가 후 재실행하면 신규 주차만 추가 등록됨.

### 5-2. generated_files (채널1 소스 파일 관리)

```sql
CREATE TABLE IF NOT EXISTS generated_files (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_type   TEXT NOT NULL,   -- 'rain_video' | 'rain_audio'
    file_path   TEXT NOT NULL,
    is_used     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

### 5-3. api_keys (Google TTS 키 관리)

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id      SERIAL PRIMARY KEY,
    service TEXT NOT NULL,
    api_key TEXT NOT NULL
);
-- 데이터 삽입
INSERT INTO api_keys (service, api_key) VALUES ('google-tts', 'YOUR_KEY');
```

---

## 6. 스크립트 JSON 작성 기준

### 채널2 (공룡) — 목표 10분

```json
{
  "topic": "티라노사우루스 렉스",
  "scenes": [
    {
      "scene_num": 1,
      "title": "씬 제목",
      "narration_kr": "한국어 나레이션 텍스트..."
    }
  ]
}
```

- `duration_sec` 불필요 — TTS 실측값으로 자동 계산
- **권장 분량: 씬당 300~400자, 총 6~8씬** (전체 ~2,000자)
- 씬 이미지는 씬 수만큼 준비 (부족 시 마지막 이미지 반복)

### 채널3 (역사) — 목표 15분 슬라이드쇼

```json
{
  "topic": "문명의 새벽",
  "scenes": [
    {
      "scene_num": 1,
      "narration_kr": "한국어 나레이션 텍스트..."
    }
  ]
}
```

- **권장 분량: 씬당 300~400자, 총 10씬** (전체 ~3,500자)
- 씬 이미지는 씬 수만큼 준비 (10장 권장)
- TTS 합계가 15분 미달 시 마지막 씬 이미지 자동 연장

---

## 7. 채널별 영상 구조

| 채널 | 영상 구조 | 총 길이 |
|------|---------|--------|
| 채널1 비소리 | 15분 영상 루프(페이드아웃) + 검은화면 + 오디오 루프 | 3시간 |
| 채널2 공룡 | 오프닝(5초, 페이드전환 2초) + 슬라이드쇼 + 검은화면 | ~10분 |
| 채널3 역사 | 오프닝(5초, 페이드전환 2초) + 슬라이드쇼 15분(페이드아웃 3초) + 검은화면 50분 | ~65분 |

### 채널2·3 공통 오디오 규칙

| 항목 | 값 |
|------|-----|
| 씬 사이 무음 | 3초 |
| 문장 끝 pause (SSML) | 1초 (`.` `!` `?` 뒤) |
| 씬 시작 전 여유 | 1초 (오프닝 직후 첫 씬) |
| 오프닝→슬라이드쇼 전환 | 페이드아웃 2초 + 페이드인 2초 |

---

## 8. 크론 스케줄

```bash
bash scheduler/setup_cron.sh   # 등록
crontab -l                     # 확인
```

| 채널 | 실행 |
|------|------|
| 채널1 비소리 | 매주 **월요일** 자정 |
| 채널2 공룡   | 매주 **화요일** 자정 |
| 채널3 역사   | 매주 **수요일** 자정 |

> Mac이 잠들어 있으면 실행 안 됨 — 시스템 설정 → 배터리 → 전원 어댑터 연결 시 절전 방지 권장

---

## 9. 주간 워크플로우

```
월 자정  →  채널1 비소리 영상 자동 생성
화 자정  →  채널2 공룡 영상 자동 생성
수 자정  →  채널3 역사 영상 자동 생성
목/금    →  b4_upload/ 확인 → YouTube 업로드 → 파일 삭제
```

**주차 소스 추가 루틴 (매주):**
```
1. channel2_source/wXX_dino_source/ 폴더에 JSON + PNG 저장
2. channel3_source/wXX_his_source/ 폴더에 JSON + PNG 저장
3. python3 scripts/setup_weekly_schedule.py   # 신규 주차 자동 등록
4. git add & push
```

**업로드 체크리스트:**
- 제목, 설명, 태그 → `.txt` 파일에서 복사
- 세부정보 → 고급 → 변경된 콘텐츠(AI 생성) → **YES** 체크

---

## 10. 수동 실행

```bash
source venv/bin/activate

python3 channel1_rain/run.py
python3 channel2_dino/run.py
python3 channel3_history/run.py
```

**is_used 리셋 (재실행 시):**
```bash
python3 -c "
from shared.supabase_client import get_client
sb = get_client()
# 채널2 1주차 리셋
sb.table('weekly_schedule').update({'is_used': False}).eq('channel', 'dino').eq('week_num', 1).execute()
# 채널3 1주차 리셋
sb.table('weekly_schedule').update({'is_used': False}).eq('channel', 'history').eq('week_num', 1).execute()
"
```

---

## 11. 로그 확인

```bash
tail -f logs/cron_channel1.log
tail -f logs/cron_channel2.log
tail -f logs/cron_channel3.log

# 날짜별 상세 로그
tail -f logs/channel1_rain_YYYYMMDD.log
tail -f logs/channel2_dino_YYYYMMDD.log
tail -f logs/channel3_history_YYYYMMDD.log
```

---

## 12. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: supabase` | venv 미활성화 | `source venv/bin/activate` |
| `사용 가능한 주차가 없습니다` | weekly_schedule 미등록 또는 전부 is_used | `setup_weekly_schedule.py` 실행 또는 is_used 리셋 |
| JSON 파싱 오류 | 마크다운 코드블록 또는 Perplexity 링크 포함 | `load_source_json()` 자동 전처리 — 그래도 실패 시 JSON 수동 확인 |
| TTS 실패 | Google API 키 문제 | Supabase `api_keys` 테이블 확인 |
| 씬 이미지 싱크 불일치 | 이전 시스템 잔재 (`duration_sec` 기반) | 현재 시스템은 TTS 실측값 자동 적용 — 무시 가능 |
| FFmpeg 오류 | 경로 불일치 | `.env`의 `FFMPEG_PATH` 수정 |
| 썸네일 한글 깨짐 | 나눔 폰트 미설치 | `brew install --cask nanum-font` |
| 크론 미실행 | Mac 절전 | 절전 방지 설정 또는 수동 실행 |
| 마지막 씬 이미지 오래 표시 | 스크립트 분량 부족 | 채널2: ~2,000자 / 채널3: ~3,500자 맞추기 |
