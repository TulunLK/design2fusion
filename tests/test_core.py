"""Tests sin FigCraft: solo emisión de .comp, kit y utilidades."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from d2f.comp import _hex_of, generate_comp, lua_q  # noqa: E402
from d2f.model import slug  # noqa: E402
from d2f.settings import KIT, write_kit  # noqa: E402

HAVE_IM = bool(shutil.which("convert") or shutil.which("magick"))


def balanced(text):
    pairs = {"{": "}", "(": ")", "[": "]"}
    closers = set(pairs.values())
    stack = []
    for ch in text:
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closers:
            if not stack or stack.pop() != ch:
                return False
    return not stack


def tiny_png(path):
    exe = shutil.which("magick") or "convert"
    subprocess.run([exe, "-size", "20x10", "xc:red", path], check=True,
                   capture_output=True)


@unittest.skipUnless(HAVE_IM, "necesita ImageMagick para los PNG de prueba")
class CompTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="d2f-test-")
        os.makedirs(os.path.join(self.dir, "capas"))
        tiny_png(os.path.join(self.dir, "capas", "01_panel.png"))
        tiny_png(os.path.join(self.dir, "capas", "01_panel_mask.png"))
        tiny_png(os.path.join(self.dir, "capas", "02_texto.png"))
        self.manifest = {
            "source": {"file_key": "t.figcraft", "frame_id": "3",
                       "frame_name": "Slide 16:9 - 1"},
            "frame": {"width": 1920.0, "height": 1080.0, "background_fill": None},
            "layers": [
                {"name": "Panel", "figma_id": "5", "figma_type": "RECTANGLE",
                 "z": 0, "opacity": 1, "width": 240.0, "height": 64.0,
                 "center_x": 1001.0, "center_y": 227.0, "rotation_deg": 0,
                 "blend_mode": "normal", "png": "capas/01_panel.png",
                 "png_rect": {"x": 881.0, "y": 195.0, "w": 240.0, "h": 64.0},
                 "corner_radius": 32.0,
                 "glass": {"radius": 8.0, "mask": "capas/01_panel_mask.png",
                           "figma_glass_effect": True}},
                {"name": "REPRODUCIR", "figma_id": "6", "figma_type": "TEXT",
                 "z": 1, "opacity": 1, "width": 110.0, "height": 18.0,
                 "center_x": 1001.0, "center_y": 227.0, "rotation_deg": 0,
                 "blend_mode": "normal", "png": "capas/02_texto.png",
                 "png_rect": {"x": 946.0, "y": 218.0, "w": 110.0, "h": 18.0},
                 "text": {"content": "REPRODUCIR", "font_family": "Inter",
                          "font_style": "Bold", "font_size_px": 17.0,
                          "color": "#FFFFFF@100%", "align_h": "center",
                          "align_v": "center", "line_height_px": 20.4,
                          "letter_spacing": 0.34}},
            ],
        }

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_comp_estructura(self):
        path = generate_comp(self.manifest, self.dir, log=lambda m: None)
        with open(path) as f:
            text = f.read()
        self.assertTrue(balanced(text), "llaves desbalanceadas en el .comp")
        self.assertIn("MediaIn1 = MediaIn", text)
        self.assertIn("Loader00 = Loader", text)
        self.assertIn("Loader01 = Loader", text)
        self.assertIn("BlurGlass1 = Blur", text)
        self.assertIn("BitmapGlass1 = Bitmap", text)
        self.assertIn('FormatID = Input { Value = "OpenEXRFormat" }', text)
        self.assertIn("Merge01 = Merge", text)
        self.assertIn("Merge02 = Merge", text)
        self.assertIn("ActiveTool = ", text)
        # centro normalizado del panel: 1001/1920 y 1-227/1080
        self.assertIn("0.521354", text)
        self.assertIn("0.789815", text)

    def test_textplus_alternativo(self):
        generate_comp(self.manifest, self.dir, log=lambda m: None)
        snips = os.path.join(self.dir, "fusion", "textplus_alternativo.txt")
        with open(snips) as f:
            text = f.read()
        self.assertIn("TextPlus_6", text)
        self.assertIn('StyledText = Input { Value = "REPRODUCIR" }', text)
        self.assertIn('Font = Input { Value = "Inter" }', text)
        self.assertTrue(balanced(text))


class UtilTest(unittest.TestCase):
    def test_lua_q_escapa(self):
        self.assertEqual(lua_q('a"b\\c'), '"a\\"b/c"')

    def test_slug_dedupe(self):
        used = set()
        self.assertEqual(slug("Panel Vidrio", used), "Panel_Vidrio")
        self.assertEqual(slug("Panel Vidrio", used), "Panel_Vidrio_2")

    def test_hex_of(self):
        self.assertEqual(_hex_of("#00ff00@50%")[1], 1.0)
        self.assertEqual(_hex_of("#fff")[0], 1.0)

    def test_kit_valido(self):
        with tempfile.TemporaryDirectory() as d:
            paths = write_kit(d)
            self.assertEqual(len(paths), len(KIT))
            for p in paths:
                with open(p) as f:
                    text = f.read()
                self.assertTrue(balanced(text), p)
                self.assertIn("ActiveTool", text)
                self.assertIn("Tools = ordered()", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
