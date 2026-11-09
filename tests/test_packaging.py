import subprocess
import tarfile
import uuid
from pathlib import Path, PurePosixPath


def _build_sdist(repository: Path, output: Path) -> list[str]:
    subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(output)],
        cwd=repository,
        check=True,
    )
    [sdist] = output.glob("*.tar.gz")
    with tarfile.open(sdist, "r:gz") as archive:
        return archive.getnames()


def test_sdist_excludes_local_worktrees(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    worktrees = repository / ".worktrees"
    created_worktrees_directory = not worktrees.exists()
    worktrees.mkdir(exist_ok=True)
    sentinel = worktrees / f"packaging-sentinel-{uuid.uuid4().hex}"
    sentinel.touch()

    try:
        members = _build_sdist(repository, tmp_path)
    finally:
        sentinel.unlink(missing_ok=True)
        if created_worktrees_directory:
            worktrees.rmdir()

    worktree_members = [
        name for name in members if ".worktrees" in PurePosixPath(name).parts
    ]
    assert worktree_members == []


def test_sdist_excludes_local_handoff(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[1]
    handoff = repository / "HANDOFF.md"
    created_handoff = not handoff.exists()
    if created_handoff:
        handoff.write_text("packaging test sentinel\n")

    try:
        members = _build_sdist(repository, tmp_path)
    finally:
        if created_handoff:
            handoff.unlink(missing_ok=True)

    handoff_members = [
        name
        for name in members
        if len(PurePosixPath(name).parts) == 2
        and PurePosixPath(name).name == "HANDOFF.md"
    ]
    assert handoff_members == []
