"""
전체 모듈 통합 테스트 스크립트
- Mac mini 배포 전 실행하여 모든 API/모듈 동작 확인
- FFmpeg 테스트는 Mac에서만 동작 (SKIP_FFMPEG=1로 건너뛰기 가능)
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SKIP_FFMPEG = os.environ.get("SKIP_FFMPEG", "0") == "1"
passed = []
failed = []


def test(name):
    """테스트 데코레이터"""
    def decorator(func):
        def wrapper():
            try:
                func()
                passed.append(name)
                print(f"  PASS  {name}")
            except Exception as e:
                failed.append(name)
                print(f"  FAIL  {name}: {e}")
        return wrapper
    return decorator


# === 1. Supabase ===
@test("supabase_connection")
def t1():
    from shared.supabase_client import get_client
    client = get_client()
    resp = client.table("api_keys").select("service").execute()
    assert len(resp.data) > 0, "api_keys empty"

@test("supabase_get_api_key")
def t2():
    from shared.supabase_client import get_api_key
    key = get_api_key("claude")
    assert key.startswith("sk-ant-"), f"unexpected key: {key[:10]}"

@test("supabase_dinosaur_topics")
def t3():
    from shared.supabase_client import get_unused_item
    item = get_unused_item("dinosaur_topics")
    assert item and "name" in item, "no unused dino"

@test("supabase_history_categories")
def t4():
    from shared.supabase_client import get_next_category
    cat = get_next_category()
    assert cat and "category" in cat, "no category"


# === 2. Claude API ===
@test("claude_title_description")
def t5():
    from shared.claude_api import generate_title_description
    meta = generate_title_description(
        'Test: JSON only. {"title": "test title", "description": "test desc"}'
    )
    assert "title" in meta and "description" in meta

@test("claude_generate_script")
def t6():
    from shared.claude_api import generate_script
    script = generate_script("Say hello in Korean, one sentence only.", max_tokens=64)
    assert len(script) > 0

@test("claude_generate_topic")
def t7():
    from shared.claude_api import generate_topic
    topic = generate_topic("Pick one Korean history topic. Reply topic name only.")
    assert len(topic.strip()) > 0


# === 3. Google TTS ===
@test("tts_short")
def t8():
    from shared.tts import synthesize_speech
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        synthesize_speech("TTS test.", tmp)
        assert os.path.getsize(tmp) > 0
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

@test("tts_chunked")
def t9():
    from shared.tts import synthesize_speech
    long_text = "This is a long text for chunked TTS. " * 200
    tmp = tempfile.mktemp(suffix=".mp3")
    try:
        synthesize_speech(long_text, tmp)
        assert os.path.getsize(tmp) > 1000
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# === 4. HuggingFace Image ===
@test("image_gen")
def t10():
    from shared.image_gen import generate_images
    tmp_dir = tempfile.mkdtemp(prefix="img_test_")
    try:
        paths = generate_images("a cute cat", tmp_dir, count=1)
        assert len(paths) == 1
        assert os.path.getsize(paths[0]) > 1000
    finally:
        shutil.rmtree(tmp_dir)


# === 5. file_utils ===
@test("file_utils_save")
def t11():
    from shared.file_utils import save_output, cleanup_temp
    tmp_dir = tempfile.mkdtemp(prefix="fu_test_")
    out_dir = os.path.join(tmp_dir, "out")
    dummy = os.path.join(tmp_dir, "v.mp4")
    with open(dummy, "wb") as f:
        f.write(b"fake")
    result = save_output(dummy, "title", "desc", out_dir)
    assert os.path.exists(result["video"])
    assert os.path.exists(result["txt"])
    cleanup_temp(tmp_dir)
    assert not os.path.exists(tmp_dir)


# === 6. FFmpeg (Mac only) ===
@test("ffmpeg_loop_video")
def t12():
    if SKIP_FFMPEG:
        print("    (skipped)")
        return
    from shared.ffmpeg_utils import loop_video, capture_thumbnail
    # 짧은 테스트용 영상이 있어야 함
    from shared.supabase_client import get_client
    client = get_client()
    resp = client.table("generated_files").select("file_path").eq("file_type", "rain_video").limit(1).execute()
    if not resp.data:
        print("    (no test video, skipped)")
        return
    src = resp.data[0]["file_path"]
    if not os.path.exists(src):
        print(f"    (file not found: {src}, skipped)")
        return
    tmp_dir = tempfile.mkdtemp(prefix="ff_test_")
    try:
        out = os.path.join(tmp_dir, "loop.mp4")
        loop_video(src, out, duration=5)
        assert os.path.getsize(out) > 0
        thumb = os.path.join(tmp_dir, "thumb.jpg")
        capture_thumbnail(out, thumb)
        assert os.path.getsize(thumb) > 0
    finally:
        shutil.rmtree(tmp_dir)


# === Run all ===
if __name__ == "__main__":
    print("=" * 50)
    print("YouTube Auto - Integration Test")
    print("=" * 50)

    for func in [t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12]:
        func()

    print("\n" + "=" * 50)
    print(f"PASSED: {len(passed)}/{len(passed)+len(failed)}")
    if failed:
        print(f"FAILED: {failed}")
        sys.exit(1)
    else:
        print("All tests passed!")
