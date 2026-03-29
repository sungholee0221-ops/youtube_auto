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

### Git clone
```bash
cd ~
git clone <레포 주소> youtube_auto
cd youtube_auto
```

### 가상환경 생성 및 패키지 설치
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 3. 환경 설정 (.env)

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 항목 채우기:

| 항목 | 설명 | 비고 |
|------|------|------|
| `SUPABASE_URL` | Supabase 프로젝트 URL | 기존 값 그대로 |
| `SUPABASE_KEY` | Supabase anon key | 기존 값 그대로 |
| `ANTHROPIC_API_KEY` | Claude API 키 | Anthropic Console |
| `GOOGLE_TTS_API_KEY` | Google TTS API 키 | Google Cloud Console |
| `HF_API_TOKEN` | HuggingFace 토큰 | huggingface.co/settings/tokens |
| `PEXELS_API_KEY` | Pexels API 키 | pexels.com/api |
| `FFMPEG_PATH` | FFmpeg 경로 | `which ffmpeg` 결과 |
| `OUTPUT_DIR_RAIN` | 비소리 출력 경로 | 예: `/Users/xxx/youtube_auto/b4_upload` |
| `OUTPUT_DIR_DINO` | 공룡 출력 경로 | 위와 동일 |
| `OUTPUT_DIR_HISTORY` | 역사 출력 경로 | 위와 동일 |

---

## 4. 채널 소스 파일 등록 (비소리 채널만)

### channel1_source 폴더에 파일 복사
```
channel1_source/
  pexels-rain-forest-01.mp4   ← 비 내리는 영상 (Pexels)
  pexels-rain-window-02.mp4
  freesound-rain-heavy-01.mp3 ← 빗소리 오디오 (Freesound)
  freesound-rain-light-02.mp3
  ...
```

### Supabase에 등록
```bash
source venv/bin/activate
python3 scripts/register_rain_videos.py        # 등록
python3 scripts/register_rain_videos.py --list # 목록 확인
```

---

## 5. 동작 테스트

각 채널을 이미지 수를 줄여서 빠르게 테스트:

```bash
source venv/bin/activate

# 채널 1 - 비소리
python3 channel1_rain/run.py

# 채널 2 - 공룡 (테스트용 6장)
DINO_IMAGE_COUNT=6 python3 channel2_dino/run.py

# 채널 3 - 역사 (테스트용 6장)
HISTORY_IMAGE_COUNT=6 python3 channel3_history/run.py
```

생성 파일 확인: `b4_upload/` 폴더

---

## 6. 크론 스케줄 등록

```bash
bash scheduler/setup_cron.sh
```

등록 확인:
```bash
crontab -l
```

| 채널 | 실행 시간 |
|------|---------|
| 비소리 | 매주 월요일 자정 |
| 공룡   | 매주 화요일 자정 |
| 역사   | 매주 수요일 자정 |

> ⚠️ Mac이 잠들어 있으면 실행 안 됨.
> 시스템 설정 → 배터리 → 전원 어댑터 연결 시 절전 방지 권장.

---

## 7. 주간 업로드 워크플로우

```
월 자정  →  비소리 영상 자동 생성
화 자정  →  공룡 영상 자동 생성
수 자정  →  역사 영상 자동 생성
목/금    →  b4_upload/ 확인 → YouTube 업로드 → 파일 삭제
```

### 업로드 시 체크리스트 (txt 파일에 포함됨)
- 제목, 설명, 태그 → txt 파일에서 복사
- ⚠️ **세부정보 → 연령제한(고급) → 변경된 콘텐츠 → YES** 반드시 체크

---

## 8. 로그 확인

```bash
# 크론 실행 로그
tail -f logs/cron_channel1.log
tail -f logs/cron_channel2.log
tail -f logs/cron_channel3.log
```

---

## 9. 채널별 영상 구조

| 채널 | 영상 구조 | 길이 |
|------|---------|------|
| 비소리 | 15분 Pexels 영상 + 검은화면 + 빗소리 루프 | 3시간 |
| 공룡   | AI 이미지 + 실사 사진 슬라이드쇼 + TTS 나레이션 | ~10분 |
| 역사   | 3분 슬라이드쇼 + 검은화면 + TTS 나레이션 | ~20분 |

---

## 10. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `HF_API_TOKEN` 오류 | HuggingFace 토큰 만료 | huggingface.co에서 재발급 |
| 이미지 생성 실패 | HF API 한도 초과 | 자동으로 Pexels only 전환됨 |
| TTS 실패 | Google API 키 문제 | Supabase api_keys 테이블 확인 |
| FFmpeg 오류 | 경로 불일치 | `.env`의 `FFMPEG_PATH` 수정 |
| 썸네일 한글 깨짐 | 나눔 폰트 미설치 | `brew install --cask nanum-font` |
| 크론 미실행 | Mac 절전 | 절전 방지 설정 또는 수동 실행 |
