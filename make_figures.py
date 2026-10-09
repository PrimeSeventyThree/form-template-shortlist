"""Build the README figures from a finished run (python run.py first).

Usage:  python make_figures.py [--out DIR]       reads DIR/results.json and DIR/png, writes docs/
  docs/results.svg       outcome per test form: shortlist rank, MinHash alone, MinHash + printed code
  docs/margins.svg       verified score of the top candidate vs the runner-up, with the accept threshold
  docs/scan-quality.png  the same region of a test form at the three scan qualities
(docs/pipeline.svg is drawn by hand and not generated.)

SVG colours are CSS variables with a dark-mode override; every status colour comes with an icon and a text
label, so nothing depends on colour alone.
"""
import argparse, json, sys
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import forms, shortlist  # noqa: E402

LABELS = {
    "q01-current": "Current version", "q02-current-mild-scan": "Current version, mild scan",
    "q03-current-poor-fax": "Current version, poor fax", "q04-older-version": "Older version",
    "q05-older-version-poor-fax": "Older version, poor fax", "q06-plan-02": "Same client, plan 02",
    "q07-other-client": "Other client, same funds", "q08-grsp": "Same client, Group RRSP",
    "q09-unregistered-version": "Unregistered new version", "q10-dental-claim": "Unrelated form (dental claim)"}

STYLE = """<style>
  svg { --surface:#fcfcfb; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7;
        --series-1:#2a78d6; --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  @media (prefers-color-scheme: dark) {
    svg { --surface:#1a1a19; --ink:#ffffff; --ink-2:#c3c2b7; --grid:#2c2c2a; --axis:#383835; --series-1:#3987e5; } }
  .bg { fill: var(--surface); } .ink { fill: var(--ink); } .ink2 { fill: var(--ink-2); } .muted { fill: var(--muted); }
  .title { font-size: 17px; font-weight: 600; fill: var(--ink); } .sub { font-size: 13px; fill: var(--ink-2); }
  .head { font-size: 12px; font-weight: 600; fill: var(--ink-2); } .cell { font-size: 13px; fill: var(--ink); }
  .grid { stroke: var(--grid); stroke-width: 1; } .rule { stroke: var(--axis); stroke-width: 1; }
  .good { --s: var(--good); } .warning { --s: var(--warning); } .critical { --s: var(--critical); }
  .chip { fill: var(--s); fill-opacity: .14; stroke: var(--s); stroke-width: 1.5; }
  .dot { fill: var(--s); } .glyph { stroke: #ffffff; stroke-width: 2; fill: none; stroke-linecap: round; }
  .warning .glyph { stroke: #0b0b0b; } .warning .glyph-dot { fill: #0b0b0b; } .glyph-dot { fill: #ffffff; }
  .stem { stroke: var(--axis); stroke-width: 2; }
  .winner { fill: var(--series-1); stroke: var(--surface); stroke-width: 2; }
  .runner { fill: var(--muted); stroke: var(--surface); stroke-width: 2; }
  .threshold { stroke: var(--ink-2); stroke-width: 1.5; stroke-dasharray: 5 4; }
  .band { fill: var(--series-1); fill-opacity: .08; }
</style>"""

GLYPH = {  # icon drawn inside a 9 px circle, centred on 0,0
    "good": '<path class="glyph" d="M-4 0.5 L-1.2 3.2 L4 -2.8"/>',
    "warning": '<path class="glyph" d="M0 -4.2 V1"/><circle class="glyph-dot" cx="0" cy="3.7" r="1.2"/>',
    "critical": '<path class="glyph" d="M-3.2 -3.2 L3.2 3.2 M3.2 -3.2 L-3.2 3.2"/>'}


def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{escape(title)}"><title>{escape(title)}</title>{STYLE}'
            f'<rect class="bg" width="{w}" height="{h}" rx="12"/>{body}</svg>\n')


def chip(x, y, status, text, width=180):
    if status is None:                                           # not applicable: plain muted text
        return f'<text class="muted" x="{x + 4}" y="{y + 17}" font-size="13">{escape(text)}</text>'
    return (f'<g class="{status}" transform="translate({x},{y})"><rect class="chip" width="{width}" height="26" rx="6"/>'
            f'<g transform="translate(15,13)"><circle class="dot" r="9"/>{GLYPH[status]}</g>'
            f'<text class="cell" x="32" y="17.5">{escape(text)}</text></g>')


