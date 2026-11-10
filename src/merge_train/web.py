"""CSS, JavaScript und Bilder der Seiten (liegen als Dateien in web/)."""
import base64, pkgutil


def _text(name):
    return "\n" + pkgutil.get_data(__package__, "web/" + name).decode("utf-8")


CSS = _text("basis.css")
CSS_REVIEW = _text("review.css")
# Seiten-Skripte, in dieser Reihenfolge in einem <script> (jede Datei in eigener Funktion, gemeinsam nur über App):
# Diff-Seiten alle, Startseite nur JS_START.
JS_DATEIEN = ("app.js", "navigation.js", "zeichnungen.js", "zug.js", "diff.js", "review.js", "hud.js", "toasts.js", "bahnhof.js",
              "beobachten.js")
JS_START_DATEIEN = ("app.js", "zeichnungen.js", "zug.js", "bahnhof.js")
JS = "".join(_text(n) for n in JS_DATEIEN)
JS_START = "".join(_text(n) for n in JS_START_DATEIEN)
FAVICON = _text("favicon.svg")
ICON = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
BAHNHOF_BILD = base64.b64encode(pkgutil.get_data(__package__, "web/bahnhof.webp")).decode()  # für eine data:-URL
