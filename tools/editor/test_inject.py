"""Run: python3 tools/editor/test_inject.py"""
import json
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


def _site_with_markers():
    return (
        "<html><body>\n"
        "<!--edit:intro-heading--><!--/edit:intro-heading-->\n"
        "<!--edit:intro-body--><!--/edit:intro-body-->\n"
        "</body></html>"
    )


def _rd_site_with_markers():
    return (
        "<html><body>\n"
        "<!--edit:rd-description--><!--/edit:rd-description-->\n"
        "</body></html>"
    )


def _with_temp_site_and_content():
    """Context manager-ish helper: point serve.CONTENT/SITE at a fresh temp dir
    seeded with both pages, yielding (content_dir, site_dir), restoring after."""
    import contextlib

    @contextlib.contextmanager
    def _cm():
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            content_dir, site_dir = tmp / "content", tmp / "site"
            content_dir.mkdir()
            site_dir.mkdir()
            (site_dir / "reactor-drone").mkdir()
            (site_dir / "index.html").write_text(_site_with_markers(), encoding="utf-8")
            (site_dir / "reactor-drone" / "index.html").write_text(
                _rd_site_with_markers(), encoding="utf-8")
            orig_content, orig_site = serve.CONTENT, serve.SITE
            serve.CONTENT, serve.SITE = content_dir, site_dir
            try:
                yield content_dir, site_dir
            finally:
                serve.CONTENT, serve.SITE = orig_content, orig_site

    return _cm()


def test_save_embeds_one_build_stamp_in_every_written_page():
    with _with_temp_site_and_content() as (_content_dir, site_dir):
        payload = {
            "intro-heading": {"md": "h", "html": "<h1>h</h1>"},
            "rd-description": {"md": "d", "html": "<p>d</p>"},
        }
        stamp, log = serve.save(payload)
        assert len(stamp) == 12
        assert all(c in "0123456789abcdef" for c in stamp)
        marker = f"<!--build:{stamp}-->"
        home = (site_dir / "index.html").read_text(encoding="utf-8")
        rd = (site_dir / "reactor-drone" / "index.html").read_text(encoding="utf-8")
        assert home.count(marker) == 1
        assert rd.count(marker) == 1
        assert any(line == "wrote site/index.html" for line in log)


def test_save_twice_same_content_same_stamp_no_accumulation():
    with _with_temp_site_and_content() as (_content_dir, site_dir):
        payload = {"intro-heading": {"md": "h", "html": "<h1>h</h1>"}}
        stamp1, _ = serve.save(payload)
        stamp2, _ = serve.save(payload)
        assert stamp1 == stamp2
        home = (site_dir / "index.html").read_text(encoding="utf-8")
        assert home.count(f"<!--build:{stamp1}-->") == 1


def test_save_changing_block_html_changes_stamp():
    with _with_temp_site_and_content() as (_content_dir, _site_dir):
        stamp1, _ = serve.save({"intro-heading": {"md": "h", "html": "<h1>h</h1>"}})
        stamp2, _ = serve.save({"intro-heading": {"md": "h2", "html": "<h1>h2</h1>"}})
        assert stamp1 != stamp2


def _drive_publish(run_results, live=True, saved=("wrote site/index.html",), branch="master"):
    """Run publish() with save/run/wait_until_live stubbed. Returns the yielded lines.

    run_results answers every run() call after the branch probe, which is
    answered by `branch` (defaulting to the production branch so existing
    callers still exercise the post-guard path unchanged).
    """
    calls = []
    results = [(0, branch)] + list(run_results)
    real = (serve.save, serve.run, serve.wait_until_live)
    serve.save = lambda payload: ("stamp123456", list(saved))
    serve.run = lambda cmd: (calls.append(cmd), results.pop(0))[1]
    serve.wait_until_live = lambda *a, **k: live
    try:
        return list(serve.publish({"intro-heading": {"md": "x", "html": "<h1>x</h1>"}})), calls
    finally:
        serve.save, serve.run, serve.wait_until_live = real


class _Resp:
    """Minimal context-manager stand-in for urlopen()'s response object."""
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def test_page_url_for_nested_page_is_a_directory_url():
    assert serve._page_url("index.html") == "https://thebrainstormlabs.com/"
    assert serve._page_url("reactor-drone/index.html") == "https://thebrainstormlabs.com/reactor-drone/"


