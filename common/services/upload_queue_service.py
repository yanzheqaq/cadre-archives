# -*- coding: utf-8 -*-
"""
图片上传任务队列服务（Redis 驱动）

架构说明
--------
  UI 主线程                        QThread 后台工作线程
  ┌────────────┐                  ┌──────────────────────┐
  │ 用户选择图片 │ ──push task──▶  │ Redis LIST (FIFO)    │
  │            │                  │  ↓ BLPOP              │
  │ 进度条/状态 │ ◀──signal────── │  处理：拷贝 + 写DB     │
  └────────────┘                  └──────────────────────┘

关键设计:
  1. 任务以 JSON 序列化后 RPUSH 到 Redis LIST，保证 FIFO 顺序
  2. Worker 线程使用 BLPOP 阻塞等待任务，不轮询
  3. 通过 pyqtSignal 将进度/完成/错误安全回传到 UI 线程
  4. 支持批量上传（一次选多张图片作为一个 task）
  5. Redis 不可用时自动降级为同步模式，保证功能可用
"""
import json
import os
import mimetypes
import time
import uuid
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from common.services.crypto_service import CryptoService, encrypt_image


# ---------------------------------------------------------------------------
# Redis 连接管理
# ---------------------------------------------------------------------------

_redis_client = None


def _get_redis():
    """获取 Redis 连接（懒加载单例）。连接失败返回 None。"""
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    try:
        import redis
        from common.config.redis_config import RedisConfig
        _redis_client = redis.Redis(**RedisConfig.get_connection_kwargs())
        _redis_client.ping()
        return _redis_client
    except Exception as e:
        print(f"[upload-queue] Redis 连接失败，将使用同步模式: {e}")
        _redis_client = None
        return None


def _queue_key():
    from common.config.redis_config import RedisConfig
    return RedisConfig.UPLOAD_QUEUE_KEY


def _failed_key():
    from common.config.redis_config import RedisConfig
    return RedisConfig.UPLOAD_FAILED_KEY


# ---------------------------------------------------------------------------
# 任务数据结构
# ---------------------------------------------------------------------------

def build_upload_task(
    *,
    entry_id,
    tpl_item_id,
    ec_item_id: int,
    image_root: str,
    files: List[str],
    cleanup_source_files: bool = False,
) -> dict:
    """
    构建一个上传任务字典。

    Parameters
    ----------
    entry_id : int or str
        条目 ID
    tpl_item_id : int
        模板目录项 ID
    ec_item_id : int
        条目目录项 ID（用于写入 DB）
    image_root : str
        图片存储根目录
    files : list[str]
        要上传的源文件路径列表
    """
    if not image_root:
        try:
            from common.config import AppSettings
            image_root = AppSettings().get_image_root()
        except Exception:
            image_root = os.path.join(os.getcwd(), "data", "images")

    return {
        "task_id": str(uuid.uuid4()),
        "entry_id": str(entry_id),
        "tpl_item_id": int(tpl_item_id),
        "ec_item_id": int(ec_item_id),
        "image_root": image_root,
        "files": files,
        "cleanup_source_files": bool(cleanup_source_files),
        "created_at": time.time(),
    }


# ---------------------------------------------------------------------------
# 推送任务
# ---------------------------------------------------------------------------