def outcome_chip(x, y, outcome):
    status = {"correct": "good", "person checks": "warning", "WRONG": "critical"}[outcome]
    return chip(x, y, status, {"correct": "Correct", "person checks": "Person checks", "WRONG": "Wrong template"}[outcome])


def results_svg(results):
    w, top, row = 940, 104, 40
    h = top + row * len(results) + 74
    cols = (24, 300, 506, 712)
    body = [f'<text class="title" x="24" y="34">Outcome per test form</text>',
            f'<text class="sub" x="24" y="56">Library of {len(forms.LIBRARY)} templates; thresholds fixed before the first run. '
            f'"Person checks" is safe: the form goes to a human queue.</text>']
    for x, head in zip(cols, ("TEST FORM", "CORRECT TEMPLATE IN TOP 5", "MINHASH ALONE", "MINHASH + PRINTED CODE")):
        body.append(f'<text class="head" x="{x}" y="{top - 14}" letter-spacing=".04em">{head}</text>')
    for n, r in enumerate(results):
        y = top + n * row
        body.append(f'<line class="grid" x1="24" x2="{w - 24}" y1="{y}" y2="{y}"/>')
        body.append(f'<text class="cell" x="{cols[0]}" y="{y + 25}">{escape(LABELS.get(r["test"], r["test"]))}</text>')
        if r["expected"] in ("review", "unknown"):
            body.append(chip(cols[1], y + 7, None, "not in library"))
        elif r["rank"]:
            body.append(chip(cols[1], y + 7, "good", f"Rank {r['rank']}"))
        else:
            body.append(chip(cols[1], y + 7, "warning", "Not in top 5"))
        body.append(outcome_chip(cols[2], y + 7, r["minhash_outcome"]))
        body.append(outcome_chip(cols[3], y + 7, r["combined_outcome"]))
    yb = top + row * len(results)
    ok = sum(r["combined_outcome"] == "correct" and r["expected"] not in ("review", "unknown") for r in results)
    wrong = sum(r["combined_outcome"] == "WRONG" for r in results)
    body.append(f'<line class="rule" x1="24" x2="{w - 24}" y1="{yb}" y2="{yb}"/>')
    known = sum(r["expected"] not in ("review", "unknown") for r in results)
    body.append(f'<text class="sub" x="24" y="{yb + 28}">In these {len(results)} synthetic cases, MinHash + printed code '
                f'accepted {ok} of {known} known forms and {wrong} wrong.</text>'
                f'<text class="sub" x="24" y="{yb + 47}">The unregistered version and the unrelated form were not '
                f'accepted.</text>')
    return svg(w, h, "".join(body), "Outcome per test form")


