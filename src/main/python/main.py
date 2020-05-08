import json
import logging
import uuid
from threading import RLock

from PySide2.QtCore import QFile, QIODevice, QEvent, QObject, Qt, QDir
from PySide2.QtGui import QPixmapCache
from PySide2.QtWidgets import QFileDialog, QLabel, QAction, QSlider, QPushButton, QGroupBox, QGraphicsView, QListWidget, \
    QLineEdit, QMenu, QMessageBox, QTextEdit
from fbs_runtime.application_context.PySide2 import ApplicationContext
from PySide2.QtUiTools import QUiLoader

import sys

from classes.VideoStream import VideoStream
from classes.Utils import json_to_html
from classes.Shape import Shape, ShapeType

logger = logging.getLogger('Main')

# DEPENDENCIES:
# Python 3.6
# pip install numpy Pygments coloredlogs PySide2 opencv-python-headless qimage2ndarray fbs pyinstaller==3.4

# if "Can not find path ./libshiboken2.abi3.5.14.dylib" on freeze,
# copy ~/.conda/envs/<YOUR_ENV>/lib/python3.6/site-packages/shiboken2/libshiboken2.abi3.5.14.dylib
# to .../site-packages/PyInstaller/hooks/ and .../site-packages/PySide2/

class EditNewMessageFilter(QObject):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return:
                self.main.ui_btn_add_new_message_clicked()
            elif event.key() == Qt.Key_Escape:
                self.main.ui_edit_new_message.clearFocus()
            else:
                return QLineEdit.eventFilter(self, obj, event)
            return True
        return QLineEdit.eventFilter(self, obj, event)


class GlobalEventFilter(QObject):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Up:
                if event.modifiers() & Qt.ShiftModifier == Qt.ShiftModifier:
                    self.main.ui_edit_new_message.setFocus()
                else:
                    self.main.select_prev_message()
                return True
            if event.key() == Qt.Key_Down:
                if event.modifiers() & Qt.ShiftModifier == Qt.ShiftModifier:
                    self.main.ui_edit_new_message.setFocus()
                else:
                    self.main.select_next_message()
                return True
            if not hasattr(self.main, 'ui_edit_new_message') or not self.main.ui_edit_new_message.hasFocus():
                if event.key() == Qt.Key_Return:
                    self.main.ui_btn_create_event_clicked()
                    return True
                if event.key() == Qt.Key_Escape:
                    if not self.main.videostream.playing:
                        self.main.reset_shape()
                    return True
                if event.key() == Qt.Key_G:
                    self.main.ui_btn_shape_global_clicked()
                    return True
                if event.key() == Qt.Key_R:
                    self.main.ui_btn_shape_rectangle_clicked()
                    return True
                if event.key() == Qt.Key_E:
                    self.main.ui_btn_shape_ellipse_clicked()
                    return True
                if event.key() == Qt.Key_P:
                    self.main.ui_btn_shape_polygon_clicked()
                    return True
                if event.key() == Qt.Key_L:
                    self.main.ui_btn_shape_line_clicked()
                    return True
                if event.key() == Qt.Key_Space:
                    if self.main.videostream.playing:
                        self.main.pause()
                    else:
                        self.main.play()
                    return True
                if event.key() == Qt.Key_Right:
                    if self.main.videostream.playing:
                        self.main.ui_btn_add5sec_clicked()
                    else:
                        self.main.ui_btn_add1frame_clicked()
                    return True
                if event.key() == Qt.Key_Left:
                    if self.main.videostream.playing:
                        self.main.ui_btn_rem5sec_clicked()
                    else:
                        self.main.ui_btn_rem1frame_clicked()
                    return True
        return False


