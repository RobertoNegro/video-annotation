import logging
import math
import time
from multiprocessing import Process, Pipe, connection, Queue, Lock, RLock
from threading import Thread
import cv2
import numpy as np
import qimage2ndarray
from PySide2.QtCore import Signal, QObject
from PySide2.QtGui import QPixmap
from classes.Shape import Shape, ShapeType

# fix for multiprocessing
cv2.setNumThreads(0)


def reader(conn_player: connection.Connection, filename, container_width, container_height, cache_dim):
    logger = logging.getLogger('Reader')
    try:
        terminate = False

        container_width = int(container_width)
        container_height = int(container_height)

        logger.render(f'File: {filename}')
        video = cv2.VideoCapture(filename)

        video_fps = video.get(cv2.CAP_PROP_FPS)
        video_width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        video_height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))

        def get_resized_size():
            video_ratio = video_width / video_height
            w = int(min(container_width, container_height * video_ratio))
            h = int(min(container_height, container_width / video_ratio))
            return w, h

        video_resized_width, video_resized_height = get_resized_size()

        video_total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)
        video.set(cv2.CAP_PROP_POS_FRAMES, video_total_frames)
        check = False
        while not check:
            check, frame = video.read()
            if not check:
                video_total_frames -= 1
                video.set(cv2.CAP_PROP_POS_FRAMES, video_total_frames)
        video.set(cv2.CAP_PROP_POS_FRAMES, 0)
        video_total_frames += 1
        video_total_frames = int(video_total_frames)

        assert None not in (
        container_height, container_width, video, video_fps, video_width, video_height, video_resized_width,
        video_resized_height, video_total_frames)

        def send_metadata():
            metadata = {
                'action': 'metadata',
                'fps': video_fps,
                'width': video_width,
                'height': video_height,
                'resized_width': video_resized_width,
                'resized_height': video_resized_height,
                'total_frames': video_total_frames,
                'container_width': container_width,
                'container_height': container_height,
            }
            conn_player.send(metadata)

        send_metadata()

        index = 0
        skip_cache = dict()
        cache = dict()
        shapes = dict()
        drawing_shapes = []
        highlight_shape = None
        highlight_color = None

        def get_modifier(shape: Shape):
            if highlight_shape == shape.id:
                color = highlight_color
                if shape.color == shape.last_color:
                    last_color = highlight_color
                else:
                    last_color = shape.last_color
            else:
                color = shape.color
                last_color = shape.last_color

            def mask_negative(frame, mask):
                negative = frame.copy()
                negative = cv2.bitwise_not(negative)
                negative = cv2.bitwise_and(negative, negative, mask=mask)

                mask = cv2.bitwise_not(mask)
                frame = cv2.bitwise_and(frame, frame, mask=mask)
                frame = cv2.bitwise_or(negative, frame)
                return frame

            def mask_opposite(frame, mask):
                opposite = frame.copy()
                opposite = cv2.inRange(opposite, np.array([0, 0, 0]), np.array([128, 128, 128]))
                opposite = cv2.cvtColor(opposite, cv2.COLOR_GRAY2RGB)
                opposite = cv2.bitwise_and(opposite, opposite, mask=mask)

                mask = cv2.bitwise_not(mask)
                frame = cv2.bitwise_and(frame, frame, mask=mask)
                frame = cv2.bitwise_or(opposite, frame)

                return frame

            def negative_text(frame, text, x, y):
                w, h, _ = frame.shape
                mask = np.zeros((w, h), frame.dtype)
                cv2.putText(mask, text, (x, y), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 1)
                frame = mask_opposite(frame, mask)

                return frame

            if shape.shape == ShapeType.globals:
                def modifier(frame):
                    cv2.rectangle(frame, (0, 0), (video_width, video_height), color, 3)
                    frame = negative_text(frame, shape.message, 10, 40)
                    return frame
            elif shape.shape == ShapeType.pointer:
                def modifier(frame):
                    if len(shape.points) >= 1:
                        x, y = shape.points[0]
                        if None not in (x, y):
                            w, h, _ = frame.shape
                            mask = np.zeros((w, h), frame.dtype)
                            cv2.line(mask, (x, 0), (x, video_height), (255, 255, 255), 3)
                            cv2.line(mask, (0, y), (video_width, y), (255, 255, 255), 3)
                            frame = mask_negative(frame, mask)
                            return frame

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

                            cv2.ellipse(frame, (centerx, centery), (sizex, sizey), 0, 0, 360, color, 3)
                            frame = negative_text(frame, shape.message, centerx - sizex + 10, centery + 7)
                    elif len(shape.points) == 1:
                        x, y = shape.points[0]
                        cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, color, 3)
                        frame = negative_text(frame, shape.message, x + 10, y + 40)
                    return frame
            elif shape.shape == ShapeType.rectangle:
                def modifier(frame):
                    if len(shape.points) >= 2:
                        x1, y1 = shape.points[0]
                        x2, y2 = shape.points[1]
                        if None not in (x1, y1, x2, y2):
                            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                        frame = negative_text(frame, shape.message, min(x1, x2) + 10, min(y1, y2) + 40)
                    elif len(shape.points) == 1:
                        x, y = shape.points[0]
                        cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, color, 3)
                        frame = negative_text(frame, shape.message, x + 10, y + 40)
                    return frame
            elif shape.shape == ShapeType.polygon:
                def modifier(frame):
                    if len(shape.points) > 1:
                        for i, p in enumerate(shape.points):
                            x1, y1 = shape.points[i]
                            if i == len(shape.points) - 1:
                                c = last_color
                                x2, y2 = shape.points[0]
                            else:
                                c = color
                                x2, y2 = shape.points[i + 1]

                            cv2.line(frame, (x1, y1), (x2, y2), c, 3)
                        xt, yt = shape.points[0]
                        frame = negative_text(frame, shape.message, xt + 10, yt + 40)
                    elif len(shape.points) == 1:
                        x, y = shape.points[0]
                        cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, color, 3)
                        frame = negative_text(frame, shape.message, x + 10, y + 40)
                    return frame
            elif shape.shape == ShapeType.line:
                def modifier(frame):
                    if len(shape.points) > 1:
                        for i, p in enumerate(shape.points):
                            if i < len(shape.points) - 1:
                                x1, y1 = shape.points[i]
                                if i == len(shape.points) - 2:
                                    c = last_color
                                else:
                                    c = color
                                x2, y2 = shape.points[i + 1]

                                cv2.line(frame, (x1, y1), (x2, y2), c, 3)
                        xt, yt = shape.points[0]
                        frame = negative_text(frame, shape.message, xt + 10, yt + 40)
                    elif len(shape.points) == 1:
                        x, y = shape.points[0]
                        cv2.ellipse(frame, (x, y), (2, 2), 0, 0, 360, color, 3)
                        frame = negative_text(frame, shape.message, x + 10, y + 40)
                    return frame
            else:
                def modifier(frame):
                    return frame

                logger.warning(f'Unknown shape while trying to add a new modifier: {shape.shape}')
            return modifier

        while not terminate:
            already_skipped = False
            while not terminate and (conn_player.poll() or len(cache) >= cache_dim):
                player_action = conn_player.recv()
                logger.render(f'Action player -> reader: {player_action}')
                if player_action['action'] == 'END':
                    terminate = True
                elif player_action['action'] == 'resize':
                    container_width = player_action['width']
                    container_height = player_action['height']
                    video_resized_width, video_resized_height = get_resized_size()
                    send_metadata()
                elif player_action['action'] == 'skip_to':
                    index = player_action['index']
                    if already_skipped:
                        skip_cache.update(cache.copy())
                    else:
                        skip_cache = cache.copy()
                    cache.clear()
                    logger.render(f'Cached for skip: {skip_cache.keys()}')
                    already_skipped = True
                elif player_action['action'] == 'gc':
                    if player_action['index'] in cache:
                        del cache[player_action['index']]
                elif player_action['action'] == 'set_shapes':
                    shapes.clear()
                    new_shapes = player_action['shapes']
                    for (index, shape) in new_shapes:
                        if index not in shapes:
                            shapes[index] = []
                        # for k in shapes:
                        #     shapes[k] = [m for m in shapes[k] if m.id != shape.id]
                        shapes[index].append(shape)
                elif player_action['action'] == 'add_shape':
                    index = player_action['index']
                    if index not in shapes:
                        shapes[index] = []
                    for k in shapes:
                        shapes[k] = [m for m in shapes[k] if m.id != player_action['shape'].id]
                    shapes[index].append(player_action['shape'])
                elif player_action['action'] == 'remove_shape':
                    for k in shapes:
                        shapes[k] = [m for m in shapes[k] if m.id != player_action['id']]
                elif player_action['action'] == 'clear_shapes':
                    shapes.clear()
                elif player_action['action'] == 'highlight_shape':
                    highlight_shape = player_action['id']
                    highlight_color = player_action['color']
                elif player_action['action'] == 'add_drawing_shape':
                    drawing_shapes = [m for m in drawing_shapes if m.id != player_action['shape'].id]
                    drawing_shapes.append(player_action['shape'])
                elif player_action['action'] == 'remove_drawing_shape':
                    drawing_shapes = [m for m in drawing_shapes if m.id != player_action['id']]
                elif player_action['action'] == 'clear_drawing_shapes':
                    drawing_shapes.clear()

            if not terminate and len(cache) < cache_dim:
                if index in skip_cache:
                    check = True
                    frame = skip_cache[index]
                else:
                    video_index = int(video.get(cv2.CAP_PROP_POS_FRAMES))
                    if index != video_index:
                        logger.render(f'Misalignment: wanted {index}, seek at {video_index}')
                        video.set(cv2.CAP_PROP_POS_FRAMES, index)
                    check, frame = video.read()

                if check:
                    cache[index] = frame.copy()

                    if index in shapes:
                        for s in shapes[index]:
                            frame = get_modifier(s)(frame)
                    for s in drawing_shapes:
                        frame = get_modifier(s)(frame)

                    frame = cv2.resize(frame, (video_resized_width, video_resized_height),
                                       interpolation=cv2.INTER_CUBIC)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    conn_player.send({
                        'action': 'frame',
                        'frame': frame,
                        'index': index,
                    })

                    # logger.render(f'Frame {index} cached ({len(cache)})')
                    index += 1

        conn_player.send({'action': 'ENDED'})
        conn_player.close()
    except Exception as e:
        logger.error(f'Error: {e}')


