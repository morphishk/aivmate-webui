"""归档压缩模块（P1 Day 2 完整实现）

负责：
- 归档策略配置管理
- 旧会话 ZIP 打包归档
- 归档会话解压恢复
- 归档统计查询（直接查 SQLite，不使用冗余索引文件）
"""

import os
import json
import time
import zipfile
import shutil
import logging
import threading
from conversation import (
    _get_db, _db_lock, get_session_messages
)

ARCHIVE_BASE = "data/archive"
ARCHIVE_CONFIG_PATH = "data/db/archive_config.json"


def _load_archive_config() -> dict:
    """加载归档配置，不存在则创建默认配置

    Returns:
        dict: 归档配置字典
    """
    default = {"archive_days": 30, "enabled": True, "archive_time": "02:00"}
    if os.path.exists(ARCHIVE_CONFIG_PATH):
        try:
            with open(ARCHIVE_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.getLogger("archive").warning(f"读取归档配置失败: {e}，使用默认配置")
            return default
    os.makedirs(os.path.dirname(ARCHIVE_CONFIG_PATH), exist_ok=True)
    with open(ARCHIVE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(default, f, indent=2)
    return default


def archive_old_sessions() -> dict:
    """归档超过 archive_days 天未更新的会话

    流程：
    1. 查询 updated_at < now - archive_days 且 is_archived=0 的会话
    2. 对每个会话读取 messages 表全部记录
    3. 打包 ZIP：data/archive/YYYY-MM/session_id.zip
       - session.json    (会话元数据)
       - messages.json   (消息数组，image_path/file_path 保留相对路径)
       - images/         (图片文件)
       - files/          (附件文件)
    4. 删除 SQLite 中该会话的 messages 记录
    5. 更新 conversations.is_archived=1, archive_path=...
    6. 可选：删除原 data/sessions/{id}/ 目录以节省空间

    Returns:
        dict: {"archived_count": int, "archived_sessions": list[str]}
    """
    config = _load_archive_config()
    if not config.get("enabled", True):
        return {"archived_count": 0, "archived_sessions": []}

    archive_days = config.get("archive_days", 30)
    cutoff_time = time.time() - (archive_days * 24 * 3600)

    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, message_count, created_at, updated_at "
            "FROM conversations WHERE is_archived = 0 AND updated_at < ?",
            (cutoff_time,),
        ).fetchall()
    finally:
        conn.close()

    archived_sessions = []
    for row in rows:
        session_id = row[0]
        try:
            success = _archive_single_session(session_id, row)
            if success:
                archived_sessions.append(session_id)
        except Exception as e:
            logging.getLogger("archive").error(f"归档会话 {session_id} 失败: {e}", exc_info=True)

    return {"archived_count": len(archived_sessions), "archived_sessions": archived_sessions}


def _archive_single_session(session_id: str, session_row: tuple) -> bool:
    """归档单个会话

    Args:
        session_id: 会话 UUID
        session_row: 会话元数据元组 (id, title, message_count, created_at, updated_at)

    Returns:
        bool: 是否成功归档
    """
    # 1. 读取全部消息
    messages = get_session_messages(session_id, limit=10000)

    # 2. 准备目录
    now_str = time.strftime("%Y-%m")
    archive_dir = os.path.join(ARCHIVE_BASE, now_str)
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{session_id}.zip")

    # 3. 准备 session.json
    session_meta = {
        "id": session_row[0],
        "title": session_row[1],
        "message_count": session_row[2],
        "created_at": session_row[3],
        "updated_at": session_row[4],
        "archived_at": time.time(),
    }

    # 4. 准备 messages.json（使用相对路径）
    messages_data = []
    for m in messages:
        messages_data.append({
            "role": m["role"],
            "content": m["content"],
            "image_path": m.get("image_path"),
            "file_name": m.get("file_name"),
            "file_path": m.get("file_path"),
            "timestamp": m.get("timestamp"),
        })

    # 5. 打包 ZIP
    session_fs_dir = os.path.join("data", "sessions", session_id)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # session.json
        zf.writestr("session.json", json.dumps(session_meta, ensure_ascii=False, indent=2))
        # messages.json
        zf.writestr("messages.json", json.dumps(messages_data, ensure_ascii=False, indent=2))
        # images/
        images_dir = os.path.join(session_fs_dir, "images")
        if os.path.exists(images_dir):
            for fname in os.listdir(images_dir):
                fpath = os.path.join(images_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, os.path.join("images", fname))
        # files/
        files_dir = os.path.join(session_fs_dir, "files")
        if os.path.exists(files_dir):
            for fname in os.listdir(files_dir):
                fpath = os.path.join(files_dir, fname)
                if os.path.isfile(fpath):
                    zf.write(fpath, os.path.join("files", fname))

    # 6. 删除 SQLite messages 记录，标记归档状态
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute(
                "UPDATE conversations SET is_archived = 1, archive_path = ? WHERE id = ?",
                (archive_path, session_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # 7. 删除原目录以节省空间
    if os.path.exists(session_fs_dir):
        shutil.rmtree(session_fs_dir)

    # 8. 级联删除音频缓存（Session 隔离）
    try:
        from tts import delete_session_audio
        delete_session_audio(session_id)
    except Exception:
        logging.getLogger("archive").exception(f"归档时删除会话音频缓存失败: {session_id}")

    logging.getLogger("archive").info(f"会话 {session_id} 已归档到 {archive_path}")
    return True


def restore_session(session_id: str) -> bool:
    """从归档 ZIP 恢复会话到活跃状态

    去重设计：
    - 解压前检查 data/sessions/{id}/ 是否已存在，如存在先删除
    - 解压后读取 session.json + messages.json
    - 将 messages 插入 SQLite（先清空再插入，避免重复）
    - 标记 conversations.is_archived=0
    - 更新 updated_at = now()（防止立即又被归档）

    Args:
        session_id: 会话 UUID

    Returns:
        bool: 是否成功恢复
    """
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT archive_path FROM conversations WHERE id = ? AND is_archived = 1",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row or not row[0] or not os.path.exists(row[0]):
        logging.getLogger("archive").warning(f"会话 {session_id} 归档文件不存在")
        return False

    archive_path = row[0]
    session_dir = os.path.join("data", "sessions", session_id)

    # 1. 如已存在，先删除原目录
    if os.path.exists(session_dir):
        shutil.rmtree(session_dir)

    # 2. 解压 ZIP
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(session_dir)
    except Exception as e:
        logging.getLogger("archive").error(f"解压归档 {archive_path} 失败: {e}", exc_info=True)
        return False

    # 3. 读取元数据
    try:
        with open(os.path.join(session_dir, "session.json"), "r", encoding="utf-8") as f:
            session_meta = json.load(f)
        with open(os.path.join(session_dir, "messages.json"), "r", encoding="utf-8") as f:
            messages = json.load(f)
    except Exception as e:
        logging.getLogger("archive").error(f"读取归档元数据失败: {e}", exc_info=True)
        return False

    # 4. 插入 SQLite（先清空再插入，避免重复）
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            for msg in messages:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, image_path, file_name, file_path, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_id,
                        msg["role"],
                        msg.get("content", ""),
                        msg.get("image_path"),
                        msg.get("file_name"),
                        msg.get("file_path"),
                        msg.get("timestamp", msg.get("created_at", time.time())),
                    ),
                )
            conn.execute(
                "UPDATE conversations SET is_archived = 0, archive_path = NULL, updated_at = ? WHERE id = ?",
                (time.time(), session_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    logging.getLogger("archive").info(f"会话 {session_id} 已从归档恢复")
    return True


def get_archived_sessions() -> list[dict]:
    """获取已归档会话列表（直接查 SQLite）

    Returns:
        list[dict]: 已归档会话列表
    """
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, archive_path, updated_at FROM conversations WHERE is_archived = 1"
        ).fetchall()
        return [
            {"id": r[0], "archive_path": r[1], "updated_at": r[2]} for r in rows
        ]
    finally:
        conn.close()


def get_archive_stats() -> dict:
    """获取归档统计（直接查 SQLite）

    Returns:
        dict: {"archived": int, "active": int}
    """
    conn = _get_db()
    try:
        archived = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE is_archived = 1"
        ).fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE is_archived = 0"
        ).fetchone()[0]
        return {"archived": archived, "active": active}
    finally:
        conn.close()


