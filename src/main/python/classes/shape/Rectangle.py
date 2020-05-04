from classes.shape.Shape import Shape


class Rectangle(Shape):
    def __init__(self, x_start=None, y_start=None, x_end=None, y_end=None):
        super().__init__({'top_left': (x_start, y_start), 'bottom_right': (x_end, y_end)})

    @property
    def top_left(self):
        return self.structure['top_left']

    @top_left.setter
    def top_left(self, coords):
        self.structure['top_left'] = coords

    @property
    def bottom_right(self):
        return self.structure['bottom_right']

    @bottom_right.setter
    def bottom_right(self, coords):
        self.structure['bottom_right'] = coords