def test_wait_until_live_requires_every_page_to_match():
    """A publish that only edits rd-* blocks must not go LIVE just because
    site/index.html (untouched) already has the stamp and reactor-drone doesn't."""
    stamp = "deadbeef1234"
    marker = f"<!--build:{stamp}-->"
    orig_urlopen = serve.urllib.request.urlopen
    try:
        def home_matches_rd_stale(req, timeout=10):
            if "reactor-drone" in req.full_url:
                body = b"<html><body>rd-OLD, no stamp here</body></html>"
            else:
                body = f"<html><body>home {marker}</body></html>".encode()
            return _Resp(body)

        def all_match(req, timeout=10):
            body = f"<html><body>page {marker}</body></html>".encode()
            return _Resp(body)

        serve.urllib.request.urlopen = home_matches_rd_stale
        assert serve.wait_until_live(stamp, timeout=1) is False

        serve.urllib.request.urlopen = all_match
        assert serve.wait_until_live(stamp, timeout=1) is True
    finally:
        serve.urllib.request.urlopen = orig_urlopen


def test_wait_until_live_matches_stamp_not_byte_equality():
    """The served body never equals the local file (Cloudflare rewrites mailto:
    links and injects a decode script), so matching must be on the stamp
    comment alone, tolerant of extra injected markup around it."""
    stamp = "cafef00dbeef"
    marker = f"<!--build:{stamp}-->"
    orig_urlopen = serve.urllib.request.urlopen
    try:
        def cdn_rewritten_body(req, timeout=10):
            body = (
                "<html><body>"
                f"{marker}"
                '<a href="/cdn-cgi/l/email-protection#aac9c5c4d8">[email&#160;protected]</a>'
                '<script src="/cdn-cgi/scripts/xyz/email-decode.min.js"></script>'
                "</body></html>"
            ).encode("utf-8")
            return _Resp(body)

        serve.urllib.request.urlopen = cdn_rewritten_body
        assert serve.wait_until_live(stamp, timeout=1) is True
    finally:
        serve.urllib.request.urlopen = orig_urlopen


def test_publish_reports_each_phase_then_live():
    lines, calls = _drive_publish([
        (0, ""),            # git add
        (1, ""),            # git diff --cached --quiet -> there are changes
        (0, "[site-editor abc1234] content: update site copy"),  # git commit
        (0, ""),            # git push
        (0, "Deployment complete! https://abc.brainstormlabs.pages.dev"),  # wrangler
    ])
    text = "\n".join(lines)
    assert "Saving files" in text
    assert "Pushing to GitHub" in text
    assert "pushed to github.com/conradmisz/brainstormlabs" in text
    assert "Deploying to Cloudflare Pages" in text
    assert "LIVE —" in text
    assert lines.index("Pushing to GitHub…") < lines.index("Deploying to Cloudflare Pages… (this is the slow bit)")
    assert calls[-1][:4] == ["npx", "wrangler", "pages", "deploy"]


def test_publish_commits_only_content_and_site_paths():
    """git commit must not sweep up unrelated pre-staged work under this message."""
    _, calls = _drive_publish([
        (0, ""),            # git add
        (1, ""),            # git diff --cached --quiet -> there are changes
        (0, "[site-editor abc1234] content: update site copy"),  # git commit
        (0, ""),            # git push
        (0, "Deployment complete!"),  # wrangler
    ])
    commit_call = next(c for c in calls if c[:2] == ["git", "commit"])
    assert commit_call[-3:] == ["--", "content", "site"]


def test_publish_stops_before_deploy_when_commit_fails():
    lines, calls = _drive_publish([
        (0, ""),                       # git add
        (1, ""),                       # there are changes
        (1, "nothing to commit, working tree clean"),  # git commit fails
    ])
    text = "\n".join(lines)
    assert "FAILED" in text
    assert "Deploying to Cloudflare Pages" not in text
    assert not any(c[0] == "npx" for c in calls)


def test_publish_says_not_live_when_the_site_never_updates():
    lines, _ = _drive_publish([
        (0, ""), (1, ""), (0, "committed"), (0, ""), (0, "Deployment complete!"),
    ], live=False)
    text = "\n".join(lines)
    assert "LIVE —" not in text
    assert "still served the old page" in text


