"""Neue UI: gerenderte Styles gegen den Referenz-Style-Guide prüfen.

Aufruf: python3 -m unittest tests.browser.test_new_ui_style_screenshots -v

Die Tests rendern die echte ``bin/web/nova.css`` mit einer kleinen Sonde, die
dieselben Klassen verwendet wie die neue Oberfläche (``.nv-card``,
``.nv-btn``, ``.nv-pill``, ``.nv-table``, ``.nv-switch-row``). Sie vergleichen
Screenshot-Pixel der Flächen mit den Palettewerten der zugelieferten Referenz
(``docs/style.html``) und messen die gerenderten Maße der Komponenten. Damit
wird das sichtbare Ergebnis geprüft, nicht der CSS-Quelltext. Token-Namen,
12 Akzente und die Umschaltung über ``html[data-*]`` bleiben frei.

Kein Server, keine echten MCP-Aufrufe: CSS und Sonde liegen als lokale Dateien,
der Browser wird isoliert gestartet.
"""

import base64
import os
import re
import tempfile
import unittest
from pathlib import Path

_BROWSERS = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
if not _BROWSERS:
    _DEFAULT = Path.home() / ".cache" / "ms-playwright"
    if _DEFAULT.is_dir():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_DEFAULT)

from playwright.sync_api import sync_playwright  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
NOVA_CSS = REPO / "bin" / "web" / "nova.css"

# Palette der zugelieferten Referenz ("Precise Frames × Technical Density").
# Die Werte stammen aus den --bg-canvas/--bg-surface/--bg-raised-Tokens des
# Style-Guides; der Akzent wird absichtlich nicht verglichen (Vibe behält
# blau als Standard, die Referenz zeigt indigo).
PALETTE = {
    "light": {
        "canvas": (244, 243, 240),   # #f4f3f0
        "surface": (251, 250, 248),  # #fbfaf8
        "raised": (255, 255, 255),   # #ffffff
    },
    "dark": {
        "canvas": (22, 21, 20),      # #161514
        "surface": (29, 28, 26),     # #1d1c1a
        "raised": (35, 34, 32),      # #232220
    },
}
PIXEL_TOLERANCE = 2

PROBE_HTML = """<!doctype html>
<html lang="en" data-theme="light" data-accent="blue" data-animations="off">
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="__NOVA_CSS__">
<style>
  html, body { margin: 0; }
  #p-top { position: absolute; left: 400px; top: 20px; width: 200px; height: 40px; }
  #p-card { position: absolute; left: 20px; top: 20px; width: 240px; height: 120px; }
  #p-primary { position: absolute; left: 20px; top: 180px; width: 90px; }
  #p-secondary { position: absolute; left: 130px; top: 180px; width: 90px; }
  #p-pill { position: absolute; left: 20px; top: 240px; }
  #p-table { position: absolute; left: 20px; top: 300px; width: 400px; }
  #p-switch { position: absolute; left: 20px; top: 400px; }
</style>
</head>
<body data-nv-app>
<div class="nv-top" id="p-top"></div>
<div class="nv-card" id="p-card"><p>Karte</p></div>
<button type="button" class="nv-btn nv-primary" id="p-primary"></button>
<button type="button" class="nv-btn" id="p-secondary"></button>
<span class="nv-pill" id="p-pill" data-state="running">bereit</span>
<table class="nv-table" id="p-table"><thead><tr><th id="p-th">Status</th></tr></thead>
<tbody><tr><td>ok</td></tr></tbody></table>
<label class="nv-switch-row"><input type="checkbox" id="p-switch" checked><span class="nv-switch-text">Auto</span></label>
</body>
</html>"""


def as_px(value):
    """Berechneter CSS-Wert in px (getComputedStyle liefert z. B. '34px')."""
    match = re.fullmatch(r"\s*(-?[0-9.]+)px\s*", str(value))
    if not match:
        raise AssertionError("Kein px-Wert: " + repr(value))
    return float(match.group(1))


