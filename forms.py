"""Template library, test forms, rendering and scan degradation for the shortlist PoC.

All data here is synthetic: a fictional insurer ("Example Life"), fictional plan sponsors, fund names, form
codes and member details. No real form, company or person is used.

Separation: the library is each blank form's label text, written here as source (standing in for the blank
PDF's text layer). Test forms are filled in from the same synthetic label definitions, rendered to page images,
optionally degraded and read back by OCR. Library and test forms share the label definitions but never OCR
output or OCR errors, so this tests robustness to rendering, scanning and OCR; it is not an independently
collected real-world dataset. Labels only: long legal paragraphs are
the same across a form family and are left out on purpose.

Everything random is seeded, so every run builds the same library and the same images.
"""
import io, json, random, re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DATA = Path(__file__).resolve().parent / "data"
FUNDS = json.loads((DATA / "funds.json").read_text(encoding="utf-8"))           # code -> name, in form order
FUND_LINES = [f"{name} ({code})" for code, name in FUNDS.items()]
TARGET, OWN = FUND_LINES[:30], FUND_LINES[30:]                                     # target-date / own choice

PAYROLL_M = ["001 - Maple Example Corp. (MEC)", "002 - Maple Example Logistics Inc. (MEL)",
             "003 - Maple Example Services Inc. (MES)", "004 - Maple Example Retail Inc. (MER)",
             "005 - Maple Example Holdings Inc. (MEH)"]
PERSONAL = ["1 Personal information", "First name", "Middle initial", "Last name", "Assigned sex at birth*",
            "Male", "Female", "Date of birth (dd-mm-yyyy)", "Social Insurance Number**", "Member ID",
            "Address (street number and name)", "Apartment or suite", "City", "Province", "Postal code",
            "Telephone number (day)", "Email address", "Telephone number (evening)",
            "Date of enrolment (dd-mm-yyyy)", "Date of employment (dd-mm-yyyy)", "Province of employment"]
MARITAL = ["2 Marital status", "I have a spouse.", "Spouse's first name", "Date of birth (dd-mm-yyyy)",
           "I do not have a spouse."]
RELATIONSHIPS = ["Husband (married)", "Wife (married)", "Spouse", "Civil union", "Common-law", "Fiance(e)",
                 "Friend", "Former spouse", "Father", "Mother", "Brother", "Sister", "Son", "Daughter", "Nephew",
                 "Niece", "Aunt", "Uncle", "Cousin", "Grandchild", "Grandparent", "Step family", "Family-in-law",
                 "Institution", "Other"]
BENEFICIARY = ["3 Beneficiary", "I name the following beneficiary for benefits payable on my death:",
               "Beneficiary's first name", "Relationship to you*", "Revocable**", "Percentage of benefits",
               "*Use one of these values for relationship", *RELATIONSHIPS]
CONTINGENT = ["4 Contingent beneficiary", "Name a contingent (secondary) beneficiary for your account.",
              "This replaces any earlier contingent beneficiary.", "Relationship to you* (see values above)"]
SIGN = ["7 Authorization and signature", "I do not consent to marketing contact.", "Signature", "8 Privacy"]


def dcpp(code, sponsor="Maple Example Corp.", client="K41M2", plan="01", contract="50101 -G",
         payroll=PAYROLL_M, target_funds=TARGET, own_funds=OWN, required="2%", kind="DCPP"):
    title = {"DCPP": ["Defined Contribution Pension Plan", "(DCPP) enrolment form"],
             "GRSP": ["Group Registered Retirement Savings Plan", "(GRSP) enrolment form"]}[kind]
    return {"id": code, "lines": [
        *title, "Return the completed form to:", "Example Life, Group Retirement Services",
        "PO Box 0000 Stn Example, Sampletown ON A1A 1A1", "Please print clearly.",
        "Plan sponsor information", "Completed by the plan sponsor.",
        "Name of plan sponsor", sponsor, "Client ID", client, "Plan", plan, "Contract number", contract,
        "Classifications", "Subdivision", "Payroll ID", "User Field", *payroll,
        *PERSONAL, *(MARITAL if kind == "DCPP" else []), *BENEFICIARY, *CONTINGENT,
        "5 Contributions", f"The plan deducts a required contribution of {required} from your pay.",
        "Additional contribution per pay", "% per pay, deposited into the plan.",
        "6 Investment instructions", "Percentages must be whole numbers and total 100%.",
        "Option A - target date funds", "Percentage allocation", *target_funds,
        "Option B - choose your own funds", *own_funds, "Total", *SIGN]}


def swap(lines, drop, add):
    """Fund line-up change between versions: remove lines containing any of `drop`, append `add`."""
    return [l for l in lines if not any(d in l for d in drop)] + add


# ---- the library: 6 hand-built templates + 500 seeded lookalikes ----
OLD_TARGET = swap(TARGET, ["2065"], ["Target 2020 Growth Fund (G20)", "Target 2020 Balanced Fund (B20)",
                                     "Target 2020 Cautious Fund (C20)"])
