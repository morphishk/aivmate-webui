import asyncio
import glob
import hashlib
import logging
import os
import re
import shutil
import threading
import time
print("正在加载语音合成模块...")
import edge_tts
import sherpa_onnx
import pygame as pg
import requests as rq
import soundfile as sf
print("正在加载大模型模块...")
from openai import OpenAI
from web_settings import (
    get_config_value, get_config, get_prefer_tts,
    prefer_tts, qwentts_api, qwentts_model, qwentts_voice,
    edge_speaker, edge_rate, edge_pitch,
    stream_tts_switch, gsv_api, gsv_prompt, gsv_ref_audio_path,
    gsv_prompt_lang, gsv_lang, cosy_api, voxcpm_api, index_api,
    custom_tts_url, custom_tts_model, custom_tts_voice, custom_tts_key,
    tts_cache_clean_interval_days, tts_cache_session_soft_limit,
    vits_model_name,
)

#vits_target_dir = "E:/model/TTS"
vits_target_dir = "data/model/TTS"
vits_model_dir = f"{vits_target_dir}/{vits_model_name}"
vits_tts = None
try:
    vits_model_path = glob.glob(os.path.join(vits_model_dir, "*.onnx"))[0]
    vits_tokens_path = f"{vits_model_dir}/tokens.txt"
    vits_data_dir = f"{vits_model_dir}/espeak-ng-data"
    vits_tts_config = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(
            model=vits_model_path, tokens=vits_tokens_path, data_dir=vits_data_dir), provider="cpu",
        num_threads=os.cpu_count()))
except Exception as e1:
    print(f"VITS模型加载错误，详情：{e1}")

# 音频缓存目录改为静态资源目录，方便浏览器直接访问
voice_cache_dir = 'dist/assets/cache_voice'
os.makedirs(voice_cache_dir, exist_ok=True)

# 保留旧路径变量兼容
voice_path = 'data/cache/cache_voice'
play_tts_flag = 0
tts_playing = False

# ===== 缓存清理配置 =====
# 从 web_settings 读取用户配置（修改后需重启生效）
CACHE_MAX_AGE_HOURS = 24      # 默认：24小时
CACHE_MAX_FILES = 100         # 根目录旧文件保留数量（按会话隔离后仅用于根目录无主文件）
CACHE_CLEAN_INTERVAL = tts_cache_clean_interval_days * 24 * 3600  # 用户配置：天 → 秒
CACHE_SESSION_SOFT_LIMIT = tts_cache_session_soft_limit  # 用户配置：单会话音频软上限

# 播放中文件保护集合（由前端 /api/audio_status 上报维护）
_playing_files: set[str] = set()


def set_tts_playing(playing):
    global tts_playing
    tts_playing = bool(playing)


# ===== 流式 TTS：后台异步生成 + 前端轮询（P2 Day 3 优化） =====
_tts_batches = {}
_tts_batches_lock = threading.Lock()

# 文本哈希 -> batch_id 映射（访问需持有 _tts_batches_lock）
_tts_hash_batches: dict[str, str] = {}


def _normalize_text(text: str) -> str:
    """规范化文本以提高缓存命中率

    处理步骤：
    1. 去除首尾空白字符
    2. 统一换行符为 \n
    3. 合并连续空白为一个空格
    """
    text = text.strip()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text)
    return text


