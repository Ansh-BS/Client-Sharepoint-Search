import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "style.css"


def _body(text):
    """Everything after the :root token block — the rules, not the palette."""
    end = text.index("}", text.index(":root {"))
    return text[end:]


def test_no_literal_colours_outside_the_token_block():
    """Rules must read var(--token). A literal here cannot be re-themed,
    which is exactly how a light mode ends up with white-on-white."""
    body = _body(CSS.read_text(encoding="utf-8"))
    literals = re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b", body)
    # The open-in-new icon is an SVG data URI whose stroke is repainted by
    # mask-image, so its %23000 is not a rendered colour.
    literals = [c for c in literals if not c.startswith("#000")]
    assert literals == [], f"literal colours outside :root: {literals}"
