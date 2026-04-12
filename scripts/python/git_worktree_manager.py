from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def ensure_git_repo(repo_root: Path) -> None:
    result = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=repo_root)
    if result.returncode != 0:
        raise SystemExit("Fehler: Der Ordner ist kein Git-Repository.")


def get_repo_root(start: Path) -> Path:
    result = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if result.returncode != 0:
        raise SystemExit("Fehler: Git-Repository konnte nicht gefunden werden.")
    return Path(result.stdout.strip())


def slugify(text: str) -> str:
    clean = "".join(ch.lower() if ch.isalnum() else "-" for ch in text.strip())
    while "--" in clean:
        clean = clean.replace("--", "-")
    return clean.strip("-") or "run"


@dataclass
class RunMeta:
    run_id: str
    name: str
    branch: str
    base_branch: str
    created_at: str
    worktree_path: str
    run_path: str
    status: str = "created"


def get_paths(repo_root: Path) -> dict[str, Path]:
    workspace_root = repo_root / "workspace"
    runs_root = workspace_root / "runs"
    worktrees_root = workspace_root / "worktrees"
    for path in [workspace_root, runs_root, worktrees_root]:
        path.mkdir(parents=True, exist_ok=True)
    return {
        "workspace_root": workspace_root,
        "runs_root": runs_root,
        "worktrees_root": worktrees_root,
    }


def load_run_meta(runs_root: Path, run_id: str) -> RunMeta:
    meta_file = runs_root / run_id / "meta.json"
    if not meta_file.exists():
        raise SystemExit(f"Fehler: Run nicht gefunden: {run_id}")
    data = json.loads(meta_file.read_text(encoding="utf-8"))
    return RunMeta(**data)


def save_run_meta(meta: RunMeta) -> None:
    meta_path = Path(meta.run_path) / "meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")


def create_task_stub(run_path: Path, run_id: str, name: str) -> None:
    content = f"""# Task

Run-ID: {run_id}
Name: {name}

## Rohanfrage

<Hier später den aufbereiteten Task einfügen>

## Ziel

<Was am Ende erreicht werden soll>

## Betroffene Dateien

- 

## Regeln

- Nur im aktuellen Worktree arbeiten
- Vor Änderungen Status prüfen
- Änderungen danach testen

## Akzeptanzkriterien

- 
"""
    (run_path / "task.md").write_text(content, encoding="utf-8")
    (run_path / "review.md").write_text("# Review\n\n<Später Review-Ergebnis eintragen>\n", encoding="utf-8")
    (run_path / "result.json").write_text("{}\n", encoding="utf-8")


def create_run(repo_root: Path, name: str, base_branch: str) -> None:
    paths = get_paths(repo_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(name)
    run_id = f"{timestamp}_{slug}"
    branch = f"run/{slug}-{timestamp}"

    run_path = paths["runs_root"] / run_id
    worktree_path = paths["worktrees_root"] / run_id

    check_branch = run_cmd(["git", "rev-parse", "--verify", base_branch], cwd=repo_root)
    if check_branch.returncode != 0:
        raise SystemExit(f"Fehler: Basis-Branch '{base_branch}' nicht gefunden.")

    result = run_cmd(["git", "worktree", "add", "-b", branch, str(worktree_path), base_branch], cwd=repo_root)
    if result.returncode != 0:
        raise SystemExit(f"Fehler beim Erstellen des Worktrees:\n{result.stderr or result.stdout}")

    run_path.mkdir(parents=True, exist_ok=True)
    meta = RunMeta(
        run_id=run_id,
        name=name,
        branch=branch,
        base_branch=base_branch,
        created_at=datetime.now().isoformat(timespec="seconds"),
        worktree_path=str(worktree_path),
        run_path=str(run_path),
        status="created",
    )
    save_run_meta(meta)
    create_task_stub(run_path, run_id, name)

    print(f"Run erstellt: {run_id}")
    print(f"Branch:       {branch}")
    print(f"Worktree:     {worktree_path}")
    print(f"Run-Meta:     {run_path}")


def list_runs(repo_root: Path) -> None:
    paths = get_paths(repo_root)
    metas = []
    for meta_file in sorted(paths["runs_root"].glob("*/meta.json")):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            metas.append(data)
        except Exception:
            continue

    if not metas:
        print("Keine Runs gefunden.")
        return

    for item in metas:
        print("-" * 80)
        print(f"Run-ID:      {item.get('run_id', '-')}")
        print(f"Name:        {item.get('name', '-')}")
        print(f"Branch:      {item.get('branch', '-')}")
        print(f"Status:      {item.get('status', '-')}")
        print(f"Erstellt:    {item.get('created_at', '-')}")
        print(f"Worktree:    {item.get('worktree_path', '-')}")


def show_run(repo_root: Path, run_id: str) -> None:
    paths = get_paths(repo_root)
    meta = load_run_meta(paths["runs_root"], run_id)
    print(json.dumps(asdict(meta), ensure_ascii=False, indent=2))


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path.resolve()))
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path.resolve())])
        return
    subprocess.Popen(["xdg-open", str(path.resolve())])


def open_run(repo_root: Path, run_id: str) -> None:
    paths = get_paths(repo_root)
    meta = load_run_meta(paths["runs_root"], run_id)
    open_path(Path(meta.worktree_path))
    print(f"Geöffnet: {meta.worktree_path}")


def remove_run(repo_root: Path, run_id: str, force: bool = False) -> None:
    paths = get_paths(repo_root)
    meta = load_run_meta(paths["runs_root"], run_id)
    worktree_path = Path(meta.worktree_path)
    run_path = Path(meta.run_path)

    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(worktree_path))
    result = run_cmd(cmd, cwd=repo_root)
    if result.returncode != 0:
        raise SystemExit(f"Fehler beim Entfernen des Worktrees:\n{result.stderr or result.stdout}")

    branch_result = run_cmd(["git", "branch", "-D" if force else "-d", meta.branch], cwd=repo_root)
    if branch_result.returncode != 0:
        print("Warnung: Branch konnte nicht gelöscht werden.")
        print(branch_result.stderr or branch_result.stdout)

    if run_path.exists():
        shutil.rmtree(run_path, ignore_errors=True)

    print(f"Run entfernt: {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Git-Worktree-Manager für lokale KI-Runs")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create", help="Neuen Run mit Worktree anlegen")
    create_parser.add_argument("--name", required=True, help="Freier Name für den Run")
    create_parser.add_argument("--base-branch", default="main", help="Basis-Branch, standardmäßig main")

    sub.add_parser("status", help="Vorhandene Runs anzeigen")

    show_parser = sub.add_parser("show", help="Run-Details anzeigen")
    show_parser.add_argument("--run-id", required=True)

    open_parser = sub.add_parser("open", help="Worktree eines Runs öffnen")
    open_parser.add_argument("--run-id", required=True)

    remove_parser = sub.add_parser("remove", help="Run und Worktree löschen")
    remove_parser.add_argument("--run-id", required=True)
    remove_parser.add_argument("--force", action="store_true", help="Erzwingt das Entfernen")

    args = parser.parse_args()
    repo_root = get_repo_root(Path.cwd())
    ensure_git_repo(repo_root)

    if args.command == "create":
        create_run(repo_root, args.name, args.base_branch)
    elif args.command == "status":
        list_runs(repo_root)
    elif args.command == "show":
        show_run(repo_root, args.run_id)
    elif args.command == "open":
        open_run(repo_root, args.run_id)
    elif args.command == "remove":
        remove_run(repo_root, args.run_id, force=args.force)


if __name__ == "__main__":
    main()
