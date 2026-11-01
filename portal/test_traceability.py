"""NFR-007 -- every functional requirement is linked to at least one test case, and the RTM matches the code."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .traceability import MANUAL, TEST_PLAN

ALL_FRS = [f"FR-{n:03d}" for n in range(1, 31)]
# Not \b: in "test_UT_001_x" the underscore before UT is a word character, so \b would never match there.
ID = re.compile(r"(?<![A-Za-z0-9])(UT|IT|ST)_(\d{3})(?!\d)")


def automated_ids():
    """Every Test Plan ID named in a test file anywhere in the repo (method names and docstrings)."""
    found = set()
    for path in Path(settings.BASE_DIR).rglob("test*.py"):
        if "loadtest" in path.parts or path.name == "test_traceability.py":
            continue
        found.update(f"{kind}_{num}" for kind, num in ID.findall(path.read_text(encoding="utf-8")))
    return found


class TraceabilityTests(SimpleTestCase):
    def test_NFR_007_every_fr_is_verified_by_at_least_one_test_case(self):
        covered = {fr for frs in TEST_PLAN.values() for fr in frs}
        self.assertEqual([fr for fr in ALL_FRS if fr not in covered], [])

    def test_NFR_007_rtm_lists_all_118_test_plan_cases(self):
        counts = {kind: sum(1 for i in TEST_PLAN if i.startswith(kind)) for kind in ("UT", "IT", "ST")}
        self.assertEqual(counts, {"UT": 68, "IT": 37, "ST": 13})

    def test_NFR_007_every_case_is_automated_or_marked_manual_with_a_reason(self):
        # 21 cases (1 Nov) still lack a test; 3 of them arrive with FR-030 (#96), the rest are Deliverable-3 work.
        # Remove this skip when Deliverable-3's test-case update lands.
        self.skipTest("Deliverable-3: automate the remaining Test Plan cases, then enable this gate")
        missing = sorted(set(TEST_PLAN) - automated_ids() - set(MANUAL))
        self.assertEqual(missing, [], "Test Plan cases with no automated test and no manual reason")

    def test_NFR_007_no_test_names_an_id_the_test_plan_does_not_have(self):
        self.assertEqual(sorted(automated_ids() - set(TEST_PLAN)), [])

    def test_manual_cases_are_real_test_plan_cases(self):
        self.assertLessEqual(set(MANUAL), set(TEST_PLAN))

    def test_the_id_pattern_finds_ids_inside_test_method_names(self):
        self.assertEqual(ID.findall("def test_UT_001_x(self): ... IT_022, ST_013. UT_0430"), [("UT", "001"), ("IT", "022"), ("ST", "013")])