def is_opaque(color):
    """Prüft den Alphakanal eines berechneten CSS-Farbwerts."""
    if color.startswith("rgba("):
        parts = color[5:-1].split(",")
        return len(parts) < 4 or float(parts[3]) >= 0.999
    if "/" in color:
        tail = color.rsplit("/", 1)[1].strip().rstrip(")").strip()
        try:
            return float(tail[:-1]) >= 99.5 if tail.endswith("%") \
                else float(tail) >= 0.999
        except ValueError:
            return False
    return True


class NovaStyleScreenshotTest(unittest.TestCase):
    """Sichtbare Flächen und Maße der neuen UI gegen die Referenz."""

    @classmethod
    def setUpClass(cls):
        if not NOVA_CSS.is_file():
            raise AssertionError("nova.css fehlt: " + str(NOVA_CSS))
        cls.tmp = tempfile.TemporaryDirectory()
        cls.probe = Path(cls.tmp.name) / "probe.html"
        cls.probe.write_text(
            PROBE_HTML.replace("__NOVA_CSS__", NOVA_CSS.as_uri()),
            encoding="utf-8",
        )
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(
            viewport={"width": 1000, "height": 700})
        self.page = self.context.new_page()
        self.page.goto(self.probe.as_uri(), wait_until="load")

    def tearDown(self):
        self.context.close()

    def set_theme(self, theme):
        self.page.evaluate(
            "t => { document.documentElement.dataset.theme = t; }", theme)
        self.page.wait_for_timeout(40)

    def screenshot_pixels(self, points):
        """Farben echter Screenshot-Pixel an den gegebenen Koordinaten."""
        png = self.page.screenshot(type="png")
        data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        return self.page.evaluate(
            """async ({url, points}) => {
              const img = new Image();
              img.src = url;
              await img.decode();
              const canvas = document.createElement('canvas');
              canvas.width = img.width;
              canvas.height = img.height;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(img, 0, 0);
              const result = {};
              for (const [name, x, y] of points) {
                const px = ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data;
                result[name] = [px[0], px[1], px[2]];
              }
              return result;
            }""",
            {"url": data_url, "points": points},
        )

    def surface_points(self):
        """Samplepunkte abseits von Text und Rahmen (rechte untere Polsterung)."""
        card = self.page.locator("#p-card").bounding_box()
        secondary = self.page.locator("#p-secondary").bounding_box()
        self.assertIsNotNone(card)
        self.assertIsNotNone(secondary)
        return [
            ["canvas", 900, 600],
            ["surface", card["x"] + card["width"] - 12,
             card["y"] + card["height"] - 12],
            ["raised", secondary["x"] + 8,
             secondary["y"] + secondary["height"] / 2],
        ]

    def assert_palette(self, theme):
        self.set_theme(theme)
        pixels = self.screenshot_pixels(self.surface_points())
        for name, expected in PALETTE[theme].items():
            with self.subTest(theme=theme, surface=name):
                actual = pixels[name]
                self.assertTrue(
                    all(abs(a - e) <= PIXEL_TOLERANCE
                        for a, e in zip(actual, expected)),
                    "Screenshot-Farbe %s/%s weicht ab: %s statt %s"
                    % (theme, name, actual, list(expected)),
                )

    def test_light_surfaces_match_reference_screenshot_palette(self):
        """Helles Canvas, Kartenfläche und Steuerfläche entsprechen der Referenz."""
        self.assert_palette("light")

    def test_dark_surfaces_match_reference_screenshot_palette(self):
        """Dieselben Flächen im dunklen Theme — identische Layoutmaße, andere Tokens."""
        self.assert_palette("dark")

    def test_control_and_switch_geometry_match_reference(self):
        """Buttons 34 px, Toggle 42×12 px, Thumb 22 px (Referenzwerte)."""
        button = self.page.locator("#p-primary").bounding_box()
        switch = self.page.locator("#p-switch").bounding_box()
        thumb = self.page.evaluate(
            """() => {
              const s = getComputedStyle(document.querySelector('#p-switch'), '::before');
              return [s.width, s.height];
            }""")
        self.assertAlmostEqual(34.0, button["height"], delta=1.0,
                               msg="Buttonhöhe entspricht nicht --control-h-md")
        self.assertAlmostEqual(42.0, switch["width"], delta=1.0,
                               msg="Toggle-Train ist nicht 42 px breit")
        self.assertAlmostEqual(12.0, switch["height"], delta=1.0,
                               msg="Toggle-Track ist nicht 12 px hoch")
        self.assertAlmostEqual(22.0, as_px(thumb[0]), delta=1.0,
                               msg="Toggle-Thumb ist nicht 22 px breit")
        self.assertAlmostEqual(22.0, as_px(thumb[1]), delta=1.0,
                               msg="Toggle-Thumb ist nicht 22 px hoch")

    def test_component_frames_use_small_radii(self):
        """Karten, Buttons und Statusmarken bleiben bei 2–6 px Radien."""
        radii = self.page.evaluate(
            """() => {
              const radius = selector =>
                getComputedStyle(document.querySelector(selector)).borderTopLeftRadius;
              return {
                cardRadius: radius('#p-card'),
                buttonRadius: radius('#p-primary'),
                pillRadius: radius('#p-pill'),
              };
            }""")
        for label, value in radii.items():
            with self.subTest(property=label):
                self.assertLessEqual(as_px(value), 6.0,
                                     label + " ist kein kleiner Radius: "
                                     + repr(value))

    def test_surfaces_are_opaque(self):
        """Deckige Flächen statt Glas: kein Alphakanal auf der Karte."""
        background = self.page.evaluate(
            "() => getComputedStyle(document.querySelector('#p-card')).backgroundColor")
        self.assertTrue(is_opaque(background),
                        "Kartenfläche ist transparent: " + background)

    def test_no_backdrop_blur_on_chrome(self):
        """Kein Frosted-Glass-Blur auf Kopfleiste und Schubladen."""
        blur = self.page.evaluate(
            """() => {
              const s = getComputedStyle(document.querySelector('#p-top'));
              return [s.backdropFilter, s.webkitBackdropFilter];
            }""")
        self.assertIn(blur[0], ("none", "", None),
                      "Backdrop-Blur ist nicht entfernt: " + repr(blur[0]))
        self.assertIn(blur[1], ("none", "", None),
                      "Webkit-Backdrop-Blur ist nicht entfernt: "
                      + repr(blur[1]))

    def test_table_headers_are_uppercase_eleven_pixel_labels(self):
        """Tabellenköpfe sind 11 px großgeschriebene Technik-Labels."""
        header = self.page.evaluate(
            """() => {
              const s = getComputedStyle(document.querySelector('#p-th'));
              return {size: s.fontSize, transform: s.textTransform};
            }""")
        self.assertAlmostEqual(11.0, as_px(header["size"]), delta=0.5,
                               msg="Tabellenkopf ist nicht 11 px")
        self.assertEqual("uppercase", header["transform"],
                         "Tabellenkopf ist nicht uppercase")

    def test_focus_outline_is_two_px_with_one_px_offset(self):
        """Fokus: 2 px Akzent-Outline mit 1 px Abstand."""
        self.page.locator("#p-primary").focus()
        focus = self.page.evaluate(
            """() => {
              const node = document.querySelector('#p-primary');
              const s = getComputedStyle(node);
              return {
                visible: node.matches(':focus-visible'),
                width: s.outlineWidth,
                offset: s.outlineOffset,
              };
            }""")
        self.assertTrue(focus["visible"], "Fokus-Zustand wurde nicht erreicht")
        self.assertAlmostEqual(2.0, as_px(focus["width"]), delta=0.1,
                               msg="Fokus-Outline ist nicht 2 px")
        self.assertAlmostEqual(1.0, as_px(focus["offset"]), delta=0.1,
                               msg="Fokus-Abstand ist nicht 1 px")


if __name__ == "__main__":
    unittest.main()
