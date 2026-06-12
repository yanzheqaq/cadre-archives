# -*- coding: utf-8 -*-
"""
档案数字化加工系统 - 入口文件

重构后的架构:
- common/config/       统一配置模块
- common/db/           数据库模块  
- common/repositories/ 数据访问层
- common/services/     业务逻辑层
- login_ui/           登录界面
- main_ui/            主界面
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QThreadPool

from common.services.upload_queue_service import shutdown_upload_queue
from common.services.catalog_snapshot_service import take_snapshot_with_timeout
from login_ui.login_window import LoginWindow


def _on_app_quit():
    """
    应用退出前的清理：
    1. 等待全局线程池中所有 Worker（目录保存、图片处理等）执行完毕，
       避免还在写 DB 的后台任务被强制中断导致数据丢失。
    2. 同步触发一次目录数据快照（带 8 秒超时），作为"丢失自检"基准。
       即使超时也只是"本次快照丢失"，事务原子性保证 DB 不损坏。
    3. 关闭上传队列 Worker 线程。
    """
    QThreadPool.globalInstance().waitForDone(5000)
    try:
        # 同步执行快照（带 8 秒超时保护）。典型耗时 ~100~500ms，
        # 超时仍让后台 daemon 线程继续，SQLite 事务原子性保证数据库不损坏。
        take_snapshot_with_timeout(kind="auto_close", timeout_seconds=8.0)
    except Exception as e:
        print(f"[snapshot] auto_close trigger failed: {e}")
    shutdown_upload_queue()


def main():
    """应用程序主入口"""
    # 启用高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # type: ignore
    
    # 创建应用程序
    app = QApplication(sys.argv)
    
    # 应用退出时：等待后台 Worker 完成，再关闭上传队列
    app.aboutToQuit.connect(_on_app_quit)
    
    # 创建并显示登录窗口
    window = LoginWindow()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