class VideoEventFilter(QObject):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

    def eventFilter(self, obj, event):
        # logger.debug(event.type())

        if event.type() == QEvent.Resize:
            if self.main.videostream:
                self.main.videostream.resize(self.main.ui_lbl_video.frameGeometry().width(),
                                             self.main.ui_lbl_video.frameGeometry().height())
                self.main.videostream.refresh()
            return True

        if self.main.videostream is not None and not self.main.videostream.playing:
            if event.type() == QEvent.Leave:
                if self.main.drawing_shape is not None:
                    self.main.hide_pointer()
                return True

            if event.type() == QEvent.MouseButtonPress:
                x, y = self.main.videostream.get_video_coord(event.x(), event.y())
                logger.debug(f'Click on ({x}, {y})')
                if event.button() == Qt.MouseButton.LeftButton:
                    self.main.video_pressed = True
                    if self.main.drawing_shape is not None:
                        self.main.hide_pointer(refresh=False)

                if self.main.drawing_shape is not None:
                    if event.button() == Qt.MouseButton.LeftButton:
                        if self.main.drawing_shape.full:
                            self.main.drawing_shape.reset()
                        self.main.drawing_shape.add_point(x, y)
                    else:
                        self.main.drawing_shape.remove_last()
                    self.main.update_shape()
                return True

            if event.type() == QEvent.MouseMove or event.type() == QEvent.MouseButtonRelease:
                x, y = self.main.videostream.get_video_coord(event.x(), event.y())

                if self.main.video_pressed:
                    if event.type() == QEvent.MouseButtonRelease:
                        logger.debug(f'Release on ({x}, {y})')
                        self.main.video_pressed = False
                        if self.main.drawing_shape is not None:
                            self.main.drawing_pointer.remove_last()
                            self.main.drawing_pointer.add_point(x, y)
                            self.main.show_pointer(refresh=False)

                    if self.main.drawing_shape is not None:
                        if len(self.main.drawing_shape.points) > 1:
                            self.main.drawing_shape.remove_last()
                        self.main.drawing_shape.add_point(x, y)
                        self.main.update_shape()
                else:
                    if self.main.drawing_shape is not None:
                        self.main.drawing_pointer.remove_last()
                        self.main.drawing_pointer.add_point(x, y)
                        self.main.update_pointer()
                return True

        return False