def push_upload_task(task: dict) -> bool:
    """
    将一个上传任务推入 Redis 队列。

    Returns
    -------
    bool
        True = 已推入 Redis 队列，False = Redis 不可用（调用方应降级为同步处理）
    """
    r = _get_redis()
    if r is None:
        return False
    try:
        r.rpush(_queue_key(), json.dumps(task, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"[upload-queue] push task failed: {e}")
        return False


def get_queue_length() -> int:
    """获取当前队列中待处理任务数量"""
    r = _get_redis()
    if r is None:
        return 0
    try:
        return r.llen(_queue_key())
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 实际处理逻辑（在 Worker 线程中执行）
# ---------------------------------------------------------------------------

def _process_single_task(task: dict, progress_callback=None) -> dict:
    """
    处理一个上传任务：拷贝文件 + 写数据库。

    Parameters
    ----------
    task : dict
        任务字典，由 build_upload_task 构建
    progress_callback : callable, optional
        回调签名 (current_idx, total, file_name) -> None

    Returns
    -------
    dict
        {"task_id": ..., "success": int, "failed": int, "errors": [...]}
    """
    from common.repositories.image_repo import (
        get_next_image_sort_base,
        upsert_original_images,
    )

    task_id = task.get("task_id", "unknown")
    entry_id = task.get("entry_id", "unknown")
    tpl_item_id = task.get("tpl_item_id")
    ec_item_id = task.get("ec_item_id")
    image_root = task.get("image_root", "")
    files = task.get("files", [])
    cleanup_source_files = bool(task.get("cleanup_source_files", False))

    if not image_root:
        try:
            from common.config import AppSettings
            image_root = AppSettings().get_image_root()
        except Exception:
            image_root = os.path.join(os.getcwd(), "data", "images")

    dest_dir = os.path.join(image_root, str(entry_id), str(tpl_item_id))
    os.makedirs(dest_dir, exist_ok=True)

    sort_base = get_next_image_sort_base(entry_catalog_item_id=int(ec_item_id))
    to_upsert = []
    errors = []
    total = len(files)

    for idx, src in enumerate(files):
        fname = os.path.basename(src)
        if progress_callback:
            try:
                progress_callback(idx, total, fname)
            except Exception:
                pass
        try:
            if not os.path.exists(src):
                errors.append(f"文件不存在: {src}")
                continue
            dest_name = fname if fname.lower().endswith(CryptoService.ENCRYPTED_EXT) else fname + CryptoService.ENCRYPTED_EXT
            dest_path = os.path.join(dest_dir, dest_name)
            encrypt_image(src, dest_path)
            mime, _ = mimetypes.guess_type(src)
            size = os.path.getsize(dest_path)
            to_upsert.append({
                "file_path": dest_path,
                "file_name": dest_name,
                "file_size": size,
                "mime_type": mime or "",
                "sort_order": sort_base + idx,
            })
        except Exception as e:
            errors.append(f"{fname}: {e}")

    # 批量写入数据库
    if to_upsert:
        try:
            upsert_original_images(
                entry_catalog_item_id=int(ec_item_id),
                files=to_upsert,
            )
        except Exception as e:
            errors.append(f"数据库写入失败: {e}")

    # 报告最后一个的进度 (100%)
    if progress_callback:
        try:
            progress_callback(total, total, "")
        except Exception:
            pass

    if cleanup_source_files and not errors:
        for src in files:
            try:
                if os.path.isfile(src):
                    os.remove(src)
            except Exception:
                pass

    return {
        "task_id": task_id,
        "ec_item_id": ec_item_id,
        "success": len(to_upsert),
        "failed": len(errors),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# QThread 后台 Worker
# ---------------------------------------------------------------------------

class UploadWorker(QObject):
    """
    运行在 QThread 中的上传队列消费者。

    Signals
    -------
    task_started(task_id, total_files)
        一个任务开始处理
    file_progress(task_id, current, total, file_name)
        单个文件的进度
    task_finished(result_dict)
        一个任务处理完成，result_dict 包含 success/failed/errors
    worker_error(error_msg)
        Worker 级别的错误
    queue_empty()
        队列已清空（所有任务都处理完）
    """

    task_started = pyqtSignal(str, int)              # task_id, total_files
    file_progress = pyqtSignal(str, int, int, str)   # task_id, current, total, file_name
    task_finished = pyqtSignal(dict)                  # result dict
    worker_error = pyqtSignal(str)                    # error message
    queue_empty = pyqtSignal()                        # 队列清空

    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        """请求停止 Worker（将在当前任务处理完后退出循环）"""
        self._running = False

    def run(self):
        """
        主循环：从 Redis BLPOP 取任务并处理。

        使用 BLPOP 阻塞等待，超时 2 秒后检查 _running 标志。
        这样既不忙等，又能及时响应停止请求。
        """
        while self._running:
            r = _get_redis()
            if r is None:
                # Redis 不可用，短暂休眠后重试
                time.sleep(3)
                continue

            try:
                # BLPOP: 阻塞弹出，超时 2 秒
                result = r.blpop(_queue_key(), timeout=2)
                if result is None:
                    # 超时，无任务，检查是否要退出
                    continue

                _, raw = result
                task = json.loads(raw)
                task_id = task.get("task_id", "unknown")
                files = task.get("files", [])

                self.task_started.emit(task_id, len(files))

                def on_progress(current, total, fname, tid=task_id):
                    self.file_progress.emit(tid, current, total, fname)

                res = _process_single_task(task, progress_callback=on_progress)
                self.task_finished.emit(res)

                # 检查队列是否已空
                remaining = get_queue_length()
                if remaining == 0:
                    self.queue_empty.emit()

            except json.JSONDecodeError as e:
                self.worker_error.emit(f"任务数据格式错误: {e}")
            except Exception as e:
                self.worker_error.emit(f"处理任务异常: {e}")
                time.sleep(1)  # 异常后短暂休眠，防止疯狂循环


class FallbackUploadWorker(QObject):
    task_started = pyqtSignal(str, int)
    file_progress = pyqtSignal(str, int, int, str)
    task_finished = pyqtSignal(dict)
    worker_error = pyqtSignal(str)

    def process_task(self, task: dict):
        task_id = task.get("task_id", "unknown")
        try:
            files = task.get("files", [])
            self.task_started.emit(task_id, len(files))

            def on_progress(current, total, fname, tid=task_id):
                self.file_progress.emit(tid, current, total, fname)

            res = _process_single_task(task, progress_callback=on_progress)
            self.task_finished.emit(res)
        except Exception as e:
            self.worker_error.emit(f"本地上传任务异常: {e}")
            self.task_finished.emit({
                "task_id": task_id,
                "ec_item_id": task.get("ec_item_id"),
                "success": 0,
                "failed": 1,
                "errors": [str(e)],
            })


# ---------------------------------------------------------------------------
# 上传队列管理器（单例，供 UI 层使用）
# ---------------------------------------------------------------------------

class UploadQueueManager(QObject):
    """
    上传队列管理器 —— 单例

    职责:
      1. 管理 Worker 线程的生命周期
      2. 提供 push_task() 给 UI 层调用
      3. 转发 Worker 信号给外部订阅者
      4. Redis 不可用时自动降级为同步处理

    典型用法::

        mgr = get_upload_queue_manager()
        mgr.task_finished.connect(self._on_upload_done)
        mgr.file_progress.connect(self._on_upload_progress)
        mgr.push_task(task)
    """

    # 转发信号
    task_started = pyqtSignal(str, int)
    file_progress = pyqtSignal(str, int, int, str)
    task_finished = pyqtSignal(dict)
    worker_error = pyqtSignal(str)
    queue_empty = pyqtSignal()

    # 降级同步模式的信号
    sync_mode_used = pyqtSignal()  # 通知 UI 当前使用了同步模式
    _fallback_task_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[UploadWorker] = None
        self._started = False
        self._fallback_thread: Optional[QThread] = None
        self._fallback_worker: Optional[FallbackUploadWorker] = None
        self._fallback_started = False
        self._fallback_pending = 0

    def _ensure_worker(self):
        """确保 Worker 线程已启动"""
        if self._started and self._thread and self._thread.isRunning():
            return True

        # 先检查 Redis 是否可用
        r = _get_redis()
        if r is None:
            return False

        self._thread = QThread()
        self._worker = UploadWorker()
        self._worker.moveToThread(self._thread)

        # 连接 Worker 信号到管理器
        self._worker.task_started.connect(self.task_started)
        self._worker.file_progress.connect(self.file_progress)
        self._worker.task_finished.connect(self.task_finished)
        self._worker.worker_error.connect(self.worker_error)
        self._worker.queue_empty.connect(self.queue_empty)

        # 线程启动后运行 Worker.run
        self._thread.started.connect(self._worker.run)

        self._thread.start()
        self._started = True
        print("[upload-queue] Worker 线程已启动")
        return True

    def _ensure_fallback_worker(self):
        if self._fallback_started and self._fallback_thread and self._fallback_thread.isRunning():
            return True

        self._fallback_thread = QThread()
        self._fallback_worker = FallbackUploadWorker()
        self._fallback_worker.moveToThread(self._fallback_thread)

        self._fallback_task_requested.connect(self._fallback_worker.process_task)
        self._fallback_worker.task_started.connect(self.task_started)
        self._fallback_worker.file_progress.connect(self.file_progress)
        self._fallback_worker.task_finished.connect(self._on_fallback_task_finished)
        self._fallback_worker.worker_error.connect(self.worker_error)

        self._fallback_thread.start()
        self._fallback_started = True
        return True

    def _on_fallback_task_finished(self, result: dict):
        self.task_finished.emit(result)
        self._fallback_pending = max(0, self._fallback_pending - 1)
        if self._fallback_pending == 0:
            self.queue_empty.emit()

    def push_task(self, task: dict) -> bool:
        """
        推送上传任务。

        Returns
        -------
        bool
            True = 已加入队列（异步处理）
            False = Redis 不可用，已降级为同步处理
        """
        # 尝试推入 Redis
        pushed = push_upload_task(task)
        if pushed:
            # 确保 Worker 线程在运行
            self._ensure_worker()
            return True

        # 降级：同步处理
        print("[upload-queue] 降级为同步模式")
        self.sync_mode_used.emit()
        self._ensure_fallback_worker()
        self._fallback_pending += 1
        self._fallback_task_requested.emit(task)
        return False

    def _sync_fallback(self, task: dict):
        """Redis 不可用时的同步降级处理"""
        task_id = task.get("task_id", "unknown")
        files = task.get("files", [])
        self.task_started.emit(task_id, len(files))

        def on_progress(current, total, fname, tid=task_id):
            self.file_progress.emit(tid, current, total, fname)

        res = _process_single_task(task, progress_callback=on_progress)
        self.task_finished.emit(res)
        self.queue_empty.emit()

    def shutdown(self):
        """关闭 Worker 线程"""
        if self._worker:
            self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)
            print("[upload-queue] Worker 线程已停止")
        if self._fallback_thread and self._fallback_thread.isRunning():
            self._fallback_thread.quit()
            self._fallback_thread.wait(5000)
        self._started = False
        self._worker = None
        self._thread = None
        self._fallback_started = False
        self._fallback_worker = None
        self._fallback_thread = None
        self._fallback_pending = 0

    def is_running(self) -> bool:
        """Worker 线程是否在运行"""
        return self._started and self._thread is not None and self._thread.isRunning()

    def pending_count(self) -> int:
        """获取队列中待处理的任务数"""
        return get_queue_length()


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_manager_instance: Optional[UploadQueueManager] = None


def get_upload_queue_manager() -> UploadQueueManager:
    """获取上传队列管理器单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = UploadQueueManager()
    return _manager_instance


def shutdown_upload_queue():
    """关闭上传队列（应用退出时调用）"""
    global _manager_instance
    if _manager_instance is not None:
        _manager_instance.shutdown()
        _manager_instance = None
