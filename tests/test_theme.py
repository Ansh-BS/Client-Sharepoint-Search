import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "style.css"


def _body(text):
    """Everything after the :root token blocks — the rules, not the palette.

    Task 2 split the single :root block into three (light, shared, dark).
    They no longer sit at one contiguous span starting at the first `:root {`,
    so this now skips past every top-level :root / :root.dark block — not
    just the first — and returns whatever comes after the last of them.
    """
    ends = [text.index("\n}", m.start()) + 2
            for m in re.finditer(r":root(?:\.dark)? \{", text)]
    return text[max(ends):]


def test_no_literal_colours_outside_the_token_block():
    """Rules must read var(--token). A literal here cannot be re-themed,
    which is exactly how a light mode ends up with white-on-white."""
    body = _body(CSS.read_text(encoding="utf-8"))
    literals = re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b", body)
    # The open-in-new icon is an SVG data URI whose stroke is repainted by
    # mask-image, so its %23000 is not a rendered colour.
    literals = [c for c in literals if not c.startswith("#000")]
    assert literals == [], f"literal colours outside :root: {literals}"


def _tokens(text, selector):
    start = text.index(selector + " {")
    block = text[start:text.index("\n}", start)]
    return set(re.findall(r"^\s*(--[a-z0-9-]+):", block, re.M))


def test_light_and_dark_define_the_same_tokens():
    """A token defined in one theme and not the other is the classic bug:
    it silently inherits the wrong value instead of failing loudly."""
    text = CSS.read_text(encoding="utf-8")
    light = _tokens(text, ":root")
    dark = _tokens(text, ":root.dark")
    assert light == dark, (
        f"only in light: {sorted(light - dark)}; only in dark: {sorted(dark - light)}"
    )


def test_both_themes_set_color_scheme():
    """Native controls — scrollbar, the search field's clear ×, the file
    button — follow color-scheme, not our tokens."""
    text = CSS.read_text(encoding="utf-8")
    assert "color-scheme: light" in text
    assert "color-scheme: dark" in text


def test_theme_independent_values_are_not_duplicated():
    """Spacing, motion and the gold action do not vary by theme. Duplicating
    them into both blocks invites the two copies to drift apart."""
    text = CSS.read_text(encoding="utf-8")
    for token in ("--sp-4", "--radius", "--dur", "--ease-out", "--mono",
                  "--display", "--action", "--action-hover"):
        assert len(re.findall(rf"^\s*{token}:", text, re.M)) == 1, \
            f"{token} is defined more than once"
