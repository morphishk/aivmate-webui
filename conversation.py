"""会话管理模块 - SQLite CRUD、消息持久化、标题生成

P1 新增模块，负责：
- 会话 CRUD（conversations 表）
- 消息 CRUD（messages 表）
- 异步标题生成（ThreadPoolExecutor）
- 数据库自动初始化（WAL 模式）

MySQL 迁移预留：所有 SQL 使用 ANSI 标准语法，
SQLite 特有语法（如 AUTOINCREMENT）已在注释中标注 MySQL 等效语法。
"""

import atexit
import sqlite3
import os
import shutil
import time
import uuid
import threading
import concurrent.futures
import logging
from collections import defaultdict, OrderedDict

# ============================================================
# 模块级常量
# ============================================================

DB_PATH = "data/db/conversations.db"

TITLE_PROMPT = """请根据以下对话内容，生成一个 5~10 字的中文标题，概括讨论主题：

用户：{user_msg}
AI：{assistant_msg}

只输出标题文字，不要解释，不要加引号。"""

SCHEMA_SQL = """
-- 会话表
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,              -- UUID v4
    title       TEXT DEFAULT '',               -- 会话标题
    message_count INTEGER DEFAULT 0,           -- 消息总数
    is_archived INTEGER DEFAULT 0,            -- 0=活跃 1=已归档 2=损坏
    archive_path TEXT DEFAULT NULL,            -- 归档 ZIP 路径
    created_at  REAL NOT NULL,                 -- Unix timestamp
    updated_at  REAL NOT NULL                  -- Unix timestamp
);

-- 消息表（不含 base64，仅存图片/文件的路径）
-- MySQL 迁移：AUTOINCREMENT -> AUTO_INCREMENT
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content     TEXT DEFAULT '',               -- 文本内容
    image_path  TEXT DEFAULT NULL,             -- 图片相对路径
    file_name   TEXT DEFAULT NULL,             -- 上传的文件名
    file_path   TEXT DEFAULT NULL,             -- 文件相对路径
    file_content TEXT DEFAULT NULL,             -- 文件文本内容
    created_at  REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_archived ON conversations(is_archived, updated_at);
"""

# ============================================================
# 线程锁与线程池
# ============================================================

_db_lock = threading.Lock()
_title_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
atexit.register(_title_executor.shutdown, wait=True)

# ============================================================
# 数据库连接
# ============================================================


def _get_db() -> sqlite3.Connection:
    """获取数据库连接，启用 WAL 模式 + 外键约束 + Row 工厂

    Returns:
        sqlite3.Connection: 配置好的数据库连接
    """
    _init_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ============================================================
# 自动初始化
# ============================================================


def _ensure_dirs() -> None:
    """确保必要的目录结构存在"""
    os.makedirs("data/db", exist_ok=True)
    os.makedirs("data/sessions", exist_ok=True)
    os.makedirs("data/archive", exist_ok=True)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """幂等执行 schema 升级

    Args:
        conn: 已建立的数据库连接（由 _init_db 传入，避免递归）
    """
    cursor = conn.execute("PRAGMA table_info(messages)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'file_content' not in columns:
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN file_content TEXT;")
        except sqlite3.OperationalError:
            pass
    if 'agent_id' not in columns:
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN agent_id TEXT;")
        except sqlite3.OperationalError:
            pass
    if 'agent_result' not in columns:
        try:
            conn.execute("ALTER TABLE messages ADD COLUMN agent_result TEXT;")
        except sqlite3.OperationalError:
            pass


_db_initialized = False

def _init_db() -> None:
    """懒初始化数据库和目录结构"""
    global _db_initialized
    if _db_initialized:
        return
    _ensure_dirs()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.execute('PRAGMA foreign_keys=ON;')
    conn.executescript(SCHEMA_SQL)
    _migrate_schema(conn)
    conn.close()
    _db_initialized = True

# ============================================================
# 会话 CRUD
# ============================================================


def create_session(title: str = "") -> str:
    """创建新会话，返回 UUID

    Args:
        title: 会话标题，默认为空字符串

    Returns:
        str: 新生成的会话 UUID（uuid4，保证唯一性，不复用已删除 ID）
    """
    session_id = str(uuid.uuid4())
    now = time.time()
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
            conn.commit()
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()
    return session_id


def get_session(session_id: str) -> dict | None:
    """获取会话元数据

    Args:
        session_id: 会话 UUID

    Returns:
        dict | None: 会话信息字典，不存在则返回 None
    """
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT id, title, message_count, is_archived, archive_path, created_at, updated_at "
            "FROM conversations WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "message_count": row[2],
            "is_archived": bool(row[3]),
            "archive_path": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }
    finally:
        conn.close()


