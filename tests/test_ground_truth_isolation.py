"""Tripwire: the agent runtime must never be able to reach ground-truth
material (docs/internal/, eval/reference/, eval/internal/, verification/).

Per docs/internal/README_ISOLATION.md this is a hard architectural
constraint, not a suggestion. This test fails loudly (in CI) the moment any
of the following happens:
  - src/ code mentions a ground-truth path or filename, for any reason
    (including trying to deny-list it -- the string itself is a leak).
  - the loaded Settings model exposes a field that could resolve into a
    ground-truth path.
  - docker-compose.yml starts mounting anything beyond `./src` into the
    `api` service.
"""
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"

# src/config.py is the one intentional, narrow exception to "src/ never
# mentions ground-truth paths": it contains a denylist validator whose sole
# purpose is to REJECT an artifact_dir that resolves into one of them. A
# rejection rule cannot avoid naming what it rejects. It never reads, joins,
# or otherwise turns those paths into something readable -- only into a
# ValueError, which test_artifact_dir_rejects_ground_truth_paths below
# verifies actually happens. See docs/architecture/m1_foundation.md.
CONFIG_GUARD_FILE = SRC_DIR / "config.py"

FORBIDDEN_SUBSTRINGS = [
    "docs/internal",
    "docs\\internal",
    "eval/reference",
    "eval\\reference",
    "eval/internal",
    "eval\\internal",
    "verification/anomalies",
    "verification\\anomalies",
    "ground_truth",
    "post_inject_manifest",
]

GROUND_TRUTH_DIRS = [
    REPO_ROOT / "docs" / "internal",
    REPO_ROOT / "eval" / "reference",
    REPO_ROOT / "eval" / "internal",
    REPO_ROOT / "verification",
]


def test_ground_truth_dirs_actually_exist_and_are_nonempty():
    """Sanity check the test itself isn't vacuous."""
    for d in GROUND_TRUTH_DIRS:
        assert d.exists(), f"expected ground-truth dir missing: {d}"


def test_src_never_mentions_ground_truth_paths():
    offenders = []
    for py_file in SRC_DIR.rglob("*.py"):
        if py_file == CONFIG_GUARD_FILE:
            continue
        text = py_file.read_text(encoding="utf-8")
        for needle in FORBIDDEN_SUBSTRINGS:
            if needle in text:
                offenders.append((str(py_file.relative_to(REPO_ROOT)), needle))

    assert not offenders, (
        "src/ must never reference ground-truth paths, not even to deny-list "
        f"them: {offenders}"
    )


@pytest.mark.parametrize(
    "artifact_dir_env",
    [
        "docs/internal",
        "eval/reference",
        "eval/internal",
        "verification",
        "verification/anomalies",
        "docs/internal/some_subdir",
        ".",  # repo root itself -- would expose ground-truth dirs as children
    ],
)
def test_artifact_dir_rejects_ground_truth_paths(
    monkeypatch: pytest.MonkeyPatch, artifact_dir_env: str
):
    """The static scan above can't catch a runtime-configured path. This
    exercises the actual env -> Settings path the concern is about."""
    monkeypatch.setenv("ARTIFACT_DIR", artifact_dir_env)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_artifact_dir_rejects_traversal_that_only_resolve_would_catch(
    monkeypatch: pytest.MonkeyPatch,
):
    """A naive raw-string substring check would miss this: the literal value
    never spells out the ground-truth folder as one contiguous path, only
    Path.resolve() reveals where it actually lands."""
    traversal = REPO_ROOT / "docs" / "public" / ".." / "internal"
    assert str(traversal.resolve()) == str(REPO_ROOT / "docs" / "internal")

    monkeypatch.setenv("ARTIFACT_DIR", str(traversal))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_artifact_dir_allows_ordinary_workspace_paths(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARTIFACT_DIR", "./artifacts")
    settings = Settings(_env_file=None)
    assert settings.artifact_dir == Path("./artifacts")

    monkeypatch.setenv("ARTIFACT_DIR", "./run_outputs/2026-01-01")
    settings = Settings(_env_file=None)
    assert settings.artifact_dir == Path("./run_outputs/2026-01-01")


def test_settings_has_no_ground_truth_path_field():
    settings = Settings(_env_file=None)
    dumped = settings.model_dump()
    for key, value in dumped.items():
        value_str = str(value)
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in value_str, (
                f"Settings field {key!r} resolves to a ground-truth path: {value_str!r}"
            )


def test_docker_compose_api_service_only_mounts_src():
    compose_path = REPO_ROOT / "docker-compose.yml"
    text = compose_path.read_text(encoding="utf-8")

    match = re.search(r"^  api:\n(.*?)(?=^  \S|\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, "could not locate the `api` service block in docker-compose.yml"
    api_block = match.group(1)

    volumes_match = re.search(r"volumes:\n((?:\s+- .*\n)+)", api_block)
    assert volumes_match, "api service has no `volumes:` block to check"
    volume_lines = [line.strip() for line in volumes_match.group(1).splitlines() if line.strip()]

    assert volume_lines == ["- ./src:/app/src"], (
        f"api service volume mounts changed -- verify none of them reach "
        f"ground-truth folders: {volume_lines}"
    )
