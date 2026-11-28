import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from d2f.comp import shape_block, generate_comp

class ShapeTest(unittest.TestCase):
    def test_shape_block_rectangle(self):
        lay = {
            "name": "Cuadrado Azul",
            "shape": {
                "type": "RECTANGLE",
                "color": "#0066FF@100%",
                "corner_radius": 16.0
            },
            "width": 200.0,
            "height": 100.0,
            "center_x": 960.0,
            "center_y": 540.0,
            "rotation_deg": 0.0
        }
        block = shape_block(lay, 1920.0, 1080.0, "CuadradoAzul", pos=(0, 0))
        self.assertIn("CuadradoAzul = Background {", block)
        self.assertIn("CuadradoAzulMask = RectangleMask {", block)
        self.assertIn("TopLeftBlue = Input { Value = 1.0", block) # FF en azul
        self.assertIn("CornerRadius =", block)

    def test_shape_block_ellipse(self):
        lay = {
            "name": "Circulo",
            "shape": {
                "type": "ELLIPSE",
                "color": "#FF0000@100%",
                "corner_radius": 0.0
            },
            "width": 150.0,
            "height": 150.0,
            "center_x": 500.0,
            "center_y": 500.0,
            "rotation_deg": 0.0
        }
        block = shape_block(lay, 1920.0, 1080.0, "Circulo", pos=(0, 0))
        self.assertIn("Circulo = Background {", block)
        self.assertIn("CirculoMask = EllipseMask {", block)
        self.assertNotIn("CornerRadius", block)

if __name__ == "__main__":
    unittest.main()
