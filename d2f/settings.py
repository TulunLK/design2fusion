"""Kit de macros .setting sueltas para armar en Fusion a mano.

Son herramientas simples (un solo tool por archivo), el mismo formato que
Resolve guarda al usar "Save Setting" sobre un nodo. El panel de vidrio no va
aquí porque necesita la silueta del diseño: eso lo resuelve el .comp.
"""

MEDIA_IN = """{
\tTools = ordered() {
\t\tMediaIn1 = MediaIn {
\t\t\tInputs = {
\t\t\t\tGlobalIn = Input { Value = 1, },
\t\t\t\tGlobalOut = Input { Value = 1000, },
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 0, 0 } },
\t\t},
\t},
\tActiveTool = "MediaIn1"
}
"""


def _textplus(font, style):
    return """{
\tTools = ordered() {
\t\tTextPlus1 = TextPlus {
\t\t\tInputs = {
\t\t\t\tGlobalOut = Input { Value = 1000, },
\t\t\t\tWidth = Input { Value = 1920, },
\t\t\t\tHeight = Input { Value = 1080, },
\t\t\t\tUseFrameFormatSettings = Input { Value = 1, },
\t\t\t\tStyledText = Input { Value = "Texto", },
\t\t\t\tFont = Input { Value = "%s", },
\t\t\t\tStyle = Input { Value = "%s", },
\t\t\t\tSize = Input { Value = 0.06, },
\t\t\t\tRed1 = Input { Value = 1, },
\t\t\t\tGreen1 = Input { Value = 1, },
\t\t\t\tBlue1 = Input { Value = 1, },
\t\t\t\tAlpha1 = Input { Value = 1, },
\t\t\t\tVerticalJustificationNew = Input { Value = 3, },
\t\t\t\tHorizontalJustificationNew = Input { Value = 3, },
\t\t\t\tCenter = Input { Value = { 0.5, 0.5 } },
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 0, 0 } },
\t\t},
\t},
\tActiveTool = "TextPlus1"
}
""" % (font, style)


BLUR = """{
\tTools = ordered() {
\t\tBlur1 = Blur {
\t\t\tInputs = {
\t\t\t\tXBlurSize = Input { Value = 10, },
\t\t\t\tYBlurSize = Input { Value = 10, },
\t\t\t\tBlurType = Input { Value = 0, },
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 0, 0 } },
\t\t},
\t},
\tActiveTool = "Blur1"
}
"""

MERGE = """{
\tTools = ordered() {
\t\tMerge1 = Merge {
\t\t\tInputs = {
\t\t\t\tCenter = Input { Value = { 0.5, 0.5 } },
\t\t\t\tSize = Input { Value = 1, },
\t\t\t\tAngle = Input { Value = 0, },
\t\t\t\tBlend = Input { Value = 1, },
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 0, 0 } },
\t\t},
\t},
\tActiveTool = "Merge1"
}
"""

SOFT_GLOW = """{
\tTools = ordered() {
\t\tSoftGlow1 = SoftGlow {
\t\t\tInputs = {
\t\t\t\tGlowSize = Input { Value = 6, },
\t\t\t\tGlow = Input { Value = 0.6, },
\t\t\t},
\t\t\tViewInfo = OperatorInfo { Pos = { 0, 0 } },
\t\t},
\t},
\tActiveTool = "SoftGlow1"
}
"""

KIT = {
    "MediaIn.setting": MEDIA_IN,
    "TextPlus_Montserrat_Bold.setting": _textplus("Montserrat", "Bold"),
    "TextPlus_Inter_Bold.setting": _textplus("Inter", "Bold"),
    "Blur.setting": BLUR,
    "Merge.setting": MERGE,
    "SoftGlow.setting": SOFT_GLOW,
}


def write_kit(outdir):
    """Escribe el kit en <outdir> y devuelve las rutas."""
    import os
    kdir = os.path.join(outdir, "kit")
    os.makedirs(kdir, exist_ok=True)
    paths = []
    for name, content in KIT.items():
        p = os.path.join(kdir, name)
        with open(p, "w") as f:
            f.write(content)
        paths.append(p)
    return paths