def _get_text_hash(text: str) -> str:
    """计算文本的 SHA256 哈希（取前 16 位）

    Args:
        text: 规范化后的文本

    Returns:
        str: 16 位十六进制哈希字符串
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _cleanup_old_batches(max_age_sec: int = 300, completed_max_age_sec: int = 60):
    """清理超过 max_age_sec 的旧 batch，防止内存泄漏。
    对于已完成的 batch，使用更短的 completed_max_age_sec（默认 60 秒）快速清理。
    注意：调用者必须已持有 _tts_batches_lock。"""
    now = time.time()
    expired = []
    for bid, b in _tts_batches.items():
        if b.get("done") and b.get("completed_at"):
            if now - b["completed_at"] > completed_max_age_sec:
                expired.append(bid)
        elif now - b.get("created_at", 0) > max_age_sec:
            expired.append(bid)
    for bid in expired:
        del _tts_batches[bid]


def _generate_remaining_async(batch_id: str, segments: list, engine, start_idx: int):
    """后台线程：继续生成剩余段的 TTS 音频。
    支持被取消：每段生成前检查 _tts_batches[batch_id]['cancelled']。"""
    print(f"[TTS Streaming] _generate_remaining_async START batch={batch_id} start_idx={start_idx} total_segments={len(segments)}")
    for i, seg in enumerate(segments):
        print(f"[TTS Streaming] segment[{i}]: {repr(seg[:50])}")
    for idx in range(start_idx, len(segments)):
        # 检查是否被取消
        with _tts_batches_lock:
            batch = _tts_batches.get(batch_id)
        if not batch or batch.get("cancelled"):
            print(f"[TTS Streaming] batch {batch_id} 已被取消，停止后台生成")
            return
        if not segments[idx].strip():
            print(f"[TTS Streaming] segment[{idx}] is empty, skip")
            continue
        local_path = get_cache_voice_path(segment_index=idx)
        print(f"[TTS Streaming] generating segment[{idx}]: {repr(segments[idx][:50])} -> {local_path}")
        try:
            generate_tts_segment(segments[idx], engine=engine, output_path=local_path)
            print(f"[TTS Streaming] segment[{idx}] generated OK")
            with _tts_batches_lock:
                if batch_id in _tts_batches:
                    _tts_batches[batch_id]["urls"].append({
                        "local_path": local_path,
                        "url": get_tts_url(local_path)
                    })
                    print(f"[TTS Streaming] segment[{idx}] appended to batch, total urls={len(_tts_batches[batch_id]['urls'])}")
        except Exception as e:
            print(f"[TTS Streaming] 后台生成失败（段 {idx}/{len(segments)}）: {e}")
    with _tts_batches_lock:
        if batch_id in _tts_batches:
            _tts_batches[batch_id]["done"] = True
            _tts_batches[batch_id]["completed_at"] = time.time()
            print(f"[TTS Streaming] batch {batch_id} marked done, final urls={len(_tts_batches[batch_id]['urls'])}")


def _generate_remaining_async_cached(batch_id: str, text_hash: str, segments: list, engine, start_idx: int, session_id: str = ""):
    """后台线程：继续生成剩余段的 TTS 音频（使用哈希缓存文件名 + Session 隔离）。"""
    print(f"[TTS Streaming] _generate_remaining_async_cached START batch={batch_id} text_hash={text_hash} session_id={session_id} start_idx={start_idx} total_segments={len(segments)}")
    for idx in range(start_idx, len(segments)):
        with _tts_batches_lock:
            batch = _tts_batches.get(batch_id)
        if not batch or batch.get("cancelled"):
            print(f"[TTS Streaming] batch {batch_id} 已被取消，停止后台生成")
            return
        if not segments[idx].strip():
            print(f"[TTS Streaming] segment[{idx}] is empty, skip")
            continue
        # 使用哈希文件名 + Session 隔离
        local_path = get_cache_voice_path(text=segments[idx], segment_index=idx, session_id=session_id)
        print(f"[TTS Streaming] generating segment[{idx}]: {repr(segments[idx][:50])} -> {local_path}")
        try:
            generate_tts_segment(segments[idx], engine=engine, output_path=local_path)
            print(f"[TTS Streaming] segment[{idx}] generated OK")
            with _tts_batches_lock:
                if batch_id in _tts_batches:
                    _tts_batches[batch_id]["urls"].append({
                        "local_path": local_path,
                        "url": get_tts_url(local_path)
                    })
                    print(f"[TTS Streaming] segment[{idx}] appended to batch, total urls={len(_tts_batches[batch_id]['urls'])}")
        except Exception as e:
            print(f"[TTS Streaming] 后台生成失败（段 {idx}/{len(segments)}）: {e}")
    with _tts_batches_lock:
        if batch_id in _tts_batches:
            _tts_batches[batch_id]["done"] = True
            _tts_batches[batch_id]["completed_at"] = time.time()
            print(f"[TTS Streaming] batch {batch_id} marked done, final urls={len(_tts_batches[batch_id]['urls'])}")


def generate_tts_streaming(text: str, engine=None, session_id: str = "") -> dict:
    """
    流式 TTS：立即生成第 1 段并返回，剩余段后台异步生成。
    支持文本哈希缓存：同文本第二次请求直接返回已有缓存（按 Session 隔离）。

    Args:
        text: 要合成的文本
        engine: TTS 引擎
        session_id: 会话 ID（可选，非空时音频存到 cache_voice/{session_id}/）

    Returns:
        {
            "first_url": str,      # 第 1 段可直接播放的 URL
            "batch_id": str,       # 轮询批次 ID
            "total": int,          # 总段数
            "audio_urls": [str],   # 当前已生成的全部 URL（兼容旧前端）
            "cached": bool,        # 是否命中缓存
        }
    """
    processed_text = text.split("</think>")[-1].strip()
    processed_text = re.sub(r'[(（].*?[)）]', '', processed_text)

    cfg = get_config()
    if cfg.get("stream_tts_switch", stream_tts_switch) == "on":
        segments = split_text(processed_text)
        if not segments:
            segments = [processed_text]
    else:
        segments = [processed_text]

    total = len(segments)

    # --- Session 隔离的缓存键 ---
    normalized = _normalize_text(processed_text)
    text_hash = _get_text_hash(normalized)
    cache_key = f"{session_id}:{text_hash}" if session_id else text_hash

    with _tts_batches_lock:
        # 检查内存缓存：是否已有 batch 在生成或已完成
        cached_batch_id = _tts_hash_batches.get(cache_key)
        if cached_batch_id:
            # batch 存在，返回已有 batch_id，前端轮询进度
            batch = _tts_batches.get(cached_batch_id)
            if batch:
                urls = [u["url"] for u in batch.get("urls", [])]
                return {
                    "first_url": urls[0] if urls else "",
                    "batch_id": cached_batch_id,
                    "total": batch.get("total", total),
                    "audio_urls": urls,
                    "cached": True,
                }

    # 检查磁盘缓存：是否已有完整分段文件（按 Session 隔离）
    cached_paths = _find_cached_audio(text_hash, session_id=session_id)
    if cached_paths:
        urls = [get_tts_url(p) for p in cached_paths]
        batch_id = f"cached_{text_hash}"
        with _tts_batches_lock:
            _tts_hash_batches[cache_key] = batch_id
            _tts_batches[batch_id] = {
                "urls": [{"local_path": p, "url": u} for p, u in zip(cached_paths, urls)],
                "done": True,
                "total": len(urls),
                "created_at": time.time(),
                "completed_at": time.time(),
            }
        return {
            "first_url": urls[0] if urls else "",
            "batch_id": batch_id,
            "total": len(urls),
            "audio_urls": urls,
            "cached": True,
        }

    # --- 缓存未命中，继续原有生成逻辑 ---
    batch_id = f"tts_{int(time.time() * 1000)}"
    print(f"[TTS Streaming] generate_tts_streaming batch={batch_id} session_id={session_id} total={total}")

    # 立即生成第 1 段（使用哈希文件名 + Session 隔离）
    first_path = get_cache_voice_path(text=processed_text, segment_index=0, session_id=session_id)
    print(f"[TTS Streaming] generating segment[0]: {repr(segments[0][:50])} -> {first_path}")
    generate_tts_segment(segments[0], engine=engine, output_path=first_path)
    first_url = get_tts_url(first_path)
    print(f"[TTS Streaming] segment[0] generated OK")

    with _tts_batches_lock:
        # 只清理过期 batch，不强制取消未完成的 batch。
        # 避免用户在不同会话切换时，新 TTS 请求意外中断旧会话的后台生成。
        _cleanup_old_batches()
        _tts_batches[batch_id] = {
            "urls": [{"local_path": first_path, "url": first_url}],
            "done": total <= 1,
            "total": total,
            "created_at": time.time(),
        }
        # 生成完成后写入内存缓存（Session 隔离键）
        _tts_hash_batches[cache_key] = batch_id

    # 启动后台线程生成剩余段（使用哈希文件名 + Session 隔离）
    if total > 1:
        t = threading.Thread(
            target=_generate_remaining_async_cached,
            args=(batch_id, text_hash, segments, engine, 1, session_id),
            daemon=True
        )
        t.start()

    return {
        "first_url": first_url,
        "batch_id": batch_id,
        "total": total,
        "audio_urls": [first_url],
        "cached": False,
    }


def get_tts_batch_progress(batch_id: str) -> dict:
    """查询某 batch 的当前生成进度。"""
    with _tts_batches_lock:
        batch = _tts_batches.get(batch_id)
    if not batch:
        return {"status": "error", "message": "batch 不存在或已过期"}
    return {
        "status": "success",
        "urls": [u["url"] for u in batch["urls"]],
        "done": batch["done"],
        "total": batch["total"],
    }


def stop_tts():
    global play_tts_flag, tts_playing
    # pg.quit()  # 移除：浏览器模式下 pygame 不再播放音频
    play_tts_flag = 0
    tts_playing = False


def split_text(text2):
    """按标点符号分割文本"""
    segments2 = re.split(r'([\n:：!！?？;；。])', text2)
    combined = []
    for i in range(0, len(segments2), 2):
        if i + 1 < len(segments2):
            combined.append(segments2[i] + segments2[i + 1])
        elif segments2[i].strip():
            combined.append(segments2[i])
    return [seg.strip() for seg in combined if seg.strip()]


def get_cache_voice_path(text: str = "", segment_index: int = 0, session_id: str = "") -> str:
    """生成音频文件路径（支持哈希缓存 + Session 隔离）

    - 若 text 非空，使用哈希作为文件名前缀：tts_{hash}_{index}.mp3
    - 若 text 为空，回退时间戳模式：tts_{timestamp}_{index}.mp3
    - 若 session_id 非空，存储到 cache_voice/{session_id}/ 子目录

    Args:
        text: 原始文本（用于哈希）
        segment_index: 分段索引
        session_id: 会话 ID（可选）

    Returns:
        str: 本地文件绝对路径
    """
    if text:
        normalized = _normalize_text(text)
        text_hash = _get_text_hash(normalized)
        filename = f"tts_{text_hash}_{segment_index}.mp3"
    else:
        filename = f"tts_{int(time.time() * 1000)}_{segment_index}.mp3"

    if session_id:
        session_dir = os.path.join(voice_cache_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)
        local_path = os.path.join(session_dir, filename)
    else:
        local_path = os.path.join(voice_cache_dir, filename)
    return local_path


def _find_cached_audio(text_hash: str, session_id: str = "", cache_dir: str = voice_cache_dir) -> list[str] | None:
    """查找已存在的音频缓存文件

    Args:
        text_hash: 文本哈希值
        session_id: 会话 ID（可选，非空时在该会话子目录查找）
        cache_dir: 缓存目录

    Returns:
        list[str] | None: 按 segment_index 排序的本地路径列表，无缓存返回 None
    """
    if session_id:
        search_dir = os.path.join(cache_dir, session_id)
    else:
        search_dir = cache_dir

    pattern = os.path.join(search_dir, f"tts_{text_hash}_*.mp3")
    files = glob.glob(pattern)
    if not files:
        return None

    # 从文件名提取 segment_index 并排序
    def _extract_index(path: str) -> int:
        basename = os.path.basename(path)
        # 格式: tts_{hash}_{index}.mp3
        parts = basename.replace(".mp3", "").split("_")
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return -1

    files.sort(key=_extract_index)
    return files


def get_tts_url(local_path):
    """将本地路径转换为浏览器可访问的 URL"""
    # local_path: dist/assets/cache_voice/xxx.mp3
    # URL: /assets/cache_voice/xxx.mp3
    rel = os.path.relpath(local_path, 'dist')
    return '/' + rel.replace('\\', '/')


async def ms_edge_tts(segment2, output_path):
    """edge-tts 异步生成音频"""
    cfg = get_config()
    speaker = cfg.get("edge_speaker", edge_speaker)
    rate = cfg.get("edge_rate", edge_rate)
    pitch = cfg.get("edge_pitch", edge_pitch)
    communicate = edge_tts.Communicate(segment2, voice=speaker, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def tts_vits(text, output_path):
    """VITS 生成音频"""
    global vits_tts
    if vits_tts is None:
        vits_tts = sherpa_onnx.OfflineTts(vits_tts_config)
    audio = vits_tts.generate(text, sid=0, speed=1.0)
    sf.write(output_path, audio.samples, samplerate=audio.sample_rate, subtype="PCM_16", format="wav")


def custom_tts(text, output_path):
    """自定义 TTS 生成音频"""
    cfg = get_config()
    url = cfg.get("custom_tts_url", custom_tts_url)
    model = cfg.get("custom_tts_model", custom_tts_model)
    voice = cfg.get("custom_tts_voice", custom_tts_voice)
    key = cfg.get("custom_tts_key", custom_tts_key)
    client = OpenAI(api_key=key, base_url=url)
    with client.audio.speech.with_streaming_response.create(
            model=model, voice=voice, input=text, response_format="mp3") as response:
        response.stream_to_file(output_path)


def generate_tts_segment(segment, engine=None, output_path=None):
    """
    生成单段 TTS 音频文件，返回本地文件路径。
    :param segment: 要合成的文本
    :param engine: TTS 引擎，None 则使用 prefer_tts
    :param output_path: 输出文件路径，None 则自动生成
    :return: 本地音频文件路径
    """
    if engine is None:
        engine = get_prefer_tts()
    if output_path is None:
        output_path = get_cache_voice_path()

    cfg = get_config()

    if engine == "edge-tts":
        asyncio.run(ms_edge_tts(segment, output_path))
    elif engine == "VITS":
        tts_vits(segment, output_path)
    elif engine == "GPT-SoVITS":
        api = cfg.get("gsv_api", gsv_api)
        prompt = cfg.get("gsv_prompt", gsv_prompt)
        ref_audio = cfg.get("gsv_ref_audio_path", gsv_ref_audio_path)
        prompt_lang = cfg.get("gsv_prompt_lang", gsv_prompt_lang)
        lang = cfg.get("gsv_lang", gsv_lang)
        url = f'{api}/tts?text={segment}&text_lang={lang}&prompt_text={prompt}&prompt_lang={prompt_lang}&ref_audio_path={ref_audio}'
        res = rq.get(url)
        with open(output_path, 'wb') as f:
            f.write(res.content)
    elif engine == "CosyVoice":
        api = cfg.get("cosy_api", cosy_api)
        url = f'{api}/cosyvoice/?text={segment}'
        res = rq.get(url)
        with open(output_path, 'wb') as f:
            f.write(res.content)
    elif engine == "Qwen-TTS":
        api = cfg.get("qwentts_api", qwentts_api)
        url = f'{api}/qwen_tts/?text={segment}'
        res = rq.get(url)
        with open(output_path, 'wb') as f:
            f.write(res.content)
    elif engine == "Qwen3-TTS":
        api = cfg.get("qwentts_api", qwentts_api)
        model = cfg.get("qwentts_model", qwentts_model)
        voice = cfg.get("qwentts_voice", qwentts_voice)
        url = f'{api}/v1/audio/speech'
        res = rq.post(url, json={
            "model": model,
            "input": segment,
            "speaker": voice,
            "response_format": "mp3",
        }, timeout=120)
        res.raise_for_status()
        with open(output_path, 'wb') as f:
            f.write(res.content)
    elif engine == "VoxCPM":
        api = cfg.get("voxcpm_api", voxcpm_api)
        url = f'{api}/voxcpm/?text={segment}'
        res = rq.get(url)
        with open(output_path, 'wb') as f:
            f.write(res.content)
    elif engine == "Index-TTS":
        api = cfg.get("index_api", index_api)
        url = f'{api}/indextts/?text={segment}'
        res = rq.get(url)
        with open(output_path, 'wb') as f:
            f.write(res.content)
    elif engine == "CustomTTS":
        custom_tts(segment, output_path)
    else:
        raise ValueError(f"不支持的 TTS 引擎: {engine}")
    return output_path


def generate_tts(text, engine=None):
    """
    生成 TTS 音频，支持自动分段（当 stream_tts_switch == "on" 时）。
    :param text: 要合成的文本
    :param engine: TTS 引擎，None 则使用 prefer_tts
    :return: list[dict]，每个元素包含 {"local_path": ..., "url": ...}
    """
    processed_text = text.split("</think>")[-1].strip()
    processed_text = re.sub(r'[(（].*?[)）]', '', processed_text)

    cfg = get_config()
    if cfg.get("stream_tts_switch", stream_tts_switch) == "on":
        segments = split_text(processed_text)
        if not segments:
            segments = [processed_text]
    else:
        segments = [processed_text]

    results = []
    for idx, segment in enumerate(segments):
        if not segment.strip():
            continue
        try:
            local_path = get_cache_voice_path(segment_index=idx)
            generate_tts_segment(segment, engine=engine, output_path=local_path)
            results.append({
                "local_path": local_path,
                "url": get_tts_url(local_path)
            })
        except Exception as e:
            print(f"TTS 生成失败（{engine}）：{e}")
    return results


def play_tts(audio_path):
    """
    本地播放音频（保留供本地模式备用，默认不调用）。
    :param audio_path: 音频文件路径
    """
    global play_tts_flag
    play_tts_flag = 1
    pg.mixer.init()
    try:
        pg.mixer.music.load(audio_path)
        pg.mixer.music.play()
        while pg.mixer.music.get_busy() and play_tts_flag == 1:
            pg.time.Clock().tick(1)
        pg.mixer.music.stop()
    except Exception:
        pass
    pg.quit()


# 保留旧接口兼容：生成并直接播放（供本地/语音交互模式使用）
def play_tts_legacy(text):
    """
    旧接口：生成音频后立即本地播放。
    供 main.py 语音交互线程等本地模式使用。
    """
    global play_tts_flag, tts_playing
    play_tts_flag = 1

    processed_text = text.split("</think>")[-1].strip()
    processed_text = re.sub(r'[(（].*?[)）]', '', processed_text)

    cfg = get_config()
    if cfg.get("stream_tts_switch", stream_tts_switch) == "on":
        segments = split_text(processed_text)
        if not segments:
            segments = [processed_text]
    else:
        segments = [processed_text]

    for segment in segments:
        if play_tts_flag != 1:
            break
        try:
            local_path = get_cache_voice_path()
            generate_tts_segment(segment, output_path=local_path)
            tts_playing = True
            play_tts(local_path)
            tts_playing = False
        except Exception as e:
            tts_playing = False
            print(f"语音合成服务出错：{e}")


def delete_session_audio(session_id: str) -> dict:
    """删除指定会话的所有音频缓存

    Args:
        session_id: 会话 UUID

    Returns:
        dict: {"deleted": int, "freed_bytes": int}
    """
    import logging
    logger = logging.getLogger("tts")
    result = {"deleted": 0, "freed_bytes": 0}

    if not session_id:
        return result

    session_dir = os.path.join(voice_cache_dir, session_id)
    if not os.path.exists(session_dir):
        return result

    # 统计删除前目录大小
    try:
        total_size = sum(
            os.path.getsize(os.path.join(session_dir, f))
            for f in os.listdir(session_dir)
            if os.path.isfile(os.path.join(session_dir, f))
        )
    except (OSError, IOError):
        total_size = 0

    # 整目录删除
    shutil.rmtree(session_dir, ignore_errors=True)
    result["deleted"] = 1  # 统计为 1 个目录
    result["freed_bytes"] = total_size

    # 清理内存缓存中该会话相关的键
    prefix = f"{session_id}:"
    with _tts_batches_lock:
        keys_to_remove = [k for k in _tts_hash_batches if k.startswith(prefix)]
        for k in keys_to_remove:
            del _tts_hash_batches[k]

    logger.info(
        f"[TTS-CACHE] 会话 {session_id} 音频缓存已删除, "
        f"释放 {total_size / (1024 * 1024):.2f} MB"
    )
    return result


def cleanup_cache_voice(
    cache_dir: str = voice_cache_dir,
    active_session_ids: set[str] | None = None,
    playing_files: set[str] | None = None
) -> dict:
    """清理过期音频缓存文件（Session 隔离版）

    三步清理：
    1. 清理根目录无主文件（旧全局格式）
    2. 清理非活跃会话目录（整目录删除）
    3. 清理活跃会话内部文件（按年龄 + 软上限）

    Args:
        cache_dir: 缓存目录路径
        active_session_ids: 活跃会话 ID 集合（None 时跳过目录级清理）
        playing_files: 当前正在播放的文件路径集合

    Returns:
        dict: {'deleted': int, 'skipped_playing': int, 'freed_bytes': int}
    """
    import logging
    logger = logging.getLogger("tts")

    result = {"deleted": 0, "skipped_playing": 0, "freed_bytes": 0}

    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)
        return result

    playing = playing_files if playing_files is not None else _playing_files
    playing_normalized = {os.path.normpath(p) for p in playing}
    now = time.time()
    max_age_sec = CACHE_MAX_AGE_HOURS * 3600

    # ===== 第 1 步：清理根目录无主文件（旧全局格式） =====
    root_pattern = os.path.join(cache_dir, "tts_*.mp3")
    root_files = glob.glob(root_pattern)
    if root_files:
        files_with_mtime = []
        for f in root_files:
            try:
                mtime = os.path.getmtime(f)
                files_with_mtime.append((f, mtime))
            except (OSError, IOError):
                continue
        files_with_mtime.sort(key=lambda x: x[1])

        to_delete = set()
        # 按年龄删除
        for f, mtime in files_with_mtime:
            if now - mtime > max_age_sec:
                to_delete.add(f)
        # 按数量删除（保留最新的 CACHE_MAX_FILES 个）
        if len(files_with_mtime) > CACHE_MAX_FILES:
            for f, _ in files_with_mtime[:-CACHE_MAX_FILES]:
                to_delete.add(f)
        # 保护播放中文件
        for f in list(to_delete):
            if os.path.normpath(f) in playing_normalized:
                to_delete.discard(f)
                result["skipped_playing"] += 1
        # 执行删除
        for f in to_delete:
            try:
                size = os.path.getsize(f)
                os.remove(f)
                result["deleted"] += 1
                result["freed_bytes"] += size
            except (OSError, IOError):
                continue

    # ===== 第 2 步：清理非活跃会话目录 =====
    if active_session_ids is not None:
        try:
            for entry in os.listdir(cache_dir):
                entry_path = os.path.join(cache_dir, entry)
                # 只处理子目录
                if not os.path.isdir(entry_path):
                    continue
                # 跳过根目录下的非 UUID 目录（如 .git、logs 等）
                if not _is_valid_session_id(entry):
                    continue
                # 非活跃会话 → 整目录删除
                if entry not in active_session_ids:
                    # 保护播放中文件
                    has_playing = False
                    for f in glob.glob(os.path.join(entry_path, "tts_*.mp3")):
                        if os.path.normpath(f) in playing_normalized:
                            has_playing = True
                            result["skipped_playing"] += 1
                            break
                    if not has_playing:
                        try:
                            dir_size = sum(
                                os.path.getsize(os.path.join(entry_path, f))
                                for f in os.listdir(entry_path)
                                if os.path.isfile(os.path.join(entry_path, f))
                            )
                        except (OSError, IOError):
                            dir_size = 0
                        shutil.rmtree(entry_path, ignore_errors=True)
                        result["deleted"] += 1
                        result["freed_bytes"] += dir_size
                        logger.info(f"[TTS-CACHE] 删除非活跃会话目录: {entry}")
        except (OSError, IOError):
            pass

    # ===== 第 3 步：清理活跃会话内部文件 =====
    if active_session_ids:
        for sid in active_session_ids:
            session_dir = os.path.join(cache_dir, sid)
            if not os.path.exists(session_dir):
                continue
            session_files = glob.glob(os.path.join(session_dir, "tts_*.mp3"))
            if not session_files:
                continue

            files_with_mtime = []
            for f in session_files:
                try:
                    mtime = os.path.getmtime(f)
                    files_with_mtime.append((f, mtime))
                except (OSError, IOError):
                    continue
            files_with_mtime.sort(key=lambda x: x[1])

            to_delete = set()
            # 按年龄删除
            for f, mtime in files_with_mtime:
                if now - mtime > max_age_sec:
                    to_delete.add(f)
            # 软上限：超过 1000 个时删最旧的
            if len(files_with_mtime) > CACHE_SESSION_SOFT_LIMIT:
                for f, _ in files_with_mtime[:-CACHE_SESSION_SOFT_LIMIT]:
                    to_delete.add(f)
            # 保护播放中文件
            for f in list(to_delete):
                if os.path.normpath(f) in playing_normalized:
                    to_delete.discard(f)
                    result["skipped_playing"] += 1
            # 执行删除
            for f in to_delete:
                try:
                    size = os.path.getsize(f)
                    os.remove(f)
                    result["deleted"] += 1
                    result["freed_bytes"] += size
                except (OSError, IOError):
                    continue

    freed_mb = result["freed_bytes"] / (1024 * 1024)
    logger.info(
        f"[TTS-CACHE] 清理完成: 删除 {result['deleted']} 个文件/目录, "
        f"释放 {freed_mb:.2f} MB, 跳过 {result['skipped_playing']} 个播放中文件"
    )

    return result


def _is_valid_session_id(s: str) -> bool:
    """粗略判断字符串是否为会话 UUID（hex + hyphens）"""
    if not s or len(s) < 8:
        return False
    # UUID 格式：8-4-4-4-12，共 36 字符
    # 粗略检查：包含 hyphens，且主要由 hex 字符组成
    parts = s.split("-")
    if len(parts) != 5:
        return False
    expected_lens = [8, 4, 4, 4, 12]
    for p, expected in zip(parts, expected_lens):
        if len(p) != expected:
            return False
        if not all(c in "0123456789abcdefABCDEF" for c in p):
            return False
    return True


def _cache_cleanup_loop() -> None:
    """后台清理守护线程主循环"""
    while True:
        try:
            # 动态导入获取活跃会话列表
            try:
                from conversation import list_sessions
                sessions = list_sessions(limit=10000)
                active_ids = {s["id"] for s in sessions if not s.get("is_archived")}
            except Exception:
                logging.getLogger("tts").exception("获取活跃会话列表失败，跳过目录级清理")
                active_ids = None
            cleanup_cache_voice(active_session_ids=active_ids)
        except Exception:
            logging.getLogger("tts").exception("定时清理异常，下一轮继续")
        time.sleep(CACHE_CLEAN_INTERVAL)


def _start_cache_cleanup_thread() -> None:
    """启动后台清理守护线程"""
    t = threading.Thread(target=_cache_cleanup_loop, daemon=True)
    t.start()
    logging.getLogger("tts").info("[TTS-CACHE] 后台清理线程已启动")


# 服务启动时执行一次清理
cleanup_cache_voice()
# 启动后台定时清理线程
_start_cache_cleanup_thread()