def delete_archive_file(session_id: str) -> bool:
    """删除会话的归档 ZIP 文件

    Args:
        session_id: 会话 UUID

    Returns:
        bool: 是否成功删除
    """
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT archive_path FROM conversations WHERE id = ?", (session_id,)
        ).fetchone()
        if row and row[0] and os.path.exists(row[0]):
            os.remove(row[0])
            # 尝试删除空目录
            dir_path = os.path.dirname(row[0])
            if os.path.isdir(dir_path) and not os.listdir(dir_path):
                os.rmdir(dir_path)
            return True
        return False
    finally:
        conn.close()


# ============================================================
# 归档定时任务
# ============================================================

_archive_timer = None


def _start_archive_timer() -> None:
    """启动归档定时扫描线程，每天 02:00 执行一次

    服务启动时立即执行一次归档扫描（避免停机期间错过），
    然后按配置中的 archive_time 定时执行。
    """
    global _archive_timer

    def _run_once() -> None:
        try:
            result = archive_old_sessions()
            if result.get("archived_count", 0) > 0:
                logging.getLogger("archive").info(
                    f"定时归档完成: {result['archived_count']} 个会话已归档"
                )
        except Exception as e:
            logging.getLogger("archive").error(f"定时归档异常: {e}", exc_info=True)

    def _schedule_next() -> None:
        global _archive_timer
        config = _load_archive_config()
        if not config.get("enabled", True):
            return

        archive_time = config.get("archive_time", "02:00")
        try:
            hour, minute = map(int, archive_time.split(":"))
        except ValueError:
            hour, minute = 2, 0

        now = time.localtime()
        next_run = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, minute, 0, 0, 0, -1))
        if next_run <= time.time():
            next_run += 24 * 3600

        delay = next_run - time.time()
        _archive_timer = threading.Timer(delay, _tick)
        _archive_timer.daemon = True
        _archive_timer.start()

    def _tick() -> None:
        _run_once()
        _schedule_next()

    # 启动时立即执行一次
    _run_once()
    _schedule_next()
