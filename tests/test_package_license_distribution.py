"""Distribution acceptance for the repository license grant."""

from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile


def _license_member(paths: list[str]) -> str:
    """Return the unique archive member that carries the canonical root LICENSE."""

    matches = [path for path in paths if PurePosixPath(path).name == "LICENSE"]
    assert len(matches) == 1, f"distribution must contain exactly one LICENSE, found {matches}"
    return matches[0]


def test_built_distributions_include_canonical_license(tmp_path: Path) -> None:
    """Require wheel and sdist buyers to receive the exact repository LICENSE payload."""

    repository_root = Path(__file__).resolve().parents[1]
    expected_license = (repository_root / "LICENSE").read_bytes()
    output_directory = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--out-dir", str(output_directory)],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel = next(output_directory.glob("*.whl"))
    source_distribution = next(output_directory.glob("*.tar.gz"))

    with zipfile.ZipFile(wheel) as archive:
        license_member = _license_member(archive.namelist())
        assert archive.read(license_member) == expected_license

    with tarfile.open(source_distribution, mode="r:gz") as archive:
        license_member = _license_member(archive.getnames())
        extracted = archive.extractfile(license_member)
        assert extracted is not None
        assert extracted.read() == expected_license