def test_publish_refuses_from_a_non_production_branch():
    lines, calls = _drive_publish([], branch="site-editor")
    text = "\n".join(lines)
    assert "FAILED" in text
    assert "site-editor" in text
    assert "master" in text
    assert calls == [["git", "rev-parse", "--abbrev-ref", "HEAD"]]
    assert not any(c[:2] == ["git", "commit"] for c in calls)
    assert not any(c[0] == "npx" for c in calls)


def test_publish_push_uses_dash_u_origin_head():
    _, calls = _drive_publish([
        (0, ""), (1, ""), (0, "committed"), (0, ""), (0, "Deployment complete!"),
    ])
    push_call = next(c for c in calls if c[:2] == ["git", "push"])
    assert push_call == ["git", "push", "-u", "origin", "HEAD"]


def test_publish_pushes_exactly_once_when_there_was_something_to_commit():
    _, calls = _drive_publish([
        (0, ""), (1, ""), (0, "committed"), (0, ""), (0, "Deployment complete!"),
    ])
    push_calls = [c for c in calls if c[:2] == ["git", "push"]]
    assert len(push_calls) == 1


def test_publish_pushes_when_nothing_to_commit():
    """Bug 2: master ended up 17 commits ahead of origin because push only ran
    inside the 'there is something to commit' branch. A publish with no copy
    changes must still push whatever local commits already exist."""
    lines, calls = _drive_publish([
        (0, ""),            # git add
        (0, ""),            # git diff --cached --quiet -> nothing to commit
        (0, ""),            # git push
        (0, "Deployment complete!"),  # wrangler
    ])
    text = "\n".join(lines)
    assert "Nothing to commit" in text
    assert not any(c[:2] == ["git", "commit"] for c in calls)
    push_calls = [c for c in calls if c[:2] == ["git", "push"]]
    assert push_calls == [["git", "push", "-u", "origin", "HEAD"]]
    assert calls[-1][:4] == ["npx", "wrangler", "pages", "deploy"]


def _fake_handler(body: bytes):
    """A serve.Handler instance wired to in-memory rfile/wfile, bypassing real sockets."""
    import io
    h = serve.Handler.__new__(serve.Handler)
    h.rfile = io.BytesIO(body)
    h.wfile = io.BytesIO()
    h.headers = {"Content-Length": str(len(body))}
    h.path = "/publish"
    h.command = "POST"
    h.request_version = "HTTP/1.1"
    h.client_address = ("127.0.0.1", 0)
    h.requestline = "POST /publish HTTP/1.1"
    h.close_connection = True
    return h


def test_do_post_reports_failed_sentinel_on_unexpected_exception():
    """A stray OSError (e.g. git/wrangler missing from PATH) inside publish() must
    still reach the client as a FAILED line, not kill the request silently."""
    real_publish = serve.publish

    def boom(payload):
        yield "Saving files…"
        raise FileNotFoundError("[Errno 2] No such file or directory: 'git'")

    serve.publish = boom
    try:
        h = _fake_handler(json.dumps({"intro-heading": {"md": "x", "html": "<h1>x</h1>"}}).encode())
        h.do_POST()
    finally:
        serve.publish = real_publish
    out = h.wfile.getvalue().decode()
    assert "Saving files" in out
    assert "FAILED" in out
    assert "No such file or directory" in out


def test_do_post_bad_json_body_gets_clean_400():
    h = _fake_handler(b"not json")
    h.do_POST()
    out = h.wfile.getvalue()
    assert b"400" in out
    assert b"bad request" in out


def test_do_post_non_dict_body_gets_clean_400():
    h = _fake_handler(json.dumps([1, 2, 3]).encode())
    h.do_POST()
    out = h.wfile.getvalue()
    assert b"400" in out
    assert b"bad request" in out


def test_do_post_still_reports_not_published_for_validation_errors():
    """Existing save()-raised ValueError/KeyError must stay distinct from the
    generic FAILED sentinel."""
    real_publish = serve.publish

    def rejects(payload):
        yield "Saving files…"
        raise ValueError("bad block")

    serve.publish = rejects
    try:
        h = _fake_handler(json.dumps({"intro-heading": {"md": "x", "html": "<h1>x</h1>"}}).encode())
        h.do_POST()
    finally:
        serve.publish = real_publish
    out = h.wfile.getvalue().decode()
    assert "NOT PUBLISHED" in out
    assert "FAILED" not in out


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