LIBRARY = [
    dcpp("K41M2.01 DCPP E-07-25"),                                                   # the current version
    dcpp("K41M2.01 DCPP E-01-24", target_funds=OLD_TARGET),                          # older version: 6 fund lines differ
    dcpp("K41M2.02 DCPP E-07-25", plan="02", contract="50102 -G", target_funds=[]),  # same client, plan 02
    dcpp("K77B3.01 DCPP E-07-25", sponsor="Birch Sample Holdings Ltd.", client="K77B3", contract="60201 -G",
         payroll=["001 - Birch Sample Holdings Ltd. (BSH)", "002 - Birch Sample Transport Inc. (BST)"]),  # other client, same funds
    dcpp("K41M2.01 GRSP E-07-25", kind="GRSP", required="0%"),                       # same client, other product
    {"id": "K41M2 BENCHG E-05-24", "lines": ["Beneficiary change request", "Name of plan sponsor",
     "Maple Example Corp.", "Client ID", "K41M2", *PERSONAL[:10], *BENEFICIARY, *CONTINGENT, "Signature"]},
]
_rnd = random.Random(2026)
for _ in range(500):
    name = f"Company {_rnd.choice('CDEFGHJKLMNPRSTUVW')}{_rnd.randrange(10, 99)} {_rnd.choice(['Inc.', 'Ltd.', 'Corp.'])}"
    client = f"C{_rnd.randrange(10, 99)}{_rnd.choice('BCDEFGH')}{_rnd.randrange(1, 9)}"
    kind = _rnd.choice(["DCPP"] * 4 + ["GRSP"])
    LIBRARY.append(dcpp(
        f"{client}.0{_rnd.randrange(1, 4)} {kind} E-{_rnd.randrange(1, 13):02d}-{_rnd.randrange(21, 26)}",
        kind=kind, sponsor=name, client=client, contract=f"{_rnd.randrange(10000, 99999)} -G",
        payroll=[f"00{j} - {name.split()[0]} {name.split()[1]} {_rnd.choice(['Group', 'Capital', 'Services'])} Inc."
                 for j in range(1, _rnd.randrange(2, 6))],
        target_funds=_rnd.sample(TARGET, _rnd.randrange(15, 31)), own_funds=_rnd.sample(OWN, _rnd.randrange(8, 17)),
        required=f"{_rnd.randrange(0, 6)}%"))

# ---- forms that are NOT in the library ----
UNREGISTERED = dcpp("K41M2.01 DCPP E-10-26", required="3%",                       # a newer version nobody registered
                    target_funds=swap(TARGET, ["Retirement", "2025"], ["Target 2070 Growth Fund (G70)",
                                      "Target 2070 Balanced Fund (B70)", "Target 2070 Cautious Fund (C70)"]))
DENTAL = {"id": "D1102 DENTAL CLAIM E-02-25", "lines": [
    "Dental claim form", "Plan member information", "Policy number", "Certificate number", "Member name",
    "Date of birth (dd-mm-yyyy)", "Address", "City", "Province", "Postal code", "Patient information",
    "Patient name", "Relationship to plan member", "Is the patient covered under another plan?", "Yes", "No",
    "Dentist's statement", "Procedure code", "Tooth code", "Tooth surface", "Date of service", "Dentist's fee",
    "Lab charge", "Total fee", "Assignment of benefits", "I authorize payment directly to the dentist.",
    "Member signature", "Dentist signature", "Office use only"]}

# ---- filled-in member data for the test forms: obvious placeholders, no real person ----
MEMBER = {"First name": "Jane", "Last name": "Sample", "Date of birth (dd-mm-yyyy)": "01-01-1990",
          "Social Insurance Number**": "000 000 000", "Member ID": "0000000001",
          "Address (street number and name)": "1 Example Street", "City": "Sampletown", "Province": "ON",
          "Postal code": "A1A 1A1", "Telephone number (day)": "555-0100", "Email address": "jane.sample@example.com",
          "Date of enrolment (dd-mm-yyyy)": "01-03-2026", "Date of employment (dd-mm-yyyy)": "01-03-2026",
          "Province of employment": "ON", "Beneficiary's first name": "John", "Relationship to you*": "Spouse",
          "Percentage of benefits": "100 %", "Additional contribution per pay": "5 %"}

def fill(t, funds):
    return {**MEMBER, **{l: f"{p} %" for l in t["lines"] for code, p in funds.items() if f"({code})" in l}}

