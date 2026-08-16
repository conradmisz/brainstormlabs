"""Run: python3 tools/editor/test_inject.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import serve
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


def test_save_missing_md_raises_and_writes_nothing():
    """A block missing 'md' must fail before any file is written (all-or-nothing)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        content_dir = tmp / "content"
        site_dir = tmp / "site"
        content_dir.mkdir()
        site_dir.mkdir()
        (site_dir / "index.html").write_text(
            "<!--edit:intro-heading--><!--/edit:intro-heading-->"
            "<!--edit:intro-body--><!--/edit:intro-body-->"
        )
        orig_content, orig_site = serve.CONTENT, serve.SITE
        serve.CONTENT, serve.SITE = content_dir, site_dir
        try:
            payload = {
                "intro-heading": {"md": "PARTIAL-WRITE-PROBE", "html": "<p>h</p>"},
                "intro-body": {"html": "<p>b</p>"},  # missing "md"
            }
            try:
                serve.save(payload)
            except KeyError:
                pass
            else:
                raise AssertionError("expected KeyError for a block missing 'md'")
            assert not (content_dir / "intro-heading.md").exists()
            assert not (content_dir / "intro-body.md").exists()
            assert (site_dir / "index.html").read_text() == (
                "<!--edit:intro-heading--><!--/edit:intro-heading-->"
                "<!--edit:intro-body--><!--/edit:intro-body-->"
            )
        finally:
            serve.CONTENT, serve.SITE = orig_content, orig_site


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
