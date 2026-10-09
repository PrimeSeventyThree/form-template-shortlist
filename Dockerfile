# Optional: a pinned Linux environment for the PoC (the plain Python setup in RUNBOOK.md works without Docker).
# Pinned by digest (python:3.12-slim as pulled on 2026-10-08) so the base image can't change under the tag.
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f
# OpenCV (pulled in by RapidOCR) needs these two shared libraries on slim Linux images.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /matcher
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "python -m unittest discover -s tests && python -I run.py --out /matcher/out"]
