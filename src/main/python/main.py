import logging
from threading import RLock

from PySide2.QtWebEngineWidgets import QWebEngineView

from PySide2.QtCore import QFile, QIODevice, QEvent, QObject, Qt
from PySide2.QtGui import QPixmapCache
from PySide2.QtWidgets import QFileDialog, QLabel, QAction, QSlider, QPushButton, QGroupBox, QGraphicsView, QListWidget, \
    QLineEdit
from fbs_runtime.application_context.PySide2 import ApplicationContext
from PySide2.QtUiTools import QUiLoader

import sys

from classes.Utils import json_to_html
from classes.VideoStream import VideoStream
from classes.Shape import Shape, ShapeType

logger = logging.getLogger('Main')


class VideoEventFilter(QObject):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

    def eventFilter(self, obj, event):
        # logger.debug(event.type())

        if event.type() == QEvent.Resize:
            if self.main.video:
                self.main.video.refresh()
            return True

        if self.main.video is not None and not self.main.video.is_playing:
            if event.type() == QEvent.Leave:
                if self.main.drawing_shape is not None:
                    self.main.hide_pointer()
                return True

            if event.type() == QEvent.MouseButtonPress:
                x, y = self.main.video.get_video_coord(event.x(), event.y())
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
                x, y = self.main.video.get_video_coord(event.x(), event.y())

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

        self.draw_mutex = RLock()
        self.video: VideoStream = None

        self.was_playing = False

        self.video_pressed = False

        self.drawing_shape = None
        self.drawing_pointer = Shape('drawing_pointer', 0, ShapeType.pointer)

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

        self.ui_web_json_shape: QWebEngineView = self.window.findChild(QWebEngineView, 'web_json_shape')

        self.ui_list_messages: QListWidget = self.window.findChild(QListWidget, 'list_messages')
        self.ui_edit_new_message: QLineEdit = self.window.findChild(QLineEdit, 'edit_new_message')
        self.ui_btn_add_new_message: QPushButton = self.window.findChild(QPushButton, 'btn_add_new_message')
        self.ui_btn_remove_message: QPushButton = self.window.findChild(QPushButton, 'btn_remove_message')
        self.ui_btn_edit_message: QPushButton = self.window.findChild(QPushButton, 'btn_edit_message')

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

        self.ui_btn_add_new_message.clicked.connect(self.ui_btn_add_new_message_clicked)
        self.ui_btn_remove_message.clicked.connect(self.ui_btn_remove_message_clicked)
        self.ui_btn_edit_message.clicked.connect(self.ui_btn_edit_message_clicked)

        QPixmapCache.setCacheLimit(1024 * 1024 * 1024)

        self.appctxt.app.aboutToQuit.connect(self.about_to_quit)

        self.window.show()

        self.load_video("/Users/robertonegro/Desktop/UniTN/Fundamentals of Image and Video Processing/video.mp4")

        exit_code = self.appctxt.app.exec_()
        sys.exit(exit_code)

    def get_selected_message(self):
        selected_items = self.ui_list_messages.selectedItems()
        if selected_items:
            for item in selected_items:
                return item
        return ''

    def add_message_to_list(self, message):
        self.ui_list_messages.addItem(message)

    def remove_selected_message_from_list(self):
        selected_items = self.ui_list_messages.selectedItems()
        if selected_items:
            for item in selected_items:
                self.ui_list_messages.takeItem(self.ui_list_messages.row(item))

    def ui_btn_add_new_message_clicked(self):
        self.add_message_to_list(self.ui_edit_new_message.text())
        self.ui_edit_new_message.setText('')

    def ui_btn_remove_message_clicked(self):
        self.remove_selected_message_from_list()

    def ui_btn_edit_message_clicked(self):
        text = self.get_selected_message().text()
        self.remove_selected_message_from_list()
        self.ui_edit_new_message.setText(text)

    def update_pointer(self, refresh=True):
        self.show_pointer(refresh=refresh)

    def show_pointer(self, refresh=True):
        self.video.add_modifier(self.drawing_pointer)
        if refresh:
            self.video.refresh()

    def hide_pointer(self, refresh=True):
        self.video.remove_modifier(self.drawing_pointer)
        if refresh:
            self.video.refresh()

    def reset_shape(self, refresh=True):
        if self.drawing_shape is not None:
            self.video.remove_modifier(self.drawing_shape)
            self.drawing_shape = None
            self.ui_web_json_shape.setHtml('')
            if refresh:
                self.video.refresh()

    def draw_shape(self, shape_type, refresh=True):
        if self.video:
            self.pause()
            self.reset_shape(refresh=False)
            self.drawing_shape = Shape('drawing_shape', self.video.get_frameindex, shape_type)
            self.update_shape(refresh=refresh)

    def update_shape(self, refresh=True):
        if self.drawing_shape is not None:
            self.video.add_modifier(self.drawing_shape)
            self.ui_web_json_shape.setHtml(json_to_html(self.drawing_shape.to_json(hide_id=True)))
            if refresh:
                self.video.refresh()
        else:
            self.ui_web_json_shape.setHtml('')

    def ui_btn_shape_global_clicked(self):
        self.draw_shape(ShapeType.globals)

    def ui_btn_shape_rectangle_clicked(self):
        self.draw_shape(ShapeType.rectangle)

    def ui_btn_shape_ellipse_clicked(self):
        self.draw_shape(ShapeType.ellipse)

    def ui_btn_shape_polygon_clicked(self):
        self.draw_shape(ShapeType.polygon)

    def ui_btn_play_clicked(self):
        if self.video:
            if self.video.is_playing:
                self.pause()
            else:
                self.play()

    def pause(self):
        if self.video:
            if self.video.is_playing:
                self.video.pause()
                self.ui_btn_play.setText('Play')

    def play(self):
        if self.video:
            if not self.video.is_playing:
                self.reset_shape(refresh=False)
                self.video.refresh(play_after_refresh=True)
                self.ui_btn_play.setText('Pause')

    def ui_slider_timeline_sliderPressed(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.was_playing = self.video.is_playing
            self.pause()
            self.ui_slider_timeline.valueChanged.connect(self.ui_slider_timeline_valueChanged)

    def ui_slider_timeline_valueChanged(self):
        if self.video:
            new_frame_index = self.ui_slider_timeline.value()
            self.video.skip_to_frame(new_frame_index)

    def ui_slider_timeline_sliderReleased(self):
        self.ui_slider_timeline.valueChanged.disconnect()
        if self.video:
            new_frame_index = self.ui_slider_timeline.value()
            self.video.skip_to_frame(new_frame_index, play_after_skip=self.was_playing)

    def ui_btn_add5sec_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.add_seconds(5)

    def ui_btn_rem5sec_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.remove_seconds(5)

    def ui_btn_add10sec_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.add_seconds(10)

    def ui_btn_rem10sec_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.remove_seconds(10)

    def ui_btn_add30sec_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.add_seconds(30)

    def ui_btn_rem30sec_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.remove_seconds(30)

    def ui_btn_add1frame_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.add_frames(1)

    def ui_btn_rem1frame_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.remove_frames(1)

    def ui_btn_add5frame_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.add_frames(5)

    def ui_btn_rem5frame_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.remove_frames(5)

    def ui_btn_add10frame_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.add_frames(10)

    def ui_btn_rem10frame_clicked(self):
        if self.video:
            self.reset_shape(refresh=False)
            self.video.remove_frames(10)

    def ui_slider_speed_valueChanged(self):
        if self.video:
            slider_value = self.ui_slider_speed.value()
            speed = slider_value * 0.25
            self.ui_lbl_speed.setText(f'{speed}x')
            self.video.set_speed(speed)

    def on_frame_drawn(self, frame, index):
        self.draw_mutex.acquire()

        if self.video.is_playing:
            self.ui_slider_timeline.setValue(self.video.get_frameindex)

        self.ui_lbl_video.setPixmap(frame)
        self.ui_grp_time.setTitle(f'Time: {self.video.get_timestamp} / {self.video.get_total_length}')
        self.ui_grp_frame.setTitle(f'Frame: {self.video.get_frameindex + 1} / {self.video.get_total_frames}')

        if self.drawing_shape is not None:
            self.drawing_shape.frame = self.video.get_frameindex + 1

        self.draw_mutex.release()

    def ui_action_load_video_triggered(self):
        filename, file_filter = QFileDialog.getOpenFileName(parent=self.window,
                                                            caption='Open file',
                                                            dir='.',
                                                            filter='Movie Files (*.mp4)')

        if filename:
            self.load_video(filename)

    def load_video(self, filename):
        self.video = VideoStream(filename, self.ui_lbl_video)
        self.video.frame_drawn.connect(self.on_frame_drawn)

        self.ui_slider_speed.setValue(4)
        self.ui_slider_speed.setEnabled(True)

        self.ui_slider_timeline.setMaximum(self.video.get_total_frames - 1)
        self.ui_slider_timeline.setEnabled(True)

        self.play()

    def about_to_quit(self):
        self.video.destroy()


if __name__ == '__main__':
    Main()
