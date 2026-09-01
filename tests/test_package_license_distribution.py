"""Distribution acceptance for the repository license grant."""

from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import zipfile


def _contains_license(paths: list[str]) -> bool:
    """Return whether an archive exposes the canonical root LICENSE payload."""

    return any(PurePosixPath(path).name == "LICENSE" for path in paths)


def test_built_distributions_include_license(tmp_path: Path) -> None:
    """Require both wheel and sdist buyers to receive the declared LICENSE file."""

    repository_root = Path(__file__).resolve().parents[1]
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
        assert _contains_license(archive.namelist()), "wheel must contain LICENSE"

    with tarfile.open(source_distribution, mode="r:gz") as archive:
        assert _contains_license(archive.getnames()), "sdist must contain LICENSE"
