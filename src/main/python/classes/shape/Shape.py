import json


class Shape:
    def __init__(self, structure):
        self.structure = structure

    def to_json(self):
        return json.dumps(self.structure)
