"""Template -> schema selection: the last step from scanned form to the JSON schema to extract it with.

A local registry (data/registry.json) maps each registered template ID, which includes its edition
(e.g. "K41M2.01 DCPP E-07-25"), to a schema ID and a schema file under data/. Several templates can share a
schema. Only accepted matches get a schema; review and unknown results get none. A missing registry entry or a
bad schema file raises SchemaLookupError with an explicit reason, so a configuration gap is never silent.

This stops at selecting the schema: it does not extract data or validate form data against the schema.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


class SchemaLookupError(Exception):
    """reason is one of: missing_mapping, schema_file_missing, schema_invalid_json, schema_not_object,
    schema_id_mismatch, invalid_registry."""

    def __init__(self, reason, template_id, detail=""):
        self.reason, self.template_id = reason, template_id
        super().__init__(f"{reason}: {template_id}" + (f" ({detail})" if detail else ""))


class SchemaRegistry:
    def __init__(self, path=DATA / "registry.json"):
        self.path = Path(path)
        self.base = self.path.parent                              # schema paths are relative to the registry
        try:
            entries = json.loads(self.path.read_text(encoding="utf-8"))["templates"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SchemaLookupError("invalid_registry", str(self.path), str(e)) from None
        self.entries = {}
        for e in entries:
            if not all(isinstance(e.get(k), str) and e[k] for k in ("template_id", "schema_id", "schema_path")):
                raise SchemaLookupError("invalid_registry", str(e.get("template_id")), "incomplete entry")
            if e["template_id"] in self.entries:
                raise SchemaLookupError("invalid_registry", e["template_id"], "duplicate entry")
            self.entries[e["template_id"]] = e

    def lookup(self, template_id):
        """Return {template_id, schema_id, schema_path} for a registered template whose schema file is valid."""
        e = self.entries.get(template_id)
        if e is None:
            raise SchemaLookupError("missing_mapping", template_id)
        file = self.base / e["schema_path"]
        try:
            schema = json.loads(file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SchemaLookupError("schema_file_missing", template_id, e["schema_path"]) from None
        except ValueError as err:
            raise SchemaLookupError("schema_invalid_json", template_id, f"{e['schema_path']}: {err}") from None
        if not isinstance(schema, dict) or schema.get("type") != "object" or "$schema" not in schema:
            raise SchemaLookupError("schema_not_object", template_id, e["schema_path"])
        if schema.get("$id") != e["schema_id"]:
            raise SchemaLookupError("schema_id_mismatch", template_id,
                                    f"registry says {e['schema_id']}, file says {schema.get('$id')}")
        return {"template_id": template_id, "schema_id": e["schema_id"], "schema_path": e["schema_path"]}


def select_schema(match, registry):
    """Schema selection for a match result from shortlist.Index.match.
    Accepted: {"status": "selected", template_id, schema_id, schema_path}.
    Review or unknown: {"status": "none", ...} with no schema. Raises SchemaLookupError on a registry problem."""
    if match["combined_decision"] != "accept":
        return {"status": "none", "template_id": None, "schema_id": None, "schema_path": None}
    return {"status": "selected", **registry.lookup(match["best"])}