def list_sessions(limit: int = 100) -> list[dict]:
    """获取会话列表（按 updated_at 倒序）

    Args:
        limit: 最大返回数量，默认 100

    Returns:
        list[dict]: 会话信息列表
    """
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, message_count, is_archived, created_at, updated_at "
            "FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "message_count": r[2],
                "is_archived": bool(r[3]),
                "created_at": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """删除会话（CASCADE 自动删消息）

    Args:
        session_id: 会话 UUID

    Returns:
        bool: 是否成功删除
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # 先删除关联的文件目录
            session_dir = os.path.join("data", "sessions", session_id)
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir)
            # SQLite ON DELETE CASCADE 自动删除 messages 记录
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def update_session_title(session_id: str, title: str) -> bool:
    """更新会话标题

    Args:
        session_id: 会话 UUID
        title: 新标题

    Returns:
        bool: 是否成功更新
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, time.time(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def update_session_message_count(session_id: str, count: int) -> bool:
    """更新会话消息计数和更新时间

    Args:
        session_id: 会话 UUID
        count: 消息总数

    Returns:
        bool: 是否成功更新
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE conversations SET message_count = ?, updated_at = ? WHERE id = ?",
                (count, time.time(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def _upsert_messages(conn: sqlite3.Connection, session_id: str, messages: list[dict]) -> int:
    """执行消息去重、插入、文件路径保留的核心逻辑

    Args:
        conn: 数据库连接（已开启事务）
        session_id: 会话 UUID
        messages: 消息字典列表

    Returns:
        int: 实际插入的消息数
    """
    existing_rows = conn.execute(
        "SELECT role, content, image_path, file_name, file_path, created_at FROM messages WHERE session_id = ? ORDER BY created_at",
        (session_id,),
    ).fetchall()
    existing_map = defaultdict(list)
    for r in existing_rows:
        key = (r[0], r[1])
        existing_map[key].append({
            "image_path": r[2],
            "file_name": r[3],
            "file_path": r[4],
            "created_at": r[5],
        })

    inserted = 0
    for msg in messages:
        ts = msg.get("timestamp")
        role = msg.get("role", "user")
        # assistant 消息使用更大的时间窗口（30秒），避免前后端时间不同步
        # 或网络延迟导致切换会话时的 _doSave 竞态重复
        time_window = 30.0 if role == "assistant" else 10.0
        dup = conn.execute(
            "SELECT id FROM messages WHERE session_id=? AND role=? AND content=? AND ABS(created_at - ?) < ?",
            (session_id, role, msg.get("content", ""), ts if ts else 0.0, time_window),
        ).fetchone()
        if dup:
            continue

        key = (msg.get("role", "user"), msg.get("content", ""))
        existing = None
        if key in existing_map and existing_map[key]:
            existing = existing_map[key].pop(0)

        image_path = msg.get("image_path")
        file_name = msg.get("file_name")
        file_path = msg.get("file_path")
        if existing and not image_path:
            image_path = existing["image_path"]
        if existing and not file_name:
            file_name = existing["file_name"]
        if existing and not file_path:
            file_path = existing["file_path"]

        created_at = ts if ts else time.time()
        conn.execute(
            "INSERT INTO messages (session_id, role, content, image_path, file_name, file_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                msg.get("role", "user"),
                msg.get("content", ""),
                image_path,
                file_name,
                file_path,
                created_at,
            ),
        )
        inserted += 1

    if inserted > 0:
        conn.execute(
            "UPDATE conversations SET message_count = (SELECT COUNT(*) FROM messages WHERE session_id = ?), updated_at = ? WHERE id = ?",
            (session_id, time.time(), session_id),
        )
    return inserted


def update_session_with_lock(session_id: str, messages: list[dict], expected_updated_at: float | None = None) -> dict:
    """带乐观锁的会话消息批量更新

    用于前端 auto-save 和 /api/sessions/<id>/save 的兜底保存。
    如传入 expected_updated_at，则比对数据库中的 updated_at，
    不一致时返回冲突错误，避免覆盖其他客户端的更新。

    Args:
        session_id: 会话 UUID
        messages: 消息字典列表
        expected_updated_at: 预期的最后更新时间（乐观锁版本号）

    Returns:
        dict: {"status": "success" | "error", "message"?: str, "code"?: str}
    """
    if not messages:
        return {"status": "success"}

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")

            # 乐观锁检查
            if expected_updated_at is not None:
                row = conn.execute(
                    "SELECT updated_at FROM conversations WHERE id = ? AND is_archived = 0",
                    (session_id,),
                ).fetchone()
                if not row:
                    conn.rollback()
                    return {"status": "error", "message": "会话不存在或已归档", "code": "NOT_FOUND"}
                if abs(row[0] - expected_updated_at) > 0.001:
                    conn.rollback()
                    return {
                        "status": "error",
                        "message": "会话已在其他位置更新，请刷新",
                        "code": "CONCURRENT_WRITE",
                    }

            _upsert_messages(conn, session_id, messages)
            conn.commit()
            return {"status": "success"}
        except sqlite3.OperationalError as e:
            conn.rollback()
            if "database is locked" in str(e):
                return {"status": "error", "message": "数据库忙，请稍后重试", "code": "DB_LOCKED"}
            return {"status": "error", "message": f"数据库错误: {e}", "code": "DB_ERROR"}
        except (sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def mark_session_archived(session_id: str, archive_path: str) -> bool:
    """标记会话为已归档

    Args:
        session_id: 会话 UUID
        archive_path: 归档 ZIP 路径

    Returns:
        bool: 是否成功更新
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE conversations SET is_archived = 1, archive_path = ? WHERE id = ?",
                (archive_path, session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def restore_session_from_archive(session_id: str) -> bool:
    """将会话从归档状态恢复为活跃

    Args:
        session_id: 会话 UUID

    Returns:
        bool: 是否成功更新
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE conversations SET is_archived = 0, archive_path = NULL, updated_at = ? WHERE id = ?",
                (time.time(), session_id),
            )
            conn.commit()
            return cur.rowcount > 0
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================
# 消息 CRUD
# ============================================================


def save_message(
    session_id: str,
    role: str,
    content: str = "",
    image_path: str | None = None,
    file_name: str | None = None,
    file_path: str | None = None,
    file_content: str | None = None,
    agent_id: str | None = None,
    agent_result: dict | None = None,
) -> int:
    """保存单条消息，返回消息 ID

    Args:
        session_id: 会话 UUID
        role: 消息角色 ('user' | 'assistant' | 'system')
        content: 文本内容
        image_path: 图片相对路径
        file_name: 上传的文件名
        file_path: 文件相对路径
        file_content: 文件文本内容
        agent_id: 触发消息的 Agent ID
        agent_result: Agent 结构化结果 JSON

    Returns:
        int: 新插入消息的 ID
    """
    import json
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, image_path, file_name, file_path, file_content, agent_id, agent_result, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, role, content, image_path, file_name, file_path, file_content, agent_id, json.dumps(agent_result, ensure_ascii=False) if agent_result else None, time.time()),
            )
            conn.commit()
            return cur.lastrowid
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def get_session_messages(session_id: str, limit: int = 20) -> list[dict]:
    """获取会话最近 N 条消息（按 created_at 正序）

    Args:
        session_id: 会话 UUID
        limit: 最大返回数量，默认 20

    Returns:
        list[dict]: 消息列表（OpenAI 格式兼容）
    """
    import json
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, role, content, image_path, file_name, file_path, file_content, agent_id, agent_result, created_at "
            "FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        # 返回正序（旧 -> 新）
        rows = list(reversed(rows))
        result = []
        for r in rows:
            agent_result = r[8]
            if agent_result and isinstance(agent_result, str):
                try:
                    agent_result = json.loads(agent_result)
                except (json.JSONDecodeError, TypeError):
                    agent_result = None
            result.append({
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "image_path": r[3],
                "file_name": r[4],
                "file_path": r[5],
                "file_content": r[6],
                "agent_id": r[7],
                "agent_result": agent_result,
                "timestamp": r[9],
            })
        return result
    finally:
        conn.close()


def delete_session_messages(session_id: str) -> bool:
    """删除会话的全部消息（归档时用）

    Args:
        session_id: 会话 UUID

    Returns:
        bool: 是否成功删除（有记录被删除返回 True）
    """
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


def save_messages_batch(session_id: str, messages: list[dict]) -> bool:
    """批量保存消息（前端兜底保存用）

    Args:
        session_id: 会话 UUID
        messages: 消息字典列表，每个字典需包含 role, content 等字段

    Returns:
        bool: 是否成功保存
    """
    if not messages:
        return True

    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _upsert_messages(conn, session_id, messages)
            conn.commit()
            return True
        except (sqlite3.OperationalError, sqlite3.IntegrityError, OSError):
            conn.rollback()
            raise
        finally:
            conn.close()


# ============================================================
# 标题生成（异步线程池）
# ============================================================


def generate_title_async(
    session_id: str, user_msg: str, assistant_msg: str, llm_config: dict
) -> None:
    """异步生成会话标题，3秒超时，失败静默

    Args:
        session_id: 会话 UUID
        user_msg: 用户首条消息
        assistant_msg: AI 首条回复
        llm_config: LLM 配置字典，包含 prefer_llm 等
    """

    def _do_generate() -> None:
        try:
            prompt = TITLE_PROMPT.format(
                user_msg=user_msg[:200], assistant_msg=assistant_msg[:200]
            )
            title = _call_llm_for_title(prompt, llm_config)
            if title:
                title = title.strip().strip('"').strip("'").strip()
                if 2 <= len(title) <= 20:
                    update_session_title(session_id, title)
                    logging.getLogger("conversation").info(f"会话 {session_id} 标题生成: {title}")
                else:
                    # Fallback: 使用首条用户消息前 15 字
                    _fallback_title(session_id, user_msg)
            else:
                _fallback_title(session_id, user_msg)
        except concurrent.futures.TimeoutError:
            _fallback_title(session_id, user_msg)
        except Exception as e:
            logging.getLogger("conversation").warning(f"标题生成失败: {e}")
            _fallback_title(session_id, user_msg)

    _title_executor.submit(_do_generate)


def _fallback_title(session_id: str, user_msg: str) -> None:
    """标题生成失败时的 fallback：使用首条用户消息前 15 字

    Args:
        session_id: 会话 UUID
        user_msg: 用户首条消息
    """
    if user_msg and user_msg.strip():
        fallback = user_msg.strip()[:15]
    else:
        fallback = "图片对话"
    update_session_title(session_id, fallback)
    logging.getLogger("conversation").info(f"会话 {session_id} fallback 标题: {fallback}")


def search_messages(keyword: str, limit: int = 50) -> list[dict]:
    """全局搜索消息内容，按会话分组返回

    Args:
        keyword: 搜索关键词（已在前端做基础 trim）
        limit: 最大返回条数（默认 50，后端查 limit+1 用于判断 has_more）

    Returns:
        list[dict]: 按会话分组的搜索结果
    """
    if not keyword or not keyword.strip():
        return []

    # SQL 注入防护：严格按此顺序 escape：\ → \\（最先），% → \%，_ → \_
    escaped = keyword.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    pattern = f'%{escaped}%'

    conn = _get_db()
    try:
        cursor = conn.execute('''
            SELECT
                m.id as message_id,
                m.session_id,
                m.role,
                m.content,
                m.created_at,
                c.title as session_title,
                c.is_archived
            FROM messages m
            JOIN conversations c ON m.session_id = c.id
            WHERE (m.content LIKE ? ESCAPE '\\' OR m.file_content LIKE ? ESCAPE '\\')
              AND m.role != 'system'
            ORDER BY m.created_at DESC
            LIMIT ?
        ''', (pattern, pattern, limit + 1))

        rows = cursor.fetchall()
    finally:
        conn.close()

    # 按 session_id 分组
    groups = OrderedDict()
    for row in rows:
        sid = row['session_id']
        if sid not in groups:
            groups[sid] = {
                'session_id': sid,
                'session_title': row['session_title'] or '未命名会话',
                'is_archived': row['is_archived'],
                'matches': []
            }

        # 生成预览文本：关键词前后各 30 字
        content = row['content'] or ''
        idx = content.lower().find(keyword.lower())
        start = max(0, idx - 30)
        end = min(len(content), idx + len(keyword) + 30)
        preview = content[start:end]
        if start > 0:
            preview = '...' + preview
        if end < len(content):
            preview = preview + '...'

        groups[sid]['matches'].append({
            'message_id': row['message_id'],
            'role': row['role'],
            'content_preview': preview,
            'created_at': row['created_at']
        })

    return list(groups.values())


def _call_llm_for_title(prompt: str, llm_config: dict) -> str:
    """调用 LLM 生成标题

    Args:
        prompt: 标题生成提示词
        llm_config: LLM 配置字典

    Returns:
        str: 生成的标题文本
    """
    prefer_llm = llm_config.get("prefer_llm", "OpenAI")

    if prefer_llm == "ZhipuAI":
        from zai import ZhipuAiClient
        glm_key = llm_config.get("glm_key", "")
        glm_llm_model = llm_config.get("glm_llm_model", "glm-4-flash")
        if not glm_key:
            return ""
        client = ZhipuAiClient(api_key=glm_key)
        completion = client.chat.completions.create(
            model=glm_llm_model,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "disabled"},
        )
        return completion.choices[0].message.content.strip()

    elif prefer_llm == "OpenAI":
        from openai import OpenAI
        openai_url = llm_config.get("openai_url", "")
        openai_key = llm_config.get("openai_key", "")
        openai_llm_model = llm_config.get("openai_llm_model", "gpt-3.5-turbo")
        if not openai_url or not openai_key:
            return ""
        client = OpenAI(base_url=openai_url, api_key=openai_key)
        completion = client.chat.completions.create(
            model=openai_llm_model,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content.strip()

    elif prefer_llm == "Ollama":
        from openai import OpenAI
        ollama_url = llm_config.get("ollama_url", "")
        ollama_llm_model = llm_config.get("ollama_llm_model", "llama3")
        if not ollama_url:
            return ""
        client = OpenAI(base_url=ollama_url, api_key="ollama")
        completion = client.chat.completions.create(
            model=ollama_llm_model,
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content.strip()

    elif prefer_llm == "LM Studio":
        from openai import OpenAI
        lmstudio_url = llm_config.get("lmstudio_url", "")
        if not lmstudio_url:
            return ""
        client = OpenAI(base_url=lmstudio_url, api_key="lm-studio")
        completion = client.chat.completions.create(
            model="",
            messages=[{"role": "user", "content": prompt}],
        )
        return completion.choices[0].message.content.strip()

    # AnythingLLM / Dify / RKLLM 不支持标题生成，直接返回空触发 fallback
    return ""
