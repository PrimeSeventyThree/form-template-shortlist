# Runbook: form template shortlist PoC

How to set up, run and verify the PoC on a new machine, change it, and fix common problems. For what it
shows and why, see [README.md](README.md).

All commands run from the repository root (the folder that contains `run.py`). It is self-contained: copy or
clone it anywhere.

## 1. Requirements

| | Needed |
|---|---|
| Python | **3.12** (the pinned numpy needs ≥ 3.12; rapidocr-onnxruntime 1.4.4 declares < 3.13) |
| OS | macOS, Linux or Windows; x86_64 or ARM64 (verified: macOS x86_64, Linux x86_64) |
| System packages | None on macOS or Windows. Minimal Linux images (e.g. `python:3.12-slim`) also need `libgl1` and `libglib2.0-0` for OpenCV |
| Disk | About 350 MB for the virtual environment |
| Network | Only for `pip install`. The OCR models ship inside the package, and runs are fully offline |
| Time | About 1.5 to 3 minutes for a full run on a laptop CPU, most of it OCR |

Alternatively, with **Docker** installed, nothing else is needed (see section 4).

## 2. Set up

macOS / Linux:

```bash
cd <repository folder>
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
cd <repository folder>
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

On Debian/Ubuntu servers without a desktop, if OpenCV complains later (see section 7):
`sudo apt-get install -y libgl1 libglib2.0-0`.

## 3. Verify and run

**Step 1: fast checks** (no OCR, about 5 seconds). These check that this machine builds the same library, the
same MinHash signatures and the same page images as the reference machines. They also check the decision
rules: empty input, weak content with a matching code, conflicting codes across pages, and OCR variants of a
code. And they check schema selection: registry lookups, shared schemas, no schema without an accept, missing
mappings and bad schema files.

```bash
.venv/bin/python -m unittest discover -s tests -v          # Windows: .venv\Scripts\python -m unittest discover -s tests -v
```

Expected: `Ran 30 tests ... OK`.

**Step 2: full run.**

```bash
.venv/bin/python -I run.py                                 # Windows: .venv\Scripts\python -I run.py
```

Expected: progress lines (`scanned q01-current: 3 page(s), ...`), then a report ending in this table, then
exit code 0:

```
test                       expected                top-5   MinHash alone   MinHash + printed code                   schema
q01-current                K41M2.01 DCPP E-07-25   rank 1  person checks   correct (code_agrees)                    dcpp-enrolment/2025-07
q02-current-mild-scan      K41M2.01 DCPP E-07-25   rank 1  person checks   correct (code_agrees)                    dcpp-enrolment/2025-07
q03-current-poor-fax       K41M2.01 DCPP E-07-25   -       person checks   person checks (low_containment)          -
q04-older-version          K41M2.01 DCPP E-01-24   rank 1  person checks   correct (code_agrees)                    dcpp-enrolment/2024-01
q05-older-version-poor-fax K41M2.01 DCPP E-01-24   -       person checks   person checks (low_containment)          -
q06-plan-02                K41M2.02 DCPP E-07-25   rank 1  correct         correct (code_agrees)                    dcpp-enrolment/2025-07
q07-other-client           K77B3.01 DCPP E-07-25   rank 1  correct         correct (code_agrees)                    dcpp-enrolment/2025-07
q08-grsp                   K41M2.01 GRSP E-07-25   rank 1  correct         correct (code_agrees)                    grsp-enrolment/2025-07
q09-unregistered-version   review                  -       correct         correct (code_disagrees)                 -
q10-dental-claim           unknown                 -       correct         correct (low_containment)                -

