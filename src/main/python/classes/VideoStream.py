import logging
import math
import time
from queue import Queue, Empty
from threading import RLock, Condition

import cv2
import qimage2ndarray
from PySide2.QtCore import QThread, QObject, Signal
from PySide2.QtGui import QPixmap
from PySide2.QtWidgets import QLabel

from classes.Shape import Shape, ShapeType

logger = logging.getLogger('VideoStream')


class VideoStream(QObject):
    @staticmethod
    def __frameindex_to_formatted_time(frame, fps):
        hours = math.floor(frame / fps / 60 / 60)
        minutes = math.floor(frame / fps / 60) - hours * 60
        seconds = math.floor(frame / fps) - hours * 60 * 60 - minutes * 60
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

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
        video.set(cv2.CAP_PROP_POS_FRAMES, 0)
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
            logger.info(f'Pause')

    def play(self):
        if not self.is_playing:
            self.__is_playing = True
            logger.info(f'Play')

    def add_seconds(self, seconds):
        self.skip_to_frame(min(self.__render_index + self.__video_fps * seconds, self.__video_total_frames - 1))

    def remove_seconds(self, seconds):
        self.skip_to_frame(max(0, self.__render_index - self.__video_fps * seconds))

    def add_frames(self, frames):
        self.skip_to_frame(min(self.__render_index + frames, self.__video_total_frames - 1))

    def remove_frames(self, frames):
        self.skip_to_frame(max(0, self.__render_index - frames))

    def refresh(self, play_after_refresh=False):
        logger.render(f'Refreshing render')
        self.skip_to_frame(self.__render_index, play_after_skip=play_after_refresh)

    def clear_modifiers(self):
        self.__frame_modifiers_lock.acquire()
        self.__frame_modifiers.clear()
        self.__frame_modifiers_lock.release()

    def remove_modifier(self, shape: Shape):
        self.__frame_modifiers_lock.acquire()
        if shape.id in self.__frame_modifiers:
            del self.__frame_modifiers[shape.id]
        self.__frame_modifiers_lock.release()

    def add_modifier(self, shape: Shape):
        if shape.shape == ShapeType.globals:
            def modifier(frame):
                cv2.rectangle(frame, (0, 0), (int(self.__video_width), int(self.__video_height)), (0, 0, 255), 3)
                return frame
        elif shape.shape == ShapeType.pointer:
            def modifier(frame):
                if len(shape.points) >= 1:
                    x, y = shape.points[0]
                    if None not in (x, y):
                        cv2.line(frame, (x, 0), (x, int(self.__video_height)), (64, 64, 64), 3)
                        cv2.line(frame, (0, y), (int(self.__video_width), y), (64, 64, 64), 3)
                return frame
        elif shape.shape == ShapeType.ellipse:
            def modifier(frame):
                if len(shape.points) >= 2:
                    x1, y1 = shape.points[0]
                    x2, y2 = shape.points[1]
                    if None not in (x1, y1, x2, y2):
                        centerx = int((x1 + x2) / 2)
                        centery = int((y1 + y2) / 2)
                        sizex = int(abs(x1 - centerx))
                        sizey = int(abs(y1 - centery))

                        cv2.ellipse(frame, (centerx, centery), (sizex, sizey), 0, 0, 360, (0, 0, 255), 3)
                elif len(shape.points) == 1:
                    x, y = shape.points[0]
                    cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, (0, 0, 255), 3)
                return frame
        elif shape.shape == ShapeType.rectangle:
            def modifier(frame):
                if len(shape.points) >= 2:
                    x1, y1 = shape.points[0]
                    x2, y2 = shape.points[1]
                    if None not in (x1, y1, x2, y2):
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                elif len(shape.points) == 1:
                    x, y = shape.points[0]
                    cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, (0, 0, 255), 3)
                return frame
        elif shape.shape == ShapeType.polygon:
            def modifier(frame):
                if len(shape.points) > 1:
                    for i, p in enumerate(shape.points):
                        x1, y1 = shape.points[i]
                        if i == len(shape.points) - 1:
                            color = (0, 0, 255)
                            x2, y2 = shape.points[0]
                        else:
                            color = (255, 0, 0)
                            x2, y2 = shape.points[i + 1]

                        cv2.line(frame, (x1, y1), (x2, y2), color, 3)
                elif len(shape.points) == 1:
                    x, y = shape.points[0]
                    cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, (0, 0, 255), 3)

                return frame
        else:
            def modifier(frame):
                return frame
            logger.warning(f'Unknown shape while trying to add a new modifier: {shape.shape}')

        self.__frame_modifiers_lock.acquire()
        self.__frame_modifiers[shape.id] = modifier
        self.__frame_modifiers_lock.release()

    def skip_to_frame(self, new_next_index, play_after_skip=False):
        self.__skip_condition.acquire()
        self.__skip_to = new_next_index
        self.__skip_play_after = play_after_skip
        self.__skip_condition.notify()
        self.__skip_condition.release()
        logger.skip(f'Skipping to: {new_next_index}')

    def set_speed(self, speed: float):
        self.__speed = speed

    def __skip_frame(self):
        while True:
            self.__skip_condition.acquire()
            self.__skip_condition.wait()
            if self.__skip_to is not None:
                new_next_index = self.__skip_to
                play_after_skip = self.__skip_play_after
                self.__skip_to = None
                self.__skip_play_after = False

                if new_next_index < 0:
                    new_next_index = 0
                elif new_next_index > self.__video_total_frames - 1:
                    new_next_index = self.__video_total_frames - 1
                new_next_index = int(new_next_index)

                self.__skip_condition.release()

                logger.skip(f'S -> {new_next_index} (play after: {play_after_skip})')

                self.__caching_lock.acquire()
                self.__rendering_lock.acquire()

                self.__cache_next_index = new_next_index
                is_refresh = self.__cache_next_index == self.__render_index
                if is_refresh:
                    previous_refresh_cache = self.__refresh_cache
                    dim = 1
                    dim += self.__cache.qsize()
                    dim += 0 if previous_refresh_cache is None else previous_refresh_cache.qsize()

                    self.__refresh_cache = Queue(dim)
                    self.__refresh_cache.put(self.__render_original)
                    while not self.__cache.empty():
                        try:
                            _, original_frame, _ = self.__cache.get_nowait()
                            self.__refresh_cache.put(original_frame)
                        except Empty:
                            pass
                    if previous_refresh_cache is not None:
                        while not previous_refresh_cache.empty():
                            try:
                                frame = previous_refresh_cache.get_nowait()
                                self.__refresh_cache.put(frame)
                            except Empty:
                                pass

                else:
                    while not self.__cache.empty():
                        try:
                            self.__cache.get_nowait()
                        except Empty:
                            pass
                    self.__refresh_cache = None

                    self.__video.set(cv2.CAP_PROP_POS_FRAMES, self.__cache_next_index)

                self.__render_skip = True

                if play_after_skip:
                    self.__is_playing = play_after_skip
                self.__caching_lock.release()
                self.__rendering_lock.release()
            else:
                self.__skip_condition.release()

    def __render_frame(self):
        frame = None
        while True:
            interval = 1.0 / (self.__video_fps * self.__speed)
            interval = 0.016 if interval < 0.016 else interval

            if frame is None or self.__is_playing or self.__render_skip:
                self.__rendering_lock.acquire()
                if self.__render_skip:
                    self.__render_skip = False

                frame, frame_original, index = self.__cache.get()
                render_time = time.time()
                self.__render_index = index
                self.__render_original = frame_original

                logger.render(f'R {self.__render_index} ({QThread.currentThread().objectName()})')
                self.frame_drawn.emit(frame, index)

                self.__rendering_lock.release()
                while time.time() - render_time < interval and not self.__render_skip:
                    pass

    def __cache_frame(self):
        while True:
            if not self.__cache.full():
                self.__caching_lock.acquire()

                if self.__refresh_cache is not None and not self.__refresh_cache.empty():
                    check = True
                    frame = self.__refresh_cache.get()
                    is_refresh = True
                else:
                    video_frame = int(self.__video.get(cv2.CAP_PROP_POS_FRAMES))
                    if self.__cache_next_index != video_frame:
                        logger.warning(f'Misalignment: {self.__cache_next_index} -> {video_frame}')
                        self.__video.set(cv2.CAP_PROP_POS_FRAMES, self.__cache_next_index)
                    check, frame = self.__video.read()
                    is_refresh = False

                if check:
                    frame_original = frame.copy()

                    resized_w, resized_h = VideoStream.__get_resized_size(self.__container.frameGeometry().width(),
                                                                          self.__container.frameGeometry().height(),
                                                                          self.__video_width,
                                                                          self.__video_height)

                    self.__frame_modifiers_lock.acquire()
                    for modifier in self.__frame_modifiers:
                        frame = self.__frame_modifiers[modifier](frame)
                    self.__frame_modifiers_lock.release()

                    frame = VideoStream.__frame_resize(frame, resized_w, resized_h)

                    frame = VideoStream.__frame_convert_colors(frame)
                    frame = VideoStream.__frame_to_qpixmap(frame)

                    self.__cache_index = self.__cache_next_index
                    self.__cache_next_index += 1

                    self.__caching_lock.release()

                    self.__cache.put((frame, frame_original, self.__cache_index))
                    cached_txt = '(prev. cached original frame)' if is_refresh else ''
                    logger.cache(
                        f'C {self.__cache_index}, {self.__cache.qsize()} in C ({QThread.currentThread().objectName()}) {cached_txt}')

    frame_drawn = Signal(QPixmap, int)

    def destroy(self):
        self.__render_thread.terminate()
        self.__cache_thread.terminate()
        self.__skip_thread.terminate()

    def __init__(self, filename: str, container: QLabel):
        super(VideoStream, self).__init__()
        self.__video = cv2.VideoCapture(filename)
        self.__container = container

        self.__frame_modifiers = dict()
        self.__frame_modifiers_lock = RLock()

        self.__video_fps = self.__video.get(cv2.CAP_PROP_FPS)
        self.__video_width = self.__video.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.__video_height = self.__video.get(cv2.CAP_PROP_FRAME_HEIGHT)
        self.__video_total_frames = VideoStream.__get_video_total_frames(self.__video)

        logger.info(f'FPS: {self.__video_fps}')
        logger.info(f'Resolution: {self.__video_width} x {self.__video_height}')
        logger.info(f'Total frames: {self.__video_total_frames}')

        self.__speed = 1

        self.__rendering_lock = RLock()
        self.__is_playing = False
        self.__render_index = -1
        self.__render_original = None
        self.__render_skip = False

        self.__caching_lock = RLock()
        self.__cache_index = -1
        self.__cache_next_index = 0
        self.__cache = Queue(5)

        self.__skip_to = None
        self.__skip_play_after = False
        self.__skip_condition = Condition()
        self.__refresh_cache = None

        self.__render_thread = QThread()
        self.__render_thread.setObjectName('RenderThread')
        self.__render_thread.run = self.__render_frame

        self.__cache_thread = QThread()
        self.__cache_thread.setObjectName('CacheThread')
        self.__cache_thread.run = self.__cache_frame

        self.__skip_thread = QThread()
        self.__skip_thread.setObjectName('SkipThread')
        self.__skip_thread.run = self.__skip_frame

        self.__render_thread.start()
        self.__cache_thread.start()
        self.__skip_thread.start()
