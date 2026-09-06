"""Unit tests for the split-stratification logic in scripts/make_split.py — the part
of Phase 2C most likely to have a subtle bug silently corrupt the bias-aware validation
split. Training/data scripts under scripts/ are treated like Phase 2B's
benchmark_x3d.py (manual tools, not part of the app/ contract) — this test targets only
the one pure, easy-to-get-wrong function, not full coverage of the scripts."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from make_split import VERIFIED_GOOD_NONVIOLENCE, stratum_for  # noqa: E402


def test_webcam_clips_get_their_own_stratum_regardless_of_label():
    assert stratum_for(r"C:\datasets\webcam_normal\webcam_normal_000.mp4", 0, "webcam") == "webcam_nonviolence"


def test_verified_good_nonviolence_gets_its_own_stratum():
    fname = next(iter(VERIFIED_GOOD_NONVIOLENCE))
    assert stratum_for(rf"C:\datasets\rlvs\NonViolence\{fname}", 0, "rlvs") == "rlvs_nonviolence_verified"


def test_unverified_nonviolence_is_a_separate_stratum_from_verified():
    assert stratum_for(r"C:\datasets\rlvs\NonViolence\NV_999999.mp4", 0, "rlvs") == "rlvs_nonviolence_unverified"


def test_violence_is_never_treated_as_verified_nonviolence():
    # A filename collision with the verified-good set must not matter for Violence —
    # the label, not just the filename, determines the stratum.
    fname = next(iter(VERIFIED_GOOD_NONVIOLENCE))
    assert stratum_for(rf"C:\datasets\rlvs\Violence\{fname}", 1, "rlvs") == "rlvs_violence"