_by_id = {t["id"]: t for t in LIBRARY}
# (test id, form, fund allocations, scan quality, expected outcome: a template id, "review" or "unknown")
TESTS = [
    ("q01-current",                _by_id["K41M2.01 DCPP E-07-25"], {"CBI": 60, "B65": 40}, "clean", "K41M2.01 DCPP E-07-25"),
    ("q02-current-mild-scan",      _by_id["K41M2.01 DCPP E-07-25"], {"CBI": 60, "B65": 40}, "mild",  "K41M2.01 DCPP E-07-25"),
    ("q03-current-poor-fax",       _by_id["K41M2.01 DCPP E-07-25"], {"CBI": 60, "B65": 40}, "poor",  "K41M2.01 DCPP E-07-25"),
    ("q04-older-version",          _by_id["K41M2.01 DCPP E-01-24"], {"B20": 100}, "clean", "K41M2.01 DCPP E-01-24"),
    ("q05-older-version-poor-fax", _by_id["K41M2.01 DCPP E-01-24"], {"B20": 100}, "poor",  "K41M2.01 DCPP E-01-24"),
    ("q06-plan-02",                _by_id["K41M2.02 DCPP E-07-25"], {"USE": 100}, "clean", "K41M2.02 DCPP E-07-25"),
    ("q07-other-client",           _by_id["K77B3.01 DCPP E-07-25"], {"CBI": 100}, "clean", "K77B3.01 DCPP E-07-25"),
    ("q08-grsp",                   _by_id["K41M2.01 GRSP E-07-25"], {"USI": 100}, "clean", "K41M2.01 GRSP E-07-25"),
    ("q09-unregistered-version",   UNREGISTERED, {"B70": 100}, "clean", "review"),
    ("q10-dental-claim",           DENTAL, {}, "clean", "unknown"),
]
# What the combined rule is meant to do with each case; run.py fails if any result differs. An accept also
# has to pick the expected template.
INTENDED = {
    "q01-current": {"accept"}, "q02-current-mild-scan": {"accept"}, "q04-older-version": {"accept"},
    "q06-plan-02": {"accept"}, "q07-other-client": {"accept"}, "q08-grsp": {"accept"},
    "q03-current-poor-fax": {"review", "unknown"}, "q05-older-version-poor-fax": {"review", "unknown"},
    "q09-unregistered-version": {"review"}, "q10-dental-claim": {"unknown"},
}


# ---- rendering: A4 at 150 dpi, boxed labels in three columns, values under labels ----
W, H, MARGIN = 1240, 1754, 90
_font = lambda size: ImageFont.load_default(size=size)       # Pillow's bundled scalable font: same on every OS
F_LABEL, F_VALUE, F_HEAD, F_FOOT = _font(17), _font(24), _font(20), _font(15)

def _wrap(text, font, width):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and font.getlength(trial) > width:
            lines.append(cur); cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines

def render(form, values):
    """Render a (filled) form as a list of page images."""
    pages, col = [], (W - 2 * MARGIN) // 3
    def new_page():
        pages.append(Image.new("L", (W, H), 255)); return ImageDraw.Draw(pages[-1])
    d, x, y, row_h = new_page(), MARGIN, MARGIN, 0
    for line in form["lines"]:
        heading = bool(re.match(r"^\d \w", line))
        wide = heading or len(line) > 45
        w = W - 2 * MARGIN if wide else col
        label = _wrap(line, F_HEAD if heading else F_LABEL, w - 16)
        value = values.get(line, "")
        h = 36 if heading else max(56, 12 + 21 * len(label) + (32 if value else 0))
        if wide or x + w > W - MARGIN + 1:                     # start a new row
            x, y, row_h = MARGIN, y + row_h, 0
        if y + h > H - MARGIN - 40:                            # start a new page
            d, x, y, row_h = new_page(), MARGIN, MARGIN, 0
        if heading:
            d.rectangle([x, y + 6, x + w, y + h], fill=0)
            d.text((x + 8, y + 12), line, font=F_HEAD, fill=255)
        else:
            d.rectangle([x, y, x + w, y + h], outline=0, width=2)
            for n, part in enumerate(label):
                d.text((x + 8, y + 6 + 21 * n), part, font=F_LABEL, fill=0)
            if value:
                d.text((x + 8, y + 10 + 21 * len(label)), value, font=F_VALUE, fill=0)
        if wide:
            y, row_h = y + h, 0
        else:
            x, row_h = x + w, max(row_h, h)
    for n, page in enumerate(pages, 1):                        # footer with the printed form code
        ImageDraw.Draw(page).text((MARGIN, H - MARGIN), f"Page {n} of {len(pages)}    {form['id']}",
                                  font=F_FOOT, fill=0)
    return pages


SCAN = {  # rotation (deg), downscale factor, blur radius, noise sigma, JPEG quality
    "mild": (0.5, 0.80, 0.5, 10, 45),
    "poor": (1.2, 0.55, 1.1, 28, 18),        # poor fax: a person can still read it, OCR struggles
}

def degrade(img, quality, seed=5):
    """Simulate a scan of the given quality ("mild" or "poor")."""
    angle, scale, blur, noise, jpeg = SCAN[quality]
    im = img.convert("L").rotate(angle, expand=True, fillcolor=255)
    w, h = im.size
    im = im.resize((int(w * scale), int(h * scale))).resize((w, h)).filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(im, dtype=np.float32) + np.random.default_rng(seed).normal(0, noise, (h, w))
    buf = io.BytesIO()
    Image.fromarray(a.clip(0, 255).astype("uint8")).save(buf, format="JPEG", quality=jpeg)
    return Image.open(io.BytesIO(buf.getvalue())).convert("L")
