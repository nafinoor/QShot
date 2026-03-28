#!/usr/bin/env python3
"""
QShot - Screenshot and Annotation Tool for Ubuntu 24.04 LTS
Dependencies: PyQt6, Pillow, requests
Install: pip install PyQt6 Pillow requests
"""

import sys
import io
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog,
                             QColorDialog, QSpinBox, QMessageBox, QSystemTrayIcon,
                             QMenu, QDialog, QLineEdit, QComboBox, QScrollArea)
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QEvent
from PyQt6.QtGui import (QPainter, QPen, QColor, QPixmap, QImage, QCursor, 
                        QIcon, QScreen, QGuiApplication, QKeySequence, QShortcut, QFontMetrics)
from datetime import datetime
import tempfile
import os



class ScreenshotSelector(QWidget):
    """Widget for selecting screenshot area"""
    screenshot_taken = pyqtSignal(QPixmap, QRect)
    
    def __init__(self, screenshot):
        super().__init__()
        self.screenshot = screenshot
        self.begin = QPoint()
        self.end = QPoint()
        self.is_selecting = False
        
        # Make fullscreen and frameless
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        # Set the screenshot as background
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        
    def paintEvent(self, event):
        painter = QPainter(self)
        
        # Draw dimmed screenshot
        painter.setOpacity(0.3)
        painter.drawPixmap(0, 0, self.screenshot)
        painter.setOpacity(1.0)
        
        # Draw selection rectangle
        if self.is_selecting and not self.begin.isNull() and not self.end.isNull():
            rect = QRect(self.begin, self.end).normalized()
            
            # Draw clear area (undimmed)
            painter.setClipRect(rect)
            painter.drawPixmap(rect, self.screenshot, rect)
            painter.setClipping(False)
            
            # Draw selection border
            pen = QPen(QColor(0, 120, 215), 2)
            painter.setPen(pen)
            painter.drawRect(rect)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.begin = event.pos()
            self.end = self.begin
            self.is_selecting = True
            self.update()
            
    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end = event.pos()
            self.update()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            rect = QRect(self.begin, self.end).normalized()
            
            if rect.width() > 5 and rect.height() > 5:
                # Capture the selected area
                cropped = self.screenshot.copy(rect)
                self.screenshot_taken.emit(cropped, rect)
                self.close()
            else:
                self.close()
                
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


