"""Shortlist, verify, decide: which library template is this scanned form, or should a person look?

1. Fingerprint: character 5-grams of each OCR line (spaces and punctuation removed), after folding common OCR
   confusions on both sides (o->0, i/l->1, s->5). Printed form-code and page lines are removed, so the
   similarity tests the content, not the ID in the footer (that is used separately as a cross-check).
2. Shortlist: rank by the 128-hash MinHash Jaccard estimate and keep the top 5. Containment (share of the
   blank form's labels found in the scan) is used only for the "no template fits" test: ranking by it
   favours smaller templates that are subsets of the real one. The comparison is brute force over all
   signatures; an index (LSH) is a possible later choice depending on library size, latency and hardware.
3. Verify the top 5 with exact sets, counting only the shingles that differ between the shortlisted templates.
4. MinHash-only decision, thresholds fixed before the first run: unknown / accept / review.
5. Combined rule (the proposal). Accept only if all of these hold:
   - content gate: the best template's containment is at least UNKNOWN_BELOW (otherwise "unknown");
   - the verified winner's score is at least ACCEPT_SCORE (unrounded);
   - every printed form code found in the text is the same code (after OCR folding), and it matches the winner.
   A matching code may stand in for the ACCEPT_MARGIN lead, which is what resolves close versions. Anything
   else is "review", with the reason recorded. Text with no usable content is "review" (no_readable_text).
   The code pattern fits this synthetic library's codes (e.g. "K41M2.01 DCPP E-07-25"), not every insurer's.
"""
import hashlib, re

import numpy as np

NUM_PERM, P, TOP, K = 128, (1 << 31) - 1, 5, 5
UNKNOWN_BELOW = 0.50     # best template has under half its labels in the scan -> no template fits
ACCEPT_SCORE = 0.75      # verified score of the winner on its distinguishing labels
ACCEPT_MARGIN = 0.20     # lead over the runner-up for a MinHash-only accept
_r = np.random.default_rng(7)
A, B = _r.integers(1, P, NUM_PERM, dtype=np.uint64), _r.integers(0, P, NUM_PERM, dtype=np.uint64)
FOLD = str.maketrans("oils", "0115")
# Client (5 chars), optional .plan, product words, edition. Tolerates OCR dropping spaces and reading 0/1 as O/I/l.
FORM_CODE = re.compile(r"[A-Z0-9][A-Za-z0-9]{4}(?:\.[0-9OIl]{2})?\s*[A-Z]+(?:\s+[A-Z]+)*\s*[EF]-[0-9OIl]{2}-[0-9OIl]{2}")


def shingles(lines):
    """Character K-grams per line, ignoring spaces and punctuation: OCR engines often drop or add spaces
    ("ContributionPensionPlan"), which would break word-based shingles."""
    out = set()
    for line in lines:
        if re.search(r"[EF]-\d{2}-\d|Page \d+ of \d+", line):        # footer: form code, page number
            continue
        s = re.sub(r"[^a-z0-9]", "", line.lower().translate(FOLD))
        out |= {s} if 0 < len(s) <= K else {s[i:i + K] for i in range(len(s) - K + 1)}
    return out


def signature(sh):
    if not sh:
        raise ValueError("cannot sign an empty shingle set")
    x = np.fromiter((int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big") % P for s in sh),
                    np.uint64, len(sh))
    return ((np.outer(x, A) + B) % P).min(axis=0)


def norm_code(code):
    """Form code identity under OCR noise: no spaces, upper case, 0/O and 1/I/l treated as equal."""
    return re.sub(r"\s", "", code.upper()).translate(str.maketrans("OIL", "011"))


def same_code(a, b):
    return norm_code(a) == norm_code(b)


def printed_codes(lines):
    """Every form code found, one entry per distinct spelling, in order of appearance (searched per line)."""
    found = [m.group() for line in lines for m in FORM_CODE.finditer(line)]
    return list(dict.fromkeys(found))


def code_status(codes, best_id):
    if not codes:
        return "unreadable"
    if len({norm_code(c) for c in codes}) > 1:
        return "conflict"                                           # e.g. two versions in one submission
    if best_id is None:
        return "not_compared"
    return "agrees" if same_code(codes[0], best_id) else "disagrees"


def combine(minhash_decision, best_verify, status):
    """The combined rule: returns (decision, reason)."""
    if minhash_decision == "unknown":
        return "unknown", "low_containment"
    if status != "agrees":
        return "review", {"conflict": "code_conflict", "disagrees": "code_disagrees"}.get(status, "code_unreadable")
    if best_verify < ACCEPT_SCORE:
        return "review", "below_accept_score"
    return "accept", "code_agrees"


class Index:
    def __init__(self, library):
        self.ids = [t["id"] for t in library]
        self.sets = [shingles(t["lines"]) for t in library]
        self.sigs = np.stack([signature(s) for s in self.sets])
        self.sizes = np.array([len(s) for s in self.sets])

    def match(self, lines):
        q, codes = shingles(lines), printed_codes(lines)
        if not q:                                                   # nothing to compare: no candidates
            return {"shortlist": [], "verified": [], "best": None, "margin": None,
                    "minhash_decision": "review", "printed_codes": codes, "code_status": code_status(codes, None),
                    "combined_decision": "review", "reason": "no_readable_text"}
        j = (self.sigs == signature(q)).mean(axis=1)                                 # MinHash Jaccard estimate
        est = np.minimum(1.0, j * (self.sizes + len(q)) / ((1 + j) * self.sizes))  # -> containment in the scan
        top = [int(i) for i in np.argsort(-j, kind="stable")[:TOP]]
        common = set.intersection(*(self.sets[i] for i in top))
        diff = {i: self.sets[i] - common for i in top}
        evidence = set().union(*diff.values()) & q                   # distinguishing labels seen in the scan
        rows = []
        for i in top:
            hit = len(diff[i] & q)
            cov = hit / len(diff[i]) if diff[i] else 0.0             # its own distinguishing labels present
            expl = hit / len(evidence) if evidence else 0.0          # share of the evidence it explains
            score = 2 * cov * expl / (cov + expl) if cov + expl else 0.0
            rows.append({"id": self.ids[i], "minhash_j": float(j[i]), "containment": float(est[i]), "verify": score})
        rows.sort(key=lambda r: -r["verify"])
        best = rows[0]
        margin = best["verify"] - (rows[1]["verify"] if len(rows) > 1 else 0.0)
        # Decisions use unrounded values; rounding below is for display only.
        if max(r["containment"] for r in rows) < UNKNOWN_BELOW:
            decision = "unknown"
        elif best["verify"] >= ACCEPT_SCORE and margin >= ACCEPT_MARGIN:
            decision = "accept"
        else:
            decision = "review"
        status = code_status(codes, best["id"])
        combined, reason = combine(decision, best["verify"], status)
        shown = [{k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()} for r in rows]
        return {"shortlist": [self.ids[i] for i in top], "verified": shown, "best": best["id"],
                "margin": round(margin, 3), "minhash_decision": decision, "printed_codes": codes,
                "code_status": status, "combined_decision": combined, "reason": reason}


def outcome(expected, decision, best):
    """Grade a decision: correct, person checks (safe), or WRONG (accepted the wrong template)."""
    if decision == "accept":
        return "correct" if best == expected else "WRONG"
    if expected in ("review", "unknown"):
        return "correct"
    return "person checks"
