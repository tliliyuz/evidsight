#!/usr/bin/env bash
set -euo pipefail

DOCMIND_DIR="${DOCMIND_DIR:-../docmind}"
RESEARCHMIND_DIR="${RESEARCHMIND_DIR:-../ResearchMind}"
DOCMIND_COMMIT="a390a2a"
RESEARCHMIND_COMMIT="40f7faa"

test "$(git -C "$DOCMIND_DIR" rev-parse --short=7 HEAD)" = "$DOCMIND_COMMIT"
test "$(git -C "$RESEARCHMIND_DIR" rev-parse --short=7 HEAD)" = "$RESEARCHMIND_COMMIT"
git -C "$DOCMIND_DIR" status --short
git -C "$RESEARCHMIND_DIR" status --short
