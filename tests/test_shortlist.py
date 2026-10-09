"""Fast checks (no OCR, a few seconds): determinism across machines and the matching rules.
Run from the repository root:  python -m unittest discover -s tests -v
"""
import hashlib, json, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forms, shortlist  # noqa: E402


class Determinism(unittest.TestCase):
    """Same inputs must give the same library, hashes and page images on every machine."""

    def test_library_is_identical(self):
        digest = hashlib.sha256(json.dumps(forms.LIBRARY, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, "c989645819e1881075ebd40ed75ecb68581d282a21171c2cbf2f1ec8aaa7a267")

    def test_minhash_signature_is_identical(self):
        sig = shortlist.signature(shortlist.shingles(["Target 2065 Balanced Fund (B65)"]))
        self.assertEqual([int(v) for v in sig[:3]], [12143725, 77172069, 274548949])

    def test_rendered_pages_are_identical(self):
        pages = forms.render(forms.LIBRARY[0], forms.fill(forms.LIBRARY[0], {"CBI": 60}))
        digest = hashlib.sha256(b"".join(p.tobytes() for p in pages)).hexdigest()
        self.assertEqual((len(pages), digest),
                         (3, "82f9bd83eb936ec2770c88125640948a907eb9e234b152be9ad0b1fe84c58abb"))


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = shortlist.Index(forms.LIBRARY)

    def test_shingles_ignore_spaces_and_footer(self):
        a = shortlist.shingles(["Defined Contribution Pension Plan", "Page 1 of 5", "K41M2.01 DCPP E-07-25"])
        self.assertEqual(a, shortlist.shingles(["DefinedContributionPensionPlan"]))

    def test_each_hand_built_template_matches_itself(self):
        for t in forms.LIBRARY[:6]:
            with self.subTest(t["id"]):
                r = self.index.match(t["lines"] + [f"Page 1 of 1 {t['id']}"])
                self.assertEqual(r["best"], t["id"])
                self.assertEqual(r["combined_decision"], "accept")

    def test_code_disagreement_never_accepts(self):
        t = forms.UNREGISTERED                                  # new version, not in the library
        r = self.index.match(t["lines"] + [f"Page 1 of 1 {t['id']}"])
        self.assertNotEqual(r["combined_decision"], "accept")

    def test_unrelated_form_is_unknown(self):
        self.assertEqual(self.index.match(forms.DENTAL["lines"])["combined_decision"], "unknown")

    def test_form_code_tolerates_ocr(self):
        self.assertTrue(shortlist.same_code("K4lM2.O2DCPP E-07-25", "K41M2.02 DCPP E-07-25"))
        self.assertFalse(shortlist.same_code("K41M2.01 DCPP E-10-26", "K41M2.01 DCPP E-07-25"))


CURRENT, OLDER = forms.LIBRARY[0], forms.LIBRARY[1]          # K41M2.01 DCPP E-07-25 / E-01-24
footer = lambda t, n=1, of=1: f"Page {n} of {of} {t['id']}"


class EmptyInput(unittest.TestCase):
    """No usable text must be a review case with a reason, never a crash or an invented best template."""

    @classmethod
    def setUpClass(cls):
        cls.index = shortlist.Index(forms.LIBRARY)

    def test_no_text_variants_go_to_review(self):
        for name, lines in (("empty list", []), ("whitespace", ["   ", ""]), ("footer only", [footer(CURRENT)])):
            with self.subTest(name):
                r = self.index.match(lines)
                self.assertEqual((r["combined_decision"], r["reason"]), ("review", "no_readable_text"))
                self.assertEqual((r["best"], r["margin"], r["verified"], r["shortlist"]), (None, None, [], []))

    def test_report_handles_empty_result(self):
        import run
        r = run.annotate(self.index.match([]), "q-empty", CURRENT["id"], "clean")
        self.assertEqual(r["combined_outcome"], "person checks")
        report = run.format_report([r])
        self.assertIn("no readable text", report)
        self.assertIn("margin -", report)


class CombinedRule(unittest.TestCase):
    """Accept needs content evidence (verify >= ACCEPT_SCORE) and one consistent code that agrees."""

    @classmethod
    def setUpClass(cls):
        cls.index = shortlist.Index(forms.LIBRARY)

    def test_matching_footer_does_not_rescue_weak_content(self):
        r = self.index.match(CURRENT["lines"][:105] + [footer(CURRENT)])       # about 70% of the form
        self.assertEqual(r["best"], CURRENT["id"])
        self.assertEqual(r["code_status"], "agrees")
        self.assertLess(r["verified"][0]["verify"], shortlist.ACCEPT_SCORE)
        self.assertEqual((r["combined_decision"], r["reason"]), ("review", "below_accept_score"))

    def test_footer_resolves_small_margin_when_content_is_strong(self):
        r = self.index.match(CURRENT["lines"] + [footer(CURRENT)])
        self.assertLess(r["margin"], shortlist.ACCEPT_MARGIN)                  # too close for MinHash alone
        self.assertEqual(r["minhash_decision"], "review")
        self.assertEqual((r["combined_decision"], r["reason"]), ("accept", "code_agrees"))

    def test_conflicting_versions_across_pages_go_to_review(self):
        r = self.index.match(CURRENT["lines"] + [footer(CURRENT, 1, 3), footer(OLDER, 2, 3)])
        self.assertEqual(r["code_status"], "conflict")
        self.assertEqual((r["combined_decision"], r["reason"]), ("review", "code_conflict"))
        self.assertEqual(len(r["printed_codes"]), 2)

    def test_repeated_identical_codes_are_fine(self):
        r = self.index.match(CURRENT["lines"] + [footer(CURRENT, n, 3) for n in (1, 2, 3)])
        self.assertEqual((r["code_status"], r["combined_decision"]), ("agrees", "accept"))

    def test_equivalent_ocr_variants_are_one_code(self):
        r = self.index.match(CURRENT["lines"] + ["Page 1 of 2 K41M2.01 DCPP E-07-25", "Page2of2K4lM2.O1DCPP E-07-25"])
        self.assertEqual(len(r["printed_codes"]), 2)
        self.assertEqual((r["code_status"], r["combined_decision"]), ("agrees", "accept"))

    def test_single_code_disagreeing_with_content_goes_to_review(self):
        r = self.index.match(CURRENT["lines"] + [footer(OLDER)])
        self.assertEqual(r["best"], CURRENT["id"])
        self.assertEqual((r["combined_decision"], r["reason"]), ("review", "code_disagrees"))

    def test_unreadable_code_goes_to_review(self):
        r = self.index.match(CURRENT["lines"])
        self.assertEqual((r["code_status"], r["combined_decision"]), ("unreadable", "review"))


if __name__ == "__main__":
    unittest.main()
