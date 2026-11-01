"""NFR-005 -- works on the two latest Chrome, Edge and Firefox, and is usable at 360 px without horizontal scrolling.

Automated here: the parts a Django test can see. The rest is a manual run recorded in the PR description:
for each browser, sign in as STU_A, complete EXM_1 end to end, and confirm at 360 px width (DevTools device
toolbar, "Responsive", 360 x 740) that no page scrolls sideways. Put one row per browser + version in the PR.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


def full_pages():
    """Every template that is a whole HTML document (partials such as _nav.html and _timer.html are skipped)."""
    for path in Path(settings.BASE_DIR).rglob("templates/**/*.html"):
        if ".venv" not in path.parts and "<html" in path.read_text(encoding="utf-8"):
            yield path


class ResponsiveTests(SimpleTestCase):
    def test_every_page_declares_the_mobile_viewport(self):
        # TODO(Kartik): add VIEWPORT inside <head> of every template this lists (20 today).
        missing = [str(p.relative_to(settings.BASE_DIR)) for p in full_pages() if VIEWPORT not in p.read_text(encoding="utf-8")]
        self.assertEqual(missing, [])

    def test_stylesheet_has_a_narrow_screen_rule(self):
        css = (Path(settings.BASE_DIR) / "portal/static/portal/site.css").read_text(encoding="utf-8")
        # TODO(Kartik): in site.css add   @media (max-width: 480px) { ... }   that at least:
        #   - lets .topbar and its nav wrap (flex-wrap: wrap) instead of overflowing,
        #   - makes tables scroll inside their own box: wrap the rule as  table { display: block; overflow-x: auto; }
        #   - lets the #timer stop floating (float: none; position: sticky stays) so it doesn't cover the stem,
        #   - keeps long words from pushing the page wide: body { overflow-wrap: anywhere; }
        self.assertRegex(css, re.compile(r"@media\s*\(max-width:\s*480px\)"))

    def test_no_fixed_widths_wider_than_360px(self):
        css = (Path(settings.BASE_DIR) / "portal/static/portal/site.css").read_text(encoding="utf-8")
        # A fixed `width: 400px` (not max-width) forces sideways scrolling on a 360 px phone.
        wide = [w for w in re.findall(r"(?<!-)width:\s*(\d+)px", css) if int(w) > 360]
        self.assertEqual(wide, [])
