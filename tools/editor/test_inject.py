"""Run: python3 tools/editor/test_inject.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from serve import inject

PAGE = (
    "<body>\n"
    "  <p>untouched before</p>\n"
    "  <!--edit:intro-->\n"
    "  <p>old</p>\n"
    "  <!--/edit:intro-->\n"
    "  <p>untouched after</p>\n"
    "</body>\n"
)


def test_replaces_only_between_markers():
    out = inject(PAGE, "intro", "<p>new</p>")
    assert "<p>new</p>" in out
    assert "<p>old</p>" not in out
    assert "<p>untouched before</p>" in out
    assert "<p>untouched after</p>" in out
    assert out.startswith("<body>\n  <p>untouched before</p>\n")
    assert out.endswith("  <p>untouched after</p>\n</body>\n")


def test_is_idempotent():
    once = inject(PAGE, "intro", "<p>new</p>")
    twice = inject(once, "intro", "<p>new</p>")
    assert once == twice


def test_leading_and_trailing_whitespace_in_body_is_normalised():
    a = inject(PAGE, "intro", "<p>new</p>")
    b = inject(PAGE, "intro", "\n\n  <p>new</p>  \n\n")
    assert a == b


def test_missing_marker_raises():
    try:
        inject(PAGE, "nope", "<p>new</p>")
    except ValueError as e:
        assert "nope" in str(e)
    else:
        raise AssertionError("expected ValueError for a missing marker")


def test_unclosed_marker_raises():
    page = "<body><!--edit:intro--><p>old</p></body>"
    try:
        inject(page, "intro", "<p>new</p>")
    except ValueError as e:
        assert "intro" in str(e)
    else:
        raise AssertionError("expected ValueError for an unclosed marker")


def test_duplicated_marker_raises():
    page = PAGE + PAGE
    try:
        inject(page, "intro", "<p>new</p>")
    except ValueError as e:
        assert "intro" in str(e)
    else:
        raise AssertionError("expected ValueError for a duplicated marker")


def test_close_before_open_raises():
    page = "<body><!--/edit:intro--><p>old</p><!--edit:intro--></body>"
    try:
        inject(page, "intro", "<p>new</p>")
    except ValueError as e:
        assert "intro" in str(e)
    else:
        raise AssertionError("expected ValueError when close precedes open")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
