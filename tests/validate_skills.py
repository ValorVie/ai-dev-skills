#!/usr/bin/env python3
"""Validate the public ai-dev skill collection without third-party packages."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
ALLOWED_FRONTMATTER = {
    "allowed-tools",
    "compatibility",
    "description",
    "license",
    "metadata",
    "name",
}
RESTRICTED = {
    "internal-brand-a": re.compile("".join(("q", "dm")), re.IGNORECASE),
    "internal-brand-b": re.compile("".join(("sympa", "soft")), re.IGNORECASE),
    "internal-account-path": re.compile(
        "".join(("valor", "love_gmail")), re.IGNORECASE
    ),
    "internal-home-path-a": re.compile(
        "/home/" + "".join(("valor", "love_gmail_com")) + "/"
    ),
    "internal-home-path-b": re.compile(
        "/home/" + "".join(("sympa", "sof")) + "/"
    ),
    "credential-storage": re.compile(
        "".join(("credential", "-files")), re.IGNORECASE
    ),
}
IGNORED_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def frontmatter_value(text: str, key: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", text[4:end])
    if not match:
        return None
    value = match.group(1).strip()
    if value in {"|", ">"}:
        remainder = text[4:end][match.end() :]
        return remainder.strip() or None
    return value.strip('"\'') or None


def frontmatter_keys(text: str) -> set[str]:
    if not text.startswith("---\n"):
        return set()
    end = text.find("\n---\n", 4)
    if end < 0:
        return set()
    return set(re.findall(r"(?m)^([A-Za-z0-9_-]+):", text[4:end]))


def iter_public_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def validate_skill_metadata(errors: list[str]) -> None:
    names: dict[str, Path] = {}
    skill_files = sorted(SKILLS_ROOT.glob("*/SKILL.md"))
    if not skill_files:
        errors.append("No skills/*/SKILL.md files found")
        return

    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        name = frontmatter_value(text, "name")
        description = frontmatter_value(text, "description")
        directory = skill_file.parent.name
        unexpected = frontmatter_keys(text) - ALLOWED_FRONTMATTER

        if not name:
            errors.append(f"{skill_file}: missing frontmatter name")
            continue
        if not description:
            errors.append(f"{skill_file}: missing frontmatter description")
        if unexpected:
            errors.append(
                f"{skill_file}: unexpected frontmatter keys {sorted(unexpected)}"
            )
        if not NAME_RE.fullmatch(name):
            errors.append(f"{skill_file}: invalid canonical ID {name!r}")
        if directory != name:
            errors.append(f"{skill_file}: directory {directory!r} != name {name!r}")
        if name in names:
            errors.append(f"duplicate canonical ID {name!r}: {names[name]} and {skill_file}")
        names[name] = skill_file


def validate_links(errors: list[str]) -> None:
    for skill_file in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        skill_root = skill_file.parent.resolve()
        for markdown in sorted(skill_root.rglob("*.md")):
            in_fence = False
            for line_number, line in enumerate(
                markdown.read_text(encoding="utf-8").splitlines(), 1
            ):
                if line.lstrip().startswith(("```", "~~~")):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                for match in LINK_RE.finditer(line):
                    raw = match.group(1).strip().split()[0].strip("<>")
                    if not raw or raw.startswith(("#", "http://", "https://", "mailto:")):
                        continue
                    target = (markdown.parent / raw.split("#", 1)[0]).resolve()
                    try:
                        target.relative_to(skill_root)
                    except ValueError:
                        errors.append(
                            f"{markdown}:{line_number}: relative link escapes skill root: {raw}"
                        )
                        continue
                    if not target.exists():
                        errors.append(
                            f"{markdown}:{line_number}: relative link target missing: {raw}"
                        )


def validate_public_boundary(errors: list[str]) -> None:
    for path in iter_public_files():
        if path.suffix in {".pyc", ".pyo"}:
            errors.append(f"generated Python file is tracked: {path}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in RESTRICTED.items():
            if pattern.search(text):
                errors.append(f"{path}: restricted public-boundary term ({label})")


def validate_portable_paths(errors: list[str]) -> None:
    work_log = (SKILLS_ROOT / "work-log-claude" / "SKILL.md").read_text(encoding="utf-8")
    if 'SKILL_DIR="<skill_path>"' not in work_log:
        errors.append("work-log-claude must resolve its runtime from <skill_path>")
    if 'SKILL_DIR="$HOME/.claude/skills/work-log-claude"' in work_log:
        errors.append("work-log-claude must not assume the Claude Code global path")

    notify = (SKILLS_ROOT / "custom-skills-notify" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    if "npx skills` 只安裝本 skill" not in notify:
        errors.append("custom-skills-notify must document the companion plugin boundary")


def main() -> int:
    errors: list[str] = []
    validate_skill_metadata(errors)
    validate_links(errors)
    validate_public_boundary(errors)
    validate_portable_paths(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    count = len(list(SKILLS_ROOT.glob("*/SKILL.md")))
    print(f"OK: validated {count} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
