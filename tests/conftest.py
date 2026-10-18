"""Tests stub or omit the Replay distribution; real installs are checked against the pinned revision (see test_replay_installed_revision)."""
import os

os.environ.setdefault("ODES_ALLOW_UNVERIFIED_REPLAY", "1")