class Main:
    def __init__(self):
        self.appctxt = ApplicationContext()

        ui_file_name = self.appctxt.get_resource("mainwindow.ui")
        ui_file = QFile(ui_file_name)
        if not ui_file.open(QIODevice.ReadOnly):
            logger.error("Cannot open {}: {}".format(ui_file_name, ui_file.errorString()))
            sys.exit(-1)
        loader = QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()
        if not self.window:
            logger.error(loader.errorString())
            sys.exit(-1)

        self.window_filter = GlobalEventFilter(self.appctxt.app, self)
        self.appctxt.app.installEventFilter(self.window_filter)

        self.videostream: VideoStream = None

        self.draw_mutex = RLock()

        self.force_update_timeline_slider = False
        self.was_playing = False

        self.video_pressed = False

        self.drawing_shape = None
        self.drawing_pointer = Shape('drawing_pointer', ShapeType.pointer)

        self.timeline = []

        self.ui_lbl_video: QLabel = self.window.findChild(QLabel, 'lbl_video')
        self.ui_lbl_video.setMouseTracking(True)

        self.video_filter = VideoEventFilter(self.ui_lbl_video, self)
        self.ui_lbl_video.installEventFilter(self.video_filter)

        self.ui_action_load_video: QAction = self.window.findChild(QAction, 'action_load_video')
        self.ui_action_load_annotations: QAction = self.window.findChild(QAction, 'action_load_annotations')
        self.ui_action_save_annotations: QAction = self.window.findChild(QAction, 'action_save_annotations')

        self.ui_slider_speed: QSlider = self.window.findChild(QSlider, 'slider_speed')
        self.ui_lbl_speed: QLabel = self.window.findChild(QLabel, 'lbl_speed')
        self.ui_btn_play: QPushButton = self.window.findChild(QPushButton, 'btn_play')
        self.ui_btn_add5sec: QPushButton = self.window.findChild(QPushButton, 'btn_add5sec')
        self.ui_btn_rem5sec: QPushButton = self.window.findChild(QPushButton, 'btn_rem5sec')
        self.ui_btn_add10sec: QPushButton = self.window.findChild(QPushButton, 'btn_add10sec')
        self.ui_btn_rem10sec: QPushButton = self.window.findChild(QPushButton, 'btn_rem10sec')
        self.ui_btn_add30sec: QPushButton = self.window.findChild(QPushButton, 'btn_add30sec')
        self.ui_btn_rem30sec: QPushButton = self.window.findChild(QPushButton, 'btn_rem30sec')
        self.ui_btn_add1frame: QPushButton = self.window.findChild(QPushButton, 'btn_add1frame')
        self.ui_btn_rem1frame: QPushButton = self.window.findChild(QPushButton, 'btn_rem1frame')
        self.ui_btn_add5frame: QPushButton = self.window.findChild(QPushButton, 'btn_add5frame')
        self.ui_btn_rem5frame: QPushButton = self.window.findChild(QPushButton, 'btn_rem5frame')
        self.ui_btn_add10frame: QPushButton = self.window.findChild(QPushButton, 'btn_add10frame')
        self.ui_btn_rem10frame: QPushButton = self.window.findChild(QPushButton, 'btn_rem10frame')
        self.ui_lbl_timeline: QLabel = self.window.findChild(QLabel, 'lbl_timeline')
        self.ui_slider_timeline: QSlider = self.window.findChild(QSlider, 'slider_timeline')
        self.ui_grp_time: QGroupBox = self.window.findChild(QGroupBox, 'grp_time')
        self.ui_grp_frame: QGroupBox = self.window.findChild(QGroupBox, 'grp_frame')

        self.ui_btn_shape_global: QPushButton = self.window.findChild(QPushButton, 'btn_shape_global')
        self.ui_btn_shape_rectangle: QPushButton = self.window.findChild(QPushButton, 'btn_shape_rectangle')
        self.ui_btn_shape_ellipse: QPushButton = self.window.findChild(QPushButton, 'btn_shape_ellipse')
        self.ui_btn_shape_polygon: QPushButton = self.window.findChild(QPushButton, 'btn_shape_polygon')
        self.ui_btn_shape_line: QPushButton = self.window.findChild(QPushButton, 'btn_shape_line')

        self.ui_text_json_shape: QTextEdit = self.window.findChild(QTextEdit, 'text_json_shape')

        self.ui_list_timeline: QListWidget = self.window.findChild(QListWidget, 'list_timeline')
        self.ui_btn_edit_timeline: QPushButton = self.window.findChild(QPushButton, 'btn_edit_timeline')
        self.ui_btn_delete_timeline: QPushButton = self.window.findChild(QPushButton, 'btn_delete_timeline')

        self.ui_list_messages: QListWidget = self.window.findChild(QListWidget, 'list_messages')
        self.ui_edit_new_message: QLineEdit = self.window.findChild(QLineEdit, 'edit_new_message')
        self.ui_btn_add_new_message: QPushButton = self.window.findChild(QPushButton, 'btn_add_new_message')
        self.ui_btn_remove_message: QPushButton = self.window.findChild(QPushButton, 'btn_remove_message')
        self.ui_btn_edit_message: QPushButton = self.window.findChild(QPushButton, 'btn_edit_message')

        self.ui_btn_create_event: QPushButton = self.window.findChild(QPushButton, 'btn_create_event')

        self.ui_action_help: QAction = self.window.findChild(QAction, 'action_help')
        self.ui_action_help.triggered.connect(self.show_help)

        self.ui_action_about: QAction = self.window.findChild(QAction, 'action_about')
        self.ui_action_about.triggered.connect(self.show_about)

        self.ui_btn_add_new_message.setEnabled(False)
        self.ui_edit_new_message.textChanged.connect(self.ui_edit_new_message_text_changed)

        self.edit_new_message_filter = EditNewMessageFilter(self.ui_edit_new_message, self)
        self.ui_edit_new_message.installEventFilter(self.edit_new_message_filter)

        self.ui_action_load_video.triggered.connect(self.ui_action_load_video_triggered)
        self.ui_action_load_annotations.triggered.connect(self.ui_action_load_annotations_triggered)
        self.ui_action_save_annotations.triggered.connect(self.ui_action_save_annotations_triggered)

        self.ui_slider_speed.valueChanged.connect(self.ui_slider_speed_valueChanged)
        self.ui_btn_play.clicked.connect(self.ui_btn_play_clicked)
        self.ui_btn_add5sec.clicked.connect(self.ui_btn_add5sec_clicked)
        self.ui_btn_rem5sec.clicked.connect(self.ui_btn_rem5sec_clicked)
        self.ui_btn_add10sec.clicked.connect(self.ui_btn_add10sec_clicked)
        self.ui_btn_rem10sec.clicked.connect(self.ui_btn_rem10sec_clicked)
        self.ui_btn_add30sec.clicked.connect(self.ui_btn_add30sec_clicked)
        self.ui_btn_rem30sec.clicked.connect(self.ui_btn_rem30sec_clicked)
        self.ui_btn_add1frame.clicked.connect(self.ui_btn_add1frame_clicked)
        self.ui_btn_rem1frame.clicked.connect(self.ui_btn_rem1frame_clicked)
        self.ui_btn_add5frame.clicked.connect(self.ui_btn_add5frame_clicked)
        self.ui_btn_rem5frame.clicked.connect(self.ui_btn_rem5frame_clicked)
        self.ui_btn_add10frame.clicked.connect(self.ui_btn_add10frame_clicked)
        self.ui_btn_rem10frame.clicked.connect(self.ui_btn_rem10frame_clicked)

        self.ui_slider_timeline.sliderPressed.connect(self.ui_slider_timeline_sliderPressed)
        self.ui_slider_timeline.sliderReleased.connect(self.ui_slider_timeline_sliderReleased)

        self.ui_btn_shape_global.clicked.connect(self.ui_btn_shape_global_clicked)
        self.ui_btn_shape_rectangle.clicked.connect(self.ui_btn_shape_rectangle_clicked)
        self.ui_btn_shape_ellipse.clicked.connect(self.ui_btn_shape_ellipse_clicked)
        self.ui_btn_shape_polygon.clicked.connect(self.ui_btn_shape_polygon_clicked)
        self.ui_btn_shape_line.clicked.connect(self.ui_btn_shape_line_clicked)

        self.ui_btn_add_new_message.clicked.connect(self.ui_btn_add_new_message_clicked)
        self.ui_btn_remove_message.clicked.connect(self.ui_btn_remove_message_clicked)
        self.ui_btn_edit_message.clicked.connect(self.ui_btn_edit_message_clicked)

        self.ui_btn_create_event.clicked.connect(self.ui_btn_create_event_clicked)

        self.update_btn_create_event()
        self.ui_list_messages.itemSelectionChanged.connect(self.ui_list_messages_item_changed)

        self.ui_list_timeline.itemSelectionChanged.connect(self.ui_list_timeline_item_changed)
        self.ui_btn_edit_timeline.clicked.connect(self.ui_btn_edit_timeline_clicked)
        self.ui_btn_delete_timeline.clicked.connect(self.ui_btn_delete_timeline_clicked)

        QPixmapCache.setCacheLimit(1024 * 1024 * 1024)

        self.appctxt.app.aboutToQuit.connect(self.about_to_quit)

        self.window.show()

        exit_code = self.appctxt.app.exec_()
        sys.exit(exit_code)

    def show_help(self):
        msg_box = QMessageBox()
        msg_box.setText("Keyboard shortcuts")
        msg_box.setInformativeText("Up Arrow: Previous event message\n"
                                   "Down Arrow: Next event message\n"
                                   "Right Arrow: Next frame / forward 5 secs (if playing)\n"
                                   "Left Arrow: Previous frame / backward 5 secs (if playing)\n"
                                   "Shift + Up/Down Arrow: Insert new message\n"
                                   "Escape: Clear the current drawing shape\n"
                                   "Return: Create event\n"
                                   "Space: Play / Pause\n"
                                   "G: Global\n"
                                   "R: Rectangle\n"
                                   "E: Ellipse\n"
                                   "P: Polygon\n"
                                   "L: Line\n\nIn order to create a new event, you need to select a valid shape and a valid (non-empty) message.")
        msg_box.exec_()

    def show_about(self):
        msg_box = QMessageBox()
        msg_box.setText("Video Annotator")
        msg_box.setInformativeText("Video Annotator is created by Roberto Negro as a course project for the course Fundamentals of Image and Video Processing at University of Trento (a.y. 2019/20). If needed, you can contact me via e-mail at roberto.negro@studenti.unitn.it")
        msg_box.exec_()

    def ui_btn_edit_timeline_clicked(self):
        deleted = self.delete_selected_list_timeline()
        if deleted is not None:
            frame, shape = deleted
            shape.id = 'drawing_shape'
            shape.color = (0, 0, 255)
            shape.last_color = (0, 255, 255)
            self.reset_shape(refresh=False)
            self.drawing_shape = shape
            self.update_shape()

    def ui_btn_delete_timeline_clicked(self):
        self.delete_selected_list_timeline()

    def clear_timeline(self):
        if self.videostream is not None:
            self.videostream.clear_shapes()
        self.timeline.clear()
        self.update_list_timeline()

    def delete_selected_list_timeline(self):
        selected = self.list_timeline_get_selected()
        if selected is not None:
            index, frame, shape = selected
            self.videostream.remove_shape(shape.id)
            self.videostream.refresh()
            del self.timeline[index]
            self.update_list_timeline()
            return frame, shape
        return None

    def deselect_list_timeline(self):
        for i in range(self.ui_list_timeline.count()):
            item = self.ui_list_timeline.item(i)
            self.ui_list_timeline.setItemSelected(item, False)

    def list_timeline_get_selected(self):
        selected_indexes = self.ui_list_timeline.selectedIndexes()
        if selected_indexes:
            for i in selected_indexes:
                return (i.row(),) + self.timeline[i.row()]
        return None

    def update_list_timeline(self):
        self.ui_list_timeline.clear()
        for (frame, shape) in self.timeline:
            self.ui_list_timeline.addItem(f'{frame + 1} - {shape.message} ({shape.shape})')

    def ui_list_timeline_item_changed(self):
        selected = self.list_timeline_get_selected()
        if selected is not None:
            i, frame, shape = selected
            if self.videostream:
                self.videostream.highlight_shape(shape.id)
                self.pause()
                self.skip_to(frame)
        else:
            self.videostream.highlight_shape(None)
            self.videostream.refresh()
        self.ui_lbl_video.setFocus()

    def update_btn_create_event(self):
        self.ui_btn_create_event.setEnabled(self.videostream is not None and
                                            self.drawing_shape is not None and
                                            self.drawing_shape.valid and len(self.ui_list_messages.selectedItems()) > 0)

    def get_selected_message_index(self):
        selected_indexes = self.ui_list_messages.selectedIndexes()
        if selected_indexes:
            for i in selected_indexes:
                return i.row()
        return None

    def select_next_message(self):
        if self.ui_list_messages.count() > 0:
            index = self.get_selected_message_index()
            if index is not None:
                index += 1
                if index > self.ui_list_messages.count() - 1:
                    self.ui_edit_new_message.setFocus()
                index = min(index, self.ui_list_messages.count() - 1)
            else:
                index = self.ui_list_messages.count() - 1
            self.ui_list_messages.setCurrentItem(self.ui_list_messages.item(index))
        else:
            self.ui_edit_new_message.setFocus()

    def select_prev_message(self):
        if self.ui_list_messages.count() > 0:
            index = self.get_selected_message_index()
            if index is not None:
                index -= 1
                if index < 0:
                    self.ui_edit_new_message.setFocus()
                index = max(index, 0)
            else:
                index = 0
            self.ui_list_messages.setCurrentItem(self.ui_list_messages.item(index))
        else:
            self.ui_edit_new_message.setFocus()

    def ui_list_messages_item_changed(self):
        message = self.get_selected_message()
        if self.drawing_shape is not None:
            self.drawing_shape.message = message
            self.update_shape()
        self.update_btn_create_event()
        self.ui_lbl_video.setFocus()

    def ui_btn_create_event_clicked(self):
        if self.videostream is not None and self.drawing_shape is not None and self.drawing_shape.valid and len(
                self.ui_list_messages.selectedItems()) > 0:
            self.pause()
            self.drawing_shape.id = uuid.uuid1().hex
            self.drawing_shape.color = (255, 0, 0)
            self.drawing_shape.last_color = (255, 0, 0)
            self.videostream.add_shape(self.videostream.current_frame, self.drawing_shape)
            self.timeline.append((self.videostream.current_frame, self.drawing_shape))
            self.update_list_timeline()
            self.reset_shape()
        elif self.drawing_shape is not None and self.drawing_shape.valid:
            self.ui_edit_new_message.setFocus()

    def get_selected_message(self):
        selected_items = self.ui_list_messages.selectedItems()
        if selected_items:
            for item in selected_items:
                return item.text()
        return ''

    def ui_edit_new_message_text_changed(self):
        message = self.ui_edit_new_message.text().strip()
        self.ui_btn_add_new_message.setEnabled(len(message) > 0)

    def clear_messages(self):
        self.ui_list_messages.clear()

    def add_message_to_list(self, message):
        found = None
        for i in range(self.ui_list_messages.count()):
            temp_message = self.ui_list_messages.item(i)
            if temp_message.text() == message:
                found = temp_message

        if found is None:
            self.ui_list_messages.addItem(message)
            for i in range(self.ui_list_messages.count()):
                temp_message = self.ui_list_messages.item(i)
                if temp_message.text() == message:
                    self.ui_list_messages.setCurrentItem(temp_message)
                    break
        else:
            self.ui_list_messages.setCurrentItem(found)
        self.ui_lbl_video.setFocus()

    def remove_selected_message_from_list(self):
        selected_items = self.ui_list_messages.selectedItems()
        if selected_items:
            for item in selected_items:
                self.ui_list_messages.takeItem(self.ui_list_messages.row(item))

    def ui_btn_add_new_message_clicked(self):
        message = self.ui_edit_new_message.text().strip()
        if len(message) > 0:
            self.add_message_to_list(message)
            self.ui_edit_new_message.setText('')

    def ui_btn_remove_message_clicked(self):
        self.remove_selected_message_from_list()

    def ui_btn_edit_message_clicked(self):
        text = self.get_selected_message()
        self.remove_selected_message_from_list()
        self.ui_edit_new_message.setText(text)

    def update_pointer(self, refresh=True):
        self.show_pointer(refresh=refresh)

    def show_pointer(self, refresh=True):
        if self.videostream:
            self.videostream.add_drawing_shape(self.drawing_pointer)
            if refresh:
                self.videostream.refresh()

    def hide_pointer(self, refresh=True):
        if self.videostream:
            self.videostream.remove_drawing_shape(self.drawing_pointer.id)
            if refresh:
                self.videostream.refresh()

    def reset_shape(self, refresh=True):
        if self.videostream:
            self.videostream.remove_drawing_shape('drawing_shape')
            self.drawing_shape = None
            self.hide_pointer(refresh=False)
            self.ui_text_json_shape.setHtml('')
            if refresh:
                self.videostream.refresh()
        self.update_btn_create_event()

    def update_shape(self, refresh=True):
        if self.drawing_shape is not None:
            self.videostream.add_drawing_shape(self.drawing_shape)
            self.ui_text_json_shape.setHtml(json_to_html(self.drawing_shape.to_json(hide_id=True)))
            if refresh:
                self.videostream.refresh()
            self.update_btn_create_event()
        else:
            self.reset_shape(refresh)

    def draw_shape(self, shape_type, refresh=True):
        if self.videostream:
            self.pause()
            self.reset_shape(refresh=False)
            self.drawing_shape = Shape('drawing_shape', shape_type, color=(0, 0, 255), last_color=(0, 255, 255))
            self.drawing_shape.message = self.get_selected_message()
            self.update_shape(refresh=refresh)
        self.update_btn_create_event()

    def ui_btn_shape_global_clicked(self):
        self.draw_shape(ShapeType.globals, refresh=True)

    def ui_btn_shape_rectangle_clicked(self):
        self.draw_shape(ShapeType.rectangle)

    def ui_btn_shape_ellipse_clicked(self):
        self.draw_shape(ShapeType.ellipse)

    def ui_btn_shape_polygon_clicked(self):
        self.draw_shape(ShapeType.polygon)

    def ui_btn_shape_line_clicked(self):
        self.draw_shape(ShapeType.line)

    def ui_btn_play_clicked(self):
        if self.videostream:
            if self.videostream.playing:
                self.pause()
            else:
                self.play()

    def pause(self):
        if self.videostream:
            self.videostream.pause()
            self.ui_btn_play.setText('Play')

    def play(self):
        if self.videostream:
            self.deselect_list_timeline()
            self.hide_pointer()
            self.videostream.play()
            self.ui_btn_play.setText('Pause')

    def ui_slider_timeline_sliderPressed(self):
        if self.videostream:
            self.was_playing = self.videostream.playing
            self.pause()

            new_frame_index = self.ui_slider_timeline.value()
            self.videostream.skip_to(new_frame_index)

            self.ui_slider_timeline.valueChanged.connect(self.ui_slider_timeline_valueChanged)

    def ui_slider_timeline_valueChanged(self):
        if self.videostream:
            new_frame_index = self.ui_slider_timeline.value()
            self.videostream.skip_to(new_frame_index)

    def ui_slider_timeline_sliderReleased(self):
        if self.videostream:
            self.ui_slider_timeline.valueChanged.disconnect()

            new_frame_index = self.ui_slider_timeline.value()
            self.videostream.skip_to(new_frame_index)

            if self.was_playing:
                self.play()

    def ui_btn_add5sec_clicked(self):
        self.add_seconds(5)

    def ui_btn_rem5sec_clicked(self):
        self.add_seconds(-5)

    def ui_btn_add10sec_clicked(self):
        self.add_seconds(10)

    def ui_btn_rem10sec_clicked(self):
        self.add_seconds(-10)

    def ui_btn_add30sec_clicked(self):
        self.add_seconds(30)

    def ui_btn_rem30sec_clicked(self):
        self.add_seconds(-30)

    def ui_btn_add1frame_clicked(self):
        self.add_frames(1)

    def ui_btn_rem1frame_clicked(self):
        self.add_frames(-1)

    def ui_btn_add5frame_clicked(self):
        self.add_frames(5)

    def ui_btn_rem5frame_clicked(self):
        self.add_frames(-5)

    def ui_btn_add10frame_clicked(self):
        self.add_frames(10)

    def ui_btn_rem10frame_clicked(self):
        self.add_frames(-10)

    def add_frames(self, frames):
        if self.videostream:
            self.deselect_list_timeline()
            self.videostream.add_frames(frames)
            self.force_update_timeline_slider = True

    def add_seconds(self, seconds):
        if self.videostream:
            self.deselect_list_timeline()
            self.videostream.add_seconds(seconds)
            self.force_update_timeline_slider = True

    def skip_to(self, frame):
        if self.videostream:
            self.videostream.skip_to(frame)
            self.force_update_timeline_slider = True
            if self.videostream.playing:
                self.deselect_list_timeline()

    def ui_slider_speed_valueChanged(self):
        if self.videostream:
            slider_value = self.ui_slider_speed.value()
            speed = slider_value * 0.25
            self.ui_lbl_speed.setText(f'{speed}x')
            self.videostream.speed(speed)

    def on_frame_drawn(self, frame, current_frame, total_frames, current_timestamp, total_timestamp, playing):
        self.draw_mutex.acquire()

        if playing or self.force_update_timeline_slider:
            if self.force_update_timeline_slider:
                self.force_update_timeline_slider = False
            self.ui_slider_timeline.setValue(current_frame)
        self.ui_grp_time.setTitle(f'Time: {current_timestamp} / {total_timestamp}')
        self.ui_grp_frame.setTitle(f'Frame: {current_frame + 1} / {total_frames}')

        self.ui_lbl_video.setPixmap(frame)

        if self.drawing_shape is not None:
            self.drawing_shape.frame = current_frame + 1

        self.ui_slider_timeline.setMaximum(total_frames - 1)
        self.ui_slider_timeline.setEnabled(True)

        self.draw_mutex.release()

    def ui_action_save_annotations_triggered(self):
        if self.videostream is not None:
            self.pause()
            filename, file_filter = QFileDialog.getSaveFileName(parent=self.window,
                                                                caption='Save annotations',
                                                                dir=QDir.homePath(),
                                                                filter='JSON Files (*.json)')
            if filename:
                t = [shape.to_save_format(frame) for (frame, shape) in self.timeline]
                j = json.dumps(t, indent=2)
                with open(filename, 'w') as f:
                    f.write(j)

    def ui_action_load_annotations_triggered(self):
        if self.videostream is not None:
            self.pause()
            filename, file_filter = QFileDialog.getOpenFileName(parent=self.window,
                                                                caption='Open annotations',
                                                                dir=QDir.homePath(),
                                                                filter='JSON Files (*.json)')
            if filename:
                self.clear_shapes_and_messages()
                with open(filename) as f:
                    loaded_data = json.load(f)
                    new_messages = []
                    new_timeline = []
                    shapes = []

                    for t in loaded_data:
                        frame = t['frame']
                        shape = Shape.from_save_format(t)

                        new_timeline.append((frame, shape))

                        if shape.message not in new_messages:
                            new_messages.append(shape.message)

                        shapes.append((frame, shape))
                    self.videostream.set_shapes(shapes)
                    for m in new_messages:
                        self.add_message_to_list(m)

                    self.timeline = new_timeline
                    self.update_list_timeline()
                    self.videostream.refresh()

    def ui_action_load_video_triggered(self):
        filename, file_filter = QFileDialog.getOpenFileName(parent=self.window,
                                                            caption='Open file',
                                                            dir=QDir.homePath(),
                                                            filter='Movie Files (*.mp4)')

        if filename:
            self.load_video(filename)

    def clear_shapes_and_messages(self):
        self.reset_shape(refresh=False)
        self.clear_messages()
        self.clear_timeline()

    def load_video(self, filename):
        if self.videostream is not None and not self.videostream.is_destroyed:
            self.clear_shapes_and_messages()

            def after_destroying():
                self.videostream.destroyed.disconnect(after_destroying)
                self.load_video(filename)
            self.videostream.destroyed.connect(after_destroying)
            self.videostream.destroy()
        else:
            self.videostream = VideoStream()
            self.videostream.start(filename,
                                   self.ui_lbl_video.frameGeometry().width(), self.ui_lbl_video.frameGeometry().height())
            self.videostream.draw_frame_signal.connect(self.on_frame_drawn)

            self.ui_slider_speed.setValue(4)
            self.ui_slider_speed.setEnabled(True)

            self.play()

    def about_to_quit(self):
        if self.videostream:
            self.videostream.destroy()


if __name__ == '__main__':
    Main()
