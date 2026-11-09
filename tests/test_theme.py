import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from guitarapp import theme


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_approved_palette_roles_are_exact():
    expected = {
        "cream": "#FFF6E7",
        "navy": "#1D2B3D",
        "peach": "#EFA77D",
        "honey": "#E3B652",
        "green": "#B9D0A9",
        "blue": "#91ACD2",
    }
    for role, value in expected.items():
        assert theme.PALETTE[role].upper() == value


def test_every_text_surface_pair_meets_aa_contrast():
    assert theme.TEXT_PAIRS, "stylesheet must declare its text/surface pairs"
    for text_role, surface_role in theme.TEXT_PAIRS:
        ratio = contrast(theme.PALETTE[text_role], theme.PALETTE[surface_role])
        assert ratio >= 4.5, f"{text_role} on {surface_role} is {ratio:.2f}:1"


def test_stylesheet_uses_palette_and_has_focus_disabled_selected_states():
    qss = theme.application_stylesheet()
    assert theme.PALETTE["cream"] in qss
    assert theme.PALETTE["navy"] in qss
    for state in (":focus", ":disabled", ":checked", ":hover"):
        assert state in qss
    for selector in ("#NavButton", "#ActionCard", "QToolBar", "QLineEdit", "#PageTitle"):
        assert selector in qss


def test_every_tool_icon_paints_at_requested_size(app):
    for name in theme.TOOL_ICONS:
        icon = theme.tool_icon(name, 40)
        assert not icon.isNull()
        pixmap = icon.pixmap(40, 40)
        assert pixmap.width() == 40 and pixmap.height() == 40
        image = pixmap.toImage()
        painted = sum(
            1 for x in range(0, 40, 2) for y in range(0, 40, 2) if image.pixelColor(x, y).alpha() > 0
        )
        assert painted > 10, f"{name} icon looks empty"


def test_supported_tool_names(app):
    assert set(theme.TOOL_ICONS) == {
        "home", "library", "practice", "tuner", "metronome", "theory", "quiz", "progress",
    }
    with pytest.raises(KeyError):
        theme.tool_icon("unknown")