wrong accepts, MinHash alone (finding, not a failure): 0
wrong accepts, MinHash + printed code (the proposed rule): 0
intended decisions: 10 of 10
schema selected for 6 accepted forms; registry errors: 0
```

The run fails (exit code 1) if any test case doesn't get its intended combined decision (`INTENDED` in
`forms.py`: the six readable known forms accepted as the right template, both poor-fax scans not accepted,
the unregistered version sent to review, the dental claim unknown), or if any form is accepted as the wrong
template, or if an accepted form's schema can't be selected from the registry. A change that sent
everything to review would therefore fail too. The reason in brackets is the
combined rule's recorded reason (see section 5).

**Step 3: rebuild the figures** (optional, a few seconds). Regenerates `docs/results.svg`,
`docs/margins.svg` and `docs/scan-quality.png` from `out/`:

```bash
.venv/bin/python -I make_figures.py                        # Windows: .venv\Scripts\python -I make_figures.py
```

**Re-score without OCR.** After changing thresholds or shingling, reuse the saved OCR text (takes seconds):

```bash
.venv/bin/python -I run.py --reuse-ocr
```

## 4. Run with Docker (optional)

Runs the fast checks, then the full run, in Linux. The base image is pinned by digest and the Python packages
by version; the two OS libraries installed with `apt-get` are not version-pinned.

```bash
docker build -t form-shortlist-poc .
docker run --rm -v "$PWD/out:/matcher/out" form-shortlist-poc
```

On Windows PowerShell, use `-v "${PWD}/out:/matcher/out"`. The report and results then appear in `./out`.

## 5. Outputs

| File | Contents |
|---|---|
| `out/report.txt` | Per test form: verified top 3 with scores, rank of the correct template, printed codes found, both decisions with the reason, selected schema; summary table |
| `out/results.json` | The same data, machine-readable (one object per test form) |
| `out/png/<test>-<page>.png` | The exact page images that were OCR'd (open them to see the degraded scans) |
| `out/ocr/<test>.txt` | OCR text per test form |

**Reading the scores in the report:**
- **MinHash J:** estimated overlap between the scan's shingles and the template's (0 to 1).
- **contain.:** estimated share of the template's shingles found in the scan. Used only for the "unknown" test.
- **verify:** score on the shingles that differ between the 5 candidates (0 to 1). Decides accept or review.
- **margin:** the winner's verify score minus the runner-up's.
- **printed codes / code status:** every form code read from the footers, and their status: `agrees` or
  `disagrees` with the winner, `conflict` (different codes on different pages), `unreadable` (none found), or
  `not_compared` (a code but no readable content to compare it with).
- **reason** for the combined decision: `code_agrees` (accepted), `below_accept_score`, `code_disagrees`,
  `code_conflict`, `code_unreadable`, `low_containment` (unknown) or `no_readable_text`. Decisions use
  unrounded scores; the report shows them rounded.

## 6. Reproducibility

- **Seeded.** All randomness (lookalike templates, scan noise, MinHash hash functions) uses fixed seeds.
- **Pinned.** Package versions are fixed in `requirements.txt`.
- **Checked by the fast tests:** the library, the signatures and the rendered pages are byte-identical to the
  reference machines.
- **Verified 2026-10-08:** `out/results.json` and every `out/ocr/*.txt` were byte-identical between macOS
  x86_64 and Linux x86_64 (Docker). All 27 page images were pixel-identical; the `.png` files themselves
  can differ in a few bytes because PNG compression varies by platform.
- **Possible differences elsewhere:** the OCR model runs on the CPU in floating point. On another CPU type
  (e.g. Apple Silicon or ARM servers), OCR text may differ in a few characters, which shifts scores in the
  second decimal. To check, compare the summary table above, not the raw scores. A change in the "MinHash +
  printed code" column is a real difference; report it with `out/report.txt` attached.

## 7. Common changes

- **Add a template.** Append to `LIBRARY` in `forms.py`, using `dcpp(...)` for DCPP/GRSP forms or a
  `{"id": ..., "lines": [...]}` dict for other forms. The `id` must be the form code printed in the footer.
  Then update the golden digest in `tests/test_shortlist.py` (`test_library_is_identical`) after confirming
  the change is intended.
- **Register a template's schema.** Add an entry to `data/registry.json` (`template_id` exactly as in
  `forms.py`, `schema_id`, and `schema_path` relative to `data/`). The schema file must be JSON with
  `"$schema"`, `"type": "object"` and an `"$id"` equal to the `schema_id`. Several templates may point at the
  same schema file.
- **Add a test form.** Append a row to `TESTS` in `forms.py`: id, form, fund allocations, scan quality
  (`clean`, `mild` or `poor`) and the expected outcome (a template id, `review` or `unknown`). Add its
  intended combined decision to `INTENDED` in the same file.
- **Change thresholds.** Edit `UNKNOWN_BELOW`, `ACCEPT_SCORE` and `ACCEPT_MARGIN` in `shortlist.py`, then
  run `run.py --reuse-ocr`. Calibrate on real scans, not on this test set.
- **Change the scan quality.** Edit the `SCAN` settings in `forms.py`. Delete `out/` (or skip `--reuse-ocr`) so the
  pages are re-rendered and re-OCR'd.

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ImportError: libGL.so.1` or `libgthread-2.0.so.0` | Minimal Linux image without OpenCV's libraries: `apt-get install -y libgl1 libglib2.0-0` |
| `No matching distribution found for numpy==2.5.3`, or pip refuses rapidocr-onnxruntime | Wrong Python version: create the venv with Python 3.12 (`python3.12 -m venv .venv`; check with `.venv/bin/python --version`) |
| `ModuleNotFoundError: forms` | Run from the repository root, or call `python -I /path/to/run.py` |
| A determinism test fails | Different package versions than `requirements.txt` (check `pip freeze`), or the library/rendering code changed. Reinstall into a fresh venv |
| Full run very slow (over 10 minutes) | OCR on a slow CPU. Use `--reuse-ocr` for re-scoring; the first run must OCR 27 pages |
| `SchemaLookupError: invalid_registry` when `run.py` starts | `data/registry.json` is unreadable, or has an incomplete entry or a duplicate `template_id`. Fix the file |
| `schema: ERROR missing_mapping` (or `schema_file_missing`, `schema_invalid_json`, `schema_not_object`, `schema_id_mismatch`) | An accepted template has no registry entry, or its schema file is missing or invalid. Fix `data/registry.json` or the file under `data/schemas/` (see section 7) |
| Exit code 1 | A test case didn't get its intended decision, a form was accepted as the wrong template, or an accepted form's schema couldn't be selected. The last lines name the cases; see their blocks in `out/report.txt` (marked `NOT AS INTENDED`) |

## 9. Clean up

Delete `.venv/` and `out/`. With Docker, also run `docker rmi form-shortlist-poc`.
