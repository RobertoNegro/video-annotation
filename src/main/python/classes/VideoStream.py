import math
import time
from queue import Queue, Empty
from threading import RLock, Thread

import cv2
import qimage2ndarray
from PySide2.QtCore import QThread, QObject, Signal
from PySide2.QtGui import QPixmap, QPixmapCache
from PySide2.QtWidgets import QLabel


class VideoStream(QObject):
    @staticmethod
    def __frameindex_to_formatted_time(frame, fps):
        hours = math.floor(frame / fps / 60 / 60)
        minutes = math.floor(frame / fps / 60) - hours * 60
        seconds = math.floor(frame / fps) - hours * 60 * 60 - minutes * 60
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    @staticmethod
    def __frame_draw_global(frame, area_width, area_height):
        cv2.rectangle(frame, (0, 0), (area_width, area_height), (0, 0, 255), 3)
        return frame

    @staticmethod
    def __frame_draw_border(frame, frame_index):
        cv2.putText(frame, f"{int(frame_index)}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255))
        return frame

    @staticmethod
    def __get_resized_size(area_width, area_height, video_width, video_height):
        video_ratio = video_width / video_height
        ratio_width = area_height * video_ratio
        ratio_height = area_width / video_ratio

        w = min(area_width, video_width, ratio_width)
        h = min(area_height, video_height, ratio_height)
        return int(w), int(h)

    @staticmethod
    def __frame_resize(frame, w, h):
        frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
        return frame

    @staticmethod
    def __frame_convert_colors(frame):
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return frame

    @staticmethod
    def __frame_to_qpixmap(frame):
        image = qimage2ndarray.array2qimage(frame)
        return QPixmap.fromImage(image)

    @staticmethod
    def __get_video_total_frames(video):
        """
        The count is sometimes bigger than the real
        number of valid frames contained in the video
        :return: The total number of valid frames
        """

        index = video.get(cv2.CAP_PROP_FRAME_COUNT)
        video.set(cv2.CAP_PROP_POS_FRAMES, index)
        check = False
        while not check:
            check, frame = video.read()
            if not check:
                index -= 1
                video.set(cv2.CAP_PROP_POS_FRAMES, index)
        return int(index + 1)

    @property
    def is_playing(self):
        return self.__is_playing

    @property
    def get_timestamp(self):
        return VideoStream.__frameindex_to_formatted_time(self.__render_index, self.__video_fps)

    @property
    def get_total_length(self):
        return VideoStream.__frameindex_to_formatted_time(self.get_total_frames, self.__video_fps)

    @property
    def get_frameindex(self):
        return self.__render_index

    @property
    def get_total_frames(self):
        return self.__video_total_frames

    def get_video_coord(self, container_x, container_y):
        container_w = self.__container.frameGeometry().width()
        container_h = self.__container.frameGeometry().height()
        w, h = VideoStream.__get_resized_size(container_w,
                                              container_h,
                                              self.__video_width,
                                              self.__video_height)

        container_x -= (container_w - w) / 2
        container_y -= (container_h - h) / 2

        container_x = int(max(min(container_x, w), 0))
        container_y = int(max(min(container_y, h), 0))

        x = self.__video_width * container_x / w
        y = self.__video_height * container_y / h
        return int(x), int(y)

    def pause(self):
        if self.is_playing:
            self.__is_playing = False
            print(f'Pause')

    def play(self):
        if not self.is_playing:
            self.__is_playing = True
            print(f'Play')

    def add_seconds(self, seconds):
        self.skip_to_frame(min(self.__render_index + self.__video_fps * seconds, self.__video_total_frames - 1))

    def remove_seconds(self, seconds):
        self.skip_to_frame(max(0, self.__render_index - self.__video_fps * seconds))

    def add_frames(self, frames):
        self.skip_to_frame(min(self.__render_index + frames, self.__video_total_frames - 1))

    def remove_frames(self, frames):
        self.skip_to_frame(max(0, self.__render_index - frames))

    def refresh(self):
        self.skip_to_frame(self.__render_index)

    def skip_to_frame(self, new_next_index):
        if new_next_index < 0:
            new_next_index = 0
        elif new_next_index > self.__video_total_frames - 1:
            new_next_index = self.__video_total_frames - 1

        print(f'Skipping to: {new_next_index}')

        self.__skip_lock.acquire()
        while not self.__cache.empty():
            try:
                self.__cache.get_nowait()
            except Empty:
                pass

        self.__skip_to = int(new_next_index)
        self.__skip_lock.release()

    def set_speed(self, speed: float):
        self.__speed = speed

    def __render_frame(self):
        frame = None
        while True:
            interval = 1.0 / (self.__video_fps * self.__speed)
            interval = 0.016 if interval < 0.016 else interval

            if frame is None or self.__is_playing or self.__render_skip:
                self.__render_skip = False
                frame, index = self.__cache.get()
                render_time = time.time()
                self.__render_index = index

                print(f'R {self.__render_index} ({QThread.currentThread().objectName()})')

                self.frame_drawn.emit(frame, index)

                while time.time() - render_time < interval:
                   pass

    def __cache_frame(self):
        while True:
            self.__skip_lock.acquire()
            if self.__skip_to is not None:
                self.__cache_next_index = self.__skip_to
                self.__skip_to = None
                self.__skip_lock.release()

                self.__video.set(cv2.CAP_PROP_POS_FRAMES, self.__cache_next_index)

                # Clean again because, if queue full, after cleaning in skip_to_frame will be added
                # one more spurious frame from the previous stream that was waiting on queue.put()
                while not self.__cache.empty():
                    try:
                        self.__cache.get_nowait()
                    except Empty:
                        pass

                print(f'C SKIP -> {self.__cache_next_index}, c flushed, r skip ({QThread.currentThread().objectName()})')
                self.__render_skip = True
            else:
                self.__skip_lock.release()
                self.__cache_next_index += 1

            check, frame = self.__video.read()
            if check:
                resized_w, resized_h = VideoStream.__get_resized_size(self.__container.frameGeometry().width(),
                                                                      self.__container.frameGeometry().height(),
                                                                      self.__video_width,
                                                                      self.__video_height)

                frame = VideoStream.__frame_resize(frame, resized_w, resized_h)
                frame = VideoStream.__frame_draw_global(frame, resized_w, resized_h)
                frame = VideoStream.__frame_convert_colors(frame)
                frame = VideoStream.__frame_to_qpixmap(frame)

                self.__cache_index = self.__cache_next_index
                self.__cache.put((frame, self.__cache_index))

                print(
                    f'C {self.__cache_index}, {self.__cache.qsize()} in C ({QThread.currentThread().objectName()})')

    frame_drawn = Signal(QPixmap, int)

    def destroy(self):
        self.__render_thread.terminate()
        self.__cache_thread.terminate()

    def __init__(self, filename: str, container: QLabel):
        super(VideoStream, self).__init__()
        self.__video = cv2.VideoCapture(filename)
        self.__container = container

        self.__is_playing = False
        self.__render_index = 0
        self.__cache_index = 0
        self.__cache_next_index = 0
        self.__skip_lock = RLock()
        self.__skip_to = 0
        self.__render_skip = False
        self.__render_skip_lock = RLock()
        self.__cache = Queue(10)

        self.__video_fps = self.__video.get(cv2.CAP_PROP_FPS)
        self.__video_width = self.__video.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.__video_height = self.__video.get(cv2.CAP_PROP_FRAME_HEIGHT)
        self.__video_total_frames = VideoStream.__get_video_total_frames(self.__video)

        print(f'FPS: {self.__video_fps}')
        print(f'Resolution: {self.__video_width} x {self.__video_height}')
        print(f'Total frames: {self.__video_total_frames}')

        self.__speed = 1

        # self.__render_thread = Thread(target=self.__render_frame, args=())
        # self.__cache_thread = Thread(target=self.__cache_frame, args=())
        self.__render_thread = QThread()
        self.__render_thread.setObjectName('RenderThread')
        self.__render_thread.run = self.__render_frame
        self.__cache_thread = QThread()
        self.__cache_thread.setObjectName('CacheThread')
        self.__cache_thread.run = self.__cache_frame

        self.__render_thread.start()
        self.__cache_thread.start()



