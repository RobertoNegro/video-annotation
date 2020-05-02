from threading import RLock

import PySide2
from PySide2.QtCore import QFile, QIODevice, QTimer, QEvent, Qt, QObject
from PySide2.QtGui import QPixmap, QPixmapCache
from PySide2.QtWidgets import QFileDialog, QLabel, QAction, QSlider, QPushButton, QGroupBox, QGraphicsView, \
    QGraphicsScene
from fbs_runtime.application_context.PySide2 import ApplicationContext
from PySide2.QtUiTools import QUiLoader

import qimage2ndarray
import cv2
import sys
import math
import signal


from classes.VideoStream import VideoStream


class VideoEventFilter(QObject):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

    def eventFilter(self, obj, event):
        # print(event.type())
        if event.type() == QEvent.Resize:
            self.main.video.refresh()
            return True
        if event.type() == QEvent.MouseButtonPress:
            print(self.main.video.get_video_coord(event.x(), event.y()))
            return True
        if event.type() == QEvent.MouseButtonRelease:

            return True
        return False


class Main:
    def __init__(self):
        self.appctxt = ApplicationContext()

        ui_file_name = "ui/mainwindow.ui"
        ui_file = QFile(ui_file_name)
        if not ui_file.open(QIODevice.ReadOnly):
            print("Cannot open {}: {}".format(ui_file_name, ui_file.errorString()))
            sys.exit(-1)
        loader = QUiLoader()
        self.window = loader.load(ui_file)
        ui_file.close()
        if not self.window:
            print(loader.errorString())
            sys.exit(-1)

        self.draw_mutex = RLock()
        self.video: VideoStream = None

        self.ui_grp_video: QGraphicsView = self.window.findChild(QGraphicsView, 'grp_video')
        self.ui_lbl_video: QLabel = self.window.findChild(QLabel, 'lbl_video')
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

        self.was_playing = False
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

        self.ui_lbl_video.setMouseTracking(True)
        self.ui_lbl_video.setEnabled(True)
        self.video_filter = VideoEventFilter(self.ui_lbl_video, self)
        self.ui_lbl_video.installEventFilter(self.video_filter)

        self.load_video("/Users/robertonegro/Desktop/UniTN/Fundamentals of Image and Video Processing/video.mp4")
        QPixmapCache.setCacheLimit(1024*1024*1024)

        self.appctxt.app.aboutToQuit.connect(self.about_to_quit)

        self.window.show()

        exit_code = self.appctxt.app.exec_()
        sys.exit(exit_code)

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
                self.video.play()
                self.ui_btn_play.setText('Pause')

    def ui_slider_timeline_sliderPressed(self):
        if self.video:
            self.was_playing = self.video.is_playing
            self.pause()
            self.ui_slider_timeline.valueChanged.connect(self.ui_slider_timeline_valueChanged)

    def ui_slider_timeline_valueChanged(self):
        if self.video:
            new_frame_index = self.ui_slider_timeline.value()
            self.video.skip_to_frame(new_frame_index)

    def ui_slider_timeline_sliderReleased(self):
        self.ui_slider_timeline.valueChanged.disconnect()
        self.ui_slider_timeline_valueChanged()
        if self.was_playing:
            self.play()

    def ui_btn_add5sec_clicked(self):
        if self.video:
            self.video.add_seconds(5)

    def ui_btn_rem5sec_clicked(self):
        if self.video:
            self.video.remove_seconds(5)

    def ui_btn_add10sec_clicked(self):
        if self.video:
            self.video.add_seconds(10)

    def ui_btn_rem10sec_clicked(self):
        if self.video:
            self.video.remove_seconds(10)

    def ui_btn_add30sec_clicked(self):
        if self.video:
            self.video.add_seconds(30)

    def ui_btn_rem30sec_clicked(self):
        if self.video:
            self.video.remove_seconds(30)

    def ui_btn_add1frame_clicked(self):
        if self.video:
            self.video.add_frames(1)

    def ui_btn_rem1frame_clicked(self):
        if self.video:
            self.video.remove_frames(1)

    def ui_btn_add5frame_clicked(self):
        if self.video:
            self.video.add_frames(5)

    def ui_btn_rem5frame_clicked(self):
        if self.video:
            self.video.remove_frames(5)

    def ui_btn_add10frame_clicked(self):
        if self.video:
            self.video.add_frames(10)

    def ui_btn_rem10frame_clicked(self):
        if self.video:
            self.video.remove_frames(10)

    def ui_slider_speed_valueChanged(self):
        if self.video:
            slider_value = self.ui_slider_speed.value()
            speed = slider_value * 0.25
            self.ui_lbl_speed.setText(f'{speed}x')
            self.video.set_speed(speed)

    def on_frame_drawn(self, frame, index):
        self.draw_mutex.acquire()

        self.ui_lbl_video.setPixmap(frame)
        self.ui_grp_time.setTitle(f'Time: {self.video.get_timestamp} / {self.video.get_total_length}')
        self.ui_grp_frame.setTitle(f'Frame: {self.video.get_frameindex + 1} / {self.video.get_total_frames}')

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
