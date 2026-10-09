"""Run the template-shortlist PoC end to end.

Usage:  python run.py [--out DIR] [--reuse-ocr]

Steps: build the template library -> render each (synthetic) test form to page images -> degrade them to the
requested scan quality -> OCR -> shortlist, verify, decide -> select the schema for accepted matches -> report.
Writes DIR/report.txt, DIR/results.json, DIR/png/*.png, DIR/ocr/*.txt (default DIR: ./out).
Exit code 0 only if every test case got its intended combined decision (forms.INTENDED), no case was
accepted as the wrong template, and every accepted match found its schema in the registry.
"""
import argparse, json, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                    # allow `python -I run.py` from any directory

import forms, shortlist                           # noqa: E402
from ocr import ocr_lines                         # noqa: E402
from registry import SchemaLookupError, SchemaRegistry, select_schema  # noqa: E402


def attach_schema(r, registry):
    """Select the schema for an accepted match; record a registry problem as an explicit error."""
    try:
        r["schema"] = select_schema(r, registry)
    except SchemaLookupError as e:
        r["schema"] = {"status": "error", "reason": e.reason, "detail": str(e),
                       "template_id": r["best"], "schema_id": None, "schema_path": None}
    return r


def annotate(r, qid, expected, scan):
    """Add grading fields to a match result."""
    r.update(test=qid, expected=expected, scan=scan,
             rank=next((k + 1 for k, i in enumerate(r["shortlist"]) if i == expected), None),
             minhash_outcome=shortlist.outcome(expected, r["minhash_decision"], r["best"]),
             combined_outcome=shortlist.outcome(expected, r["combined_decision"], r["best"]))
    intended = forms.INTENDED.get(qid)
    r["intended"] = sorted(intended) if intended else None
    schema_ok = r["combined_decision"] != "accept" or r.get("schema", {}).get("status") == "selected"
    r["as_intended"] = None if intended is None else (
        r["combined_decision"] in intended and r["combined_outcome"] != "WRONG" and schema_ok)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--reuse-ocr", action="store_true", help="skip OCR when DIR/ocr/<test>.txt already exists")
    args = ap.parse_args()
    out = Path(args.out)
    (out / "png").mkdir(parents=True, exist_ok=True)
    (out / "ocr").mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    index = shortlist.Index(forms.LIBRARY)
    registry = SchemaRegistry()
    print(f"library: {len(forms.LIBRARY)} templates indexed in {time.perf_counter() - t0:.1f}s", file=sys.stderr)

    results = []
    for qid, form, funds, scan, expected in forms.TESTS:
        txt = out / "ocr" / f"{qid}.txt"
        if not (args.reuse_ocr and txt.exists()):
            t = time.perf_counter()
            lines = []
            for n, img in enumerate(forms.render(form, forms.fill(form, funds)), 1):
                if scan != "clean":
                    img = forms.degrade(img, scan, seed=n)
                img.save(out / "png" / f"{qid}-{n}.png")
                lines += ocr_lines(img)
            txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"scanned {qid}: {n} page(s), {time.perf_counter() - t:.0f}s", file=sys.stderr)
        r = attach_schema(index.match(txt.read_text(encoding="utf-8").splitlines()), registry)
        results.append(annotate(r, qid, expected, scan))

    report = format_report(results)
    (out / "report.txt").write_text(report, encoding="utf-8")
    (out / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(report)
    alone = [r["test"] for r in results if r["minhash_outcome"] == "WRONG"]
    wrong = [r["test"] for r in results if r["combined_outcome"] == "WRONG"]
    off = [r["test"] for r in results if r["as_intended"] is False]
    errors = [r["test"] for r in results if r["schema"]["status"] == "error"]
    print(f"wrong accepts, MinHash alone (finding, not a failure): {len(alone)} {alone or ''}".rstrip())
    print(f"wrong accepts, MinHash + printed code (the proposed rule): {len(wrong)} {wrong or ''}".rstrip())
    print(f"intended decisions: {len(results) - len(off)} of {len(results)} {('NOT as intended: %s' % off) if off else ''}"
          .rstrip())
    print(f"schema selected for {sum(r['schema']['status'] == 'selected' for r in results)} accepted forms; "
          f"registry errors: {len(errors)} {errors or ''}".rstrip())
    return 1 if wrong or off or errors else 0


def _schema_text(sc):
    if not sc or sc["status"] == "none":
        return "none (not accepted)"
    if sc["status"] == "error":
        return f"ERROR {sc['reason']} ({sc['detail']})"
    return f"{sc['schema_id']} ({sc['schema_path']})"


def _num(v):
    return "-" if v is None else f"{v:.2f}"


def format_report(results):
    s = shortlist
    out = [f"thresholds: unknown if containment < {s.UNKNOWN_BELOW}; MinHash alone accepts if verify >= "
           f"{s.ACCEPT_SCORE} and margin >= {s.ACCEPT_MARGIN}; combined accepts if verify >= {s.ACCEPT_SCORE} "
           f"and all printed codes agree with the winner (the code stands in for the margin)\n"]
    for r in results:
        out.append(f"{r['test']}  expected: {r['expected']}  (scan: {r['scan']})")
        if r["verified"]:
            out.append(f"   {'verified shortlist (top 3 of 5)':32} {'MinHash J':>9} {'contain.':>8} {'verify':>7}")
            for v in r["verified"][:3]:
                out.append(f"   {v['id']:32} {v['minhash_j']:9.2f} {v['containment']:8.2f} {v['verify']:7.2f}")
        else:
            out.append("   no readable text: no candidates")
        out.append(f"   expected template in MinHash top {s.TOP}: {('rank %d' % r['rank']) if r['rank'] else 'no'}")
        out.append(f"   MinHash alone: {r['minhash_decision']} (margin {_num(r['margin'])}) -> {r['minhash_outcome']}")
        codes = ", ".join(r["printed_codes"]) or "none readable"
        out.append(f"   printed codes: {codes} ({r['code_status']})")
        out.append(f"   combined: {r['combined_decision']} ({r['reason']}) -> {r['combined_outcome']}")
        out.append(f"   schema: {_schema_text(r.get('schema'))}"
                   + ("" if r.get("as_intended") is not False else "   NOT AS INTENDED") + "\n")
    out.append(f"{'test':26} {'expected':23} {'top-5':7} {'MinHash alone':15} {'MinHash + printed code':40} schema")
    for r in results:
        sc = r.get("schema") or {}
        schema = sc.get("schema_id") or ("ERROR " + sc["reason"] if sc.get("status") == "error" else "-")
        out.append(f"{r['test']:26} {r['expected']:23} {('rank %d' % r['rank']) if r['rank'] else '-':7} "
                   f"{r['minhash_outcome']:15} {r['combined_outcome'] + ' (' + r['reason'] + ')':40} {schema}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    sys.exit(main())
