from classes.shape.Shape import Shape


class Ellipse(Shape):
    def __init__(self, x_center, y_center, width, height):
        super().__init__({'center': (x_center, y_center),
                        'size': (width, height)})

    @property
    def center(self):
        return self.structure['center']

    @property
    def size(self):
        return self.structure['size']