def player(conn_reader: connection.Connection, conn_ui: connection.Connection, conn_command: connection.Connection):
    logger = logging.getLogger('Player')
    try:
        terminate = False

        cache = []
        render_time = 0
        current_index = 0

        playing = False
        skipping = False
        speed = 1
        fps = None
        width = None
        height = None
        total_frames = None

        while not terminate:
            action = conn_reader.recv()
            if action['action'] == 'metadata':
                fps = action['fps']
                width = action['width']
                height = action['height']
                total_frames = action['total_frames']

                conn_ui.send(action)
                break
        assert None not in (fps, width, height, total_frames)

        def get_interval():
            i = 1.0 / (fps * speed)
            return 0.016 if i < 0.016 else i

        interval = get_interval()
        assert interval is not None

        while not terminate:
            while not terminate and conn_reader.poll():
                action = conn_reader.recv()

                tmp = action.copy()
                if 'frame' in tmp:
                    del tmp['frame']
                logger.player(f'Action reader -> player: {tmp}')

                if action['action'] == 'frame':
                    cache.append(action)
                elif action['action'] == 'metadata':
                    conn_ui.send(action)

            while not terminate and conn_command.poll():
                action = conn_command.recv()
                logger.player(f'Action command -> player: {action}')
                if action['action'] == 'pause':
                    playing = False
                elif action['action'] == 'play':
                    playing = True
                elif action['action'] == 'speed':
                    speed = action['speed']
                    interval = get_interval()
                    logger.player(f'Speed: {speed}')
                    logger.player(f'Interval: {interval}')
                elif action['action'] == 'resize':
                    conn_reader.send(action)
                elif action['action'] == 'skip_to':
                    render_time = 0
                    conn_reader.send({
                        'action': 'skip_to',
                        'index': action['index']
                    })
                    current_index = action['index']
                    cache.clear()
                    skipping = True
                elif action['action'] == 'refresh':
                    conn_reader.send({
                        'action': 'skip_to',
                        'index': current_index
                    })
                    render_time = 0
                    cache.clear()
                elif action['action'] == 'add_shape':
                    conn_reader.send(action)
                elif action['action'] == 'remove_shape':
                    conn_reader.send(action)
                elif action['action'] == 'set_shapes':
                    conn_reader.send(action)
                elif action['action'] == 'clear_shapes':
                    conn_reader.send(action)
                elif action['action'] == 'highlight_shape':
                    conn_reader.send(action)
                elif action['action'] == 'add_drawing_shape':
                    conn_reader.send(action)
                elif action['action'] == 'remove_drawing_shape':
                    conn_reader.send(action)
                elif action['action'] == 'clear_drawing_shapes':
                    conn_reader.send(action)
                elif action['action'] == 'END':
                    conn_reader.send({'action': 'END'})
                    conn_ui.send({'action': 'END'})
                    terminate = True

            # refresh
            if not terminate:
                last_index_with_current_index = max([index for index, cached in enumerate(cache) if cached['index'] == current_index] + [-1])
                if last_index_with_current_index >= 0:
                    skipping = False
                    cache = cache[last_index_with_current_index:]
                    cached = cache.pop(0)
                    conn_ui.send(cached)

            if not terminate and len(cache) > 0 and (skipping or (playing and time.time() - render_time >= interval)):
                render_time = time.time()
                cached = cache.pop(0)
                if not skipping and current_index + 1 == cached['index'] or skipping and current_index == cached['index']:
                    skipping = False
                    if current_index != cached['index']:
                        conn_reader.send({
                            'action': 'gc',
                            'index': current_index,
                        })
                    conn_ui.send(cached)
                    current_index = cached['index']

        while True:
            action = conn_reader.recv()
            if action['action'] == 'ENDED':
                logger.player(f'Action reader -> player: {action}')
                break
        conn_ui.send({'action': 'ENDED'})

        conn_ui.close()
        conn_command.close()
        conn_reader.close()
    except Exception as e:
        logger.error(e)


