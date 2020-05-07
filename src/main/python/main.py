import logging
import uuid
from threading import RLock

from PySide2.QtWebEngineWidgets import QWebEngineView

from PySide2.QtCore import QFile, QIODevice, QEvent, QObject, Qt
from PySide2.QtGui import QPixmapCache
from PySide2.QtWidgets import QFileDialog, QLabel, QAction, QSlider, QPushButton, QGroupBox, QGraphicsView, QListWidget, \
    QLineEdit
from fbs_runtime.application_context.PySide2 import ApplicationContext
from PySide2.QtUiTools import QUiLoader

import sys

from classes.VideoStream import VideoStream
from classes.Utils import json_to_html
from classes.Shape import Shape, ShapeType

logger = logging.getLogger('Main')


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

        ui_file_name = "ui/mainwindow.ui"
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

        self.ui_web_json_shape: QWebEngineView = self.window.findChild(QWebEngineView, 'web_json_shape')

        self.ui_list_timeline: QListWidget = self.window.findChild(QListWidget, 'list_timeline')
        self.ui_btn_edit_timeline: QPushButton = self.window.findChild(QPushButton, 'btn_edit_timeline')
        self.ui_btn_delete_timeline: QPushButton = self.window.findChild(QPushButton, 'btn_delete_timeline')

        self.ui_list_messages: QListWidget = self.window.findChild(QListWidget, 'list_messages')
        self.ui_edit_new_message: QLineEdit = self.window.findChild(QLineEdit, 'edit_new_message')
        self.ui_btn_add_new_message: QPushButton = self.window.findChild(QPushButton, 'btn_add_new_message')
        self.ui_btn_remove_message: QPushButton = self.window.findChild(QPushButton, 'btn_remove_message')
        self.ui_btn_edit_message: QPushButton = self.window.findChild(QPushButton, 'btn_edit_message')

        self.ui_btn_create_event: QPushButton = self.window.findChild(QPushButton, 'btn_create_event')

        self.ui_btn_add_new_message.setEnabled(False)
        self.ui_edit_new_message.textChanged.connect(self.ui_edit_new_message_text_changed)

        self.ui_action_load_video.triggered.connect(self.ui_action_load_video_triggered)
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

        QPixmapCache.setCacheLimit(1024 * 1024 * 1024)

        self.appctxt.app.aboutToQuit.connect(self.about_to_quit)

        self.window.show()

        self.load_video("/Users/robertonegro/Desktop/UniTN/Fundamentals of Image and Video Processing/video.mp4")

        exit_code = self.appctxt.app.exec_()
        sys.exit(exit_code)

    def list_timeline_get_selected(self):
        selected_indexes = self.ui_list_timeline.selectedIndexes()
        if selected_indexes:
            for i in selected_indexes:
                return self.timeline[i.row()]

    def update_list_timeline(self):
        self.ui_list_timeline.clear()
        for (frame, shape) in self.timeline:
            self.ui_list_timeline.addItem(f'{frame} - {shape.message} ({shape.shape})')

    def ui_list_timeline_item_changed(self):
        frame, shape = self.list_timeline_get_selected()

        if self.videostream:
            self.videostream.skip_to(frame)
            self.force_update_timeline_slider = True

    def update_btn_create_event(self):
        self.ui_btn_create_event.setEnabled(self.videostream is not None and
                                            self.drawing_shape is not None and
                                            self.drawing_shape.valid and len(self.ui_list_messages.selectedItems()) > 0)

    def ui_list_messages_item_changed(self):
        message = self.get_selected_message()
        if self.drawing_shape is not None:
            self.drawing_shape.message = message
            self.update_shape()
        self.update_btn_create_event()

    def ui_btn_create_event_clicked(self):
        if self.videostream is not None and self.drawing_shape is not None and self.drawing_shape.valid and len(
                self.ui_list_messages.selectedItems()) > 0:
            self.drawing_shape.id = uuid.uuid1()
            self.drawing_shape.color = (255, 0, 0)
            self.drawing_shape.last_color = (255, 0, 0)
            self.videostream.add_shape(self.videostream.current_frame, self.drawing_shape)
            self.timeline.append((self.videostream.current_frame, self.drawing_shape))
            self.update_list_timeline()
            self.reset_shape()

    def get_selected_message(self):
        selected_items = self.ui_list_messages.selectedItems()
        if selected_items:
            for item in selected_items:
                return item.text()
        return ''

    def ui_edit_new_message_text_changed(self):
        message = self.ui_edit_new_message.text().strip()
        self.ui_btn_add_new_message.setEnabled(len(message) > 0)

    def add_message_to_list(self, message):
        self.ui_list_messages.addItem(message)

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
            if self.drawing_shape is not None:
                self.videostream.remove_drawing_shape('drawing_shape')
                self.drawing_shape = None
                self.ui_web_json_shape.setHtml('')
                if refresh:
                    self.videostream.refresh()
        self.update_btn_create_event()

    def update_shape(self, refresh=True):
        if self.drawing_shape is not None:
            self.videostream.add_drawing_shape(self.drawing_shape)
            self.ui_web_json_shape.setHtml(json_to_html(self.drawing_shape.to_json(hide_id=True)))
            if refresh:
                self.videostream.refresh()
        else:
            self.ui_web_json_shape.setHtml('')
        self.update_btn_create_event()

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
            self.videostream.add_frames(frames)
            self.force_update_timeline_slider = True

    def add_seconds(self, seconds):
        if self.videostream:
            self.videostream.add_seconds(seconds)
            self.force_update_timeline_slider = True

    def ui_slider_speed_valueChanged(self):
        if self.videostream:
            slider_value = self.ui_slider_speed.value()
            speed = slider_value * 0.25
            self.ui_lbl_speed.setText(f'{speed}x')
            self.videostream.speed(speed)

    def on_frame_drawn(self, frame, index):
        self.draw_mutex.acquire()

        if self.videostream.playing or self.force_update_timeline_slider:
            if self.force_update_timeline_slider:
                self.force_update_timeline_slider = False
            self.ui_slider_timeline.setValue(self.videostream.current_frame)
        self.ui_grp_time.setTitle(f'Time: {self.videostream.current_timestamp} / {self.videostream.total_timestamp}')
        self.ui_grp_frame.setTitle(f'Frame: {self.videostream.current_frame + 1} / {self.videostream.total_frames}')

        self.ui_lbl_video.setPixmap(frame)

        if self.drawing_shape is not None:
            self.drawing_shape.frame = self.videostream.current_frame + 1

        self.ui_slider_timeline.setMaximum(self.videostream.total_frames - 1)
        self.ui_slider_timeline.setEnabled(True)

        self.draw_mutex.release()

    def ui_action_load_video_triggered(self):
        filename, file_filter = QFileDialog.getOpenFileName(parent=self.window,
                                                            caption='Open file',
                                                            dir='.',
                                                            filter='Movie Files (*.mp4)')

        if filename:
            self.load_video(filename)

    def load_video(self, filename):
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
