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


def test_every_page_loads_theme_js_before_the_stylesheet(logged_in):
    """theme.js must run before first paint, or the page paints in the wrong
    theme and visibly flips. Before the stylesheet link is the safe spot."""
    for path in ("/", "/admin"):
        html = logged_in.get(path).get_data(as_text=True)
        assert "theme.js" in html, f"{path} does not load theme.js"
        assert html.index("theme.js") < html.index("style.css"), \
            f"{path} loads theme.js after the stylesheet"


def test_login_page_loads_theme_js(client):
    html = client.get("/login").get_data(as_text=True)
    assert "theme.js" in html
    assert html.index("theme.js") < html.index("style.css")


def test_theme_js_is_not_deferred_or_async():
    """defer/async would let the page paint first — the exact flash this
    script exists to prevent."""
    for name in ("index.html", "login.html", "admin.html"):
        html = (Path(__file__).resolve().parent.parent / "templates" / name).read_text(encoding="utf-8")
        line = next(ln for ln in html.splitlines() if "theme.js" in ln)
        assert "defer" not in line and "async" not in line, f"{name}: {line}"


def test_toggle_is_on_the_signed_in_pages(logged_in):
    for path in ("/", "/admin"):
        assert 'id="theme-toggle"' in logged_in.get(path).get_data(as_text=True)


def test_toggle_is_not_on_the_login_page(client):
    """The login page is a deliberately bare centred card with no topbar.
    It still honours the saved choice, because theme.js is in its head."""
    assert 'id="theme-toggle"' not in client.get("/login").get_data(as_text=True)


def test_no_inline_script_anywhere():
    """CSP is script-src 'self'. An inline script would need a nonce or hash."""
    for name in ("index.html", "login.html", "admin.html"):
        html = (Path(__file__).resolve().parent.parent / "templates" / name).read_text(encoding="utf-8")
        assert "<script>" not in html, f"{name} has an inline script"


def test_primary_button_is_a_heroui_pill():
    text = CSS.read_text(encoding="utf-8")
    block = text[text.index("\nbutton {"):text.index("button:hover")]
    assert "border-radius: 24px" in block, "button is not a pill"
    assert "border-radius: 10px" not in block, "old rounded-rectangle radius left behind"


def test_button_press_is_a_scale_not_a_nudge():
    text = CSS.read_text(encoding="utf-8")
    assert "transform: scale(.97)" in text


def test_reduced_motion_disables_the_button_transform():
    """The rest of this stylesheet already honours prefers-reduced-motion;
    a new transform must not be the one thing that ignores it."""
    text = CSS.read_text(encoding="utf-8")
    block = text[text.index("prefers-reduced-motion"):]
    assert "button:active" in block and "transform: none" in block


def test_secondary_button_press_is_a_scale_not_a_nudge():
    """Pinned on button.secondary:active specifically, not the stylesheet at
    large: the base button:active rule already satisfies a whole-file search
    for scale(.97), so a regression here (e.g. back to translateY(1px)) would
    slip past a looser assertion while Cancel visibly presses differently
    from Replace beside it."""
    text = CSS.read_text(encoding="utf-8")
    start = text.index("button.secondary:active {")
    rule = text[start:text.index("}", start)]
    assert "transform: scale(.97)" in rule
    assert "translateY" not in rule


def test_reduced_motion_disables_both_button_transforms():
    """button.secondary:active is (0,2,1) — more specific than a bare
    button:active guard, so the guard must name the secondary selector too
    or it silently loses the cascade and the Cancel button keeps animating
    for users who asked their OS to reduce motion."""
    text = CSS.read_text(encoding="utf-8")
    block = text[text.index("prefers-reduced-motion"):]
    assert "button.secondary:active" in block
    assert "transform: none" in block
