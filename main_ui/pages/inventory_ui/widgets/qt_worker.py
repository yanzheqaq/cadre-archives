from PyQt5.QtCore import QObject, pyqtSignal, QRunnable


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class Worker(QRunnable):
    """
    简单的 QRunnable 包装器：
    - 传入一个无参函数 fn
    - 成功：signals.finished.emit(result)
    - 失败：signals.error.emit(str(e))
    """

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn()
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


