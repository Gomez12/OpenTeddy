"""
Skills manager for skills.sh — search, inspect, and install agent skills.

Usage:
    python skills_manager.py search <query>            Search for skills
    python skills_manager.py info <owner/repo>         Show skill details from a repo
    python skills_manager.py install <owner/repo> <dir>  Install skill(s) to a directory
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import URLError


SEARCH_API = "https://skills.sh/api/search"
SKILL_DIRS = ["skills", ".claude/skills", ".agents/skills", ".cline/skills"]
SKILL_FILE = "SKILL.md"
PROJECT_ROOT = Path(__file__).resolve().parent


def search(query: str, limit: int = 10) -> list[dict]:
    """Search skills.sh for skills matching a query."""
    url = f"{SEARCH_API}?q={quote(query)}&limit={limit}"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req) as resp:
        data = json.loads(resp.read())
    return data.get("skills", [])


def _clone_repo(source: str) -> Path:
    """Clone a GitHub repo to a temp directory and return its path."""
    if "/" not in source:
        raise ValueError(f"Invalid source: {source}. Use owner/repo format.")

    parts = source.split("/")
    owner, repo = parts[0], parts[1]
    subpath = "/".join(parts[2:]) if len(parts) > 2 else None
    url = f"https://github.com/{owner}/{repo}.git"

    tmp = Path(tempfile.mkdtemp(prefix="skills_"))
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(tmp / repo)],
        check=True,
    )
    base = tmp / repo
    if subpath:
        base = base / subpath
    return base, tmp


def _find_skills(base: Path) -> list[dict]:
    """Find all SKILL.md files under a base path and parse their frontmatter."""
    skills = []
    for skill_md in base.rglob(SKILL_FILE):
        parsed = _parse_frontmatter(skill_md)
        if parsed:
            parsed["path"] = skill_md.parent
            skills.append(parsed)
    return skills


def _parse_frontmatter(path: Path) -> dict | None:
    """Parse YAML frontmatter from a SKILL.md file."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    end = text.index("---", 3)
    frontmatter = text[3:end].strip()

    result = {}
    for line in frontmatter.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()

    if "name" not in result or "description" not in result:
        return None

    result["content"] = text
    return result


def cmd_search(args: argparse.Namespace) -> None:
    """Handle the search command."""
    results = search(args.query, limit=args.limit)
    if not results:
        print(f"No skills found for '{args.query}'.")
        return

    print(f"Found {len(results)} skill(s) for '{args.query}':\n")
    for i, skill in enumerate(results, 1):
        print(f"  {i}. {skill['name']}")
        print(f"     Source:   {skill['source']}")
        print(f"     Installs: {skill.get('installs', '?')}")
        print(f"     Install:  uv run skills_manager.py install {skill['source']} -s {skill['name']} <directory> ")
        print(f"     Install general :  uv run skills_manager.py install {skill['source']} -s {skill['name']} -g ")
        print(f"     Install user :  uv run skills_manager.py install {skill['source']} -s {skill['name']} -u <user> ")
        print()


def cmd_info(args: argparse.Namespace) -> None:
    """Handle the info command — clone repo, find skills, show details."""
    print(f"Fetching skills from {args.source}...")
    try:
        base, tmp = _clone_repo(args.source)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        skills = _find_skills(base)
        if not skills:
            print(f"No skills found in {args.source}.")
            return

        print(f"Found {len(skills)} skill(s) in {args.source}:\n")
        for skill in skills:
            print(f"  Name:        {skill['name']}")
            print(f"  Description: {skill['description']}")
            print(f"  Path:        {skill['path'].relative_to(base)}")
            print()
            if args.verbose:
                print("  --- SKILL.md content ---")
                for line in skill["content"].splitlines():
                    print(f"  {line}")
                print("  --- end ---\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _resolve_target(args: argparse.Namespace) -> Path:
    """Resolve the target directory from -g, -u, or explicit directory argument."""
    if args.general:
        target = PROJECT_ROOT / "agentic" / "general" / "skills"
        target.mkdir(parents=True, exist_ok=True)
        return target

    if args.user:
        user_dir = PROJECT_ROOT / "agentic" / "user" / args.user
        if not user_dir.exists():
            print(f"Error: User directory does not exist: {user_dir}", file=sys.stderr)
            sys.exit(1)
        target = user_dir / "skills"
        target.mkdir(parents=True, exist_ok=True)
        return target

    if not args.directory:
        print("Error: Provide a directory, or use -g or -u <user>.", file=sys.stderr)
        sys.exit(1)

    target = Path(args.directory).resolve()
    target.mkdir(parents=True, exist_ok=True)
    return target


def cmd_install(args: argparse.Namespace) -> None:
    """Handle the install command — clone repo, find skills, copy to target dir."""
    target = _resolve_target(args)

    print(f"Fetching skills from {args.source}...")
    try:
        base, tmp = _clone_repo(args.source)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        skills = _find_skills(base)
        if not skills:
            print(f"No skills found in {args.source}.")
            return

        # Filter by skill name if specified
        if args.skill:
            skills = [s for s in skills if s["name"] == args.skill]
            if not skills:
                print(f"Skill '{args.skill}' not found in {args.source}.")
                return

        for skill in skills:
            skill_dir = target / skill["name"]
            if skill_dir.exists():
                if not args.force:
                    print(f"  Skipping '{skill['name']}' — already exists. Use --force to overwrite.")
                    continue
                shutil.rmtree(skill_dir)

            shutil.copytree(skill["path"], skill_dir)
            print(f"  Installed '{skill['name']}' -> {skill_dir}")

        print(f"\nDone. {len(skills)} skill(s) installed to {target}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search, inspect, and install agent skills from skills.sh"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = sub.add_parser("search", help="Search for skills on skills.sh")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=10, help="Max results (default 10)")

    # info
    p_info = sub.add_parser("info", help="Show details about skills in a repo")
    p_info.add_argument("source", help="GitHub source (owner/repo or owner/repo/subpath)")
    p_info.add_argument("-v", "--verbose", action="store_true", help="Show full SKILL.md content")

    # install
    p_install = sub.add_parser("install", help="Install skills from a repo to a directory")
    p_install.add_argument("source", help="GitHub source (owner/repo or owner/repo/subpath)")
    p_install.add_argument("directory", nargs="?", default=None, help="Target directory to install skills into")
    p_install.add_argument("-s", "--skill", help="Install only this specific skill by name")
    p_install.add_argument("-f", "--force", action="store_true", help="Overwrite existing skills")
    p_install.add_argument("-g", "--general", action="store_true", help="Install to agentic/general/skills/")
    p_install.add_argument("-u", "--user", help="Install to agentic/user/<USER>/skills/ (user dir must exist)")

    args = parser.parse_args()

    try:
        {"search": cmd_search, "info": cmd_info, "install": cmd_install}[args.command](args)
    except URLError as e:
        print(f"Network error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)


if __name__ == "__main__":
    main()