class AnnotationEditor(QMainWindow):
    """Main annotation editor window"""
    
    def __init__(self, pixmap):
        super().__init__()
        self.original_pixmap = pixmap
        self.pixmap = pixmap.copy()
        
        # Drawing state
        self.drawing = False
        self.last_point = QPoint()
        self.current_tool = "pen"
        self.pen_color = QColor(255, 0, 0)
        self.pen_width = 3
        self.temp_start = None
        self.temp_end = None
        # Pen stroke points accumulated during a single drag
        self._pen_points = []
        # History for multi-step undo
        self.history = []
        self.redo_stack = []
        self.max_history = 20
        # Annotation model: each annotation is a dict {pixmap, pos(QPoint), bbox(QRect), type, meta}
        self.annotations = []
        self.selected_idx = None

        # Zoom state
        self.zoom = 1.0
        self.min_zoom = 0.2
        self.max_zoom = 5.0
        # Pan mode (space + drag)
        self.pan_mode = False
        # Runtime flags for interactions
        self.panning = False
        self.dragging_ann = False
        self.drag_start_pos = QPoint()
        self.drag_ann_orig_pos = QPoint()
        # Display mode: fit to window or actual size
        self.fit_mode = False
        self.display_pixmap = self.pixmap

        self.init_ui()
        # Shortcuts
        # install_shortcuts will be added later; safe call placeholder
        try:
            self.install_shortcuts()
        except Exception:
            pass
        
    def init_ui(self):
        self.setWindowTitle("Annotate your QShot")
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Toolbar
        toolbar = self.create_toolbar()
        layout.addLayout(toolbar)
        
        # Canvas label with mouse tracking inside a scroll area so window can be resized
        self.canvas = QLabel()
        self.canvas.setPixmap(self.pixmap)
        # Make the label size match the pixmap so scrollbars work when window is small
        self.canvas.adjustSize()
        try:
            self.canvas.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        except Exception:
            self.canvas.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.canvas.setMouseTracking(True)
        self.canvas.mousePressEvent = self.canvas_mouse_press
        self.canvas.mouseMoveEvent = self.canvas_mouse_move
        self.canvas.mouseReleaseEvent = self.canvas_mouse_release
        # Capture wheel and other events via eventFilter
        self.canvas.installEventFilter(self)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        # Do not auto-resize widget to scroll area; keep canvas at pixmap size
        self.scroll.setWidgetResizable(False)
        layout.addWidget(self.scroll)
        
        # Action buttons
        action_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save to File")
        save_btn.clicked.connect(self.save_to_file)
        action_layout.addWidget(save_btn)
        
        upload_btn = QPushButton("Upload to Cloud")
        upload_btn.clicked.connect(self.upload_to_cloud)
        action_layout.addWidget(upload_btn)
        
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        action_layout.addWidget(copy_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        action_layout.addWidget(cancel_btn)
        
        layout.addLayout(action_layout)
        
        # Start with a reasonable default window size (so controls remain visible)
        start_w = min(self.pixmap.width() + 50, 1200)
        start_h = min(self.pixmap.height() + 150, 800)
        self.resize(start_w, start_h)

        # Set initial display pixmap (actual or scaled will be chosen in showEvent)
        # Use a short timer to allow layout to compute sizes before fitting
        QTimer.singleShot(0, lambda: None)
        # Compose initial display from base image + annotations (none yet)
        self.compose_annotations()
        
    def create_toolbar(self):
        toolbar = QHBoxLayout()

        # Tool selection
        pen_btn = QPushButton("Pen")
        pen_btn.clicked.connect(lambda: self.set_tool("pen"))
        toolbar.addWidget(pen_btn)

        rect_btn = QPushButton("Rectangle")
        rect_btn.clicked.connect(lambda: self.set_tool("rectangle"))
        toolbar.addWidget(rect_btn)

        arrow_btn = QPushButton("Arrow")
        arrow_btn.clicked.connect(lambda: self.set_tool("arrow"))
        toolbar.addWidget(arrow_btn)

        text_btn = QPushButton("Text")
        text_btn.clicked.connect(lambda: self.set_tool("text"))
        toolbar.addWidget(text_btn)

        # Color picker
        color_btn = QPushButton("Color")
        color_btn.clicked.connect(self.choose_color)
        toolbar.addWidget(color_btn)

        # Fit / Actual size
        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.fit_to_window)
        toolbar.addWidget(fit_btn)

        actual_btn = QPushButton("Actual Size")
        actual_btn.clicked.connect(self.actual_size)
        toolbar.addWidget(actual_btn)

        # Pen width
        toolbar.addWidget(QLabel("Width:"))
        width_spin = QSpinBox()
        width_spin.setRange(1, 20)
        width_spin.setValue(3)
        width_spin.valueChanged.connect(self.set_pen_width)
        toolbar.addWidget(width_spin)

        # Undo button
        undo_btn = QPushButton("Undo")
        undo_btn.clicked.connect(self.undo)
        toolbar.addWidget(undo_btn)

        toolbar.addStretch()

        return toolbar
        
    def set_tool(self, tool):
        self.current_tool = tool
        
    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.pen_color = color
            
    def set_pen_width(self, width):
        self.pen_width = width
        


    def set_display_pixmap(self, pixmap):
        """Set the canvas pixmap taking fit_mode into account."""
        self.display_pixmap = pixmap
        if getattr(self, 'fit_mode', False):
            viewport = self.scroll.viewport().size()
            if viewport.width() > 0 and viewport.height() > 0:
                scaled = pixmap.scaled(viewport, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                # Use a copy when handing pixmap to the widget so we don't keep
                # a paint device alive that's being manipulated elsewhere.
                # Apply zoom on top of fit mode only if zoom != 1.0
                if self.zoom != 1.0:
                    scaled = scaled.scaled(int(scaled.width() * self.zoom), int(scaled.height() * self.zoom), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.canvas.setPixmap(scaled.copy())
            else:
                self.canvas.setPixmap(pixmap.copy())
        else:
            # Respect zoom when not in fit_mode
            if getattr(self, 'zoom', 1.0) != 1.0:
                w = int(pixmap.width() * self.zoom)
                h = int(pixmap.height() * self.zoom)
                scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.canvas.setPixmap(scaled.copy())
            else:
                self.canvas.setPixmap(pixmap.copy())
        self.canvas.adjustSize()
        # Ensure top-left is visible
        try:
            self.scroll.horizontalScrollBar().setValue(0)
            self.scroll.verticalScrollBar().setValue(0)
        except Exception:
            pass

    def widget_to_image(self, pos):
        """Convert a QPoint in widget (canvas) coordinates to image coordinates.

        When fit_mode is enabled the canvas shows a scaled pixmap; map back
        to the original image coordinate space so drawing occurs on the
        full-resolution pixmap.
        """
        # pos is in canvas widget coordinates
        try:
            pm = self.canvas.pixmap()
            if pm is None:
                return pos

            # The displayed pixmap already incorporates zoom/fit scaling. Map
            # back from widget/display coordinates to image coordinates.
            disp_pm = self.canvas.pixmap()
            if disp_pm is None:
                return pos

            disp_w = disp_pm.width()
            disp_h = disp_pm.height()
            img_w = self.display_pixmap.width()
            img_h = self.display_pixmap.height()
            if disp_w == 0 or disp_h == 0:
                return pos

            scale_x = img_w / disp_w
            scale_y = img_h / disp_h

            img_x = int(pos.x() * scale_x)
            img_y = int(pos.y() * scale_y)
            return QPoint(img_x, img_y)
        except Exception:
            return pos

    def set_preview_pixmap(self, pixmap):
        """Display a temporary preview pixmap (e.g. while dragging) respecting fit mode."""
        if getattr(self, 'fit_mode', False):
            viewport = self.scroll.viewport().size()
            if viewport.width() > 0 and viewport.height() > 0:
                scaled = pixmap.scaled(viewport, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                if getattr(self, 'zoom', 1.0) != 1.0:
                    scaled = scaled.scaled(int(scaled.width() * self.zoom), int(scaled.height() * self.zoom), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.canvas.setPixmap(scaled.copy())
            else:
                self.canvas.setPixmap(pixmap.copy())
        else:
            if getattr(self, 'zoom', 1.0) != 1.0:
                w = int(pixmap.width() * self.zoom)
                h = int(pixmap.height() * self.zoom)
                scaled = pixmap.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.canvas.setPixmap(scaled.copy())
            else:
                self.canvas.setPixmap(pixmap.copy())
        self.canvas.adjustSize()

    def compose_annotations(self):
        """Compose base image + all annotation layers into self.pixmap and update display."""
        base = self.original_pixmap.copy()
        painter = QPainter(base)
        try:
            for idx, ann in enumerate(self.annotations):
                painter.drawPixmap(ann['pos'], ann['pixmap'])
                # draw selection rectangle for selected annotation
                if idx == self.selected_idx:
                    pen = QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.drawRect(ann['bbox'])
        finally:
            painter.end()

        self.pixmap = base
        self.set_display_pixmap(self.pixmap)

    def push_history(self):
        """Snapshot the annotations list for undo."""
        # Store deep-ish copy: copy each pixmap and pos
        snap = []
        for ann in self.annotations:
            snap.append({'pixmap': ann['pixmap'].copy(), 'pos': QPoint(ann['pos']), 'bbox': QRect(ann['bbox']), 'type': ann.get('type'), 'meta': ann.get('meta')})
        self.history.append(snap)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        # clear redo on new action
        self.redo_stack.clear()

    def undo(self):
        if self.history:
            self.redo_stack.append(self.annotations)
            snap = self.history.pop()
            # restore
            self.annotations = []
            for ann in snap:
                self.annotations.append({'pixmap': ann['pixmap'].copy(), 'pos': QPoint(ann['pos']), 'bbox': QRect(ann['bbox']), 'type': ann.get('type'), 'meta': ann.get('meta')})
            self.selected_idx = None
            self.compose_annotations()
        else:
            # fallback to original
            self.annotations = []
            self.selected_idx = None
            self.compose_annotations()

    def redo(self):
        if self.redo_stack:
            snap = self.redo_stack.pop()
            self.annotations = []
            for ann in snap:
                self.annotations.append({'pixmap': ann['pixmap'].copy(), 'pos': QPoint(ann['pos']), 'bbox': QRect(ann['bbox']), 'type': ann.get('type'), 'meta': ann.get('meta')})
            self.compose_annotations()

    def fit_to_window(self):
        self.fit_mode = True
        self.set_display_pixmap(self.pixmap)

    def actual_size(self):
        self.fit_mode = False
        self.set_display_pixmap(self.pixmap)

    def showEvent(self, event):
        # When first shown, decide whether to fit to window
        super().showEvent(event)
        try:
            viewport = self.scroll.viewport().size()
            if self.original_pixmap.width() > viewport.width() or self.original_pixmap.height() > viewport.height():
                self.fit_mode = True
                self.fit_to_window()
            else:
                self.fit_mode = False
                self.actual_size()
        except Exception:
            # Fallback: just show actual size
            self.fit_mode = False
            self.set_display_pixmap(self.pixmap)
        
    def canvas_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos_widget = event.pos()
            # Only accept clicks inside the displayed canvas area
            if self.canvas.rect().contains(pos_widget):
                # Map to image coordinates if needed
                pos = self.widget_to_image(pos_widget)
                # Save state for undo
                self.push_history()
                # Pan mode (space + drag)
                if getattr(self, 'pan_mode', False):
                    self.panning = True
                    self.pan_start = pos_widget
                    self.pan_orig_x = self.scroll.horizontalScrollBar().value()
                    self.pan_orig_y = self.scroll.verticalScrollBar().value()
                    return

                # Selection / moving
                if self.current_tool in ("select", "move"):
                    # If nothing selected, select the most recent annotation
                    if self.selected_idx is None and len(self.annotations) > 0:
                        self.selected_idx = len(self.annotations) - 1

                    # If click inside selected annotation, start dragging
                    if self.selected_idx is not None:
                        ann = self.annotations[self.selected_idx]
                        if ann['bbox'].contains(pos):
                            self.dragging_ann = True
                            self.drag_start_pos = pos
                            self.drag_ann_orig_pos = QPoint(ann['pos'])
                            self.drawing = False
                            return

                # Start normal drawing
                self.drawing = True
                self.last_point = pos
                self.temp_start = pos
                
    def canvas_mouse_move(self, event):
        pos_widget = event.pos()
        if not self.canvas.rect().contains(pos_widget):
            return
        pos = self.widget_to_image(pos_widget)
        # Handle dragging/moving selected annotation
        if getattr(self, 'dragging_ann', False) and self.selected_idx is not None:
            delta = pos - self.drag_start_pos
            new_pos = self.drag_ann_orig_pos + delta
            # Update annotation position and bbox
            ann = self.annotations[self.selected_idx]
            ann['pos'] = QPoint(new_pos)
            ann['bbox'] = QRect(ann['bbox'].translated(new_pos - ann['bbox'].topLeft()))
            self.compose_annotations()
            return
        # Handle panning
        if getattr(self, 'panning', False):
            delta_widget = event.pos() - self.pan_start
            self.scroll.horizontalScrollBar().setValue(self.pan_orig_x - delta_widget.x())
            self.scroll.verticalScrollBar().setValue(self.pan_orig_y - delta_widget.y())
            return

        if self.drawing:
            if self.current_tool == "pen":
                self._pen_points.append(pos)
            else:
                # Constraint modifiers
                mods = QApplication.keyboardModifiers()
                if mods & Qt.KeyboardModifier.ShiftModifier and self.temp_start is not None:
                    # Constrain proportions: square for rectangle, straight line for arrow
                    dx = pos.x() - self.temp_start.x()
                    dy = pos.y() - self.temp_start.y()
                    if self.current_tool == "rectangle":
                        length = max(abs(dx), abs(dy))
                        sx = self.temp_start.x()
                        sy = self.temp_start.y()
                        pos = QPoint(sx + (length if dx >= 0 else -length), sy + (length if dy >= 0 else -length))
                    elif self.current_tool in ("arrow", "line"):
                        # snap to horizontal or vertical based on larger delta
                        if abs(dx) > abs(dy):
                            pos.setY(self.temp_start.y())
                        else:
                            pos.setX(self.temp_start.x())

                self.temp_end = pos
                self.update_temp_drawing()
                
    def canvas_mouse_release(self, event):
        if getattr(self, 'dragging_ann', False):
            # Finish dragging
            self.dragging_ann = False
            return

        if getattr(self, 'panning', False):
            self.panning = False
            return

        if event.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            pos_widget = event.pos()
            pos = self.widget_to_image(pos_widget)
            self.temp_end = pos
            
            if self.current_tool == "rectangle":
                self.draw_rectangle(self.temp_start, pos)
            elif self.current_tool == "arrow":
                self.draw_arrow(self.temp_start, pos)
            elif self.current_tool == "text":
                self.add_text(pos)
            elif self.current_tool == "line":
                self.draw_line(self.temp_start, pos)
            elif self.current_tool == "pen":
                self._pen_points.append(pos)
                self.draw_polyline(self._pen_points)
                self._pen_points = []
                
            self.temp_start = None
            self.temp_end = None
            
    def draw_polyline(self, points):
        if len(points) < 2:
            return
        min_x = min(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_x = max(p.x() for p in points)
        max_y = max(p.y() for p in points)
        pad = int(self.pen_width * 2) + 2
        bbox = QRect(min_x, min_y, max_x - min_x, max_y - min_y).adjusted(-pad, -pad, pad, pad)
        if bbox.width() <= 0 or bbox.height() <= 0:
            return

        ann_pm = QPixmap(bbox.size())
        ann_pm.fill(QColor(0, 0, 0, 0))

        painter = QPainter(ann_pm)
        try:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine))
            for i in range(len(points) - 1):
                local_a = QPoint(points[i].x() - bbox.left(), points[i].y() - bbox.top())
                local_b = QPoint(points[i + 1].x() - bbox.left(), points[i + 1].y() - bbox.top())
                painter.drawLine(local_a, local_b)
        finally:
            painter.end()

        ann = {'pixmap': ann_pm, 'pos': QPoint(bbox.topLeft()), 'bbox': QRect(bbox), 'type': 'pen', 'meta': {}}
        self.annotations.append(ann)
        self.selected_idx = len(self.annotations) - 1
        self.compose_annotations()

    def draw_line(self, start, end):
        self.draw_polyline([start, end])
        
    def draw_rectangle(self, start, end):
        bbox = QRect(start, end).normalized()
        if bbox.width() <= 0 or bbox.height() <= 0:
            return

        ann_pm = QPixmap(bbox.size())
        ann_pm.fill(QColor(0, 0, 0, 0))

        painter = QPainter(ann_pm)
        try:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine))
            rect_local = QRect(0, 0, bbox.width() - 1, bbox.height() - 1)
            painter.drawRect(rect_local)
        finally:
            painter.end()

        ann = {'pixmap': ann_pm, 'pos': QPoint(bbox.topLeft()), 'bbox': QRect(bbox), 'type': 'rectangle', 'meta': {}}
        self.annotations.append(ann)
        self.selected_idx = len(self.annotations) - 1
        self.compose_annotations()
        
    def draw_arrow(self, start, end):
        # Build bbox with margin for arrow head
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = (dx * dx + dy * dy) ** 0.5
        head_len = max(10, self.pen_width * 3)
        pad = int(head_len + self.pen_width * 2)
        bbox = QRect(start, end).normalized().adjusted(-pad, -pad, pad, pad)
        if bbox.width() <= 0 or bbox.height() <= 0:
            return

        ann_pm = QPixmap(bbox.size())
        ann_pm.fill(QColor(0, 0, 0, 0))

        local_start = QPoint(start.x() - bbox.left(), start.y() - bbox.top())
        local_end = QPoint(end.x() - bbox.left(), end.y() - bbox.top())

        painter = QPainter(ann_pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine))
            painter.drawLine(local_start, local_end)

            if length > 0:
                ux = dx / length
                uy = dy / length
                px = -uy
                py = ux
                left_x = local_end.x() - int(ux * head_len + px * (head_len / 2))
                left_y = local_end.y() - int(uy * head_len + py * (head_len / 2))
                right_x = local_end.x() - int(ux * head_len - px * (head_len / 2))
                right_y = local_end.y() - int(uy * head_len - py * (head_len / 2))
                painter.drawLine(local_end, QPoint(left_x, left_y))
                painter.drawLine(local_end, QPoint(right_x, right_y))
        finally:
            painter.end()

        ann = {'pixmap': ann_pm, 'pos': QPoint(bbox.topLeft()), 'bbox': QRect(bbox), 'type': 'arrow', 'meta': {}}
        self.annotations.append(ann)
        self.selected_idx = len(self.annotations) - 1
        self.compose_annotations()
        
    def add_text(self, pos):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Add Text", "Enter text:")
        if ok and text:
            font = self.font()
            font.setPointSize(12)
            fm = QFontMetrics(font)
            w = fm.horizontalAdvance(text) + 8
            h = fm.height() + 6

            ann_pm = QPixmap(w, h)
            ann_pm.fill(QColor(0, 0, 0, 0))
            painter = QPainter(ann_pm)
            try:
                painter.setPen(QPen(self.pen_color))
                painter.setFont(font)
                painter.drawText(QPoint(4, fm.ascent() + 2), text)
            finally:
                painter.end()

            ann = {'pixmap': ann_pm, 'pos': QPoint(pos.x() - 4, pos.y() - fm.ascent() - 2), 'bbox': QRect(pos.x() - 4, pos.y() - fm.ascent() - 2, w, h), 'type': 'text', 'meta': {'text': text, 'font': font}}
            self.annotations.append(ann)
            self.selected_idx = len(self.annotations) - 1
            self.compose_annotations()
            
    def update_temp_drawing(self):
        # Create a temporary pixmap to draw previews on so we never paint
        # directly onto the widget-held pixmap. Always ensure painter.end()
        # is called to avoid leaving a QPainter active on a device.
        temp_pixmap = self.pixmap.copy()
        painter = QPainter(temp_pixmap)
        try:
            painter.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.DashLine))

            if self.current_tool == "rectangle" and self.temp_start and self.temp_end:
                painter.drawRect(QRect(self.temp_start, self.temp_end).normalized())

            elif self.current_tool in ("arrow", "line") and self.temp_start and self.temp_end:
                start = self.temp_start
                end = self.temp_end
                painter.drawLine(start, end)

                if self.current_tool == "arrow":
                    # draw arrow head
                    dx = end.x() - start.x()
                    dy = end.y() - start.y()
                    length = (dx * dx + dy * dy) ** 0.5
                    if length > 0:
                        ux = dx / length
                        uy = dy / length
                        head_len = max(10, self.pen_width * 3)
                        px = -uy
                        py = ux
                        left_x = end.x() - int(ux * head_len + px * (head_len / 2))
                        left_y = end.y() - int(uy * head_len + py * (head_len / 2))
                        right_x = end.x() - int(ux * head_len - px * (head_len / 2))
                        right_y = end.y() - int(uy * head_len - py * (head_len / 2))
                        painter.drawLine(end, QPoint(left_x, left_y))
                        painter.drawLine(end, QPoint(right_x, right_y))

            elif self.current_tool == "pen" and len(self._pen_points) > 0:
                for i in range(len(self._pen_points) - 1):
                    painter.drawLine(self._pen_points[i], self._pen_points[i + 1])

        finally:
            painter.end()

        # Show preview respecting fit mode
        self.set_preview_pixmap(temp_pixmap)

    # ---------------- Shortcuts, events, zoom & selection helpers ----------------
    def install_shortcuts(self):
        # Editing
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_to_file)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.save_to_file)
        QShortcut(QKeySequence("Delete"), self, activated=self.delete_selected)

        # Tools
        QShortcut(QKeySequence("P"), self, activated=lambda: self.set_tool("pen"))
        QShortcut(QKeySequence("T"), self, activated=lambda: self.set_tool("text"))
        QShortcut(QKeySequence("R"), self, activated=lambda: self.set_tool("rectangle"))
        QShortcut(QKeySequence("A"), self, activated=lambda: self.set_tool("arrow"))
        QShortcut(QKeySequence("L"), self, activated=lambda: self.set_tool("line"))
        QShortcut(QKeySequence("E"), self, activated=lambda: self.set_tool("select"))

        # Zoom keys
        QShortcut(QKeySequence("Ctrl++"), self, activated=self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, activated=self.zoom_out)

        # Copy / Paste annotations and copy final image
        QShortcut(QKeySequence("Ctrl+C"), self, activated=self.copy_annotation)
        QShortcut(QKeySequence("Ctrl+V"), self, activated=self.paste_annotation)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, activated=self.copy_to_clipboard)

        # Redo alternate
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo)

        # Save / upload
        QShortcut(QKeySequence("Ctrl+U"), self, activated=self.upload_to_cloud)

    def delete_selected(self):
        if self.selected_idx is not None and 0 <= self.selected_idx < len(self.annotations):
            self.push_history()
            self.annotations.pop(self.selected_idx)
            self.selected_idx = None
            self.compose_annotations()

    def copy_annotation(self):
        if self.selected_idx is not None and 0 <= self.selected_idx < len(self.annotations):
            ann = self.annotations[self.selected_idx]
            self._copied_annotation = {
                'pixmap': ann['pixmap'].copy(),
                'pos': QPoint(ann['pos']),
                'bbox': QRect(ann['bbox']),
                'type': ann.get('type'),
                'meta': ann.get('meta')
            }

    def paste_annotation(self):
        if getattr(self, '_copied_annotation', None) is not None:
            copied = self._copied_annotation
            ann_pm = copied['pixmap'].copy()
            pos = QPoint(copied['pos'])
            bbox = QRect(copied['bbox'])
            ann = {'pixmap': ann_pm, 'pos': pos, 'bbox': bbox, 'type': copied.get('type', 'pasted'), 'meta': copied.get('meta')}
            self.push_history()
            self.annotations.append(ann)
            self.selected_idx = len(self.annotations) - 1
            self.compose_annotations()

    def zoom_in(self):
        self.zoom_at(1.25)

    def zoom_out(self):
        self.zoom_at(0.8)

    def zoom_at(self, factor, widget_pos=None):
        """Zoom anchored at widget_pos (QPoint in canvas coordinates). If widget_pos is None use cursor."""
        if widget_pos is None:
            widget_pos = self.canvas.mapFromGlobal(QCursor.pos())

        # Determine image coordinate under cursor
        image_pos = self.widget_to_image(widget_pos)

        # Save previous offset
        prev_disp = self.canvas.pixmap()
        if prev_disp is None:
            return
        prev_disp_w = prev_disp.width()
        img_w = self.display_pixmap.width()
        prev_image_disp_x = int(image_pos.x() * prev_disp_w / img_w)
        prev_cursor_offset = prev_image_disp_x - self.scroll.horizontalScrollBar().value()

        # Apply zoom
        new_zoom = max(self.min_zoom, min(self.max_zoom, self.zoom * factor))
        if new_zoom == self.zoom:
            return
        self.zoom = new_zoom
        # Update display pixmap with new zoom
        self.set_display_pixmap(self.pixmap)

        # Restore scroll so that image_pos remains under cursor
        new_disp = self.canvas.pixmap()
        if new_disp is None:
            return
        new_disp_w = new_disp.width()
        new_image_disp_x = int(image_pos.x() * new_disp_w / img_w)
        new_scroll = new_image_disp_x - prev_cursor_offset
        self.scroll.horizontalScrollBar().setValue(int(new_scroll))

    def eventFilter(self, obj, event):
        # Intercept wheel events on canvas for zoom/scroll
        if obj is self.canvas and event.type() == QEvent.Type.Wheel:
            modifiers = QApplication.keyboardModifiers()
            delta = event.angleDelta().y()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                # Zoom anchored at mouse. QWheelEvent in Qt6 uses position() -> QPointF
                # Convert to QPoint for our zoom_at API.
                try:
                    widget_point = event.position().toPoint()
                except Exception:
                    # Fallback for older event API
                    widget_point = event.pos()

                # Zoom anchored at mouse
                if delta > 0:
                    self.zoom_at(1.25, widget_point)
                else:
                    self.zoom_at(0.8, widget_point)
                return True
            elif modifiers & Qt.KeyboardModifier.ShiftModifier:
                # Horizontal scroll
                self.scroll.horizontalScrollBar().setValue(self.scroll.horizontalScrollBar().value() - delta)
                return True
            else:
                # Let scrollarea handle vertical scrolling
                return False

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.pan_mode = True
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
        elif event.key() == Qt.Key.Key_Escape:
            # Deselect
            self.selected_idx = None
            self.compose_annotations()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.pan_mode = False
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().keyReleaseEvent(event)
        
    def save_to_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", 
            f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
        )
        if filename:
            self.pixmap.save(filename)
            QMessageBox.information(self, "Saved", f"Screenshot saved to {filename}")
            
    def upload_to_cloud(self):
        """Upload to imgur (free public image hosting)"""
        try:
            # Convert QPixmap to bytes using QByteArray
            from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            self.pixmap.save(buffer, "PNG")
            buffer.close()

            # Convert QByteArray to Python bytes
            image_data = byte_array.data()

            # Configurable client id + dry-run support
            client_id = os.getenv("IMGUR_CLIENT_ID", "546c25a59c58ad7")
            dry_run = os.getenv("IMGUR_DRY_RUN", "0") == "1"

            # Normalize to bytes if needed
            try:
                if isinstance(image_data, (bytes, bytearray)):
                    image_bytes = bytes(image_data)
                else:
                    image_bytes = bytes(image_data)
            except Exception:
                image_bytes = image_data

            if dry_run:
                # Save to temp file and show a file:// URL instead of uploading
                fd, path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                with open(path, "wb") as f:
                    f.write(image_bytes)

                url = f"file://{path}"
                # Show URL dialog (reuse success flow)
                dialog = QDialog(self)
                dialog.setWindowTitle("Dry Run - Image Saved Locally")
                layout = QVBoxLayout(dialog)
                layout.addWidget(QLabel("Dry run enabled. Image saved locally."))
                url_input = QLineEdit(url)
                url_input.setReadOnly(True)
                url_input.selectAll()
                layout.addWidget(url_input)
                copy_btn = QPushButton("Copy URL")
                copy_btn.clicked.connect(lambda: self.copy_url_to_clipboard(url))
                layout.addWidget(copy_btn)
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(dialog.accept)
                layout.addWidget(close_btn)
                dialog.exec()
                return

            # Upload to imgur using multipart file tuple
            headers = {"Authorization": f"Client-ID {client_id}"}
            files = {"image": ("screenshot.png", image_bytes, "image/png")}
            response = requests.post(
                "https://api.imgur.com/3/image",
                headers=headers,
                files=files,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                url = data["data"]["link"]
                
                # Show URL dialog
                dialog = QDialog(self)
                dialog.setWindowTitle("Upload Successful")
                layout = QVBoxLayout(dialog)
                
                layout.addWidget(QLabel("Image uploaded successfully!"))
                
                url_input = QLineEdit(url)
                url_input.setReadOnly(True)
                url_input.selectAll()
                layout.addWidget(url_input)
                
                copy_btn = QPushButton("Copy URL")
                copy_btn.clicked.connect(lambda: self.copy_url_to_clipboard(url))
                layout.addWidget(copy_btn)
                
                close_btn = QPushButton("Close")
                close_btn.clicked.connect(dialog.accept)
                layout.addWidget(close_btn)
                
                dialog.exec()
            else:
                QMessageBox.warning(self, "Upload Failed", "Failed to upload image to cloud")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Upload error: {str(e)}")
            
    def copy_url_to_clipboard(self, url):
        QGuiApplication.clipboard().setText(url)
        QMessageBox.information(self, "Copied", "URL copied to clipboard!")
        
    def copy_to_clipboard(self):
        QGuiApplication.clipboard().setPixmap(self.pixmap)
        QMessageBox.information(self, "Copied", "Screenshot copied to clipboard!")


class QShot(QMainWindow):
    """Main application window with system tray"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QShot")
        self.setGeometry(100, 100, 400, 200)
        
        self.init_ui()
        self.create_tray_icon()
        
        # Global shortcut (Ctrl+Shift+P)
        self.shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.shortcut.activated.connect(self.take_screenshot)
        
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        layout.addWidget(QLabel("QShot :: Snapshot Tool"))
        layout.addWidget(QLabel("Press Ctrl+Shift+P or use the system tray to capture"))
        
        capture_btn = QPushButton("Capture Screenshot")
        capture_btn.clicked.connect(self.take_screenshot)
        layout.addWidget(capture_btn)
        
    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        
        tray_menu = QMenu()
        capture_action = tray_menu.addAction("Capture Screenshot")
        capture_action.triggered.connect(self.take_screenshot)
        
        show_action = tray_menu.addAction("Show Window")
        show_action.triggered.connect(self.show)
        
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
    def take_screenshot(self):
        # Hide main window
        self.hide()
        
        # Small delay to let window hide
        QTimer.singleShot(200, self.capture_screen)
        
    def capture_screen(self):
        screen = QGuiApplication.primaryScreen()
        screenshot = screen.grabWindow(0)
        
        # Show selection widget
        self.selector = ScreenshotSelector(screenshot)
        self.selector.screenshot_taken.connect(self.on_screenshot_selected)
        self.selector.show()
        
    def on_screenshot_selected(self, pixmap, rect):
        # Open annotation editor
        self.editor = AnnotationEditor(pixmap)
        self.editor.show()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("QShot")
    
    window = QShot()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()