class VideoStream(QObject):
    logger = logging.getLogger('VideoStream')

    @staticmethod
    def check_valid_video_file(filename):
        try:
            video = cv2.VideoCapture(filename)
            if not video.isOpened():
                return False
            frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
            if frame_count > 0:
                return True
            return False
        except cv2.error as e:
            return False
        except Exception as e:
            return False

    @staticmethod
    def index_to_formatted_time(frame, fps):
        hours = math.floor(frame / fps / 60 / 60)
        minutes = math.floor(frame / fps / 60) - hours * 60
        seconds = math.floor(frame / fps) - hours * 60 * 60 - minutes * 60
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    draw_frame_signal = Signal(QPixmap, int, int, str, str, bool)
    destroyed = Signal()
    container_resized_signal = Signal(QPixmap, int)

    def __init__(self):
        super(VideoStream, self).__init__()
        self.__destroyed = False
        self.__fps = 0
        self.__width = 1
        self.__height = 1
        self.__resized_width = 1
        self.__resized_height = 1
        self.__container_width = 1
        self.__container_height = 1
        self.__playing = False
        self.__current_frame = 0
        self.__total_frames = 0
        self.__commands_pipe: connection.Connection = None

    @property
    def is_destroyed(self):
        return self.__destroyed

    @property
    def fps(self):
        return self.__fps

    @property
    def width(self):
        return self.__width

    @property
    def height(self):
        return self.__height

    @property
    def current_frame(self):
        return self.__current_frame

    @property
    def current_timestamp(self):
        return self.index_to_formatted_time(self.current_frame, self.fps)

    @property
    def total_frames(self):
        return self.__total_frames

    @property
    def total_timestamp(self):
        return self.index_to_formatted_time(self.__total_frames, self.fps)

    @property
    def playing(self):
        return self.__playing

    def __thread_execution(self, conn_player: connection.Connection):
        logger = logging.getLogger('UIThread')

        terminate = False

        while not terminate:
            action = conn_player.recv()

            tmp = action.copy()
            if 'frame' in tmp:
                del tmp['frame']
            logger.render(f'Action player -> ui: {tmp}')

            if action['action'] == 'END':
                self.__destroyed = True
                self.__fps = 0
                self.__width = 1
                self.__height = 1
                self.__resized_width = 1
                self.__resized_height = 1
                self.__container_width = 1
                self.__container_height = 1
                self.__playing = False
                self.__current_frame = 0
                self.__total_frames = 0
                terminate = True
            elif action['action'] == 'frame':
                if action['index'] is not None and action['frame'] is not None:
                    self.__current_frame = action['index']
                    self.draw_frame_signal.emit(QPixmap.fromImage(qimage2ndarray.array2qimage(action['frame'])), self.current_frame, self.total_frames, self.current_timestamp, self.total_timestamp, self.playing)
            elif action['action'] == 'metadata':
                self.__fps = action['fps']
                self.__width = action['width']
                self.__height = action['height']
                self.__total_frames = action['total_frames']
                self.__resized_width = action['resized_width']
                self.__resized_height = action['resized_height']
                self.__container_width = action['container_width']
                self.__container_height = action['container_height']

        while True:
            action = conn_player.recv()
            if action['action'] == 'ENDED':
                logger.render(f'Action player -> ui: {action}')
                break
        self.destroyed.emit()
        conn_player.close()

    def start(self, filename: str, container_width, container_height, cache_size=100):
        if not self.__destroyed:
            # creating a pipe
            player_to_reader, reader_to_player = Pipe()
            ui_to_player, player_to_ui = Pipe()
            command_to_player, player_to_command = Pipe()
            self.__commands_pipe = command_to_player

            container_width = int(container_width)
            container_height = int(container_height)

            # creating new processes
            reader_process = Process(target=reader,
                                     args=(reader_to_player, filename, container_width, container_height, cache_size))
            player_process = Process(target=player, args=(player_to_reader, player_to_ui, player_to_command))

            # running processes
            reader_process.start()
            player_process.start()

            thread_execution = Thread(target=self.__thread_execution, args=(ui_to_player,))
            thread_execution.start()

    def __del__(self):
        self.destroy()

    def destroy(self):
        if not self.__destroyed:
            self.__destroyed = True
            if self.__commands_pipe is not None:
                self.__commands_pipe.send({'action': 'END'})

    def get_video_coord(self, container_x, container_y):
        # container_x -= (self.__container_width - self.__resized_width) / 2
        # container_y -= (self.__container_height - self.__resized_height) / 2
        #
        # container_x = int(max(min(container_x, self.__resized_width), 0))
        # container_y = int(max(min(container_y, self.__resized_height), 0))
        #
        # x = self.__width * container_x / self.__resized_width
        # y = self.__height * container_y / self.__resized_height

        blackbar_width = (self.__container_width - self.__resized_width) / 2
        blackbar_height = (self.__container_height - self.__resized_height) / 2
        x = self.__width * (container_x - blackbar_width) / (self.__container_width - blackbar_width * 2)
        y = self.__height * (container_y - blackbar_height) / (self.__container_height - blackbar_height * 2)

        x = max(min(x, self.__width), 0)
        y = max(min(y, self.__height), 0)
        return int(x), int(y)

    def play(self):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'play'})
            self.__playing = True

    def pause(self):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'pause'})
            self.__playing = False

    def speed(self, speed):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'speed', 'speed': speed})

    def skip_to(self, index):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'skip_to', 'index': index})

    def refresh(self):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'refresh'})

    def resize(self, width, height):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'resize', 'width': width, 'height': height})

    def add_seconds(self, seconds):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.skip_to(int(max(min(self.current_frame + self.fps * seconds, self.total_frames - 1), 0)))

    def add_frames(self, frames):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.skip_to(max(min(self.current_frame + frames, self.total_frames - 1), 0))

    def clear_shapes(self):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'clear_shapes'})

    def set_shapes(self, shapes: [(int, Shape)]):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'set_shapes', 'shapes': shapes})

    def remove_shape(self, id: str):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'remove_shape', 'id': id})

    def highlight_shape(self, id, color=(255, 255, 0)):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'highlight_shape', 'id': id, 'color': color})

    def add_shape(self, frame_index, shape: Shape):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'add_shape', 'index': frame_index, 'shape': shape})

    def clear_drawing_shapes(self):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'clear_drawing_shapes'})

    def remove_drawing_shape(self, id: str):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'remove_drawing_shape', 'id': id})

    def add_drawing_shape(self, shape: Shape):
        if not self.__destroyed and self.__commands_pipe is not None:
            self.__commands_pipe.send({'action': 'add_drawing_shape', 'shape': shape})
