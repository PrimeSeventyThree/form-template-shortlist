"""Schema selection: registry lookup, shared schemas, no schema without an accept, explicit errors.
Run from the repository root:  python -m unittest discover -s tests -v
"""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import forms, shortlist  # noqa: E402
from registry import SchemaLookupError, SchemaRegistry, select_schema  # noqa: E402

CURRENT = forms.LIBRARY[0]                                    # K41M2.01 DCPP E-07-25
LOOKALIKE = forms.LIBRARY[6]                                  # generated distractor, deliberately unregistered


def accepted(template_id):
    return {"combined_decision": "accept", "best": template_id}


def temp_registry(entries, files):
    """A registry in a temporary folder: entries for registry.json, files = {relative path: text}."""
    d = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    (d / "registry.json").write_text(json.dumps({"templates": entries}), encoding="utf-8")
    return SchemaRegistry(d / "registry.json")


class Lookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SchemaRegistry()
        cls.index = shortlist.Index(forms.LIBRARY)

    def test_every_hand_built_template_has_a_valid_schema(self):
        for t in forms.LIBRARY[:6]:
            with self.subTest(t["id"]):
                hit = self.registry.lookup(t["id"])
                self.assertTrue((Path(__file__).resolve().parents[1] / "data" / hit["schema_path"]).is_file())

    def test_registry_only_names_library_templates(self):
        ids = {t["id"] for t in forms.LIBRARY}
        self.assertLessEqual(set(self.registry.entries), ids)

    def test_templates_can_share_a_schema(self):
        shared = {self.registry.lookup(i)["schema_id"]
                  for i in ("K41M2.01 DCPP E-07-25", "K41M2.02 DCPP E-07-25", "K77B3.01 DCPP E-07-25")}
        self.assertEqual(shared, {"dcpp-enrolment/2025-07"})
        self.assertNotEqual(self.registry.lookup("K41M2.01 DCPP E-01-24")["schema_id"], "dcpp-enrolment/2025-07")

    def test_accepted_match_returns_template_and_schema(self):
        r = self.index.match(CURRENT["lines"] + [f"Page 1 of 1 {CURRENT['id']}"])
        self.assertEqual(r["combined_decision"], "accept")
        self.assertEqual(select_schema(r, self.registry),
                         {"status": "selected", "template_id": "K41M2.01 DCPP E-07-25",
                          "schema_id": "dcpp-enrolment/2025-07", "schema_path": "schemas/dcpp-enrolment-2025-07.json"})

    def test_review_and_unknown_select_no_schema(self):
        review = self.index.match(CURRENT["lines"])                         # no printed code -> review
        unknown = self.index.match(forms.DENTAL["lines"])
        for r in (review, unknown):
            with self.subTest(r["combined_decision"]):
                self.assertIn(r["combined_decision"], ("review", "unknown"))
                sel = select_schema(r, self.registry)
                self.assertEqual((sel["status"], sel["schema_id"], sel["schema_path"]), ("none", None, None))

    def test_missing_mapping_is_an_explicit_error(self):
        with self.assertRaises(SchemaLookupError) as ctx:
            select_schema(accepted(LOOKALIKE["id"]), self.registry)
        self.assertEqual((ctx.exception.reason, ctx.exception.template_id), ("missing_mapping", LOOKALIKE["id"]))

    def test_runner_records_registry_error_and_fails_the_case(self):
        import run
        r = run.attach_schema({"combined_decision": "accept", "best": LOOKALIKE["id"]}, self.registry)
        self.assertEqual((r["schema"]["status"], r["schema"]["reason"]), ("error", "missing_mapping"))


class BadSchemaFiles(unittest.TestCase):
    ENTRY = {"template_id": "T1 DCPP E-01-25", "schema_id": "s/1", "schema_path": "schemas/s1.json"}
    GOOD = json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "s/1", "type": "object"})

    def reason(self, files, entries=None):
        with self.assertRaises(SchemaLookupError) as ctx:
            temp_registry(entries or [self.ENTRY], files).lookup(self.ENTRY["template_id"])
        return ctx.exception.reason

    def test_good_file_passes(self):
        reg = temp_registry([self.ENTRY], {"schemas/s1.json": self.GOOD})
        self.assertEqual(reg.lookup(self.ENTRY["template_id"])["schema_id"], "s/1")

    def test_missing_file(self):
        self.assertEqual(self.reason({}), "schema_file_missing")

    def test_invalid_json(self):
        self.assertEqual(self.reason({"schemas/s1.json": "{not json"}), "schema_invalid_json")

    def test_not_an_object_schema(self):
        self.assertEqual(self.reason({"schemas/s1.json": "[1, 2]"}), "schema_not_object")

    def test_id_mismatch(self):
        self.assertEqual(self.reason({"schemas/s1.json": self.GOOD.replace("s/1", "s/2")}), "schema_id_mismatch")

    def test_duplicate_registry_entry(self):
        with self.assertRaises(SchemaLookupError) as ctx:
            temp_registry([self.ENTRY, self.ENTRY], {"schemas/s1.json": self.GOOD})
        self.assertEqual(ctx.exception.reason, "invalid_registry")


if __name__ == "__main__":
    unittest.main()
