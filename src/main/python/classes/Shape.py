import enum
import json
import uuid


class ShapeType:
    globals = 'global'
    rectangle = 'rectangle'
    ellipse = 'ellipse'
    polygon = 'polygon'
    line = 'line'
    pointer = 'pointer'


class Shape:
    def __init__(self, id, shape, color=(255, 0, 0), last_color=(255, 0, 0)):
        if shape == ShapeType.globals:
            self.max_points = 0
            self.min_points = None
        elif shape == ShapeType.rectangle:
            self.max_points = 2
            self.min_points = 2
        elif shape == ShapeType.ellipse:
            self.max_points = 2
            self.min_points = 2
        elif shape == ShapeType.polygon:
            self.max_points = None
            self.min_points = 3
        elif shape == ShapeType.line:
            self.max_points = None
            self.min_points = 2
        elif shape == ShapeType.pointer:
            self.max_points = 1
            self.min_points = 1
        else:
            self.max_points = 0
            self.min_points = 0

        self.__color = color
        self.__last_color = last_color

        self.__structure = dict()
        self.__structure['id'] = id
        self.__structure['shape'] = shape
        self.__structure['points'] = []
        self.__structure['message'] = ''

    @property
    def color(self):
        return self.__color

    @color.setter
    def color(self, color):
        self.__color = color

    @property
    def last_color(self):
        return self.__last_color

    @last_color.setter
    def last_color(self, last_color):
        self.__last_color = last_color

    @property
    def id(self):
        return self.__structure['id']

    @id.setter
    def id(self, id):
        self.__structure['id'] = id

    @property
    def shape(self):
        return self.__structure['shape']

    @property
    def points(self):
        return self.__structure['points']

    @property
    def message(self):
        return self.__structure['message']

    @message.setter
    def message(self, message):
        self.__structure['message'] = message

    def add_point(self, x, y):
        x = int(x)
        y = int(y)

        if self.empty:
            last_x, last_y = (-1, -1)
        else:
            last_x, last_y = self.__structure['points'][-1]
        if not self.full and (last_x != x or last_y != y):
            self.__structure['points'].append((x, y))

    def remove_last(self):
        if len(self.__structure['points']) > 0:
            self.__structure['points'].pop()

    @property
    def valid(self):
        return (self.max_points is None or len(self.__structure['points']) <= self.max_points) and (self.min_points is None or len(self.__structure['points']) >= self.min_points)

    @property
    def full(self):
        return self.max_points is not None and len(self.__structure['points']) >= self.max_points

    @property
    def empty(self):
        return len(self.__structure['points']) == 0

    def reset(self):
        self.__structure['points'].clear()

    def to_json(self, hide_id=False, indent=2):
        structure = self.__structure.copy()
        if hide_id:
            del structure['id']
        if len(structure['points']) == 0:
            del structure['points']
        return json.dumps(structure, indent=indent, sort_keys=True)

    @staticmethod
    def from_save_format(entry):
        if 'shape' in entry:
            shape = Shape(uuid.uuid1().hex, entry['shape'])
            if 'points' in entry and len(entry['points']) > 0:
                for (x, y) in entry['points']:
                    shape.add_point(x, y)
            if 'message' in entry:
                shape.message = entry['message']

            return shape
        return None

    def to_save_format(self, frame):
        structure = self.__structure.copy()

        del structure['id']
        if len(structure['points']) == 0:
            del structure['points']
        structure['frame'] = frame
        return structure
