"""CSS, JavaScript und Bilder der Seiten (liegen als Dateien in web/)."""
import base64, pkgutil


def _text(name):
    return "\n" + pkgutil.get_data(__package__, "web/" + name).decode("utf-8")


CSS = _text("basis.css")
CSS_REVIEW = _text("review.css")
JS = _text("basis.js")
JS_ZUG = _text("zug.js")
JS_DIFF = _text("diff.js")
JS_REVIEW = _text("review.js")
JS_BAHNHOF = _text("bahnhof.js")
FAVICON = _text("favicon.svg")
ICON = '<link rel="icon" type="image/svg+xml" href="/favicon.svg">'
BAHNHOF_BILD = base64.b64encode(pkgutil.get_data(__package__, "web/bahnhof.webp")).decode()  # für eine data:-URL
