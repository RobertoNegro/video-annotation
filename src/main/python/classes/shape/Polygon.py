from classes.shape.Shape import Shape


class Ellipse(Shape):
    def __init__(self, points):
        super().__init__({'points': points})

    @property
    def points(self):
        return self.structure['points']
