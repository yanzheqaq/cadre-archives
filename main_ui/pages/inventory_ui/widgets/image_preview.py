from typing import Optional

from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QPixmap, QWheelEvent, QMouseEvent, QPainter, QPen, QColor


class ImagePreview(QGraphicsView):
    """图片预览控件：Ctrl+滚轮以鼠标为中心缩放，双击在自适应与放大间切换。"""

    selectionFinished = pyqtSignal(object)  # {"rect_norm": (nx, ny, nw, nh)}
    imageChanged = pyqtSignal(bool)         # True=has image, False=cleared

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = QGraphicsPixmapItem()
        # 关键：启用平滑变换，避免缩放时出现锯齿/马赛克
        self._pixmap_item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.addItem(self._pixmap_item)

        # 高质量渲染（缩放/平移更平滑）
        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing
        )
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        # 用自实现拖拽平移，避免部分平台 ScrollHandDrag “拖不动/边界卡住”
        self.setDragMode(QGraphicsView.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 避免局部更新导致的“断点”观感
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self._has_image = False
        self._is_zoomed = False
        self._panning = False
        self._pan_last = None
        self._zoom_base_fit = 1.0
        self._zoom_factor = 1.0  # 相对 fit 的倍率
        self.zoomChanged = None  # 可由外部绑定回调：fn(percent:int)
        # 框选模式（用于污点去除）
        self._select_mode = False
        self._select_one_shot = True
        self._select_start_scene = None
        self._select_rect_item = None  # type: Optional[QGraphicsRectItem]

        # 视觉风格（接近原 QLabel 占位）
        self.setStyleSheet(
            "background: #f5f7fa; color: #777; border: 1px dashed #cfd8dc; border-radius: 4px;"
        )

    def clear(self):
        self._pixmap_item.setPixmap(QPixmap())
        self._has_image = False
        self._is_zoomed = False
        self._zoom_base_fit = 1.0
        self._zoom_factor = 1.0
        self.resetTransform()
        self._scene.setSceneRect(0, 0, 1, 1)
        self._emit_zoom()
        self.imageChanged.emit(False)

    def set_image(self, pixmap: QPixmap, preserve_view: bool = False):
        if pixmap is None or pixmap.isNull():
            self.clear()
            return
        # 记录当前视图状态（用于保持缩放/中心）
        prev_has = self._has_image
        prev_zoom = float(getattr(self, "_zoom_factor", 1.0) or 1.0)
        prev_norm = None
        if preserve_view and prev_has:
            try:
                center_scene = self.mapToScene(self.viewport().rect().center())
                center_item = self._pixmap_item.mapFromScene(center_scene)
                bw = float(self._pixmap_item.boundingRect().width() or 0.0)
                bh = float(self._pixmap_item.boundingRect().height() or 0.0)
                if bw > 1 and bh > 1:
                    nx = max(0.0, min(1.0, float(center_item.x()) / bw))
                    ny = max(0.0, min(1.0, float(center_item.y()) / bh))
                    prev_norm = (nx, ny)
            except Exception:
                prev_norm = None

        self._pixmap_item.setPixmap(pixmap)
        self._has_image = True
        self._is_zoomed = False
        self.resetTransform()
        # 给 scene 一点边距，缩放后更容易拖到边角
        self._scene.setSceneRect(self._pixmap_item.boundingRect().adjusted(-20, -20, 20, 20))
        # 先 fit，建立基准缩放
        self.fit_in_view()

        # 若需要保持视图：恢复相对缩放倍率与中心点
        if preserve_view and prev_has:
            try:
                factor = max(0.05, min(20.0, prev_zoom))
                if abs(factor - 1.0) > 1e-6:
                    self.scale(factor, factor)
                    self._zoom_factor = factor
                    self._is_zoomed = True
                else:
                    self._zoom_factor = 1.0
                    self._is_zoomed = False
                if prev_norm is not None:
                    bw2 = float(self._pixmap_item.boundingRect().width() or 0.0)
                    bh2 = float(self._pixmap_item.boundingRect().height() or 0.0)
                    x = prev_norm[0] * bw2
                    y = prev_norm[1] * bh2
                    self.centerOn(self._pixmap_item.mapToScene(x, y))
            except Exception:
                pass

        self._emit_zoom()
        self.imageChanged.emit(True)

    def enable_selection_mode(self, enabled: bool, one_shot: bool = True):
        """
        启用框选矩形模式：
        - one_shot=True：框一次后自动退出（一次性）
        - one_shot=False：持续可用，框完后继续保持可框选状态（直到外部关闭）
        """
        self._select_mode = bool(enabled)
        self._select_one_shot = bool(one_shot)
        self._select_start_scene = None
        if self._select_rect_item is not None:
            try:
                self._scene.removeItem(self._select_rect_item)
            except Exception:
                pass
            self._select_rect_item = None
        self.setCursor(Qt.CrossCursor if self._select_mode else Qt.ArrowCursor)

    def _clear_selection_overlay(self):
        self._select_start_scene = None
        if self._select_rect_item is not None:
            try:
                self._scene.removeItem(self._select_rect_item)
            except Exception:
                pass
            self._select_rect_item = None

    def _pixmap_bounds(self) -> QRectF:
        try:
            return self._pixmap_item.boundingRect()
        except Exception:
            return QRectF(0, 0, 0, 0)

    def fit_in_view(self):
        if not self._has_image:
            return
        self.resetTransform()
        self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)
        # 记录 fit 的基准缩放（取 x 轴即可）
        self._zoom_base_fit = self.transform().m11() or 1.0
        self._zoom_factor = 1.0
        self._is_zoomed = False
        self._emit_zoom()

    def zoom_to(self, factor: float):
        if not self._has_image:
            return
        self.fit_in_view()
        # 在 fit 的基础上再放大
        self.scale(factor, factor)
        self._zoom_factor = factor
        self._is_zoomed = True
        self._emit_zoom()

    def wheelEvent(self, event: QWheelEvent):
        if (event.modifiers() & Qt.ControlModifier) and self._has_image:
            delta = event.angleDelta().y()
            step = 1.15 if delta > 0 else 1 / 1.15
            self.scale(step, step)
            # 更新相对倍率
            cur = self.transform().m11() or 1.0
            self._zoom_factor = cur / (self._zoom_base_fit or 1.0)
            self._is_zoomed = True
            self._emit_zoom()
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if not self._has_image:
            return super().mouseDoubleClickEvent(event)
        # 双击在“自适应”与“放大”间切换
        if self._is_zoomed:
            self.fit_in_view()
        else:
            # 默认放大 2x（以鼠标为中心）
            self.scale(2.0, 2.0)
            cur = self.transform().m11() or 1.0
            self._zoom_factor = cur / (self._zoom_base_fit or 1.0)
            self._is_zoomed = True
            self._emit_zoom()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if self._select_mode and event.button() == Qt.LeftButton and self._has_image:
            self._select_start_scene = self.mapToScene(event.pos())
            if self._select_rect_item is None:
                self._select_rect_item = QGraphicsRectItem()
                self._select_rect_item.setZValue(10)
                pen = QPen(QColor(59, 130, 246, 220))
                pen.setWidth(2)
                self._select_rect_item.setPen(pen)
                self._select_rect_item.setBrush(QColor(59, 130, 246, 40))
                self._scene.addItem(self._select_rect_item)
            self._select_rect_item.setRect(QRectF(self._select_start_scene, self._select_start_scene))
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._has_image:
            self._panning = True
            self._pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._select_mode and self._select_start_scene is not None and self._select_rect_item is not None:
            cur = self.mapToScene(event.pos())
            rect = QRectF(self._select_start_scene, cur).normalized()
            # 限制在 pixmap bounds 内
            rect = rect.intersected(self._pixmap_item.sceneBoundingRect())
            self._select_rect_item.setRect(rect)
            event.accept()
            return
        if self._panning and self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            # 注意：滚动条方向与鼠标拖拽方向相反
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._select_mode and event.button() == Qt.LeftButton and self._select_start_scene is not None and self._select_rect_item is not None:
            rect_scene = self._select_rect_item.rect().normalized()
            # 转换到图像坐标（pixmap item 局部坐标）
            tl = self._pixmap_item.mapFromScene(rect_scene.topLeft())
            br = self._pixmap_item.mapFromScene(rect_scene.bottomRight())
            x1, y1 = max(0.0, tl.x()), max(0.0, tl.y())
            x2, y2 = max(0.0, br.x()), max(0.0, br.y())
            w = max(0.0, x2 - x1)
            h = max(0.0, y2 - y1)
            bw = float(self._pixmap_bounds().width() or 0.0)
            bh = float(self._pixmap_bounds().height() or 0.0)
            # 发出信号（取整数像素）
            if w >= 2 and h >= 2 and bw > 1 and bh > 1:
                nx = max(0.0, min(1.0, x1 / bw))
                ny = max(0.0, min(1.0, y1 / bh))
                nw = max(0.0, min(1.0, w / bw))
                nh = max(0.0, min(1.0, h / bh))
                self.selectionFinished.emit({"rect_norm": (nx, ny, nw, nh)})
            # 清理本次选择框；是否退出由 one_shot 决定
            if self._select_one_shot:
                self.enable_selection_mode(False, one_shot=True)
            else:
                self._clear_selection_overlay()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._panning:
            self._panning = False
            self._pan_last = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _emit_zoom(self):
        if callable(self.zoomChanged):
            percent = int(round((self._zoom_factor or 1.0) * 100))
            self.zoomChanged(percent)


