# -*- coding: utf-8 -*-
"""
自动补全管理模块
- 管理 Auto_complete Settings 目录结构
- 读取和解析 txt 配置文件
- 提供候选词匹配功能
"""

import os
import time
import threading
import queue
import tempfile
from typing import List, Optional


class AutocompleteManager:
    """
    自动补全管理器
    
    目录结构示例：
    Auto_complete Settings/
    └── 干部人事档案目录模板/
        ├── 履历材料.txt           # 一级目录的候选词
        ├── 考核鉴定材料.txt
        └── 学历学位、专业技术.../  # 有子级的目录
            └── 学历学位材料.txt
    
    txt 文件格式：用 ; 分割候选词
    例如：阿巴吧;啊嗷嗷嗷;阿里巴巴
    """
    
    def __init__(self, base_dir: str = None):
        """
        初始化自动补全管理器
        
        Args:
            base_dir: Auto_complete Settings 目录路径
        """
        if base_dir is None:
            # 默认在项目根目录下
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            base_dir = os.path.join(project_root, "Auto_complete Settings")
        
        self.base_dir = base_dir
        self._cache = {}  # 缓存已读取的配置 {(template_name, item_name): [候选词列表]}
        self._global_cache = {}  # 全局匹配缓存 {template_name: word_counts_dict}
        self._global_sorted_cache = {}
        # ---- 低配机优化（2026-04 新增）----
        # 所有本地 txt 词频写入都走后台线程 + 原子替换，UI 线程不再做文件 IO。
        # _pending_counts 是内存里每个文件的权威 counts 副本；writer 线程按队列顺序
        # 把最新 snapshot 落盘。flush_sync() 在对话框关闭/应用退出时等队列清空。
        self._lock = threading.RLock()
        self._pending_counts: dict = {}          # {file_path: {word: count}}
        self._writer_queue: "queue.Queue" = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._warmup_inflight: set = set()       # 正在后台预热的 template_name
        self._ensure_writer_thread()
    
    def ensure_base_dir(self):
        """确保基础目录存在"""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
    
    def get_template_dir(self, template_name: str) -> str:
        """获取模板对应的目录路径"""
        return os.path.join(self.base_dir, template_name)
    
    def ensure_template_dir(self, template_name: str) -> str:
        """确保模板目录存在"""
        self.ensure_base_dir()
        tpl_dir = self.get_template_dir(template_name)
        if not os.path.exists(tpl_dir):
            os.makedirs(tpl_dir, exist_ok=True)
        return tpl_dir
    
    def get_config_file_path(self, template_name: str, item_name: str, parent_item_name: str = None) -> str:
        """
        获取配置文件路径
        
        Args:
            template_name: 模板名称
            item_name: 目录条目名称（不含序号，如"考核鉴定材料"）
            parent_item_name: 父级目录名称（如果有子级）
        
        Returns:
            txt 文件路径
        """
        tpl_dir = self.get_template_dir(template_name)
        
        if parent_item_name:
            # 有父级，在父级文件夹下
            parent_dir = os.path.join(tpl_dir, parent_item_name)
            return os.path.join(parent_dir, f"{item_name}.txt")
        else:
            # 一级目录，直接在模板目录下
            return os.path.join(tpl_dir, f"{item_name}.txt")
    
    def _parse_candidate_entry(self, entry: str) -> tuple:
        """
        解析候选词条目，提取词语和使用次数
        
        格式：词语(次数)，如 "干部履历表(5)"
        如果没有次数，默认为 0
        
        Returns:
            (word, count) 元组
        """
        import re
        match = re.match(r'^(.+?)\((\d+)\)$', entry.strip())
        if match:
            return (match.group(1), int(match.group(2)))
        return (entry.strip(), 0)
    
    def _format_candidate_entry(self, word: str, count: int) -> str:
        """格式化候选词条目为存储格式"""
        return f"{word}({count})"
    
    def load_candidates(self, template_name: str, item_name: str, parent_item_name: str = None) -> List[str]:
        """
        加载候选词列表（按使用次数从大到小排序）
        
        Args:
            template_name: 模板名称
            item_name: 目录条目名称
            parent_item_name: 父级目录名称
        
        Returns:
            候选词列表（仅词语，不含次数）
        """
        cache_key = (template_name, parent_item_name or "", item_name)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        file_path = self.get_config_file_path(template_name, item_name, parent_item_name)
        
        candidates_with_count = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        for entry in content.split(";"):
                            entry = entry.strip()
                            if entry:
                                word, count = self._parse_candidate_entry(entry)
                                if word:
                                    candidates_with_count.append((word, count))
            except Exception:
                pass
        
        candidates_with_count.sort(key=lambda x: x[1], reverse=True)
        candidates = [word for word, count in candidates_with_count]
        self._cache[cache_key] = candidates
        return candidates
    
    def load_candidates_with_count(self, template_name: str, item_name: str, parent_item_name: str = None) -> List[tuple]:
        """
        加载候选词列表（包含次数）
        
        Returns:
            [(word, count), ...] 列表，按次数从大到小排序
        """
        file_path = self.get_config_file_path(template_name, item_name, parent_item_name)
        
        candidates_with_count = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        for entry in content.split(";"):
                            entry = entry.strip()
                            if entry:
                                word, count = self._parse_candidate_entry(entry)
                                if word:
                                    candidates_with_count.append((word, count))
            except Exception:
                pass
        
        # 按使用次数从大到小排序
        candidates_with_count.sort(key=lambda x: x[1], reverse=True)
        return candidates_with_count
    
    def record_usage(self, template_name: str, item_name: str, word: str, parent_item_name: str = None):
        """
        记录词语使用：内存中 +1 并增量更新 _global_cache，文件写入由后台线程完成。
        UI 线程几乎零耗时；flush_sync() 确保进程正常退出前全部落盘。
        崩溃时最多丢掉内存里还没 flush 的最后几次 +1（用户只会看到下次打开时某个词排序
        略靠后），绝不会损坏现有 txt（写入走 tempfile + os.replace 原子替换）。
        """
        if not word:
            return
        file_path = self.get_config_file_path(template_name, item_name, parent_item_name)
        with self._lock:
            # 第一次操作该文件：从磁盘懒加载一次现有 counts
            if file_path not in self._pending_counts:
                self._pending_counts[file_path] = self._read_file_counts(file_path)
            counts = self._pending_counts[file_path]
            new_count = counts.get(word, 0) + 1
            counts[word] = new_count
            snapshot = dict(counts)
            # 增量更新全局缓存（关键：不再让整张缓存失效）
            gc = self._global_cache.get(template_name)
            if gc is not None:
                prev = gc.get(word, 0)
                if new_count > prev:
                    gc[word] = new_count
                    self._global_sorted_cache.pop(template_name, None)
            # 单项缓存改为失效（下次 load_candidates 会重读，只涉及单文件 IO）
            cache_key = (template_name, parent_item_name or "", item_name)
            self._cache.pop(cache_key, None)
        # 入写队列（非阻塞，UI 线程立刻返回）
        try:
            self._writer_queue.put_nowait((file_path, snapshot))
        except Exception:
            # 队列异常兜底：直接同步写一次，不让计数丢失
            try:
                self._atomic_write_counts(file_path, snapshot)
            except Exception as e:
                print(f"[autocomplete] sync fallback write failed: {e}")
    
    def match_candidates(self, template_name: str, item_name: str, input_text: str, parent_item_name: str = None) -> List[str]:
        """
        根据输入文本匹配候选词（已按使用次数排序）
        
        Args:
            template_name: 模板名称
            item_name: 目录条目名称
            input_text: 用户输入的文本
            parent_item_name: 父级目录名称
        
        Returns:
            匹配的候选词列表
        """
        candidates = self.load_candidates(template_name, item_name, parent_item_name)
        
        if not input_text:
            return candidates
        
        # 匹配：候选词以输入文本开头 或 包含输入文本
        matched = []
        contains = []
        
        input_lower = input_text.lower()
        for c in candidates:
            c_lower = c.lower()
            if c_lower.startswith(input_lower):
                matched.append(c)
            elif input_lower in c_lower:
                contains.append(c)
        
        # 优先显示以输入开头的，然后是包含的（各组内已按次数排序）
        return matched + contains
    
    def match_candidates_global(self, template_name: str, input_text: str) -> List[str]:
        """
        全局匹配（UI 线程调用，必须快）：
        - 若模板词库尚未预热好，**直接返回空列表**并触发后台预热，用户下一次键入就命中缓存
        - 预热完成后从 _global_cache[template_name] 读取并按输入前缀/包含匹配
        UI 线程不做任何文件遍历/IO，低配机上也不会卡。
        """
        with self._lock:
            word_counts = self._global_cache.get(template_name)
            all_words = self._global_sorted_cache.get(template_name)
            if word_counts is not None and all_words is None:
                all_words = sorted(word_counts.keys(), key=lambda w: (-word_counts[w], w))
                self._global_sorted_cache[template_name] = all_words
        if word_counts is None:
            # 缓存未就绪：异步预热，本次返回空（不弹补全框）
            self.warmup_template_async(template_name)
            return []

        if not input_text:
            return all_words

        input_lower = input_text.lower()
        matched = [w for w in all_words if w.lower().startswith(input_lower)]
        contains = [w for w in all_words if not w.lower().startswith(input_lower) and input_lower in w.lower()]
        return matched + contains

    # ------------------------------------------------------------------
    # 后台写入 + 异步预热 + 原子写（2026-04 新增）
    # ------------------------------------------------------------------
    def _ensure_writer_thread(self):
        """确保后台写线程存活。

        线程是 non-daemon，保证进程正常退出时能把队列里剩下的写任务跑完；
        flush_sync() 会进一步等待 unfinished_tasks 归零。
        """
        t = self._writer_thread
        if t is not None and t.is_alive():
            return
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            daemon=False,
            name="autocomplete-writer",
        )
        self._writer_thread.start()

    def _writer_loop(self):
        """后台写线程：按队列顺序把 (file_path, snapshot) 原子落盘。"""
        while True:
            try:
                item = self._writer_queue.get()
            except Exception:
                return
            try:
                if item is None:  # 关闭信号
                    return
                file_path, counts = item
                try:
                    self._atomic_write_counts(file_path, counts)
                except Exception as e:
                    # 写失败只影响这次 +1 不落盘，现有文件不会被破坏
                    print(f"[autocomplete] writer failed for {file_path}: {e}")
            finally:
                try:
                    self._writer_queue.task_done()
                except Exception:
                    pass

    def _atomic_write_counts(self, file_path: str, counts: dict):
        """把 counts dict 原子写到 file_path：先写临时文件，再 os.replace。

        崩溃时 file_path 要么是旧版要么是新版，不会出现半残文件。
        """
        file_dir = os.path.dirname(file_path)
        if file_dir and not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
        entries = [
            self._format_candidate_entry(w, c)
            for w, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        ]
        data = ";".join(entries)
        fd, tmp_path = tempfile.mkstemp(prefix=".ac_", suffix=".tmp", dir=file_dir or None)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, file_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass
            raise

    def _read_file_counts(self, file_path: str) -> dict:
        """从磁盘读取一个 txt 文件的 {word: count}（静默失败返回空 dict）。"""
        counts: dict = {}
        if not file_path or not os.path.exists(file_path):
            return counts
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            for entry in content.split(";"):
                entry = entry.strip()
                if not entry:
                    continue
                word, count = self._parse_candidate_entry(entry)
                if word:
                    counts[word] = count
        except Exception:
            pass
        return counts

    def warmup_template_async(self, template_name: str):
        """后台预热 _global_cache[template_name]。可重复调用，幂等。

        在对话框加载模板后立即调用，这样用户第一次键入时缓存已经就绪。
        """
        if not template_name:
            return
        with self._lock:
            if template_name in self._global_cache:
                return
            if template_name in self._warmup_inflight:
                return
            self._warmup_inflight.add(template_name)

        def _warmup():
            try:
                word_counts: dict = {}
                tpl_dir = self.get_template_dir(template_name)
                if os.path.exists(tpl_dir):
                    for root, _, files in os.walk(tpl_dir):
                        for fname in files:
                            if not fname.endswith(".txt"):
                                continue
                            fpath = os.path.join(root, fname)
                            try:
                                with open(fpath, "r", encoding="utf-8") as f:
                                    content = f.read().strip()
                                for entry in content.split(";"):
                                    entry = entry.strip()
                                    if not entry:
                                        continue
                                    word, count = self._parse_candidate_entry(entry)
                                    if word:
                                        word_counts[word] = max(word_counts.get(word, 0), count)
                            except Exception:
                                pass
                with self._lock:
                    # 合并已有内存 +1（极小概率竞态：用户在预热期间刚好选词）
                    existing = self._global_cache.get(template_name) or {}
                    for w, c in existing.items():
                        if c > word_counts.get(w, 0):
                            word_counts[w] = c
                    self._global_cache[template_name] = word_counts
                    self._global_sorted_cache[template_name] = sorted(word_counts.keys(), key=lambda w: (-word_counts[w], w))
            except Exception as e:
                print(f"[autocomplete] warmup failed for {template_name}: {e}")
            finally:
                with self._lock:
                    self._warmup_inflight.discard(template_name)

        threading.Thread(target=_warmup, daemon=True, name="autocomplete-warmup").start()

    def flush_sync(self, timeout: float = 3.0) -> bool:
        """等待所有 pending 写任务落盘。

        在对话框关闭 / 应用退出前调用，确保词频不丢。
        返回 True 表示全部完成；False 表示超时（仍会继续后台写，只是不再阻塞调用方）。
        """
        try:
            end = time.monotonic() + max(0.0, float(timeout))
            while time.monotonic() < end:
                if self._writer_queue.unfinished_tasks == 0:
                    return True
                time.sleep(0.02)
            print(
                f"[autocomplete] flush_sync timeout, "
                f"{self._writer_queue.unfinished_tasks} task(s) remain (will continue in background)"
            )
            return False
        except Exception as e:
            print(f"[autocomplete] flush_sync error: {e}")
            return False

    def save_candidates(self, template_name: str, item_name: str, candidates: List[str], parent_item_name: str = None):
        """
        保存候选词列表到配置文件
        
        Args:
            template_name: 模板名称
            item_name: 目录条目名称
            candidates: 候选词列表
            parent_item_name: 父级目录名称
        """
        file_path = self.get_config_file_path(template_name, item_name, parent_item_name)
        
        # 确保目录存在
        file_dir = os.path.dirname(file_path)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir, exist_ok=True)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(";".join(candidates))
            
            # 更新缓存
            cache_key = (template_name, parent_item_name or "", item_name)
            self._cache[cache_key] = candidates
        except Exception:
            pass
    
    def add_candidate(self, template_name: str, item_name: str, new_candidate: str, parent_item_name: str = None):
        """
        添加一个新的候选词（如果不存在）
        
        Args:
            template_name: 模板名称
            item_name: 目录条目名称
            new_candidate: 新候选词
            parent_item_name: 父级目录名称
        """
        candidates = self.load_candidates(template_name, item_name, parent_item_name)
        
        if new_candidate not in candidates:
            candidates.append(new_candidate)
            self.save_candidates(template_name, item_name, candidates, parent_item_name)
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._global_sorted_cache.clear()
    
    def create_template_structure_from_db(self, template_name: str, items: List[dict]):
        """
        根据数据库中的模板条目创建配置目录结构
        
        Args:
            template_name: 模板名称
            items: 模板条目列表，格式 [{"id": 1, "parent_id": None, "serial": "一", "name": "履历材料", ...}]
        
        规则：
        - serial 为中文数字（一、二、三...）的是一级目录
        - serial 含 "-"（如 4-1、9-2）的是子级目录
        - 一级目录如果有子级，创建文件夹；否则创建 txt 文件
        - 子级目录只创建 txt 文件（在父级文件夹下）
        """
        tpl_dir = self.ensure_template_dir(template_name)
        
        import re
        
        # 分离一级目录和子级目录
        top_level = []  # 一级目录
        children = {}   # 子级目录，按父级 serial 前缀分组
        
        for item in items:
            serial = item.get("serial", "").strip()
            name = item.get("name", "").strip()
            if not name:
                continue
            
            # 判断是否是子级：serial 含 "-"，如 "4-1"、"9-2"
            if "-" in serial:
                # 提取父级前缀，如 "4-1" -> "4"
                parent_prefix = serial.split("-")[0]
                children.setdefault(parent_prefix, []).append(item)
            else:
                top_level.append(item)
        
        # 建立一级目录 serial 到 name 的映射（用于确定哪些有子级）
        # 中文数字到阿拉伯数字的映射
        cn_to_num = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5", 
                     "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
        
        for item in top_level:
            serial = item.get("serial", "").strip()
            name = item.get("name", "").strip()
            
            # 转换中文数字为阿拉伯数字
            num_serial = cn_to_num.get(serial, serial)
            
            # 检查是否有子级
            if num_serial in children and len(children[num_serial]) > 0:
                # 有子级，创建文件夹
                folder_path = os.path.join(tpl_dir, name)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path, exist_ok=True)
                
                # 为每个子级创建 txt 文件
                for child in children[num_serial]:
                    child_name = child.get("name", "").strip()
                    if child_name:
                        file_path = os.path.join(folder_path, f"{child_name}.txt")
                        if not os.path.exists(file_path):
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write("")
            else:
                # 无子级，直接创建 txt 文件
                file_path = os.path.join(tpl_dir, f"{name}.txt")
                if not os.path.exists(file_path):
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write("")


# 全局单例
_autocomplete_manager: Optional[AutocompleteManager] = None


def get_autocomplete_manager() -> AutocompleteManager:
    """获取全局自动补全管理器单例"""
    global _autocomplete_manager
    if _autocomplete_manager is None:
        _autocomplete_manager = AutocompleteManager()
    return _autocomplete_manager
