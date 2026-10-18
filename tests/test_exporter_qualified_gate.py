"""The exporter's qualified-build gate (decision 39-O)."""
import copy
import json
from pathlib import Path

import pytest

from odes import exporter
from odes.exporter import ExportError

ROOT = Path(__file__).resolve().parents[1]



# ------------------------------------------------------------------ exporter gate

def test_dirty_replay_checkout_is_refused_unless_development_override(monkeypatch):
    from odes.common import P2_REVISIONS
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "0")
    monkeypatch.setattr(exporter, "installed_replay_revision", lambda: P2_REVISIONS["replay"])
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: False)
    exporter._require_installed_replay(P2_REVISIONS["control_plane"])
    monkeypatch.setattr(exporter, "installed_replay_checkout_dirty", lambda: True)
    with pytest.raises(ExportError, match="uncommitted"):
        exporter._require_installed_replay(P2_REVISIONS["control_plane"])
    monkeypatch.setenv("ODES_ALLOW_UNVERIFIED_REPLAY", "1")
    exporter._require_installed_replay(P2_REVISIONS["control_plane"])


def test_dirty_state_of_a_real_checkout_is_read(tmp_path, monkeypatch):
    import os, subprocess, sys
    from odes.common import installed_replay_checkout_dirty
    repo = tmp_path / "replay"
    (repo / "agent_replay_bundle").mkdir(parents=True)
    (repo / "agent_replay_bundle" / "__init__.py").write_text("")
    env = {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@example.org", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@example.org", "PATH": os.environ["PATH"]}
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    monkeypatch.syspath_prepend(str(repo))
    sys.modules.pop("agent_replay_bundle", None)
    assert installed_replay_checkout_dirty() is False
    (repo / "agent_replay_bundle" / "__init__.py").write_text("changed = 1\n")
    assert installed_replay_checkout_dirty() is True
    sys.modules.pop("agent_replay_bundle", None)


def test_regenerated_packaging_files_do_not_make_a_checkout_dirty(tmp_path, monkeypatch):
    """A checkout that tracks generated files (package metadata directory, bytecode) is not dirty when an editable install or an
    interpreter rewrites them; a changed source file still is."""
    import os, subprocess, sys
    from odes.common import installed_replay_checkout_dirty
    repo = tmp_path / "replay"
    pkg = repo / "src" / "agent_replay_bundle"
    (pkg / "__pycache__").mkdir(parents=True)
    (repo / "src" / "agent_replay_bundle.egg-info").mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "__pycache__" / "__init__.cpython-312.pyc").write_bytes(b"a")
    (repo / "src" / "agent_replay_bundle.egg-info" / "SOURCES.txt").write_text("a\n")
    env = {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@example.org", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@example.org", "PATH": os.environ["PATH"]}
    for cmd in (["init", "-q"], ["add", "-A", "-f"], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
    monkeypatch.syspath_prepend(str(repo / "src"))
    sys.modules.pop("agent_replay_bundle", None)
    (pkg / "__pycache__" / "__init__.cpython-312.pyc").write_bytes(b"b")
    (repo / "src" / "agent_replay_bundle.egg-info" / "SOURCES.txt").write_text("b\n")
    assert installed_replay_checkout_dirty() is False
    (pkg / "__init__.py").write_text("changed = 1\n")
    assert installed_replay_checkout_dirty() is True
    sys.modules.pop("agent_replay_bundle", None)


@pytest.mark.parametrize("bundle", [{}, {"metadata": None}, {"metadata": {}}, {"metadata": {"control_plane_revision": 5}}, {"metadata": "x"}])
def test_bundle_without_a_control_plane_revision_is_refused(bundle):
    with pytest.raises(ExportError, match="control_plane_revision"):
        exporter._bundle_control_plane_revision(bundle)


def test_bundle_with_a_control_plane_revision_is_read():
    from odes.common import P2_REVISIONS
    assert exporter._bundle_control_plane_revision({"metadata": {"control_plane_revision": P2_REVISIONS["control_plane"]}}) == P2_REVISIONS["control_plane"]
