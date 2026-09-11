import argparse
import subprocess
import sys
from pathlib import Path


def run_ruff_command(cmd: list[str], cwd: Path) -> int:
    """
    Execute a ruff command
    """
    full_cmd = [sys.executable, "-m", "ruff", *cmd]
    return subprocess.run(full_cmd, cwd=cwd, check=False).returncode


def check_ruff_lint(
    root_dir: Path,
    toml_path: Path,
    paths: list[Path],
    fix: bool,
) -> int:
    """
    Run ruff check command
    """
    cmd = ["check", "--config", toml_path, *paths]
    if fix:
        cmd.append("--fix")
    return run_ruff_command(cmd, cwd=root_dir)


def check_ruff_format(
    root_dir: Path,
    toml_path: Path,
    paths: list[Path],
    fix: bool,
) -> int:
    """
    Run ruff format command
    """
    cmd = ["format", "--config", toml_path, *paths]
    if not fix:
        cmd.append("--check")
    return run_ruff_command(cmd, cwd=root_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root-dir-path",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument(
        "--toml-path",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--paths",
        type=Path,
        nargs="*",
        default=None,
    )
    parser.add_argument(
        "--fix",
        action="store_true",
    )
    parser.add_argument(
        "--lint-only",
        action="store_true",
    )
    parser.add_argument(
        "--format-only",
        action="store_true",
    )

    args = parser.parse_args()

    root_dir = args.root_dir_path
    toml_path = args.toml_path or root_dir / "pyproject.toml"
    if not toml_path.exists():
        sys.exit(1)

    if args.paths:
        paths = [
            path if path.is_absolute() else root_dir / path
            for path in args.paths
        ]
    else:
        paths = [root_dir]

    exit_code = 0

    if not args.format_only:
        exit_code |= check_ruff_lint(
            root_dir=root_dir, toml_path=toml_path, paths=paths, fix=args.fix
        )

    if not args.lint_only:
        exit_code |= check_ruff_format(
            root_dir=root_dir, toml_path=toml_path, paths=paths, fix=args.fix
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