def margins_svg(results):
    w, top, row = 940, 120, 34
    x0, x1 = 300, 720                                            # score axis 0..1
    h = top + row * len(results) + 110
    sx = lambda v: x0 + (x1 - x0) * v
    near = {"q01-current", "q04-older-version", "q09-unregistered-version"}
    body = [f'<text class="title" x="24" y="34">Top candidate vs runner-up after verification</text>',
            f'<text class="sub" x="24" y="56">Verify score counts only the labels that differ between the 5 '
            f'shortlisted templates. MinHash alone accepts at ≥ {shortlist.ACCEPT_SCORE} with a lead of '
            f'≥ {shortlist.ACCEPT_MARGIN}.</text>',
            f'<circle class="winner" cx="30" cy="84" r="6"/><text class="cell" x="42" y="88.5">Top candidate</text>',
            f'<circle class="runner" cx="160" cy="84" r="5"/><text class="cell" x="172" y="88.5">Runner-up</text>',
            f'<rect class="band" x="270" y="77" width="16" height="14" rx="2"/>'
            f'<text class="cell" x="292" y="88.5">Same margin, different truth (see note)</text>']
    yb = top + row * len(results)
    for v in (0, .25, .5, .75, 1):
        body.append(f'<line class="grid" x1="{sx(v)}" x2="{sx(v)}" y1="{top - 8}" y2="{yb}"/>'
                    f'<text class="muted" x="{sx(v)}" y="{yb + 18}" font-size="12" text-anchor="middle">{v:g}</text>')
    body.append(f'<line class="threshold" x1="{sx(shortlist.ACCEPT_SCORE)}" x2="{sx(shortlist.ACCEPT_SCORE)}" '
                f'y1="{top - 14}" y2="{yb}"/>')
    body.append(f'<text class="head" x="{x1 + 24}" y="{top - 14}" letter-spacing=".04em">MARGIN · MINHASH ALONE</text>')
    for n, r in enumerate(results):
        y = top + n * row + row / 2
        if r["test"] in near:
            body.append(f'<rect class="band" x="16" y="{y - row / 2 + 2}" width="{w - 32}" height="{row - 4}" rx="4"/>')
        body.append(f'<text class="cell" x="24" y="{y + 4.5}">{escape(LABELS.get(r["test"], r["test"]))}</text>')
        if len(r["verified"]) < 2:                               # no readable text: nothing to plot
            body.append(f'<text class="ink2" x="{x1 + 24}" y="{y + 4.5}" font-size="13">no candidates · '
                        f'{r["minhash_decision"]}</text>')
            continue
        win, run = r["verified"][0]["verify"], r["verified"][1]["verify"]
        body.append(f'<line class="stem" x1="{sx(run)}" x2="{sx(win)}" y1="{y}" y2="{y}"/>')
        body.append(f'<circle class="runner" cx="{sx(run)}" cy="{y}" r="5"/><circle class="winner" cx="{sx(win)}" cy="{y}" r="6"/>')
        body.append(f'<text class="ink2" x="{x1 + 24}" y="{y + 4.5}" font-size="13">{r["margin"]:.2f} · '
                    f'{r["minhash_decision"]}</text>')
    body.append(f'<text class="muted" x="{(x0 + x1) / 2}" y="{yb + 38}" font-size="12" text-anchor="middle">'
                f'verify score (0 to 1)</text>')
    m = [r["margin"] for r in results if r["test"] in near and r["margin"] is not None]
    body.append(f'<text class="sub" x="24" y="{yb + 64}">Note: two correct near-identical matches and the unregistered '
                f'new version lead by {min(m):.2f} to {max(m):.2f}.</text>'
                f'<text class="sub" x="24" y="{yb + 83}">In these cases, the margin alone does not separate a known '
                f'version from an unregistered one.</text>')
    return svg(w, h, "".join(body), "Top candidate vs runner-up after verification")


def scan_quality_png(out_dir, results, dest):
    """Same region (personal information block) of the current version at the three scan qualities."""
    shots = [("q01-current", "Clean"), ("q02-current-mild-scan", "Mild scan"), ("q03-current-poor-fax", "Poor fax")]
    by_test = {r["test"]: r for r in results}
    box = (90, 655, 800, 1010)                                   # in the clean 1240 x 1754 page
    font, small = ImageFont.load_default(size=36), ImageFont.load_default(size=29)
    panels = []
    for test, title in shots:
        img = Image.open(out_dir / "png" / f"{test}-1.png").convert("L")
        dx, dy = (img.width - 1240) // 2, (img.height - 1754) // 2   # degraded pages were rotated with expand
        crop = img.crop((box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy)).convert("RGB")
        r = by_test[test]
        rank = f"rank {r['rank']}" if r["rank"] else "not in top 5"
        panel = Image.new("RGB", (crop.width, crop.height + 116), "white")
        panel.paste(crop, (0, 0))
        d = ImageDraw.Draw(panel)
        d.text((4, crop.height + 14), title, font=font, fill=(11, 11, 11))
        d.text((4, crop.height + 66), f"correct template {rank} · {r['combined_outcome']}", font=small, fill=(82, 81, 78))
        panels.append(panel)
    gap = 28
    sheet = Image.new("RGB", (sum(p.width for p in panels) + gap * (len(panels) + 1), panels[0].height + 2 * gap), "white")
    x = gap
    for p in panels:
        sheet.paste(p, (x, gap)); x += p.width + gap
    sheet = sheet.resize((sheet.width * 3 // 5, sheet.height * 3 // 5), Image.LANCZOS)
    sheet.save(dest, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "out"))
    out_dir = Path(ap.parse_args().out)
    results = json.loads((out_dir / "results.json").read_text(encoding="utf-8"))
    docs = HERE / "docs"; docs.mkdir(exist_ok=True)
    (docs / "results.svg").write_text(results_svg(results), encoding="utf-8")
    (docs / "margins.svg").write_text(margins_svg(results), encoding="utf-8")
    scan_quality_png(out_dir, results, docs / "scan-quality.png")
    print("wrote docs/results.svg, docs/margins.svg, docs/scan-quality.png")


if __name__ == "__main__":
    main()
