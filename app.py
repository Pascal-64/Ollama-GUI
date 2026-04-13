from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Iterable

import requests
import streamlit as st
import streamlit.components.v1 as components

APP_ROOT = Path(__file__).resolve().parent
PROMPTS_ROOT = APP_ROOT / "prompts"
PROFILES_ROOT = PROMPTS_ROOT / "profiles"
SCRIPTS_ROOT = APP_ROOT / "scripts"
WORKSPACE_ROOT = APP_ROOT / "workspace"
OUTPUT_ROOT = WORKSPACE_ROOT / "output"
LOGS_ROOT = APP_ROOT / "logs"
CONFIG_ROOT = APP_ROOT / "config"
SETTINGS_FILE = CONFIG_ROOT / "ui_settings.json"
RUNS_ROOT = WORKSPACE_ROOT / "runs"
WORKTREES_ROOT = WORKSPACE_ROOT / "worktrees"
PROJECTS_ROOT = WORKSPACE_ROOT / "projects"

TEXT_EXTENSIONS = {
    ".txt", ".md", ".log", ".ini", ".json", ".yml", ".yaml", ".sql", ".ps1", ".bat", ".cmd",
    ".py", ".csv", ".xml", ".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".env", ".cfg",
}
SCRIPT_EXTENSIONS = {".ps1", ".bat", ".cmd", ".py"}
PROFILE_LABELS_FILE = CONFIG_ROOT / "profile_labels.json"
DEFAULT_PROFILE_LABELS = {
    "code_generate": "Code erzeugen",
    "code_debug": "Code debuggen",
    "code_refactor": "Code refactoren",
}
PROTECTED_PROFILE_KEYS = set(DEFAULT_PROFILE_LABELS.keys())
MODE_DEFINITIONS = {
    "3-Stufen Pipeline": {"kind": "pipeline", "subdir": "pipeline"},
    "Step by Step Force": {"kind": "pipeline", "subdir": "step_by_step_force"},
    "Queue": {"kind": "queue", "subdir": "queue"},
    "One-shot": {"kind": "oneshot", "subdir": "oneshot"},
}
DEFAULT_UI_SETTINGS = {
    "ui_mode": "standard",
    "visible_profiles": ["code_generate", "code_debug", "code_refactor"],
    "show_project_structure": True,
    "show_active_prompt_files": True,
    "show_active_run": True,
    "show_result_prompts": True,
    "show_result_status_messages": True,
    "show_result_metrics": True,
    "show_result_auto_review": True,
    "show_result_codex_section": True,
    "show_result_action_buttons": True,
    "show_codex_controls": True,
    "show_run_preview_files": True,
    "show_files_tab": True,
    "show_scripts_tab": True,
}


KEEP_ALIVE_OPTIONS = ["30m", "1h", "2h", "8h", "12h", "24h"]

PROMPT_BASIS_OPTIONS = ["Original + Aufbereitung", "Nur Originalprompt", "Nur lokale Aufbereitung"]
EXTERNAL_EXECUTOR_OPTIONS = ["Kein externer Executor", "Codex CLI", "Claude Code via Ollama"]
PROCESS_OWNER_OPTIONS = ["Lokales Modell", "Externer Executor"]
DEFAULT_CLAUDE_OLLAMA_MODEL = "qwen3.5"

GENERIC_ANALYSE_PROMPT = """Du bist ein technischer Anforderungsanalyst für Softwareentwicklung.

Deine Aufgabe:
Wandle die Nutzereingabe in eine klare, umsetzbare Coding-Aufgabe um.

Regeln:
- Verwende nur Informationen aus dem Input.
- Keine Annahmen als Fakten ausgeben.
- Fehlende technische Angaben klar als offene Punkte nennen.
- Kein Code.
- Keine Lösung ausformulieren.
- Ziel ist ausschließlich die Vorbereitung einer Code-Erstellung.
- Wenn die gewünschte Sprache, Plattform, Bibliothek oder Umgebung genannt wird, übernimm sie.
- Wenn sie nicht genannt wird, benenne das als offenen Punkt.

Gib die Antwort exakt in diesem Format aus:
1. Ziel
2. Technische Anforderungen
3. Eingaben/Ausgaben
4. Randbedingungen
5. Offene Punkte
6. FINAL_TASK
FINAL_TASK: <eine kurze, klare Coding-Aufgabe in einem Satz>

FINAL_TASK-Regeln:
- Maximal 15 Wörter
- Kein Code
- Keine Beispiele
- Keine Erklärungen
- Allgemein verständlich
- Fokus auf die zu erstellende Software-Funktion

Input:
[HIER TEXT EINFÜGEN]
"""

GENERIC_LOESUNG_PROMPT = """Du bist ein technischer Software-Planer.

Deine Aufgabe:
Präzisiere die Coding-Aufgabe aus dem Input so, dass daraus direkt Code erzeugt werden kann.

Regeln:
- Bleibe strikt bei Softwareentwicklung.
- Kein Kontextwechsel.
- Kein fertiger Code.
- Ergänze keine unbekannten Fakten als sicher.
- Formuliere fehlende Angaben als offene Punkte.
- Schärfe die Aufgabe technisch nach: Struktur, Verhalten, wichtige Regeln, Ein-/Ausgaben.
- Halte die Antwort kompakt und umsetzbar.

Gib die Antwort exakt in diesem Format aus:
1. Umsetzungsziel
2. Technische Umsetzungspunkte
3. Offene Punkte
4. FINAL_TASK
FINAL_TASK: <eine präzise Coding-Aufgabe in einem Satz>

FINAL_TASK-Regeln:
- Maximal 20 Wörter
- Muss direkt für die Code-Erstellung nutzbar sein
- Kein Code
- Keine Beispiele
- Keine Erklärungen

Input:
[FINAL_TASK]
"""

GENERIC_CODE_PROMPT = """Du bist ein technischer Entwickler.

Deine Aufgabe:
Erzeuge aus dem Input ausschließlich ausführbaren Code.

Regeln:
- Gib nur Code zurück.
- Keine Erklärungen.
- Keine Kommentare außerhalb des Codes.
- Keine Markdown-Codeblöcke.
- Keine Einleitung.
- Keine Zusammenfassung.
- Keine Platzhalter wie TODO, FIXME, example.com, your_api_key_here oder <PLACEHOLDER>.
- Verwende realistische Bezeichner und Werte, soweit sie aus der Aufgabe ableitbar sind.
- Wenn die Sprache genannt ist, liefere genau diese Sprache.
- Wenn die Sprache nicht genannt ist, wähle die naheliegendste Sprache für die Aufgabe.
- Der Code soll in sich konsistent und direkt nutzbar sein.
- Liefere genau das kleinste sinnvolle Ergebnis: Funktion, Skript, Klasse, SQL, HTML, CSS, JavaScript oder Konfiguration – je nach Aufgabe.

Input:
[FINAL_TASK]
"""

GENERIC_ONESHOT_PROMPT = """Du bist ein technischer Entwickler.

Löse die Aufgabe aus dem Input ausschließlich durch Code.

Regeln:
- Gib nur ausführbaren oder direkt nutzbaren Code zurück.
- Keine Erklärungen.
- Keine Kommentare außerhalb des Codes.
- Keine Markdown-Codeblöcke.
- Keine Platzhalter.
- Wenn Anforderungen fehlen, triff nur minimale, naheliegende technische Entscheidungen.
- Halte den Code so kompakt wie möglich, aber vollständig lauffähig.
- Wenn eine Sprache oder Technologie genannt wird, verwende genau diese.

Input:
[HIER TEXT EINFÜGEN]
"""


STEP_FORCE_ANALYSE_PROMPT = """Du bist ein technischer Anforderungsanalyst für Softwareentwicklung.

Deine Aufgabe:
Zerlege die Nutzereingabe strikt Schritt für Schritt in eine umsetzbare Coding-Aufgabe.

Regeln:
- Arbeite streng schrittweise.
- Verwende nur Informationen aus dem Input.
- Keine Annahmen als Fakten ausgeben.
- Fehlende technische Angaben klar als offene Punkte nennen.
- Kein Code.
- Keine Lösung ausformulieren.
- Das Ziel ist eine eindeutig umsetzbare Coding-Aufgabe.

Gib die Antwort exakt in diesem Format aus:
1. Ziel
2. Zerlegte Teilaufgaben
3. Technische Anforderungen
4. Eingaben/Ausgaben
5. Randbedingungen
6. Offene Punkte
7. FINAL_TASK
FINAL_TASK: <eine kurze, klare Coding-Aufgabe in einem Satz>

FINAL_TASK-Regeln:
- Maximal 18 Wörter
- Kein Code
- Keine Beispiele
- Keine Erklärungen
- Muss direkt in eine technische Umsetzung überführbar sein

Input:
[HIER TEXT EINFÜGEN]
"""

STEP_FORCE_LOESUNG_PROMPT = """Du bist ein technischer Software-Planer.

Deine Aufgabe:
Präzisiere die Coding-Aufgabe aus dem Input strikt Schritt für Schritt, damit daraus direkt Code erzeugt werden kann.

Regeln:
- Arbeite streng schrittweise.
- Bleibe strikt bei Softwareentwicklung.
- Kein fertiger Code.
- Ergänze keine unbekannten Fakten als sicher.
- Formuliere fehlende Angaben als offene Punkte.
- Beschreibe die Umsetzung in einer sinnvollen Reihenfolge.
- Halte die Antwort kompakt und technisch.

Gib die Antwort exakt in diesem Format aus:
1. Umsetzungsziel
2. Umsetzungsschritte
3. Technische Regeln
4. Offene Punkte
5. FINAL_TASK
FINAL_TASK: <eine präzise Coding-Aufgabe in einem Satz>

FINAL_TASK-Regeln:
- Maximal 22 Wörter
- Muss direkt für die Code-Erstellung nutzbar sein
- Kein Code
- Keine Beispiele
- Keine Erklärungen

Input:
[FINAL_TASK]
"""

STEP_FORCE_CODE_PROMPT = """Du bist ein technischer Entwickler.

Deine Aufgabe:
Erzeuge aus dem Input ausschließlich ausführbaren Code.

Regeln:
- Arbeite intern strikt Schritt für Schritt, gib aber nur Code aus.
- Gib nur Code zurück.
- Keine Erklärungen.
- Keine Kommentare außerhalb des Codes.
- Keine Markdown-Codeblöcke.
- Keine Einleitung.
- Keine Zusammenfassung.
- Keine Platzhalter wie TODO, FIXME, example.com, your_api_key_here oder <PLACEHOLDER>.
- Verwende realistische Bezeichner und Werte, soweit sie aus der Aufgabe ableitbar sind.
- Wenn die Sprache genannt ist, liefere genau diese Sprache.
- Wenn die Sprache nicht genannt ist, wähle die naheliegendste Sprache für die Aufgabe.
- Der Code soll in sich konsistent und direkt nutzbar sein.
- Liefere genau das kleinste sinnvolle Ergebnis: Funktion, Skript, Klasse, SQL, HTML, CSS, JavaScript oder Konfiguration – je nach Aufgabe.

Input:
[FINAL_TASK]
"""


QUEUE_PLAN_PROMPT = """Du bist ein technischer Projekt-Planer für Softwareentwicklung.

Deine Aufgabe:
Zerlege den Input in eine sinnvolle, abarbeitbare Warteschlange aus Arbeitsschritten.

Regeln:
- Verwende nur Informationen aus dem Input.
- Kein Code.
- Keine Lösung vorwegnehmen.
- Die Schritte müssen in einer sinnvollen Reihenfolge stehen.
- Jeder Schritt muss konkret genug sein, um separat bearbeitet zu werden.
- Maximal 10 Schritte.
- Decke Anforderungen, Struktur, Seiten, Verhalten, Design-Vorgaben und wichtige technische Punkte ab, wenn sie im Input vorkommen.

Gib die Antwort exakt in diesem Format aus:
QUEUE_SUMMARY: <eine kurze Zusammenfassung in einem Satz>
STEP 1: <konkreter Schritt>
STEP 2: <konkreter Schritt>
STEP 3: <konkreter Schritt>
...

Input:
[HIER TEXT EINFÜGEN]
"""

QUEUE_STEP_PROMPT = """Du bist ein technischer Umsetzer für eine Software-Warteschlange.

Deine Aufgabe:
Bearbeite genau einen Schritt einer größeren Aufgabe.

Regeln:
- Nutze den Original-Input, die Queue-Zusammenfassung und die bisherigen Schritt-Ergebnisse.
- Bearbeite nur den aktuellen Schritt.
- Das Ergebnis dieses Schritts muss spätere Schritte unterstützen.
- Kein unnötiger Kontext.
- Gib nur das Schritt-Ergebnis zurück.

Original-Input:
[ORIGINAL_INPUT]

Queue-Zusammenfassung:
[QUEUE_SUMMARY]

Bisherige Schritte und Ergebnisse:
[COMPLETED_STEPS]

Aktueller Schritt ([STEP_INDEX]):
[CURRENT_STEP]
"""

QUEUE_FINALIZE_PROMPT = """Du bist ein technischer Entwickler.

Deine Aufgabe:
Erzeuge aus dem Original-Input, der Queue-Zusammenfassung und den abgearbeiteten Schritten das finale Ergebnis.

Regeln:
- Führe alle relevanten Schritte zu einem konsistenten Endergebnis zusammen.
- Gib nur das finale Ergebnis zurück.
- Keine Erklärungen.
- Keine Markdown-Codeblöcke.
- Wenn der Input nach Code verlangt, liefere nur den finalen Code oder direkt nutzbaren Projektinhalt.

Original-Input:
[ORIGINAL_INPUT]

Queue-Zusammenfassung:
[QUEUE_SUMMARY]

Queue-Schritte:
[QUEUE_STEPS]

Schritt-Ergebnisse:
[QUEUE_RESULTS]
"""


AUTO_REVIEW_PROMPT = """Du bist ein strenger technischer Reviewer.

Deine Aufgabe:
Prüfe, ob die finale Antwort die ursprüngliche Aufgabe erfüllt.

Regeln:
- Bewerte nur anhand der bereitgestellten Informationen.
- Sei streng, aber fair.
- Wenn wesentliche Anforderungen fehlen, setze FAIL.
- Wenn nur kleine Verbesserungen sinnvoll wären, aber die Aufgabe im Kern erfüllt ist, darfst du PASS setzen und die Hinweise trotzdem nennen.
- Gib exakt dieses Format zurück und nichts anderes:

REVIEW_STATUS: PASS oder FAIL
REVIEW_SUMMARY: <eine kurze technische Zusammenfassung>
REVIEW_ISSUES:
- <Punkt 1>
- <Punkt 2 oder 'Keine wesentlichen Probleme'>
IMPROVEMENT_TASK: <kurze konkrete Anweisung zur Verbesserung oder NONE>

Eingabe:
[REVIEW_INPUT]
"""

AUTO_IMPROVE_PROMPT = """Du bist ein technischer Entwickler.

Deine Aufgabe:
Verbessere die finale Antwort anhand der Review-Ergebnisse.

Regeln:
- Nutze die ursprüngliche Aufgabe, die bisherige finale Antwort und die Review-Hinweise.
- Behebe nur die erkannten Probleme und verschlechtere nichts, was bereits funktioniert.
- Gib nur die verbesserte finale Antwort zurück.
- Keine Einleitung.
- Keine Erklärung.
- Keine Markdown-Codeblöcke.

Eingabe:
[IMPROVE_INPUT]
"""


class PipelineError(Exception):
    pass


st.set_page_config(page_title="Ollama GUI", layout="wide")


@st.cache_data(show_spinner=False)
def read_text_file(path_str: str) -> str:
    path = Path(path_str)
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    read_text_file.clear()


def ensure_structure() -> None:
    for path in [PROMPTS_ROOT, PROFILES_ROOT, SCRIPTS_ROOT, WORKSPACE_ROOT, OUTPUT_ROOT, LOGS_ROOT, CONFIG_ROOT, RUNS_ROOT, WORKTREES_ROOT, PROJECTS_ROOT]:
        path.mkdir(parents=True, exist_ok=True)


def prettify_profile_key(profile_key: str) -> str:
    parts = [part for part in profile_key.replace("-", "_").split("_") if part]
    if not parts:
        return profile_key
    return " ".join(part.capitalize() for part in parts)


def slugify_profile_key(label: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "custom_profile"


def load_profile_labels() -> dict[str, str]:
    labels = DEFAULT_PROFILE_LABELS.copy()
    if PROFILE_LABELS_FILE.exists():
        try:
            loaded = json.loads(PROFILE_LABELS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key, value in loaded.items():
                    if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
                        labels[key.strip()] = value.strip()
        except Exception:
            pass
    if PROFILES_ROOT.exists():
        for path in sorted(PROFILES_ROOT.iterdir(), key=lambda p: p.name.lower()):
            if path.is_dir() and path.name not in labels:
                labels[path.name] = prettify_profile_key(path.name)
    return labels


def save_profile_labels(labels: dict[str, str]) -> None:
    clean: dict[str, str] = {}
    for key, value in labels.items():
        if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
            clean[key.strip()] = value.strip()
    PROFILE_LABELS_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def get_default_visible_profiles(available_profile_keys: set[str]) -> list[str]:
    defaults = [key for key in DEFAULT_UI_SETTINGS["visible_profiles"] if key in available_profile_keys]
    if defaults:
        return defaults
    return sorted(available_profile_keys)[:1]


def create_profile_structure(profile_key: str, profile_label: str, source_profile_key: str | None = None) -> Path:
    target_root = PROFILES_ROOT / profile_key
    if target_root.exists():
        raise PipelineError(f"Profil existiert bereits: {profile_key}")

    source_root = PROFILES_ROOT / source_profile_key if source_profile_key else None
    if source_root and source_root.exists():
        shutil.copytree(source_root, target_root)
    else:
        target_root.mkdir(parents=True, exist_ok=True)

    ensure_profile_mode_files(profile_key)

    profile_labels = load_profile_labels()
    profile_labels[profile_key] = profile_label.strip()
    save_profile_labels(profile_labels)
    return target_root


def delete_profile_structure(profile_key: str) -> None:
    if profile_key in PROTECTED_PROFILE_KEYS:
        raise PipelineError("Standardprofile können hier nicht gelöscht werden.")

    target_root = PROFILES_ROOT / profile_key
    if not target_root.exists():
        raise PipelineError(f"Profilordner nicht gefunden: {profile_key}")

    shutil.rmtree(target_root)

    profile_labels = load_profile_labels()
    profile_labels.pop(profile_key, None)
    save_profile_labels(profile_labels)


def ensure_profile_label(profile_key: str) -> None:
    profile_labels = load_profile_labels()
    if profile_key not in profile_labels:
        profile_labels[profile_key] = prettify_profile_key(profile_key)
        save_profile_labels(profile_labels)


def get_default_prompt_templates(profile_key: str) -> dict[str, dict[str, str]]:
    return {
        "pipeline": {
            "01_analyse.txt": GENERIC_ANALYSE_PROMPT,
            "02_loesung.txt": GENERIC_LOESUNG_PROMPT,
            "03_code.txt": GENERIC_CODE_PROMPT,
        },
        "oneshot": {
            "01_code_only.txt": GENERIC_ONESHOT_PROMPT,
        },
        "step_by_step_force": {
            "01_analyse.txt": STEP_FORCE_ANALYSE_PROMPT,
            "02_loesung.txt": STEP_FORCE_LOESUNG_PROMPT,
            "03_code.txt": STEP_FORCE_CODE_PROMPT,
        },
        "queue": {
            "01_queue_plan.txt": QUEUE_PLAN_PROMPT,
            "02_queue_step.txt": QUEUE_STEP_PROMPT,
            "03_queue_finalize.txt": QUEUE_FINALIZE_PROMPT,
        },
    }


def ensure_profile_mode_files(profile_key: str) -> None:
    profile_root = PROFILES_ROOT / profile_key
    profile_root.mkdir(parents=True, exist_ok=True)
    for subdir, files in get_default_prompt_templates(profile_key).items():
        target_dir = profile_root / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        for file_name, content in files.items():
            target_file = target_dir / file_name
            if not target_file.exists():
                write_text_file(target_file, content)


def bootstrap_profiles() -> dict[str, str]:
    labels = load_profile_labels()
    for profile_key, profile_label in DEFAULT_PROFILE_LABELS.items():
        profile_root = PROFILES_ROOT / profile_key
        if not profile_root.exists():
            create_profile_structure(profile_key, profile_label)
    labels = load_profile_labels()
    if PROFILES_ROOT.exists():
        for path in sorted(PROFILES_ROOT.iterdir(), key=lambda p: p.name.lower()):
            if path.is_dir():
                ensure_profile_label(path.name)
                ensure_profile_mode_files(path.name)
    return load_profile_labels()


def load_ui_settings() -> dict:
    settings = DEFAULT_UI_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                settings.update({k: v for k, v in loaded.items() if k in DEFAULT_UI_SETTINGS})
        except Exception:
            pass
    available_profile_keys = set(load_profile_labels().keys())
    visible_profiles = [p for p in settings.get("visible_profiles", []) if p in available_profile_keys]
    if not visible_profiles:
        visible_profiles = get_default_visible_profiles(available_profile_keys)
    settings["visible_profiles"] = visible_profiles
    return settings


def is_advanced_mode(settings: dict) -> bool:
    return settings.get("ui_mode", "standard") == "advanced"


def save_ui_settings(settings: dict) -> None:
    clean = DEFAULT_UI_SETTINGS.copy()
    clean.update({k: v for k, v in settings.items() if k in DEFAULT_UI_SETTINGS})
    available_profile_keys = set(load_profile_labels().keys())
    visible_profiles = [p for p in clean.get("visible_profiles", []) if p in available_profile_keys]
    if not visible_profiles:
        visible_profiles = get_default_visible_profiles(available_profile_keys)
    clean["visible_profiles"] = visible_profiles
    SETTINGS_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


def get_mode_help_text(mode_name: str) -> str:
    if mode_name == "3-Stufen Pipeline":
        return "Analysiert die Eingabe, präzisiert die Aufgabe und erzeugt danach den Code. Sinnvoll bei unklaren oder knappen Anfragen."
    if mode_name == "Step by Step Force":
        return "Zerlegt die Aufgabe strikter in Schritte und erzwingt eine stärker geführte Vorbereitung vor der Code-Erzeugung."
    if mode_name == "Queue":
        return "Zerlegt eine längere Aufgabe in einzelne Arbeitsschritte und arbeitet diese nacheinander ab, bevor das finale Ergebnis erzeugt wird."
    if mode_name == "One-shot":
        return "Schickt die Anfrage direkt an das Code-Prompt. Schneller, aber bei unklaren Anfragen weniger robust."
    return "Bestimmt, wie der Prompt verarbeitet wird."


def list_files(root: Path, allowed_exts: set[str] | None = None) -> list[Path]:
    files: list[Path] = []
    if not root.exists():
        return files
    for path in root.rglob("*"):
        if path.is_file() and (allowed_exts is None or path.suffix.lower() in allowed_exts):
            files.append(path)
    return sorted(files, key=lambda p: str(p).lower())


def path_options(paths: Iterable[Path], root: Path) -> list[str]:
    return [str(path.relative_to(root)) for path in paths]


def ollama_api_url(host: str, endpoint: str) -> str:
    return host.rstrip("/") + endpoint


def is_ollama_running(host: str) -> bool:
    try:
        response = requests.get(ollama_api_url(host, "/api/tags"), timeout=3)
        response.raise_for_status()
        return True
    except Exception:
        return False


def compact_path_label(path: Path) -> str:
    return path.name or str(path)


def render_project_path_item(label: str, path: Path) -> None:
    with st.expander(f"{label}: {compact_path_label(path)}", expanded=False):
        st.code(str(path), language="text")


def project_structure_text() -> str:
    path_items = [
        ("GUI", APP_ROOT),
        ("Prompts", PROMPTS_ROOT),
        ("Profile", PROFILES_ROOT),
        ("Skripte", SCRIPTS_ROOT),
        ("Workspace", WORKSPACE_ROOT),
        ("Runs", RUNS_ROOT),
        ("Worktrees", WORKTREES_ROOT),
        ("Projects", PROJECTS_ROOT),
        ("Outputs", OUTPUT_ROOT),
        ("Logs", LOGS_ROOT),
        ("Config", CONFIG_ROOT),
    ]
    return "\n".join(f"{label}: {path}" for label, path in path_items)

def list_ollama_models(host: str) -> list[str]:
    response = requests.get(ollama_api_url(host, "/api/tags"), timeout=10)
    response.raise_for_status()
    data = response.json()
    models = data.get("models", [])
    result: list[str] = []
    for model_data in models:
        name = model_data.get("name") or model_data.get("model")
        if name:
            result.append(str(name))
    return result


def start_ollama_server_background() -> None:
    popen_kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform.startswith("win"):
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        popen_kwargs["start_new_session"] = True
    subprocess.Popen(["ollama", "serve"], **popen_kwargs)


def wait_for_ollama(host: str, timeout_seconds: int = 20) -> bool:
    end_time = time.time() + timeout_seconds
    while time.time() < end_time:
        if is_ollama_running(host):
            return True
        time.sleep(1)
    return False


def preload_model(host: str, model: str, keep_alive: str = "30m") -> dict:
    response = requests.post(
        ollama_api_url(host, "/api/generate"),
        json={"model": model, "prompt": "Antworte nur mit OK.", "stream": False, "keep_alive": keep_alive},
        timeout=600,
    )
    response.raise_for_status()
    data = response.json()
    if "response" not in data:
        raise PipelineError("Ollama-Antwort enthält kein Feld 'response'.")
    return data


def call_ollama_generate(host: str, model: str, prompt: str) -> dict:
    response = requests.post(
        ollama_api_url(host, "/api/generate"),
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=600,
    )
    response.raise_for_status()
    data = response.json()
    if "response" not in data:
        raise PipelineError("Ollama-Antwort enthält kein Feld 'response'.")
    return data


def extract_final_task(text: str) -> str:
    patterns = [
        r"(?im)^\s*(?:[-*#>]|\d+[.)])?\s*(?:\*\*)?\[?FINAL[_ ]TASK\]?(?:\*\*)?\s*:\s*(.+?)\s*$",
        r"(?im)^\s*(?:[-*#>]|\d+[.)])?\s*(?:\*\*)?FINAL[_ ]TASK(?:\*\*)?\s+(.+?)\s*$",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            candidate = matches[-1].strip().strip("`*")
            if candidate:
                return candidate

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    marker_indexes = [i for i, line in enumerate(lines) if "FINAL_TASK" in line.upper().replace(" ", "_")]
    for index in reversed(marker_indexes):
        line = lines[index]
        if ":" in line:
            candidate = line.split(":", 1)[1].strip().strip("`*")
            if candidate:
                return candidate
        if index + 1 < len(lines):
            candidate = lines[index + 1].strip().strip("`*")
            if candidate and "FINAL_TASK" not in candidate.upper():
                return candidate

    raise PipelineError("Keine FINAL_TASK-Zeile gefunden.")


def rescue_final_task(host: str, model: str, source_text: str) -> str:
    rescue_prompt = f"""Extrahiere aus dem folgenden Text genau eine kurze Coding-Aufgabe.\n\nRegeln:\n- Gib genau eine Zeile zurück.\n- Format exakt: FINAL_TASK: <Text>\n- Kein Code.\n- Keine Erklärung.\n- Maximal 20 Wörter.\n\nText:\n{source_text}"""
    rescue_data = call_ollama_generate(host, model, rescue_prompt)
    return extract_final_task(rescue_data["response"])


def load_prompt_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt-Datei fehlt: {path}")
    return read_text_file(str(path))


def build_input_prompt(template: str, user_input: str) -> str:
    prompt = template.replace("[HIER TEXT EINFÜGEN]", user_input)
    if prompt == template:
        prompt = template + f"\n\nInput:\n{user_input}\n"
    return prompt


def get_profile_config(profile_key: str, mode_name: str) -> dict:
    mode = MODE_DEFINITIONS[mode_name]
    profile_root = PROFILES_ROOT / profile_key / mode["subdir"]
    if mode["kind"] == "pipeline":
        return {
            "kind": "pipeline",
            "root": profile_root,
            "analyse": profile_root / "01_analyse.txt",
            "loesung": profile_root / "02_loesung.txt",
            "code": profile_root / "03_code.txt",
        }
    if mode["kind"] == "queue":
        return {
            "kind": "queue",
            "root": profile_root,
            "plan": profile_root / "01_queue_plan.txt",
            "step": profile_root / "02_queue_step.txt",
            "finalize": profile_root / "03_queue_finalize.txt",
        }
    return {
        "kind": "oneshot",
        "root": profile_root,
        "code": profile_root / "01_code_only.txt",
    }


def run_pipeline_mode(user_input: str, host: str, model: str, analyse_file: Path, loesung_file: Path, code_file: Path) -> dict:
    analyse_template = load_prompt_file(analyse_file)
    loesung_template = load_prompt_file(loesung_file)
    code_template = load_prompt_file(code_file)

    analyse_prompt = build_input_prompt(analyse_template, user_input)
    analyse_data = call_ollama_generate(host, model, analyse_prompt)
    analyse_response = analyse_data["response"]
    try:
        final_task_1 = extract_final_task(analyse_response)
    except PipelineError:
        final_task_1 = rescue_final_task(host, model, analyse_response)

    loesung_prompt = loesung_template.replace("[FINAL_TASK]", final_task_1)
    loesung_data = call_ollama_generate(host, model, loesung_prompt)
    loesung_response = loesung_data["response"]

    try:
        final_task_2 = extract_final_task(loesung_response)
    except PipelineError:
        try:
            final_task_2 = rescue_final_task(host, model, loesung_response)
        except PipelineError:
            final_task_2 = final_task_1

    code_prompt = code_template.replace("[FINAL_TASK]", final_task_2)
    code_data = call_ollama_generate(host, model, code_prompt)
    code_response = code_data["response"]

    return {
        "mode": "pipeline",
        "analyse_prompt": analyse_prompt,
        "analyse_response": analyse_response,
        "analyse_meta": analyse_data,
        "final_task_1": final_task_1,
        "loesung_prompt": loesung_prompt,
        "loesung_response": loesung_response,
        "loesung_meta": loesung_data,
        "final_task_2": final_task_2,
        "code_prompt": code_prompt,
        "code_response": code_response,
        "code_meta": code_data,
    }


def run_oneshot_mode(user_input: str, host: str, model: str, code_file: Path) -> dict:
    code_template = load_prompt_file(code_file)
    code_prompt = build_input_prompt(code_template, user_input)
    code_data = call_ollama_generate(host, model, code_prompt)
    return {
        "mode": "oneshot",
        "code_prompt": code_prompt,
        "code_response": code_data["response"],
        "code_meta": code_data,
    }


def parse_queue_plan(text: str) -> dict:
    summary_match = re.search(r"(?im)^\s*QUEUE_SUMMARY\s*:\s*(.+?)\s*$", text)
    summary = summary_match.group(1).strip() if summary_match else "Abarbeitbare Queue für die Eingabe"

    step_matches = re.findall(r"(?im)^\s*STEP\s+(\d+)\s*:\s*(.+?)\s*$", text)
    steps = [step_text.strip() for _, step_text in step_matches if step_text.strip()]

    if not steps:
        fallback_matches = re.findall(r"(?im)^\s*(?:\d+[.)]|[-*])\s*(.+?)\s*$", text)
        steps = [step.strip() for step in fallback_matches if step.strip() and not step.upper().startswith("QUEUE_SUMMARY")]

    if not steps:
        raise PipelineError("Queue-Plan enthält keine verwertbaren Schritte.")

    return {"summary": summary, "steps": steps}


def format_completed_queue_steps(step_runs: list[dict]) -> str:
    if not step_runs:
        return "Noch keine Schritte abgeschlossen."
    lines: list[str] = []
    for step_run in step_runs:
        lines.extend([
            f"Schritt {step_run.get('index', '-')}: {step_run.get('step', '-')}",
            step_run.get("response", "").strip() or "-",
            "",
        ])
    return "\n".join(lines).strip()


def format_queue_steps_text(steps: list[str]) -> str:
    return "\n".join(f"STEP {idx}: {step}" for idx, step in enumerate(steps, start=1))


def format_queue_step_results(step_runs: list[dict]) -> str:
    return "\n\n".join(
        f"STEP {step_run.get('index', '-')}: {step_run.get('step', '-')}\n{step_run.get('response', '').strip() or '-'}"
        for step_run in step_runs
    )


def run_queue_mode(user_input: str, host: str, model: str, plan_file: Path, step_file: Path, finalize_file: Path) -> dict:
    plan_template = load_prompt_file(plan_file)
    step_template = load_prompt_file(step_file)
    finalize_template = load_prompt_file(finalize_file)

    queue_plan_prompt = build_input_prompt(plan_template, user_input)
    queue_plan_meta = call_ollama_generate(host, model, queue_plan_prompt)
    queue_plan_response = queue_plan_meta["response"]
    queue_plan = parse_queue_plan(queue_plan_response)
    queue_summary = queue_plan["summary"]
    queue_steps = queue_plan["steps"]

    queue_step_runs: list[dict] = []
    for index, current_step in enumerate(queue_steps, start=1):
        completed_steps = format_completed_queue_steps(queue_step_runs)
        step_prompt = (
            step_template
            .replace("[ORIGINAL_INPUT]", user_input)
            .replace("[QUEUE_SUMMARY]", queue_summary)
            .replace("[COMPLETED_STEPS]", completed_steps)
            .replace("[STEP_INDEX]", str(index))
            .replace("[CURRENT_STEP]", current_step)
        )
        step_meta = call_ollama_generate(host, model, step_prompt)
        queue_step_runs.append(
            {
                "index": index,
                "step": current_step,
                "prompt": step_prompt,
                "response": step_meta["response"],
                "meta": step_meta,
            }
        )

    finalize_prompt = (
        finalize_template
        .replace("[ORIGINAL_INPUT]", user_input)
        .replace("[QUEUE_SUMMARY]", queue_summary)
        .replace("[QUEUE_STEPS]", format_queue_steps_text(queue_steps))
        .replace("[QUEUE_RESULTS]", format_queue_step_results(queue_step_runs))
    )
    finalize_meta = call_ollama_generate(host, model, finalize_prompt)

    return {
        "mode": "queue",
        "queue_plan_prompt": queue_plan_prompt,
        "queue_plan_response": queue_plan_response,
        "queue_plan_meta": queue_plan_meta,
        "queue_summary": queue_summary,
        "queue_steps": queue_steps,
        "queue_step_runs": queue_step_runs,
        "code_prompt": finalize_prompt,
        "code_response": finalize_meta["response"],
        "code_meta": finalize_meta,
    }


def open_folder_in_explorer(path: Path) -> None:
    target = str(path.resolve())
    if sys.platform.startswith("win"):
        os.startfile(target)
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def command_exists(command_name: str) -> bool:
    return shutil.which(command_name) is not None


def open_in_vscode(path: Path) -> None:
    vscode_cmd = shutil.which("code") or shutil.which("code.cmd") or shutil.which("code.exe")
    if not vscode_cmd:
        raise PipelineError("VS Code CLI 'code' wurde nicht gefunden. Installiere die Shell-Command-Integration von VS Code.")
    subprocess.Popen([vscode_cmd, str(path.resolve())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_codex_command() -> str | None:
    return shutil.which("codex") or shutil.which("codex.cmd") or shutil.which("codex.exe")


def codex_available() -> bool:
    return get_codex_command() is not None


def get_ollama_command() -> str | None:
    return shutil.which("ollama") or shutil.which("ollama.exe")


def claude_via_ollama_available() -> bool:
    return get_ollama_command() is not None


def executor_available(executor_label: str) -> bool:
    if executor_label == "Codex CLI":
        return codex_available()
    if executor_label == "Claude Code via Ollama":
        return claude_via_ollama_available()
    return False


def build_codex_exec_prompt(run_meta: dict) -> str:
    executor_config = run_meta.get("executor_config") or {}
    selected_executor = executor_config.get("external_executor", "Codex CLI")
    review_owner = executor_config.get("review_owner", "Lokales Modell")
    improve_owner = executor_config.get("improve_owner", "Lokales Modell")

    instructions = [
        f"Lies zuerst die Datei CODEX_HANDOFF.md im Root des aktuellen Worktrees und folge ihr vollständig.",
        "Arbeite nur im aktuellen Worktree.",
        "Prüfe task.md, review.md, result.json und vorhandene Outputs.",
    ]
    if review_owner == "Externer Executor":
        instructions.append("Übernimm zusätzlich die finale fachlich-technische Prüfung anhand der Handoff-Anweisungen.")
    if improve_owner == "Externer Executor":
        instructions.append("Verbessere die Lösung bei Bedarf direkt im Worktree und aktualisiere die betroffenen Dateien.")
    else:
        instructions.append("Nimm nur dann Codeänderungen vor, wenn sie aus Handoff, Review oder Ergebnis klar notwendig sind.")
    instructions.append(f"Gib am Ende als {selected_executor} eine kurze Zusammenfassung der Änderungen zurück.")
    return " ".join(instructions)


def run_codex_exec(worktree_path: Path, prompt: str) -> subprocess.CompletedProcess[str]:
    codex_cmd = get_codex_command()
    if not codex_cmd:
        raise PipelineError("Codex CLI wurde nicht gefunden. Installiere Codex CLI und melde dich an.")
    if not worktree_path.exists() or not worktree_path.is_dir():
        raise PipelineError(f"Worktree nicht gefunden: {worktree_path}")

    cmd = [
        codex_cmd,
        "exec",
        "--full-auto",
        "--sandbox",
        "workspace-write",
        prompt,
    ]
    return subprocess.run(
        cmd,
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=3600,
        encoding="utf-8",
        errors="replace",
    )


def run_claude_via_ollama_exec(worktree_path: Path, prompt: str, model_name: str) -> subprocess.CompletedProcess[str]:
    ollama_cmd = get_ollama_command()
    if not ollama_cmd:
        raise PipelineError("Ollama CLI wurde nicht gefunden. Claude Code via Ollama benötigt einen verfügbaren 'ollama'-Befehl.")
    if not worktree_path.exists() or not worktree_path.is_dir():
        raise PipelineError(f"Worktree nicht gefunden: {worktree_path}")

    cmd = [
        ollama_cmd,
        "launch",
        "claude",
        "--model",
        model_name.strip() or DEFAULT_CLAUDE_OLLAMA_MODEL,
        "--yes",
        "--",
        "-p",
        prompt,
    ]
    return subprocess.run(
        cmd,
        cwd=str(worktree_path),
        capture_output=True,
        text=True,
        timeout=3600,
        encoding="utf-8",
        errors="replace",
    )


def extract_last_message(stdout_text: str) -> str:
    text = (stdout_text or "").strip()
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    # First try to unwrap simple JSON/JSONL output that may contain a message field.
    for candidate in reversed(lines):
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue

        if isinstance(parsed, dict):
            for key in ("last_message", "message", "content", "text", "output"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            messages = parsed.get("messages")
            if isinstance(messages, list):
                for entry in reversed(messages):
                    if isinstance(entry, dict):
                        for key in ("content", "text", "message"):
                            value = entry.get(key)
                            if isinstance(value, str) and value.strip():
                                return value.strip()
                    elif isinstance(entry, str) and entry.strip():
                        return entry.strip()
        elif isinstance(parsed, str) and parsed.strip():
            return parsed.strip()

    # Fallback for plain text output.
    return lines[-1]
def write_codex_exec_artifacts(run_id: str, exec_prompt: str, process: subprocess.CompletedProcess[str], executor_label: str = "Codex CLI", executor_model: str | None = None) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")

    meta_dir = Path(str(run_meta.get("meta_path", RUNS_ROOT / run_id)))
    target_dir = get_run_target_path(run_meta)
    executed_at = datetime.now().isoformat(timespec="seconds")
    diff_summary = collect_worktree_diff_summary(target_dir) if target_dir.exists() else {
        "status_short": "",
        "diff_stat": "",
        "name_status": "",
        "entries": [],
        "changed_files": [],
        "has_changes": False,
    }
    last_message = extract_last_message((process.stdout or "").strip())

    result_payload = {
        "run_id": run_id,
        "executed_at": executed_at,
        "command": process.args,
        "executor": executor_label,
        "executor_model": executor_model,
        "returncode": process.returncode,
        "prompt": exec_prompt,
        "stdout": process.stdout or "",
        "stderr": process.stderr or "",
        "target_path": str(target_dir),
        "worktree_path": str(target_dir),
        "changed_files": diff_summary.get("changed_files", []),
        "project_changed_files": diff_summary.get("project_changed_files", []),
        "artifact_changed_files": diff_summary.get("artifact_changed_files", []),
        "changed_entries": diff_summary.get("entries", []),
        "status_short": diff_summary.get("status_short", ""),
        "diff_stat": diff_summary.get("diff_stat", ""),
        "name_status": diff_summary.get("name_status", ""),
    }

    result_json_path = meta_dir / "codex_exec_result.json"
    stdout_path = meta_dir / "codex_exec_stdout.md"
    stderr_path = meta_dir / "codex_exec_stderr.log"
    target_result_json_path = target_dir / "CODEX_EXEC_RESULT.json"
    target_stdout_path = target_dir / "CODEX_EXEC_LAST_MESSAGE.md"
    target_stderr_path = target_dir / "CODEX_EXEC_STDERR.log"

    write_text_file(result_json_path, json.dumps(result_payload, ensure_ascii=False, indent=2))
    write_text_file(stdout_path, process.stdout or "")
    write_text_file(stderr_path, process.stderr or "")
    if target_dir.exists() and target_dir.is_dir():
        write_text_file(target_result_json_path, json.dumps(result_payload, ensure_ascii=False, indent=2))
        write_text_file(target_stdout_path, last_message + "\n")
        write_text_file(target_stderr_path, process.stderr or "")

    updated_meta = update_worktree_run_meta(
        run_id,
        {
            "last_codex_exec_at": executed_at,
            "last_external_executor": executor_label,
            "last_external_executor_model": executor_model,
            "last_codex_exec_status": "success" if process.returncode == 0 else "failed",
            "last_codex_exec_result_path": str(result_json_path),
            "last_codex_exec_stdout_path": str(stdout_path),
            "last_codex_exec_stderr_path": str(stderr_path),
            "last_codex_exec_target_result_path": str(target_result_json_path),
            "last_codex_exec_target_stdout_path": str(target_stdout_path),
            "last_codex_exec_target_stderr_path": str(target_stderr_path),
            "last_codex_exec_worktree_result_path": str(target_result_json_path),
            "last_codex_exec_worktree_stdout_path": str(target_stdout_path),
        },
    )

    return {
        "run_id": run_id,
        "executed_at": executed_at,
        "returncode": process.returncode,
        "prompt": exec_prompt,
        "stdout": process.stdout or "",
        "stderr": process.stderr or "",
        "result_path": str(result_json_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "target_result_path": str(target_result_json_path),
        "target_stdout_path": str(target_stdout_path),
        "target_stderr_path": str(target_stderr_path),
        "worktree_result_path": str(target_result_json_path),
        "worktree_stdout_path": str(target_stdout_path),
        "worktree_stderr_path": str(target_stderr_path),
        "diff_summary": diff_summary,
        "changed_files": diff_summary.get("changed_files", []),
        "target_path": str(target_dir),
        "worktree_path": str(target_dir),
        "meta": updated_meta,
    }


def execute_codex_for_run(run_id: str) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")

    target_path = get_run_target_path(run_meta)
    handoff_path = Path(str(run_meta.get("last_handoff_target_path") or run_meta.get("last_handoff_worktree_path") or (target_path / "CODEX_HANDOFF.md")))
    if not handoff_path.exists() or not handoff_path.is_file():
        raise PipelineError("Keine CODEX_HANDOFF.md im aktiven Arbeitsordner gefunden. Führe zuerst einen Lauf mit Handoff aus.")

    exec_prompt = build_codex_exec_prompt(run_meta)
    process = run_codex_exec(target_path, exec_prompt)
    exec_data = write_codex_exec_artifacts(run_id, exec_prompt, process, executor_label="Codex CLI")
    exec_data["handoff_path"] = str(handoff_path)
    exec_data["target_path"] = str(target_path)
    exec_data["worktree_path"] = str(target_path)
    return exec_data


def execute_claude_for_run(run_id: str, model_name: str) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")

    target_path = get_run_target_path(run_meta)
    handoff_path = Path(str(run_meta.get("last_handoff_target_path") or run_meta.get("last_handoff_worktree_path") or (target_path / "CODEX_HANDOFF.md")))
    if not handoff_path.exists() or not handoff_path.is_file():
        raise PipelineError("Keine CODEX_HANDOFF.md im aktiven Arbeitsordner gefunden. Führe zuerst einen Lauf mit Handoff aus.")

    exec_prompt = build_codex_exec_prompt(run_meta)
    process = run_claude_via_ollama_exec(target_path, exec_prompt, model_name)
    exec_data = write_codex_exec_artifacts(run_id, exec_prompt, process, executor_label="Claude Code via Ollama", executor_model=model_name)
    exec_data["handoff_path"] = str(handoff_path)
    exec_data["target_path"] = str(target_path)
    exec_data["worktree_path"] = str(target_path)
    return exec_data


def execute_selected_executor_for_run(run_id: str, executor_label: str, claude_model: str) -> dict:
    if executor_label == "Codex CLI":
        return execute_codex_for_run(run_id)
    if executor_label == "Claude Code via Ollama":
        return execute_claude_for_run(run_id, claude_model)
    raise PipelineError("Kein externer Executor ausgewählt.")


def build_codex_handoff_markdown(run_meta: dict, user_input: str, result: dict, output_path: Path | None = None) -> str:
    automation = result.get("automation", {})
    final_review = automation.get("final_review") or automation.get("initial_review") or {}
    issues = final_review.get("issues", [])
    executor_config = result.get("executor_config", {}) if isinstance(result, dict) else {}
    prompt_basis = executor_config.get("prompt_basis", "Original + Aufbereitung")
    external_executor = executor_config.get("external_executor", "Codex CLI")
    review_owner = executor_config.get("review_owner", "Lokales Modell")
    improve_owner = executor_config.get("improve_owner", "Lokales Modell")
    target_path = get_run_target_path(run_meta)
    target_label = get_run_target_label(run_meta)

    lines = [
        f"# Executor Handoff – Run {run_meta.get('run_id', '-')}",
        "",
        "## Ziel",
        "",
        f"Übernimm diesen Run im Arbeitsordner mit {external_executor}, prüfe das aktuelle Ergebnis und verbessere es bei Bedarf direkt im Codebestand.",
        "",
        "## Zuständigkeiten",
        "",
        f"- Externer Executor: {external_executor}",
        f"- Review übernimmt: {review_owner}",
        f"- Verbesserung übernimmt: {improve_owner}",
        "",
    ]

    if prompt_basis in {"Original + Aufbereitung", "Nur Originalprompt"}:
        lines.extend([
            "## Originale Nutzereingabe",
            "",
            user_input.strip() or "-",
            "",
        ])

    if prompt_basis in {"Original + Aufbereitung", "Nur lokale Aufbereitung"}:
        lines.extend([
            "## Lokale Aufbereitung",
            "",
            f"- Analyse FINAL_TASK: {result.get('final_task_1', '-')}",
            f"- Lösung FINAL_TASK: {result.get('final_task_2', result.get('final_task_1', '-'))}",
            f"- Effektive Aufgabenfassung: {result.get('final_task_2') or result.get('final_task_1') or '-'}",
            "",
        ])
        if result.get("mode") == "queue":
            lines.extend([
                "### Queue",
                "",
                f"- Zusammenfassung: {result.get('queue_summary', '-')}",
                "",
                "```text",
                format_queue_steps_text(result.get("queue_steps", [])) or "-",
                "```",
                "",
                "### Queue-Schritt-Ergebnisse",
                "",
                "```text",
                format_queue_step_results(result.get("queue_step_runs", [])) or "-",
                "```",
                "",
            ])

    if prompt_basis == "Original + Aufbereitung":
        lines.extend([
            "## Vorrangregel",
            "",
            "Wenn sich Originalprompt und lokale Aufbereitung widersprechen, hat der Originalprompt Vorrang.",
            "",
        ])

    lines.extend([
        "## Laufkontext",
        "",
        f"- Profil: {result.get('profile_label', result.get('profile_key', '-'))}",
        f"- Modus: {result.get('mode_name', '-')}",
        f"- Modell: {result.get('model', '-')}",
        f"- {target_label}: {target_path or '-'}",
        f"- task.md im Arbeitsordner: {run_meta.get('target_task_path', run_meta.get('worktree_task_path', target_path / 'task.md' if str(target_path) else '-'))}",
        f"- review.md im Arbeitsordner: {run_meta.get('target_review_path', run_meta.get('worktree_review_path', target_path / 'review.md' if str(target_path) else '-'))}",
        f"- result.json im Arbeitsordner: {run_meta.get('target_result_path', run_meta.get('worktree_result_path', target_path / 'result.json' if str(target_path) else '-'))}",
        f"- Run task.md: {run_meta.get('task_path', '-')}",
        f"- Run review.md: {run_meta.get('review_path', '-')}",
        f"- Run result.json: {run_meta.get('result_path', '-')}",
        f"- Letzter Output: {output_path if output_path else run_meta.get('target_output_path') or run_meta.get('worktree_output_path') or run_meta.get('last_output_path', '-')}",
        "",
        "## Aktueller Review-Stand",
        "",
        f"- Status: {final_review.get('status', '-')}",
        f"- Zusammenfassung: {final_review.get('summary', '-')}",
        f"- Verbesserungsauftrag: {final_review.get('improvement_task', 'NONE')}",
        "",
        "## Auffälligkeiten",
        "",
    ])
    if issues:
        lines.extend([f"- {issue}" for issue in issues])
    else:
        lines.append("- Keine spezifischen Issues dokumentiert.")
    lines.extend([
        "",
        "## Arbeitsanweisung für den externen Executor",
        "",
        "1. Lies zuerst CODEX_HANDOFF.md, task.md, review.md und result.json.",
        "2. Nutze die Originale Nutzereingabe und/oder die lokale Aufbereitung entsprechend der angegebenen Vorrangregel.",
        "3. Prüfe den aktuellen Output gegen Aufgabe und Review-Status.",
        "4. Halte Änderungen lokal im aktuellen Arbeitsordner und ändere nicht den Hauptstand außerhalb des Runs.",
        "5. Aktualisiere am Ende die betroffenen Dateien im Arbeitsordner und hinterlasse ein sauberes Ergebnis.",
    ])
    return "\n".join(lines).strip() + "\n"


def write_codex_handoff_artifacts(run_id: str, user_input: str, result: dict, run_write: dict | None = None) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")

    meta_dir = Path(str(run_meta.get("meta_path", RUNS_ROOT / run_id)))
    target_path = get_run_target_path(run_meta)
    output_path = Path(str((run_write or {}).get("output_path") or run_meta.get("last_output_path") or "")) if ((run_write or {}).get("output_path") or run_meta.get("last_output_path")) else None

    handoff_meta_path = meta_dir / "codex_handoff.md"
    handoff_target_path = target_path / "CODEX_HANDOFF.md"
    context_path = meta_dir / "codex_context.json"

    handoff_content = build_codex_handoff_markdown(run_meta=run_meta, user_input=user_input, result=result, output_path=output_path)
    write_text_file(handoff_meta_path, handoff_content)
    if target_path.exists() and target_path.is_dir():
        write_text_file(handoff_target_path, handoff_content)

    context_payload = {
        "run_id": run_id,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "profile_key": result.get("profile_key"),
        "profile_label": result.get("profile_label"),
        "mode_name": result.get("mode_name"),
        "model": result.get("model"),
        "user_input": user_input,
        "run_meta": run_meta,
        "run_write": run_write or {},
        "review": result.get("automation", {}).get("final_review") or result.get("automation", {}).get("initial_review") or {},
        "executor_config": result.get("executor_config", {}),
        "prepared_context": {
            "analyse_final_task": result.get("final_task_1"),
            "solution_final_task": result.get("final_task_2"),
            "effective_task": result.get("final_task_2") or result.get("final_task_1"),
            "analysis_prompt": result.get("analyse_prompt"),
            "solution_prompt": result.get("loesung_prompt"),
            "code_prompt": result.get("code_prompt"),
        },
        "current_output": result.get("code_response", ""),
    }
    write_text_file(context_path, json.dumps(context_payload, ensure_ascii=False, indent=2))

    updated_meta = update_worktree_run_meta(
        run_id,
        {
            "last_handoff_at": context_payload["updated_at"],
            "last_handoff_path": str(handoff_meta_path),
            "last_handoff_target_path": str(handoff_target_path),
            "last_handoff_worktree_path": str(handoff_target_path),
            "last_context_path": str(context_path),
        },
    )
    return {
        "handoff_path": str(handoff_meta_path),
        "handoff_worktree_path": str(handoff_target_path),
        "handoff_target_path": str(handoff_target_path),
        "context_path": str(context_path),
        "worktree_path": str(target_path),
        "target_path": str(target_path),
        "meta": updated_meta,
    }


def run_script(script_path: Path, working_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
    ext = script_path.suffix.lower()
    if ext == ".ps1":
        cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    elif ext in {".bat", ".cmd"}:
        cmd = ["cmd.exe", "/c", str(script_path)]
    elif ext == ".py":
        cmd = [sys.executable, str(script_path)]
    else:
        raise PipelineError(f"Skripttyp nicht unterstützt: {ext}")

    return subprocess.run(
        cmd,
        cwd=str(working_dir or script_path.parent),
        capture_output=True,
        text=True,
        timeout=600,
        encoding="utf-8",
        errors="replace",
    )


def metric_value(meta: dict, key: str) -> int:
    value = meta.get(key)
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(value)
    except Exception:
        return 0


def format_tokens(value: int) -> str:
    if not value:
        return "-"
    return f"{value:,}".replace(",", ".")


def format_duration_ns(value: int) -> str:
    if not value:
        return "-"
    seconds = value / 1_000_000_000
    if seconds < 1:
        return f"{seconds:.2f} s"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes = int(seconds // 60)
    rest = seconds % 60
    return f"{minutes} min {rest:.1f} s"


def collect_run_stats(result: dict | None) -> dict:
    if not result:
        return {"input_tokens": 0, "output_tokens": 0, "total_duration": 0, "steps": 0}

    if result.get("mode") == "pipeline":
        metas = [result.get("analyse_meta", {}), result.get("loesung_meta", {}), result.get("code_meta", {})]
    elif result.get("mode") == "queue":
        metas = [result.get("queue_plan_meta", {})]
        metas.extend(step_run.get("meta", {}) for step_run in result.get("queue_step_runs", []))
        metas.append(result.get("code_meta", {}))
    else:
        metas = [result.get("code_meta", {})]

    automation = result.get("automation", {}) if isinstance(result, dict) else {}
    for key in ("initial_review_meta", "improve_meta", "final_review_meta"):
        value = automation.get(key)
        if isinstance(value, dict):
            metas.append(value)
    metas = [meta for meta in metas if meta]

    return {
        "input_tokens": sum(metric_value(meta, "prompt_eval_count") for meta in metas),
        "output_tokens": sum(metric_value(meta, "eval_count") for meta in metas),
        "total_duration": sum(metric_value(meta, "total_duration") for meta in metas),
        "steps": len(metas),
    }


CODEX_ARTIFACT_EXCLUDES = [
    "task.md",
    "review.md",
    "result.json",
    "CODEX_HANDOFF.md",
    "CODEX_EXEC_RESULT.json",
    "CODEX_EXEC_LAST_MESSAGE.md",
    "CODEX_EXEC_STDERR.log",
    "outputs",
]


def collect_workflow_stats(result: dict | None) -> dict:
    if not result:
        return {"input_tokens": 0, "output_tokens": 0, "total_duration": 0, "steps": 0}
    if isinstance(result, dict):
        workflow_stats = result.get("workflow_stats")
        if isinstance(workflow_stats, dict) and workflow_stats:
            return workflow_stats
    return collect_run_stats(result)


def parse_git_status_entries(status_text: str) -> list[dict]:
    entries: list[dict] = []
    for raw_line in (status_text or "").splitlines():
        if not raw_line.strip():
            continue
        status_code = raw_line[:2].strip() or "??"
        remainder = raw_line[3:].strip() if len(raw_line) > 3 else ""
        if " -> " in remainder:
            old_path, new_path = remainder.split(" -> ", 1)
            entries.append({"status": status_code, "path": new_path.strip(), "old_path": old_path.strip()})
        else:
            entries.append({"status": status_code, "path": remainder})
    return entries


def is_codex_artifact_path(rel_path: str) -> bool:
    path_value = (rel_path or "").replace("\\", "/").strip("/")
    if not path_value:
        return False

    artifact_names = {
        "task.md",
        "review.md",
        "result.json",
        "CODEX_HANDOFF.md",
        "CODEX_EXEC_RESULT.json",
        "CODEX_EXEC_LAST_MESSAGE.md",
        "CODEX_EXEC_STDERR.log",
        "codex_exec_result.json",
        "codex_exec_stdout.md",
        "codex_exec_stderr.log",
        "codex_handoff.md",
        "codex_context.json",
    }
    artifact_prefixes = (
        "outputs/",
        ".codex/",
    )
    if path_value in artifact_names:
        return True
    return any(path_value.startswith(prefix) for prefix in artifact_prefixes)



def collect_worktree_diff_summary(worktree_path: Path) -> dict:
    status_process = git_run(["status", "--short"], cwd=worktree_path)
    diff_stat_process = git_run(["diff", "--stat"], cwd=worktree_path)
    name_status_process = git_run(["diff", "--name-status"], cwd=worktree_path)

    status_short = (status_process.stdout or "").strip() if status_process.returncode == 0 else ""
    diff_stat = (diff_stat_process.stdout or "").strip() if diff_stat_process.returncode == 0 else ""
    name_status = (name_status_process.stdout or "").strip() if name_status_process.returncode == 0 else ""

    entries = parse_git_status_entries(status_short)
    changed_files = [entry.get("path", "") for entry in entries if entry.get("path")]
    project_entries = [entry for entry in entries if not is_codex_artifact_path(str(entry.get("path", "")))]
    artifact_entries = [entry for entry in entries if is_codex_artifact_path(str(entry.get("path", "")))]
    project_changed_files = [entry.get("path", "") for entry in project_entries if entry.get("path")]
    artifact_changed_files = [entry.get("path", "") for entry in artifact_entries if entry.get("path")]
    return {
        "status_short": status_short,
        "diff_stat": diff_stat,
        "name_status": name_status,
        "entries": entries,
        "changed_files": changed_files,
        "project_entries": project_entries,
        "artifact_entries": artifact_entries,
        "project_changed_files": project_changed_files,
        "artifact_changed_files": artifact_changed_files,
        "has_changes": bool(entries),
        "has_project_changes": bool(project_entries),
    }


def refresh_codex_exec_result(run_id: str) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")

    result_path = Path(str(run_meta.get("last_codex_exec_result_path", "")))
    if not result_path.exists() or not result_path.is_file():
        raise PipelineError("Kein Codex-Resultat für diesen Run gefunden.")

    data = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PipelineError("Codex-Resultat hat ein ungültiges Format.")

    target_path = get_run_target_path(run_meta)
    diff_summary = collect_worktree_diff_summary(target_path) if target_path.exists() else {
        "status_short": "",
        "diff_stat": "",
        "name_status": "",
        "entries": [],
        "changed_files": [],
        "has_changes": False,
    }
    data["diff_summary"] = diff_summary
    data["changed_files"] = diff_summary.get("changed_files", [])
    data["project_changed_files"] = diff_summary.get("project_changed_files", [])
    data["artifact_changed_files"] = diff_summary.get("artifact_changed_files", [])
    data["changed_entries"] = diff_summary.get("entries", [])
    data["target_path"] = str(target_path)
    data["worktree_path"] = str(target_path)
    return data


def git_repo_is_clean(repo_path: Path) -> tuple[bool, str]:
    process = git_run(["status", "--porcelain"], cwd=repo_path)
    output = (process.stdout or "").strip()
    return process.returncode == 0 and not output, output


def stage_non_artifact_worktree_changes(worktree_path: Path) -> list[str]:
    diff_summary = collect_worktree_diff_summary(worktree_path)
    project_files = [path for path in diff_summary.get("project_changed_files", []) if path]
    if not project_files:
        return []

    reset_process = git_run(["reset", "-q", "HEAD"], cwd=worktree_path)
    if reset_process.returncode != 0:
        raise PipelineError((reset_process.stderr or reset_process.stdout or "Git-Index konnte nicht zurückgesetzt werden.").strip())

    add_process = git_run(["add", "-A", "--", *project_files], cwd=worktree_path)
    if add_process.returncode != 0:
        raise PipelineError((add_process.stderr or add_process.stdout or "Projektdateien konnten nicht gestaged werden.").strip())

    staged_process = git_run(["diff", "--cached", "--name-only"], cwd=worktree_path)
    if staged_process.returncode != 0:
        raise PipelineError((staged_process.stderr or staged_process.stdout or "Gestagte Änderungen konnten nicht gelesen werden.").strip())

    staged_files = [line.strip() for line in (staged_process.stdout or "").splitlines() if line.strip()]
    return [path for path in staged_files if not is_codex_artifact_path(path)]


def apply_worktree_changes_to_base(run_id: str) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")
    if not is_repo_run(run_meta):
        raise PipelineError("Scratch-Runs haben keinen Git-Worktree. Für Scratch-Projekte gibt es keine Übernahme in den Basis-Branch.")

    repo_root = Path(str(run_meta.get("repo_root") or find_git_repo_root(APP_ROOT) or APP_ROOT))
    worktree_path = get_run_target_path(run_meta)
    target_branch = str(run_meta.get("base_branch") or git_default_branch(repo_root) or "main").strip() or "main"

    repo_clean, repo_status = git_repo_is_clean(repo_root)
    if not repo_clean:
        raise PipelineError(
            "Der Hauptstand ist nicht sauber. Bitte committe oder stash lokale Änderungen im Haupt-Repo, bevor du den Run übernimmst.\n\n"
            f"Aktueller Status:\n{repo_status or '-'}"
        )

    staged_files = stage_non_artifact_worktree_changes(worktree_path)
    if not staged_files:
        raise PipelineError("Es wurden keine übernehmbaren Projektänderungen gefunden. Run-, Handoff-, Review- und Output-Artefakte werden absichtlich nicht in den Basis-Branch übernommen.")

    commit_message = f"Run {run_id}: apply Codex changes"
    commit_process = git_run(["commit", "-m", commit_message], cwd=worktree_path)
    if commit_process.returncode != 0:
        raise PipelineError((commit_process.stderr or commit_process.stdout or "Commit im Worktree fehlgeschlagen.").strip())

    sha_process = git_run(["rev-parse", "HEAD"], cwd=worktree_path)
    commit_sha = (sha_process.stdout or "").strip()
    if sha_process.returncode != 0 or not commit_sha:
        raise PipelineError("Commit-SHA konnte nach dem Worktree-Commit nicht gelesen werden.")

    current_base_branch = git_current_branch(repo_root)
    if current_base_branch != target_branch:
        switch_process = git_run(["switch", target_branch], cwd=repo_root)
        if switch_process.returncode != 0:
            raise PipelineError((switch_process.stderr or switch_process.stdout or f"Branchwechsel zu {target_branch} fehlgeschlagen.").strip())

    cherry_pick_process = git_run(["cherry-pick", commit_sha], cwd=repo_root)
    if cherry_pick_process.returncode != 0:
        git_run(["cherry-pick", "--abort"], cwd=repo_root)
        raise PipelineError((cherry_pick_process.stderr or cherry_pick_process.stdout or "Cherry-pick fehlgeschlagen.").strip())

    applied_at = datetime.now().isoformat(timespec="seconds")
    updated_meta = update_worktree_run_meta(
        run_id,
        {
            "status": "applied_to_base",
            "last_applied_at": applied_at,
            "last_applied_commit": commit_sha,
            "last_applied_target_branch": target_branch,
            "last_applied_files": staged_files,
        },
    )
    return {
        "run_id": run_id,
        "target_branch": target_branch,
        "commit_sha": commit_sha,
        "staged_files": staged_files,
        "commit_message": commit_message,
        "applied_at": applied_at,
        "meta": updated_meta,
    }



OUTPUT_EXTENSIONS = [
    ".py", ".ps1", ".sql", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yml", ".txt"
]


def normalize_extension(extension: str, default: str = ".txt") -> str:
    value = (extension or "").strip()
    if not value:
        return default
    if not value.startswith("."):
        value = f".{value}"
    return value


def normalize_output_filename(base_name: str, extension: str) -> str:
    clean_extension = normalize_extension(extension, default=".txt")
    raw_name = (base_name or "generated_code").strip().replace(" ", "_")
    if not raw_name:
        raw_name = "generated_code"
    stem = Path(raw_name).stem
    if not stem:
        stem = "generated_code"
    return f"{stem}{clean_extension}"


def save_output_file(content: str, file_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = normalize_output_filename(Path(file_name).stem, Path(file_name).suffix or ".txt")
    out_path = OUTPUT_ROOT / f"{timestamp}_{safe_name}"
    write_text_file(out_path, content)
    return out_path


def file_language(path: Path) -> str:
    mapping = {
        ".py": "python", ".ps1": "powershell", ".sql": "sql", ".js": "javascript", ".ts": "typescript",
        ".html": "html", ".css": "css", ".json": "json", ".xml": "xml", ".yml": "yaml", ".yaml": "yaml",
        ".bat": "bat", ".cmd": "bat", ".md": "markdown",
    }
    return mapping.get(path.suffix.lower(), "text")


def safe_read_preview_text(path: Path) -> str:
    if not path.exists():
        raise PipelineError(f"Datei nicht vorhanden: {path}")
    if not path.is_file():
        raise PipelineError(f"Pfad ist keine Datei: {path}")
    return read_text_file(str(path))


def normalize_run_meta(data: dict, meta_file: Path) -> dict:
    normalized = dict(data)
    run_id = str(normalized.get("run_id") or meta_file.parent.name)
    meta_dir = meta_file.parent

    meta_path_value = str(normalized.get("meta_path") or normalized.get("run_path") or meta_dir)
    meta_dir_path = Path(meta_path_value)
    if meta_dir_path.suffix.lower() == ".json":
        meta_dir_path = meta_dir_path.parent

    task_path = Path(str(normalized.get("task_path") or (meta_dir_path / "task.md")))
    review_path = Path(str(normalized.get("review_path") or (meta_dir_path / "review.md")))
    result_path = Path(str(normalized.get("result_path") or (meta_dir_path / "result.json")))
    run_type = str(normalized.get("run_type") or ("scratch" if normalized.get("project_path") else "repo")).lower()
    worktree_path = Path(str(normalized.get("worktree_path") or ""))
    project_path = Path(str(normalized.get("project_path") or ""))
    target_path = Path(str(normalized.get("target_path") or project_path or worktree_path or ""))
    target_task_path = Path(str(normalized.get("target_task_path") or normalized.get("worktree_task_path") or (target_path / "task.md" if str(target_path) else "")))
    target_review_path = Path(str(normalized.get("target_review_path") or normalized.get("worktree_review_path") or (target_path / "review.md" if str(target_path) else "")))
    target_result_path = Path(str(normalized.get("target_result_path") or normalized.get("worktree_result_path") or (target_path / "result.json" if str(target_path) else "")))

    normalized["run_id"] = run_id
    normalized["run_type"] = run_type
    normalized["meta_path"] = str(meta_dir_path)
    normalized["task_path"] = str(task_path)
    normalized["review_path"] = str(review_path)
    normalized["result_path"] = str(result_path)
    normalized["project_path"] = str(project_path) if str(project_path) else ""
    normalized["target_path"] = str(target_path) if str(target_path) else ""
    normalized["target_task_path"] = str(target_task_path) if str(target_task_path) else ""
    normalized["target_review_path"] = str(target_review_path) if str(target_review_path) else ""
    normalized["target_result_path"] = str(target_result_path) if str(target_result_path) else ""
    normalized["target_exists"] = target_path.exists() if str(target_path) else False
    normalized["worktree_exists"] = worktree_path.exists() if str(worktree_path) else False
    return normalized


def is_repo_run(run_meta: dict | None) -> bool:
    if not isinstance(run_meta, dict):
        return True
    return str(run_meta.get("run_type") or "repo").lower() != "scratch"


def get_run_target_path(run_meta: dict | None) -> Path:
    if not isinstance(run_meta, dict):
        return Path("")
    target_value = str(run_meta.get("target_path") or run_meta.get("project_path") or run_meta.get("worktree_path") or "")
    return Path(target_value) if target_value else Path("")


def get_run_target_label(run_meta: dict | None) -> str:
    return "Worktree" if is_repo_run(run_meta) else "Projektordner"


def find_git_repo_root(start_path: Path) -> Path | None:
    current = start_path.resolve()
    for path in [current, *current.parents]:
        git_marker = path / ".git"
        if git_marker.exists():
            return path
    try:
        process = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start_path),
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if process.returncode == 0:
            value = (process.stdout or "").strip()
            if value:
                return Path(value)
    except Exception:
        pass
    return None


def is_git_repository(path: Path) -> bool:
    return find_git_repo_root(path) is not None


def git_run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )

def git_current_branch(repo_root: Path) -> str:
    process = git_run(["branch", "--show-current"], cwd=repo_root)
    if process.returncode == 0:
        value = (process.stdout or "").strip()
        if value:
            return value
    return ""


def git_default_branch(repo_root: Path) -> str:
    process = git_run(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_root)
    if process.returncode == 0:
        value = (process.stdout or "").strip()
        if value.startswith("refs/remotes/origin/"):
            return value.rsplit("/", 1)[-1]

    current = git_current_branch(repo_root)
    if current:
        return current

    for candidate in ("main", "master"):
        verify = git_run(["rev-parse", "--verify", candidate], cwd=repo_root)
        if verify.returncode == 0:
            return candidate
        verify_remote = git_run(["rev-parse", "--verify", f"origin/{candidate}"], cwd=repo_root)
        if verify_remote.returncode == 0:
            return candidate

    return "main"


def git_ref_exists(repo_root: Path, git_ref: str) -> bool:
    verify = git_run(["rev-parse", "--verify", f"{git_ref}^{{commit}}"], cwd=repo_root)
    return verify.returncode == 0


def list_available_git_refs(repo_root: Path) -> list[str]:
    process = git_run(
        [
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
            "refs/remotes/origin",
        ],
        cwd=repo_root,
    )
    if process.returncode != 0:
        return []
    refs = []
    for line in (process.stdout or "").splitlines():
        value = line.strip()
        if value and value != "origin/HEAD":
            refs.append(value)
    return sorted(dict.fromkeys(refs))


def build_base_ref_candidates(repo_root: Path, requested_ref: str) -> list[tuple[str, str]]:
    requested = (requested_ref or "").strip()
    default_branch = git_default_branch(repo_root)
    current_branch = git_current_branch(repo_root)
    candidates: list[tuple[str, str]] = []

    def add_ref(ref_value: str, label: str) -> None:
        ref_value = (ref_value or "").strip()
        if ref_value:
            candidates.append((ref_value, label))

    def add_branch_variants(branch_name: str, label: str | None = None) -> None:
        branch_name = (branch_name or "").strip()
        if not branch_name:
            return
        display = label or branch_name
        add_ref(branch_name, display)
        add_ref(f"refs/heads/{branch_name}", display)
        add_ref(f"origin/{branch_name}", display)
        add_ref(f"refs/remotes/origin/{branch_name}", display)

    if requested:
        if requested.upper() == "HEAD":
            add_ref("HEAD", "HEAD")
        else:
            add_branch_variants(requested, requested)

    if default_branch and default_branch != requested:
        add_branch_variants(default_branch, default_branch)
    if current_branch and current_branch not in {requested, default_branch}:
        add_branch_variants(current_branch, current_branch)

    add_ref("HEAD", current_branch or default_branch or requested or "HEAD")

    seen: set[str] = set()
    unique_candidates: list[tuple[str, str]] = []
    for ref_value, label in candidates:
        if ref_value in seen:
            continue
        seen.add(ref_value)
        unique_candidates.append((ref_value, label))
    return unique_candidates



def slugify_run_name(label: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", (label or "").strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "run"


def create_scratch_run(run_name: str) -> dict:
    repo_root = find_git_repo_root(APP_ROOT)

    run_slug = slugify_run_name(run_name)
    created_dt = datetime.now()
    run_id = f"{created_dt.strftime('%Y%m%d_%H%M%S')}_{run_slug}"
    project_path = PROJECTS_ROOT / run_id
    meta_dir = RUNS_ROOT / run_id
    task_path = meta_dir / "task.md"
    review_path = meta_dir / "review.md"
    result_path = meta_dir / "result.json"
    target_task_path = project_path / "task.md"
    target_review_path = project_path / "review.md"
    target_result_path = project_path / "result.json"

    meta_dir.mkdir(parents=True, exist_ok=True)
    project_path.mkdir(parents=True, exist_ok=True)
    (project_path / "outputs").mkdir(parents=True, exist_ok=True)

    initial_task = f"# Task\n\nRun: {run_id}\nName: {run_name}\n\n"
    initial_review = f"# Review\n\nRun: {run_id}\n\n"
    initial_result = json.dumps({"run_id": run_id, "status": "created"}, ensure_ascii=False, indent=2)

    task_path.write_text(initial_task, encoding="utf-8")
    review_path.write_text(initial_review, encoding="utf-8")
    result_path.write_text(initial_result, encoding="utf-8")
    target_task_path.write_text(initial_task, encoding="utf-8")
    target_review_path.write_text(initial_review, encoding="utf-8")
    target_result_path.write_text(initial_result, encoding="utf-8")

    meta = {
        "run_id": run_id,
        "name": run_name,
        "run_type": "scratch",
        "branch": "",
        "base_branch": "",
        "base_ref": "",
        "requested_base_ref": "",
        "status": "created",
        "created_at": created_dt.isoformat(timespec="seconds"),
        "repo_root": str(repo_root) if repo_root else "",
        "project_path": str(project_path),
        "target_path": str(project_path),
        "meta_path": str(meta_dir),
        "task_path": str(task_path),
        "review_path": str(review_path),
        "result_path": str(result_path),
        "target_task_path": str(target_task_path),
        "target_review_path": str(target_review_path),
        "target_result_path": str(target_result_path),
    }
    write_text_file(meta_dir / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def create_worktree_run(run_name: str, base_ref: str = "main") -> dict:
    repo_root = find_git_repo_root(APP_ROOT)
    if not repo_root:
        raise PipelineError("Dieses Projekt ist kein Git-Repository.")

    run_slug = slugify_run_name(run_name)
    created_dt = datetime.now()
    run_id = f"{created_dt.strftime('%Y%m%d_%H%M%S')}_{run_slug}"
    branch_name = f"run/{run_slug}-{created_dt.strftime('%Y%m%d_%H%M%S')}"
    worktree_path = WORKTREES_ROOT / run_id
    meta_dir = RUNS_ROOT / run_id
    task_path = meta_dir / "task.md"
    review_path = meta_dir / "review.md"
    result_path = meta_dir / "result.json"
    worktree_task_path = worktree_path / "task.md"
    worktree_review_path = worktree_path / "review.md"
    worktree_result_path = worktree_path / "result.json"
    requested_base_ref = (base_ref or "").strip() or git_default_branch(repo_root) or "HEAD"

    candidate_refs = build_base_ref_candidates(repo_root, requested_base_ref)
    attempt_errors: list[str] = []
    successful_ref = ""
    resolved_base_branch = requested_base_ref

    for candidate_ref, display_name in candidate_refs:
        add_process = git_run(["worktree", "add", "-b", branch_name, str(worktree_path), candidate_ref], cwd=repo_root)
        if add_process.returncode == 0:
            successful_ref = candidate_ref
            resolved_base_branch = display_name
            break
        error_text = (add_process.stderr or add_process.stdout or "Unbekannter Git-Fehler").strip()
        attempt_errors.append(f"{candidate_ref}: {error_text}")
        if worktree_path.exists() and not any(worktree_path.iterdir()):
            try:
                worktree_path.rmdir()
            except OSError:
                pass

    if not successful_ref:
        available_refs = list_available_git_refs(repo_root)
        available_preview = ", ".join(available_refs[:20]) if available_refs else "keine gefunden"
        attempts_preview = "\n".join(f"- {entry}" for entry in attempt_errors) if attempt_errors else "- keine Versuche protokolliert"
        raise PipelineError(
            f"Basis-Ref konnte nicht verwendet werden: {requested_base_ref}.\n"
            f"Erkannter Standard-Branch: {git_default_branch(repo_root) or 'unbekannt'}.\n"
            f"Gefundene Refs: {available_preview}\n\n"
            f"Getestete Git-Aufrufe:\n{attempts_preview}"
        )

    used_base_ref = successful_ref

    meta_dir.mkdir(parents=True, exist_ok=True)
    task_path.write_text(f"# Task\n\nRun: {run_id}\nName: {run_name}\n\n", encoding="utf-8")
    review_path.write_text(f"# Review\n\nRun: {run_id}\n\n", encoding="utf-8")
    result_path.write_text(json.dumps({"run_id": run_id, "status": "created"}, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = {
        "run_id": run_id,
        "name": run_name,
        "run_type": "repo",
        "branch": branch_name,
        "base_branch": resolved_base_branch,
        "base_ref": used_base_ref,
        "requested_base_ref": requested_base_ref,
        "status": "created",
        "created_at": created_dt.isoformat(timespec="seconds"),
        "repo_root": str(repo_root),
        "worktree_path": str(worktree_path),
        "target_path": str(worktree_path),
        "meta_path": str(meta_dir),
        "task_path": str(task_path),
        "review_path": str(review_path),
        "result_path": str(result_path),
        "worktree_task_path": str(worktree_task_path),
        "worktree_review_path": str(worktree_review_path),
        "worktree_result_path": str(worktree_result_path),
        "target_task_path": str(worktree_task_path),
        "target_review_path": str(worktree_review_path),
        "target_result_path": str(worktree_result_path),
    }
    write_text_file(meta_dir / "meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
    return meta

def list_worktree_runs() -> list[dict]:
    runs: list[dict] = []
    if not RUNS_ROOT.exists():
        return runs
    for meta_dir in sorted([p for p in RUNS_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name.lower(), reverse=True):
        meta_file = meta_dir / "meta.json"
        if not meta_file.exists():
            continue
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                runs.append(normalize_run_meta(data, meta_file))
        except Exception:
            continue
    return runs


def get_worktree_run(run_id: str) -> dict | None:
    meta_file = RUNS_ROOT / run_id / "meta.json"
    if not meta_file.exists():
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return normalize_run_meta(data, meta_file)
    except Exception:
        return None
    return None


def format_run_option_label(run: dict) -> str:
    run_id = str(run.get("run_id", "-"))
    name = str(run.get("name", run_id))
    status = str(run.get("status", "-")).strip() or "-"
    return f"{run_id} — {name} ({status})"


def update_worktree_run_meta(run_id: str, updates: dict) -> dict:
    meta_file = RUNS_ROOT / run_id / "meta.json"
    current = get_worktree_run(run_id)
    if not current:
        raise PipelineError(f"Run nicht gefunden: {run_id}")
    merged = dict(current)
    merged.update(updates)
    write_text_file(meta_file, json.dumps(merged, ensure_ascii=False, indent=2))
    return normalize_run_meta(merged, meta_file)


def build_review_input(user_input: str, result: dict) -> str:
    sections = [
        "## Ursprüngliche Aufgabe",
        user_input.strip() or "-",
        "",
        f"## Profil\n{result.get('profile_label', result.get('profile_key', '-'))}",
        f"## Modus\n{result.get('mode_name', '-')}",
        "",
    ]
    if result.get("final_task_1"):
        sections.extend(["## Analyse FINAL_TASK", result.get("final_task_1", "-"), ""])
    if result.get("final_task_2"):
        sections.extend(["## Lösungs FINAL_TASK", result.get("final_task_2", "-"), ""])
    if result.get("mode") == "queue":
        sections.extend([
            "## Queue-Zusammenfassung",
            result.get("queue_summary", "-"),
            "",
            "## Queue-Schritte",
            format_queue_steps_text(result.get("queue_steps", [])) or "-",
            "",
            "## Queue-Schritt-Ergebnisse",
            format_queue_step_results(result.get("queue_step_runs", [])) or "-",
            "",
        ])
    sections.extend([
        "## Finale Antwort",
        result.get("code_response", "").strip() or "-",
    ])
    return "\n".join(sections).strip()


def parse_review_response(text: str) -> dict:
    normalized = text.strip()
    status_match = re.search(r"(?im)^\s*REVIEW_STATUS\s*:\s*(PASS|FAIL)\s*$", normalized)
    summary_match = re.search(r"(?im)^\s*REVIEW_SUMMARY\s*:\s*(.+?)\s*$", normalized)
    improvement_match = re.search(r"(?im)^\s*IMPROVEMENT_TASK\s*:\s*(.+?)\s*$", normalized)

    issues_block = []
    issues_match = re.search(
        r"(?ims)^\s*REVIEW_ISSUES\s*:\s*(.+?)(?:^\s*IMPROVEMENT_TASK\s*:|\Z)",
        normalized,
    )
    if issues_match:
        block = issues_match.group(1).strip()
        for line in block.splitlines():
            cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if cleaned:
                issues_block.append(cleaned)

    status = status_match.group(1).upper() if status_match else "FAIL"
    summary = summary_match.group(1).strip() if summary_match else "Keine klare Review-Zusammenfassung erhalten."
    improvement_task = improvement_match.group(1).strip() if improvement_match else "NONE"
    if not issues_block:
        issues_block = ["Keine sauber auswertbaren Review-Punkte erkannt."]

    return {
        "status": status,
        "summary": summary,
        "issues": issues_block,
        "improvement_task": improvement_task or "NONE",
        "raw_response": normalized,
    }


def review_generated_output(host: str, model: str, user_input: str, result: dict) -> dict:
    review_input = build_review_input(user_input, result)
    review_prompt = AUTO_REVIEW_PROMPT.replace("[REVIEW_INPUT]", review_input)
    review_meta = call_ollama_generate(host, model, review_prompt)
    parsed = parse_review_response(review_meta["response"])
    parsed["prompt"] = review_prompt
    parsed["meta"] = review_meta
    return parsed


def build_improve_input(user_input: str, result: dict, review_data: dict) -> str:
    lines = [
        "## Ursprüngliche Aufgabe",
        user_input.strip() or "-",
        "",
        f"## Profil\n{result.get('profile_label', result.get('profile_key', '-'))}",
        f"## Modus\n{result.get('mode_name', '-')}",
        "",
    ]
    if result.get("final_task_1"):
        lines.extend(["## Analyse FINAL_TASK", result.get("final_task_1", "-"), ""])
    if result.get("final_task_2"):
        lines.extend(["## Lösungs FINAL_TASK", result.get("final_task_2", "-"), ""])
    if result.get("mode") == "queue":
        lines.extend([
            "## Queue-Zusammenfassung",
            result.get("queue_summary", "-"),
            "",
            "## Queue-Schritte",
            format_queue_steps_text(result.get("queue_steps", [])) or "-",
            "",
            "## Queue-Schritt-Ergebnisse",
            format_queue_step_results(result.get("queue_step_runs", [])) or "-",
            "",
        ])
    lines.extend([
        "## Bisherige finale Antwort",
        result.get("code_response", "").strip() or "-",
        "",
        "## Review-Zusammenfassung",
        review_data.get("summary", "-"),
        "",
        "## Review-Probleme",
    ])
    for issue in review_data.get("issues", []):
        lines.append(f"- {issue}")
    lines.extend([
        "",
        "## Konkrete Verbesserungsaufgabe",
        review_data.get("improvement_task", "NONE"),
    ])
    return "\n".join(lines).strip()


def improve_generated_output(host: str, model: str, user_input: str, result: dict, review_data: dict) -> dict:
    improve_input = build_improve_input(user_input, result, review_data)
    improve_prompt = AUTO_IMPROVE_PROMPT.replace("[IMPROVE_INPUT]", improve_input)
    improve_meta = call_ollama_generate(host, model, improve_prompt)
    return {
        "prompt": improve_prompt,
        "meta": improve_meta,
        "response": improve_meta["response"],
    }


def apply_automated_workflow(user_input: str, host: str, model: str, result: dict, auto_review: bool, auto_improve: bool) -> dict:
    automation = {
        "auto_review_enabled": auto_review,
        "auto_improve_enabled": auto_improve,
        "status": "not_run",
    }
    if not auto_review:
        result["automation"] = automation
        return result

    initial_review = review_generated_output(host, model, user_input, result)
    automation["initial_review"] = {
        "status": initial_review.get("status", "FAIL"),
        "summary": initial_review.get("summary", "-"),
        "issues": initial_review.get("issues", []),
        "improvement_task": initial_review.get("improvement_task", "NONE"),
        "raw_response": initial_review.get("raw_response", ""),
        "prompt": initial_review.get("prompt", ""),
    }
    automation["initial_review_meta"] = initial_review.get("meta", {})

    if initial_review.get("status") == "PASS":
        automation["status"] = "pass"
        automation["final_review"] = automation["initial_review"]
        automation["final_review_meta"] = automation["initial_review_meta"]
        result["automation"] = automation
        return result

    if not auto_improve or str(initial_review.get("improvement_task", "NONE")).strip().upper() == "NONE":
        automation["status"] = "review_fail"
        automation["final_review"] = automation["initial_review"]
        automation["final_review_meta"] = automation["initial_review_meta"]
        result["automation"] = automation
        return result

    original_response = result.get("code_response", "")
    improve_result = improve_generated_output(host, model, user_input, result, initial_review)
    result["original_code_response"] = original_response
    result["code_response"] = improve_result.get("response", original_response)
    result["automation_improved"] = True

    automation["improvement"] = {
        "prompt": improve_result.get("prompt", ""),
        "response": improve_result.get("response", ""),
    }
    automation["improve_meta"] = improve_result.get("meta", {})

    final_review = review_generated_output(host, model, user_input, result)
    automation["final_review"] = {
        "status": final_review.get("status", "FAIL"),
        "summary": final_review.get("summary", "-"),
        "issues": final_review.get("issues", []),
        "improvement_task": final_review.get("improvement_task", "NONE"),
        "raw_response": final_review.get("raw_response", ""),
        "prompt": final_review.get("prompt", ""),
    }
    automation["final_review_meta"] = final_review.get("meta", {})
    automation["status"] = "improved_pass" if final_review.get("status") == "PASS" else "improved_fail"

    result["automation"] = automation
    return result


def build_run_task_markdown(run_meta: dict, user_input: str, result: dict, profile_label: str, mode_name: str, model: str) -> str:
    lines = [
        "# Task",
        "",
        f"Run: {run_meta.get('run_id', '-')}",
        f"Name: {run_meta.get('name', '-')}",
        f"Aktualisiert: {datetime.now().isoformat(timespec='seconds')}",
        f"Profil: {profile_label}",
        f"Modus: {mode_name}",
        f"Modell: {model}",
        "",
        "## Roh-Prompt",
        "",
        user_input.strip() or "-",
        "",
    ]
    if result.get("mode") == "pipeline":
        lines.extend([
            "## Analyse FINAL_TASK",
            "",
            result.get("final_task_1", "-"),
            "",
            "## Lösungs FINAL_TASK",
            "",
            result.get("final_task_2", "-"),
            "",
            "## Analyse-Prompt",
            "",
            "```text",
            result.get("analyse_prompt", "").strip(),
            "```",
            "",
            "## Lösungs-Prompt",
            "",
            "```text",
            result.get("loesung_prompt", "").strip(),
            "```",
            "",
            "## Code-Prompt",
            "",
            "```text",
            result.get("code_prompt", "").strip(),
            "```",
        ])
    elif result.get("mode") == "queue":
        lines.extend([
            "## Queue-Zusammenfassung",
            "",
            result.get("queue_summary", "-"),
            "",
            "## Queue-Schritte",
            "",
            "```text",
            format_queue_steps_text(result.get("queue_steps", [])).strip() or "-",
            "```",
            "",
            "## Queue-Plan-Prompt",
            "",
            "```text",
            result.get("queue_plan_prompt", "").strip(),
            "```",
            "",
            "## Queue-Plan-Antwort",
            "",
            "```text",
            result.get("queue_plan_response", "").strip(),
            "```",
            "",
            "## Queue-Schritt-Ergebnisse",
            "",
            "```text",
            format_queue_step_results(result.get("queue_step_runs", [])).strip() or "-",
            "```",
            "",
            "## Finalisierungs-Prompt",
            "",
            "```text",
            result.get("code_prompt", "").strip(),
            "```",
        ])
    else:
        lines.extend([
            "## Prompt",
            "",
            "```text",
            result.get("code_prompt", "").strip(),
            "```",
        ])
    return "\n".join(lines).strip() + "\n"


def build_run_review_markdown(run_meta: dict, result: dict, output_path: Path) -> str:
    stats = collect_run_stats(result)
    automation = result.get("automation", {}) if isinstance(result, dict) else {}
    final_review = automation.get("final_review") or automation.get("initial_review") or {}
    auto_status = automation.get("status", "not_run")

    lines = [
        "# Review",
        "",
        f"Run: {run_meta.get('run_id', '-')}",
        f"Aktualisiert: {datetime.now().isoformat(timespec='seconds')}",
        f"Status: {auto_status}",
        "",
        "## Zusammenfassung",
        "",
        f"- Profil: {result.get('profile_label', result.get('profile_key', '-'))}",
        f"- Modus: {result.get('mode_name', '-')}",
        f"- Modell: {result.get('model', '-')}",
        f"- Schritte: {stats.get('steps', 0)}",
        f"- Input-Tokens: {stats.get('input_tokens', 0)}",
        f"- Output-Tokens: {stats.get('output_tokens', 0)}",
        f"- Dauer: {format_duration_ns(stats.get('total_duration', 0))}",
        f"- Ergebnisdatei: {output_path}",
        "",
        "## Automatische Bewertung",
        "",
        f"- Review-Status: {final_review.get('status', '-')}",
        f"- Zusammenfassung: {final_review.get('summary', '-')}",
        f"- Automatische Verbesserung: {'Ja' if automation.get('improvement') else 'Nein'}",
        "",
        "## Review-Punkte",
        "",
    ]

    for issue in final_review.get("issues", []):
        lines.append(f"- {issue}")

    if not final_review.get("issues"):
        lines.append("- Keine automatisch erkannten Punkte.")

    lines.extend([
        "",
        "## Manuelle Freigabe",
        "",
        "- [ ] Ergebnis fachlich geprüft",
        "- [ ] Ergebnis freigegeben",
        "- [ ] Weitere Nacharbeit nötig",
    ])
    return "\n".join(lines).strip() + "\n"

def write_run_execution_artifacts(run_id: str, user_input: str, output_filename: str, result: dict) -> dict:
    run_meta = get_worktree_run(run_id)
    if not run_meta:
        raise PipelineError(f"Aktiver Run nicht gefunden: {run_id}")

    meta_dir = Path(str(run_meta.get("meta_path", RUNS_ROOT / run_id)))
    target_dir = get_run_target_path(run_meta)
    task_path = Path(str(run_meta.get("task_path", meta_dir / "task.md")))
    review_path = Path(str(run_meta.get("review_path", meta_dir / "review.md")))
    result_path = Path(str(run_meta.get("result_path", meta_dir / "result.json")))
    target_task_path = Path(str(run_meta.get("target_task_path") or run_meta.get("worktree_task_path") or (target_dir / "task.md")))
    target_review_path = Path(str(run_meta.get("target_review_path") or run_meta.get("worktree_review_path") or (target_dir / "review.md")))
    target_result_path = Path(str(run_meta.get("target_result_path") or run_meta.get("worktree_result_path") or (target_dir / "result.json")))
    outputs_dir = meta_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    target_outputs_dir = target_dir / "outputs"
    if target_dir.exists() and target_dir.is_dir():
        target_outputs_dir.mkdir(parents=True, exist_ok=True)

    normalized_name = normalize_output_filename(Path(output_filename).stem, Path(output_filename).suffix or ".txt")
    output_path = outputs_dir / normalized_name
    write_text_file(output_path, result.get("code_response", ""))
    target_output_path = target_outputs_dir / normalized_name if target_dir.exists() and target_dir.is_dir() else None
    if target_output_path is not None:
        write_text_file(target_output_path, result.get("code_response", ""))

    task_content = build_run_task_markdown(
        run_meta=run_meta,
        user_input=user_input,
        result=result,
        profile_label=result.get("profile_label", result.get("profile_key", "-")),
        mode_name=result.get("mode_name", "-"),
        model=result.get("model", "-"),
    )
    review_content = build_run_review_markdown(run_meta=run_meta, result=result, output_path=output_path)
    write_text_file(task_path, task_content)
    write_text_file(review_path, review_content)
    if target_dir.exists() and target_dir.is_dir():
        write_text_file(target_task_path, task_content)
        write_text_file(target_review_path, review_content)

    stats = collect_run_stats(result)
    result_payload = {
        "run_id": run_id,
        "status": "result_written",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "profile_key": result.get("profile_key"),
        "profile_label": result.get("profile_label"),
        "mode_name": result.get("mode_name"),
        "model": result.get("model"),
        "output_filename": normalized_name,
        "output_path": str(output_path),
        "stats": stats,
        "final_task_1": result.get("final_task_1"),
        "final_task_2": result.get("final_task_2"),
        "queue_summary": result.get("queue_summary"),
        "queue_steps": result.get("queue_steps", []),
        "queue_step_runs": [
            {
                "index": step_run.get("index"),
                "step": step_run.get("step"),
                "response": step_run.get("response", ""),
            }
            for step_run in result.get("queue_step_runs", [])
        ],
        "code_response": result.get("code_response", ""),
        "original_code_response": result.get("original_code_response"),
        "automation": result.get("automation", {}),
    }
    result_json = json.dumps(result_payload, ensure_ascii=False, indent=2)
    write_text_file(result_path, result_json)
    if target_dir.exists() and target_dir.is_dir():
        write_text_file(target_result_path, result_json)

    updated_meta = update_worktree_run_meta(
        run_id,
        {
            "status": "result_written",
            "last_result_at": result_payload["updated_at"],
            "last_profile_key": result.get("profile_key"),
            "last_profile_label": result.get("profile_label"),
            "last_mode_name": result.get("mode_name"),
            "last_model": result.get("model"),
            "last_output_path": str(output_path),
            "last_review_status": (result.get("automation", {}).get("final_review") or result.get("automation", {}).get("initial_review") or {}).get("status"),
            "last_automation_status": result.get("automation", {}).get("status"),
            "task_path": str(task_path),
            "review_path": str(review_path),
            "result_path": str(result_path),
            "target_task_path": str(target_task_path),
            "target_review_path": str(target_review_path),
            "target_result_path": str(target_result_path),
            "target_output_path": str(target_output_path) if target_output_path is not None else None,
            "worktree_task_path": str(target_task_path),
            "worktree_review_path": str(target_review_path),
            "worktree_result_path": str(target_result_path),
            "worktree_output_path": str(target_output_path) if target_output_path is not None else None,
        },
    )
    return {
        "run_id": run_id,
        "task_path": str(task_path),
        "review_path": str(review_path),
        "result_path": str(result_path),
        "output_path": str(output_path),
        "target_task_path": str(target_task_path),
        "target_review_path": str(target_review_path),
        "target_result_path": str(target_result_path),
        "target_output_path": str(target_output_path) if target_output_path is not None else None,
        "worktree_task_path": str(target_task_path),
        "worktree_review_path": str(target_review_path),
        "worktree_result_path": str(target_result_path),
        "worktree_output_path": str(target_output_path) if target_output_path is not None else None,
        "meta": updated_meta,
    }


def remove_worktree_run(run_id: str) -> None:
    meta = get_worktree_run(run_id)
    if not meta:
        raise PipelineError(f"Run nicht gefunden: {run_id}")

    if is_repo_run(meta):
        repo_root = find_git_repo_root(APP_ROOT)
        if not repo_root:
            raise PipelineError("Dieses Projekt ist kein Git-Repository.")

        worktree_path = Path(str(meta.get("worktree_path", "")))
        branch_name = str(meta.get("branch", "")).strip()

        if worktree_path.exists():
            remove_process = git_run(["worktree", "remove", "--force", str(worktree_path)], cwd=repo_root)
            if remove_process.returncode != 0:
                raise PipelineError((remove_process.stderr or remove_process.stdout or "Worktree konnte nicht entfernt werden.").strip())

        if branch_name:
            delete_branch = git_run(["branch", "-D", branch_name], cwd=repo_root)
            if delete_branch.returncode != 0:
                raise PipelineError((delete_branch.stderr or delete_branch.stdout or "Branch konnte nicht gelöscht werden.").strip())
    else:
        project_path = get_run_target_path(meta)
        if project_path.exists():
            shutil.rmtree(project_path)

    meta_dir = RUNS_ROOT / run_id
    if meta_dir.exists():
        shutil.rmtree(meta_dir)


def run_summary_counts(runs: list[dict]) -> tuple[int, int, int]:
    total = len(runs)
    existing = sum(1 for run in runs if run.get("target_exists") or run.get("worktree_exists"))
    missing = total - existing
    return total, existing, missing


ensure_structure()
profile_labels = bootstrap_profiles()

if "ui_settings" not in st.session_state:
    st.session_state["ui_settings"] = load_ui_settings()

st.session_state.setdefault("output_base_name", "generated_code")
st.session_state.setdefault("output_extension", ".py")
st.session_state.setdefault("output_extension_mode", "Vorgabe")
st.session_state.setdefault("output_extension_custom", "")
st.session_state.setdefault("keep_alive_value", "30m")
st.session_state.setdefault("auto_review_enabled", True)
st.session_state.setdefault("auto_improve_enabled", True)
st.session_state.setdefault("codex_handoff_enabled", True)
st.session_state.setdefault("open_vscode_after_run", False)
st.session_state.setdefault("codex_exec_after_run", False)
st.session_state.setdefault("auto_apply_to_base_after_codex", False)
st.session_state.setdefault("external_executor", "Codex CLI")
st.session_state.setdefault("handoff_prompt_basis", "Original + Aufbereitung")
st.session_state.setdefault("review_owner", "Lokales Modell")
st.session_state.setdefault("improve_owner", "Lokales Modell")
st.session_state.setdefault("claude_ollama_model", DEFAULT_CLAUDE_OLLAMA_MODEL)

if st.session_state.pop("_force_full_reload", False):
    st.session_state.pop("last_result", None)
    st.session_state.pop("last_preload_result", None)
    st.info("Layout wird vollständig neu geladen...")
    components.html("""
    <script>
    const reload = () => {
      try {
        window.parent.location.reload();
      } catch (e) {
        window.location.reload();
      }
    };
    setTimeout(reload, 50);
    </script>
    """, height=0)
    st.stop()

run_refresh_notice = st.session_state.pop("_run_refresh_notice", "")
manual_codex_notice = st.session_state.pop("_codex_exec_notice", "")

st.title("Ollama GUI")
st.caption("Oberfläche mit Profilen, Dateiübersicht und Skript-Ausführung")

if "current_model" not in st.session_state:
    st.session_state["current_model"] = "llama3.2"
if "selected_mode_name" not in st.session_state or st.session_state["selected_mode_name"] not in MODE_DEFINITIONS:
    st.session_state["selected_mode_name"] = "3-Stufen Pipeline"

ui_settings = st.session_state["ui_settings"]
is_advanced = is_advanced_mode(ui_settings)

with st.sidebar:
    st.header("Konfiguration")

    all_profile_keys = list(profile_labels.keys())
    visible_profile_keys = [key for key in ui_settings.get("visible_profiles", []) if key in profile_labels]
    if not visible_profile_keys:
        visible_profile_keys = get_default_visible_profiles(set(profile_labels.keys()))

    settings_changed = False
    with st.expander("Allgemeine Einstellungen", expanded=False):
        st.caption("Hier steuerst du Bedienmodus, sichtbare Profile und zusätzliche UI-Bereiche.")
        ui_mode = st.radio(
            "Bedienmodus",
            options=["standard", "advanced"],
            index=0 if ui_settings.get("ui_mode", "standard") == "standard" else 1,
            format_func=lambda value: "Standard" if value == "standard" else "Erweitert",
            horizontal=True,
            help="Standard blendet technische Details aus. Erweitert zeigt zusätzliche Verwaltungs- und Diagnosebereiche.",
        )
        if ui_mode == "standard":
            st.caption("Standard zeigt den schlanken Ablauf: Profil, Modus, Modell, Eingabe und Ergebnis.")
        else:
            st.caption("Erweitert zeigt zusätzliche technische Details, Datei- und Skriptbereiche.")

        st.caption(f"GUI: {APP_ROOT}")

        if ui_settings.get("show_project_structure", True):
            with st.expander("Projektstruktur", expanded=False):
                st.text_area(
                    "Vollständige Pfade",
                    value=project_structure_text(),
                    height=220,
                    disabled=True,
                    label_visibility="collapsed",
                )

        st.markdown("**Profile in Profilliste**")
        selected_visible_profiles: list[str] = []
        for profile_option in all_profile_keys:
            is_checked = profile_option in visible_profile_keys
            new_value = st.checkbox(
                profile_labels.get(profile_option, profile_option),
                value=is_checked,
                key=f"setting_profile_{profile_option}",
            )
            if new_value:
                selected_visible_profiles.append(profile_option)

        if not selected_visible_profiles:
            st.warning("Mindestens ein Profil muss sichtbar bleiben.")
            selected_visible_profiles = visible_profile_keys

        st.markdown("**UI-Elemente**")
        show_project_structure = st.checkbox(
            "Projektstruktur in Einstellungen anzeigen",
            value=bool(ui_settings.get("show_project_structure", True)),
            key="setting_show_project_structure",
        )
        show_active_prompt_files = st.checkbox(
            "Aktive Prompt-Dateien anzeigen",
            value=bool(ui_settings.get("show_active_prompt_files", True)),
            key="setting_show_active_prompt_files",
        )
        show_active_run = st.checkbox(
            "Aktiver Lauf anzeigen",
            value=bool(ui_settings.get("show_active_run", True)),
            key="setting_show_active_run",
        )
        show_result_prompts = st.checkbox(
            "Prompt- und Analyse-Details im Ergebnis anzeigen",
            value=bool(ui_settings.get("show_result_prompts", True)),
            key="setting_show_result_prompts",
        )
        show_result_status_messages = st.checkbox(
            "Statusmeldungen im Ergebnis anzeigen",
            value=bool(ui_settings.get("show_result_status_messages", True)),
            key="setting_show_result_status_messages",
        )
        show_result_metrics = st.checkbox(
            "Kennzahlen im Ergebnis anzeigen",
            value=bool(ui_settings.get("show_result_metrics", True)),
            key="setting_show_result_metrics",
        )
        show_result_auto_review = st.checkbox(
            "Automatische Prüfung im Ergebnis anzeigen",
            value=bool(ui_settings.get("show_result_auto_review", True)),
            key="setting_show_result_auto_review",
        )
        show_result_codex_section = st.checkbox(
            "Codex / Git-Übernahme im Ergebnis anzeigen",
            value=bool(ui_settings.get("show_result_codex_section", True)),
            key="setting_show_result_codex_section",
        )
        show_result_action_buttons = st.checkbox(
            "Ergebnis-Aktionsbuttons anzeigen",
            value=bool(ui_settings.get("show_result_action_buttons", True)),
            key="setting_show_result_action_buttons",
        )
        show_codex_controls = st.checkbox(
            "Codex-Steuerung im Code-Tab anzeigen",
            value=bool(ui_settings.get("show_codex_controls", True)),
            key="setting_show_codex_controls",
        )
        show_run_preview_files = st.checkbox(
            "Dateivorschau im Runs-Tab anzeigen",
            value=bool(ui_settings.get("show_run_preview_files", True)),
            key="setting_show_run_preview_files",
        )
        show_files_tab = st.checkbox(
            "Dateien-Tab anzeigen",
            value=bool(ui_settings.get("show_files_tab", True)),
            key="setting_show_files_tab",
        )
        show_scripts_tab = st.checkbox(
            "Skripte-Tab anzeigen",
            value=bool(ui_settings.get("show_scripts_tab", True)),
            key="setting_show_scripts_tab",
        )

        candidate_settings = {
            "ui_mode": ui_mode,
            "visible_profiles": selected_visible_profiles,
            "show_project_structure": show_project_structure,
            "show_active_prompt_files": show_active_prompt_files,
            "show_active_run": show_active_run,
            "show_result_prompts": show_result_prompts,
            "show_result_status_messages": show_result_status_messages,
            "show_result_metrics": show_result_metrics,
            "show_result_auto_review": show_result_auto_review,
            "show_result_codex_section": show_result_codex_section,
            "show_result_action_buttons": show_result_action_buttons,
            "show_codex_controls": show_codex_controls,
            "show_run_preview_files": show_run_preview_files,
            "show_files_tab": show_files_tab,
            "show_scripts_tab": show_scripts_tab,
        }
        settings_changed = candidate_settings != ui_settings

        col_save, col_reset = st.columns(2)
        with col_save:
            if st.button("Einstellungen speichern", use_container_width=True, disabled=not settings_changed, type="primary" if settings_changed else "secondary"):
                previous_mode = ui_settings.get("ui_mode", "standard")
                st.session_state["ui_settings"] = candidate_settings
                save_ui_settings(candidate_settings)
                if candidate_settings.get("ui_mode", "standard") != previous_mode:
                    st.session_state["_force_full_reload"] = True
                st.rerun()
        with col_reset:
            if st.button("Standard wiederherstellen", use_container_width=True):
                previous_mode = ui_settings.get("ui_mode", "standard")
                st.session_state["ui_settings"] = DEFAULT_UI_SETTINGS.copy()
                save_ui_settings(DEFAULT_UI_SETTINGS.copy())
                if DEFAULT_UI_SETTINGS.get("ui_mode", "standard") != previous_mode:
                    st.session_state["_force_full_reload"] = True
                st.rerun()

    ui_settings = st.session_state["ui_settings"]
    is_advanced = is_advanced_mode(ui_settings)
    previous_ui_mode = st.session_state.get("_previous_ui_mode")
    current_ui_mode = ui_settings.get("ui_mode", "standard")
    if previous_ui_mode != current_ui_mode:
        st.session_state["_previous_ui_mode"] = current_ui_mode
        st.session_state.pop("_last_render_mode_switch", None)

    visible_profile_keys = [key for key in ui_settings.get("visible_profiles", []) if key in profile_labels]
    if not visible_profile_keys:
        visible_profile_keys = get_default_visible_profiles(set(profile_labels.keys()))

    current_profile = st.session_state.get("selected_profile_key", "code_generate")
    if current_profile not in visible_profile_keys:
        current_profile = visible_profile_keys[0]

    profile_key = st.selectbox(
        "Profil wählen:",
        options=visible_profile_keys,
        index=visible_profile_keys.index(current_profile),
        format_func=lambda key: profile_labels.get(key, key),
    )
    st.session_state["selected_profile_key"] = profile_key

    current_mode = st.session_state.get("selected_mode_name", "3-Stufen Pipeline")
    if current_mode not in MODE_DEFINITIONS:
        current_mode = "3-Stufen Pipeline"
    mode_name = st.radio(
        "Modus",
        options=list(MODE_DEFINITIONS.keys()),
        index=list(MODE_DEFINITIONS.keys()).index(current_mode),
        key="selected_mode_name",
    )

    st.divider()
    with st.expander("Modell Konfiguration", expanded=True):
        if is_advanced:
            ollama_host = st.text_input("Ollama Host", value="http://localhost:11434")
            current_keep_alive = st.session_state.get("keep_alive_value", "30m")
            if current_keep_alive not in KEEP_ALIVE_OPTIONS:
                current_keep_alive = "30m"
            keep_alive_value = st.selectbox(
                "Keep-Alive Modell",
                options=KEEP_ALIVE_OPTIONS,
                index=KEEP_ALIVE_OPTIONS.index(current_keep_alive),
                key="keep_alive_value",
            )
        else:
            ollama_host = "http://localhost:11434"
            keep_alive_value = "30m"

        ollama_running = is_ollama_running(ollama_host)
        available_models: list[str] = []
        if ollama_running:
            st.success("Ollama API erreichbar über Ollama Host")
            try:
                available_models = list_ollama_models(ollama_host)
                if available_models:
                    st.caption("Verfügbare Modelle")
                    current_model = st.session_state.get("current_model", "llama3.2")
                    default_model = current_model if current_model in available_models else available_models[0]
                    model = st.selectbox(
                        "Zielmodell",
                        options=available_models,
                        index=available_models.index(default_model),
                        help="Dieses Modell bekommt deinen Prompt und erzeugt den Code.",
                    )
                    st.session_state["current_model"] = model
                    st.caption(f"Aktuell ausgewählt: {model}")
                else:
                    st.info("Keine Modelle gefunden.")
                    model = st.text_input("Modell", value=st.session_state.get("current_model", "llama3.2"))
                    st.session_state["current_model"] = model
            except Exception as exc:
                st.warning(f"Modelle konnten nicht gelesen werden: {exc}")
                model = st.text_input("Modell", value=st.session_state.get("current_model", "llama3.2"))
                st.session_state["current_model"] = model
        else:
            st.warning("Ollama API über Ollama Host aktuell nicht erreichbar")
            model = st.text_input("Modell", value=st.session_state.get("current_model", "llama3.2"))
            st.session_state["current_model"] = model

        if not is_advanced:
            st.caption("Standard-Modus nutzt den lokalen Standard-Host und 30m Keep-Alive.")

        refresh_models = st.button("Modellliste aktualisieren", use_container_width=True, help="Liest die lokal verfügbaren Ollama-Modelle erneut ein. Nutze das nach einem neuen Pull oder nach einem Ollama-Neustart.")
        if refresh_models:
            st.rerun()

        if st.button("Ollama Server starten", use_container_width=True, help="Startet lokal den Ollama-Dienst (ollama serve). Nutze das nach einem Systemstart oder wenn die API nicht erreichbar ist."):
            try:
                if is_ollama_running(ollama_host):
                    st.info("Ollama läuft bereits.")
                else:
                    start_ollama_server_background()
                    if wait_for_ollama(ollama_host, timeout_seconds=20):
                        st.success("Ollama Server wurde gestartet.")
                    else:
                        st.error("Ollama wurde gestartet, aber die API antwortet noch nicht.")
            except Exception as exc:
                st.exception(exc)

        if st.button("Modell im Hintergrund laden", use_container_width=True, help="Lädt das gewählte Modell vorab in den Speicher und hält es für die Keep-Alive-Zeit aktiv. Nutze das vor dem ersten Run oder nach einem Modellwechsel."):
            try:
                if not is_ollama_running(ollama_host):
                    start_ollama_server_background()
                    if not wait_for_ollama(ollama_host, timeout_seconds=20):
                        raise PipelineError("Ollama API ist nicht erreichbar.")
                with st.spinner(f"Modell {model} wird geladen..."):
                    preload_result = preload_model(ollama_host, model, keep_alive=keep_alive_value.strip() or "30m")
                st.session_state["last_preload_result"] = preload_result
                st.success(f"Modell {model} ist geladen und bleibt {keep_alive_value} aktiv.")
            except Exception as exc:
                st.exception(exc)


main_area = st.empty()
with main_area.container():
    tab_definitions = [("Code", "code")]
    if is_advanced:
        tab_definitions.append(("Runs", "runs"))
        tab_definitions.append(("Profile", "profiles"))
    if is_advanced and ui_settings.get("show_files_tab", True):
        tab_definitions.append(("Dateien", "files"))
    if is_advanced and ui_settings.get("show_scripts_tab", True):
        tab_definitions.append(("Skripte", "scripts"))

    tab_objects = st.tabs([label for label, _ in tab_definitions])
    tabs_by_key = {key: obj for obj, (_, key) in zip(tab_objects, tab_definitions)}

    with tabs_by_key["code"]:
        if not is_advanced:
            st.caption("Standard-Modus aktiv: technische Details und Verwaltungsbereiche sind reduziert.")
        left, right = st.columns([1.1, 0.9])

        with right:
            mode_name = st.session_state.get("selected_mode_name", "3-Stufen Pipeline")
            if mode_name not in MODE_DEFINITIONS:
                mode_name = "3-Stufen Pipeline"
            if ui_settings.get("show_active_run", True):
                st.subheader("Aktiver Lauf")
                st.markdown(f"**Profil:** `{profile_labels.get(profile_key, profile_key)}`")

                st.markdown(
                    f"**Modus:** `{mode_name}` <span title='{get_mode_help_text(mode_name)}' style='color:#9ca3af; font-size:0.82rem; cursor:help;'>&#9432;</span>",
                    unsafe_allow_html=True,
                )

                profile_config = get_profile_config(profile_key, mode_name)
                st.markdown(f"**Zielmodell:** `{model}`")

                available_runs_for_code = list_worktree_runs()
                run_choices = [""] + [run["run_id"] for run in available_runs_for_code]
                current_run_id = st.session_state.get("selected_run_id") or ""
                if current_run_id not in run_choices:
                    current_run_id = ""
                selected_run_for_code = st.selectbox(
                    "Aktiver Run",
                    options=run_choices,
                    index=run_choices.index(current_run_id),
                    format_func=lambda run_id: "Kein Run ausgewählt" if not run_id else format_run_option_label(get_worktree_run(run_id) or {"run_id": run_id}),
                    key="code_run_selector",
                )
                st.session_state["selected_run_id"] = selected_run_for_code or None
                active_run_meta = get_worktree_run(selected_run_for_code) if selected_run_for_code else None
                if active_run_meta:
                    target_label = get_run_target_label(active_run_meta)
                    target_path = get_run_target_path(active_run_meta)
                    st.caption(f"{target_label}: {target_path or '-'}")
                    run_open_col, run_meta_col = st.columns(2)
                    with run_open_col:
                        if st.button(f"{target_label} öffnen", use_container_width=True, key="code_open_active_worktree"):
                            try:
                                open_folder_in_explorer(target_path)
                            except Exception as exc:
                                st.exception(exc)
                    with run_meta_col:
                        if st.button("Run-Meta öffnen", use_container_width=True, key="code_open_active_run_meta"):
                            try:
                                open_folder_in_explorer(Path(str(active_run_meta.get("meta_path", ""))))
                            except Exception as exc:
                                st.exception(exc)
                else:
                    st.caption("Kein aktiver Run ausgewählt. Ergebnis bleibt nur in der GUI, bis du einen Run wählst.")

                last_result_for_stats = st.session_state.get("last_result")
                if isinstance(last_result_for_stats, dict):
                    stats = last_result_for_stats.get("workflow_stats") or collect_run_stats(last_result_for_stats)
                else:
                    stats = {"input_tokens": 0, "output_tokens": 0, "total_duration": 0, "steps": 0}
                m1, m2 = st.columns(2)
                m1.metric("Input-Tokens gesamt", format_tokens(stats["input_tokens"]))
                m2.metric("Output-Tokens gesamt", format_tokens(stats["output_tokens"]))
                m3, m4 = st.columns(2)
                m3.metric("Gesamtzeit", format_duration_ns(stats["total_duration"]))
                m4.metric("Schritte", str(stats["steps"]) if stats["steps"] else "-")

                preload_result = st.session_state.get("last_preload_result")
                if is_advanced and preload_result:
                    st.subheader("Letzter Modellstart")
                    c1, c2 = st.columns(2)
                    c1.metric("Output-Tokens", format_tokens(metric_value(preload_result, "eval_count")))
                    c2.metric("Dauer", format_duration_ns(metric_value(preload_result, "total_duration")))
            else:
                profile_config = get_profile_config(profile_key, mode_name)
                st.subheader("Aktiver Lauf")
                st.caption("In den Einstellungen ausgeblendet.")

        with left:
            st.subheader("Eingabe")
            user_input = st.text_area(
                "Prompt",
                height=220,
                placeholder="Beschreibe, welchen Code du erzeugen, korrigieren oder umbauen möchtest...",
            )
            st.markdown("**Output-Dateiname**")
            output_name_col, output_ext_col = st.columns([6, 1.25], vertical_alignment="bottom")
            with output_name_col:
                output_base_name = st.text_input(
                    "Output-Dateiname",
                    key="output_base_name",
                    label_visibility="collapsed",
                    placeholder="generated_code",
                )
            with output_ext_col:
                output_extension_mode = st.selectbox(
                    "Dateiendung",
                    options=["Vorgabe", "Eigene..."],
                    index=0 if st.session_state.get("output_extension_mode", "Vorgabe") == "Vorgabe" else 1,
                    key="output_extension_mode",
                    label_visibility="collapsed",
                )

            if output_extension_mode == "Vorgabe":
                output_extension = st.selectbox(
                    "Vorgegebene Endung",
                    options=OUTPUT_EXTENSIONS,
                    index=OUTPUT_EXTENSIONS.index(st.session_state.get("output_extension", ".py")) if st.session_state.get("output_extension", ".py") in OUTPUT_EXTENSIONS else OUTPUT_EXTENSIONS.index(".py"),
                    key="output_extension",
                    label_visibility="collapsed",
                )
            else:
                custom_output_extension = st.text_input(
                    "Eigene Endung",
                    value=st.session_state.get("output_extension_custom", st.session_state.get("output_extension", ".py")),
                    key="output_extension_custom",
                    label_visibility="collapsed",
                    placeholder="z. B. .lua oder lua",
                )
                output_extension = normalize_extension(custom_output_extension, default=".txt")
                st.session_state["output_extension"] = output_extension

            output_filename = normalize_output_filename(output_base_name, output_extension)

            st.markdown("**Automatischer Ablauf**")
            workflow_col1, workflow_col2 = st.columns(2)
            with workflow_col1:
                auto_review_enabled = st.checkbox(
                    "Output automatisch prüfen",
                    key="auto_review_enabled",
                    help="Prüft die erzeugte finale Antwort automatisch gegen Aufgabe und Ergebnis.",
                )
            with workflow_col2:
                auto_improve_enabled = st.checkbox(
                    "Bei Bedarf einmal verbessern",
                    key="auto_improve_enabled",
                    disabled=not auto_review_enabled,
                    help="Führt nach einem fehlgeschlagenen Review genau einen automatischen Verbesserungsdurchlauf aus.",
                )
            if auto_review_enabled:
                if auto_improve_enabled:
                    st.caption("Aufbereitung, Ausführung, Review und einen möglichen Verbesserungsdurchlauf.")
                else:
                    st.caption("Ein Klick führt jetzt Aufbereitung, Ausführung und automatisches Review aus.")
            else:
                st.caption("Ein Klick führt nur Aufbereitung und Ausführung aus.")

            active_run_meta = get_worktree_run(st.session_state.get("selected_run_id", "")) if st.session_state.get("selected_run_id") else None
            codex_exec_btn = False
            selected_external_executor = st.session_state.get("external_executor", "Codex CLI")
            review_owner = st.session_state.get("review_owner", "Lokales Modell")
            improve_owner = st.session_state.get("improve_owner", "Lokales Modell")
            if active_run_meta and ui_settings.get("show_codex_controls", True):
                st.markdown("**Prozess-Zuordnung**")
                process_col1, process_col2 = st.columns(2)
                with process_col1:
                    st.selectbox(
                        "Externer Executor",
                        options=EXTERNAL_EXECUTOR_OPTIONS,
                        key="external_executor",
                    )
                with process_col2:
                    st.selectbox(
                        "Prompt-Basis für Executor",
                        options=PROMPT_BASIS_OPTIONS,
                        key="handoff_prompt_basis",
                    )
                process_col3, process_col4 = st.columns(2)
                with process_col3:
                    st.selectbox(
                        "Review übernimmt",
                        options=PROCESS_OWNER_OPTIONS,
                        key="review_owner",
                    )
                with process_col4:
                    st.selectbox(
                        "Verbesserung übernimmt",
                        options=PROCESS_OWNER_OPTIONS,
                        key="improve_owner",
                    )
                if st.session_state.get("external_executor") == "Claude Code via Ollama":
                    st.text_input(
                        "Claude Code via Ollama Modell",
                        key="claude_ollama_model",
                        help="Zum Beispiel qwen3.5, qwen3-coder, glm-4.7-flash oder ein :cloud-Modell.",
                    )
                st.caption("Schritt 1 bleibt lokal: Aufbereitung und Erstentwurf laufen weiter über dein lokales Ollama-Modell. Der externe Executor übernimmt danach optional den Arbeitsordner.")

                st.markdown("**Übergabe an VS Code / Executor**")
                handoff_col1, handoff_col2 = st.columns(2)
                with handoff_col1:
                    st.checkbox(
                        "Handoff-Datei für aktiven Run schreiben",
                        key="codex_handoff_enabled",
                        help="Schreibt nach dem Lauf eine Executor-Handoff-Datei in den Run und in den Arbeitsordner.",
                    )
                with handoff_col2:
                    st.checkbox(
                        "Arbeitsordner danach in VS Code öffnen",
                        key="open_vscode_after_run",
                        disabled=not command_exists("code"),
                        help="Öffnet den Arbeitsordner nach dem Lauf direkt in VS Code. Funktioniert nur, wenn der Befehl 'code' verfügbar ist.",
                    )
                executor_available_now = executor_available(st.session_state.get("external_executor", "Kein externer Executor"))
                executor_label = st.session_state.get("external_executor", "Kein externer Executor")
                exec_col1, exec_col2 = st.columns(2)
                with exec_col1:
                    st.checkbox(
                        f"{executor_label} nach Handoff automatisch starten",
                        key="codex_exec_after_run",
                        disabled=executor_label == "Kein externer Executor" or not executor_available_now,
                        help="Startet den gewählten externen Executor nach dem Lauf direkt im aktiven Arbeitsordner auf Basis von CODEX_HANDOFF.md.",
                    )
                with exec_col2:
                    codex_exec_btn = st.button(
                        f"Mit {executor_label} im aktiven Arbeitsordner ausführen",
                        use_container_width=True,
                        disabled=executor_label == "Kein externer Executor" or not executor_available_now,
                        help="Startet den gewählten externen Executor im aktiven Arbeitsordner und nutzt CODEX_HANDOFF.md als Grundlage.",
                    )
                st.checkbox(
                    "Projektänderungen nach erfolgreichem Executor-Lauf automatisch in den Basis-Branch übernehmen",
                    key="auto_apply_to_base_after_codex",
                    disabled=not st.session_state.get("codex_exec_after_run", False),
                    help="Commit im Arbeitsordner und Cherry-pick in den Basis-Branch. Wird nur bei Repo-Runs versucht, wenn der Hauptstand sauber ist.",
                )
                st.caption(f"Aktiver Run: {active_run_meta.get('run_id', '-')} → {get_run_target_path(active_run_meta) or '-'}")
                if not command_exists("code"):
                    st.caption("VS Code CLI 'code' wurde nicht gefunden. Handoff-Dateien werden trotzdem geschrieben.")
                if executor_label == "Codex CLI" and not codex_available():
                    st.caption("Codex CLI wurde nicht gefunden. Installiere Codex CLI und melde dich lokal an.")
                if executor_label == "Claude Code via Ollama" and not claude_via_ollama_available():
                    st.caption("Ollama CLI wurde nicht gefunden. Claude Code via Ollama benötigt einen lokalen 'ollama'-Befehl.")

            if is_advanced and ui_settings.get("show_active_prompt_files", True):
                st.subheader("Aktive Prompt-Dateien")
                if profile_config["kind"] == "pipeline":
                    st.code(
                        "\n".join([
                            f"Analyse: {profile_config['analyse'].relative_to(APP_ROOT)}",
                            f"Lösung:  {profile_config['loesung'].relative_to(APP_ROOT)}",
                            f"Code:    {profile_config['code'].relative_to(APP_ROOT)}",
                        ]),
                        language="text",
                    )
                elif profile_config["kind"] == "queue":
                    st.code(
                        "\n".join([
                            f"Plan:    {profile_config['plan'].relative_to(APP_ROOT)}",
                            f"Schritt: {profile_config['step'].relative_to(APP_ROOT)}",
                            f"Finale:  {profile_config['finalize'].relative_to(APP_ROOT)}",
                        ]),
                        language="text",
                    )
                else:
                    st.code(f"Code: {profile_config['code'].relative_to(APP_ROOT)}", language="text")

            run_btn = st.button("Automatischen Lauf starten", type="primary", use_container_width=True)

        if run_btn:
            if not user_input.strip():
                st.error("Bitte zuerst einen Prompt eingeben.")
            else:
                try:
                    with st.spinner("Ablauf wird ausgeführt..."):
                        if profile_config["kind"] == "pipeline":
                            result = run_pipeline_mode(
                                user_input=user_input.strip(),
                                host=ollama_host,
                                model=model,
                                analyse_file=profile_config["analyse"],
                                loesung_file=profile_config["loesung"],
                                code_file=profile_config["code"],
                            )
                        elif profile_config["kind"] == "queue":
                            result = run_queue_mode(
                                user_input=user_input.strip(),
                                host=ollama_host,
                                model=model,
                                plan_file=profile_config["plan"],
                                step_file=profile_config["step"],
                                finalize_file=profile_config["finalize"],
                            )
                        else:
                            result = run_oneshot_mode(
                                user_input=user_input.strip(),
                                host=ollama_host,
                                model=model,
                                code_file=profile_config["code"],
                            )
                    result["profile_key"] = profile_key
                    result["profile_label"] = profile_labels.get(profile_key, profile_key)
                    result["mode_name"] = mode_name
                    result["model"] = model
                    result["executor_config"] = {
                        "external_executor": st.session_state.get("external_executor", "Kein externer Executor"),
                        "prompt_basis": st.session_state.get("handoff_prompt_basis", "Original + Aufbereitung"),
                        "review_owner": st.session_state.get("review_owner", "Lokales Modell"),
                        "improve_owner": st.session_state.get("improve_owner", "Lokales Modell"),
                        "claude_ollama_model": st.session_state.get("claude_ollama_model", DEFAULT_CLAUDE_OLLAMA_MODEL),
                    }
                    result = apply_automated_workflow(
                        user_input=user_input.strip(),
                        host=ollama_host,
                        model=model,
                        result=result,
                        auto_review=st.session_state.get("auto_review_enabled", True) and st.session_state.get("review_owner", "Lokales Modell") == "Lokales Modell",
                        auto_improve=st.session_state.get("auto_improve_enabled", True) and st.session_state.get("improve_owner", "Lokales Modell") == "Lokales Modell",
                    )
                    active_run_id = st.session_state.get("selected_run_id")
                    if active_run_id:
                        result["run_write"] = write_run_execution_artifacts(
                            run_id=active_run_id,
                            user_input=user_input.strip(),
                            output_filename=output_filename,
                            result=result,
                        )
                        if st.session_state.get("codex_handoff_enabled", True):
                            result["codex_handoff"] = write_codex_handoff_artifacts(
                                run_id=active_run_id,
                                user_input=user_input.strip(),
                                result=result,
                                run_write=result.get("run_write"),
                            )
                            if st.session_state.get("open_vscode_after_run", False):
                                try:
                                    open_in_vscode(Path(str(result["codex_handoff"].get("worktree_path", ""))))
                                    result["codex_handoff"]["vscode_opened"] = True
                                except Exception as exc:
                                    result["codex_handoff_error"] = str(exc)
                            selected_executor = st.session_state.get("external_executor", "Kein externer Executor")
                            if st.session_state.get("codex_exec_after_run", False) and selected_executor != "Kein externer Executor":
                                try:
                                    with st.spinner(f"{selected_executor} arbeitet im aktiven Arbeitsordner..."):
                                        result["codex_exec"] = execute_selected_executor_for_run(
                                            active_run_id,
                                            selected_executor,
                                            st.session_state.get("claude_ollama_model", DEFAULT_CLAUDE_OLLAMA_MODEL),
                                        )
                                        result["codex_exec"] = refresh_codex_exec_result(active_run_id)
                                except Exception as exc:
                                    result["codex_exec_error"] = str(exc)

                            if (
                                st.session_state.get("auto_apply_to_base_after_codex", False)
                                and result.get("codex_exec", {}).get("returncode", 1) == 0
                            ):
                                try:
                                    result["codex_apply"] = apply_worktree_changes_to_base(active_run_id)
                                except Exception as exc:
                                    result["codex_apply_error"] = str(exc)

                    result["workflow_stats"] = collect_workflow_stats(result)
                    st.session_state["last_result"] = result
                    st.session_state["last_output_filename"] = output_filename
                    st.session_state["_run_refresh_notice"] = "Lauf abgeschlossen. Kennzahlen wurden aktualisiert."
                    st.rerun()
                except Exception as exc:
                    st.exception(exc)

        if codex_exec_btn:
            try:
                if not active_run_meta:
                    raise PipelineError("Kein aktiver Run ausgewählt.")
                selected_executor = st.session_state.get("external_executor", "Kein externer Executor")
                if selected_executor == "Kein externer Executor":
                    raise PipelineError("Kein externer Executor ausgewählt.")
                with st.spinner(f"{selected_executor} arbeitet im aktiven Arbeitsordner..."):
                    execute_selected_executor_for_run(
                        str(active_run_meta.get("run_id", "")),
                        selected_executor,
                        st.session_state.get("claude_ollama_model", DEFAULT_CLAUDE_OLLAMA_MODEL),
                    )
                    codex_exec_result = refresh_codex_exec_result(str(active_run_meta.get("run_id", "")))
                st.session_state["last_codex_exec"] = codex_exec_result
                existing_result = st.session_state.get("last_result")
                if isinstance(existing_result, dict):
                    run_write = existing_result.get("run_write", {}) if isinstance(existing_result.get("run_write"), dict) else {}
                    if run_write.get("run_id") == str(active_run_meta.get("run_id", "")):
                        existing_result["codex_exec"] = codex_exec_result
                        st.session_state["last_result"] = existing_result
                st.session_state["_codex_exec_notice"] = f"{selected_executor} wurde im aktiven Arbeitsordner ausgeführt."
                st.rerun()
            except Exception as exc:
                st.exception(exc)

        result = st.session_state.get("last_result")
        if run_refresh_notice:
            st.success(run_refresh_notice)
        if manual_codex_notice:
            st.success(manual_codex_notice)
        if result:
            st.divider()
            st.subheader("Ergebnis")
            if ui_settings.get("show_result_status_messages", True):
                if result.get("run_write"):
                    st.success(f"Aktiver Run aktualisiert: {result['run_write'].get('run_id', '-')}")
                if result.get("codex_handoff"):
                    st.info(f"Executor-Handoff geschrieben: {result['codex_handoff'].get('handoff_worktree_path', result['codex_handoff'].get('handoff_path', '-'))}")
                if result.get("codex_handoff_error"):
                    st.warning(f"VS Code konnte nicht automatisch geöffnet werden: {result['codex_handoff_error']}")
                if result.get("codex_exec"):
                    codex_exec = result.get("codex_exec", {})
                    if int(codex_exec.get("returncode", 1)) == 0:
                        st.success("Der externe Executor wurde im aktiven Arbeitsordner erfolgreich ausgeführt.")
                    else:
                        st.warning("Der externe Executor wurde ausgeführt, aber mit einem Fehlercode beendet.")
                if result.get("codex_exec_error"):
                    st.warning(f"Externer Executor konnte nicht ausgeführt werden: {result['codex_exec_error']}")
                if result.get("codex_apply"):
                    st.success(f"Executor-Änderungen wurden nach `{result['codex_apply'].get('target_branch', '-')}` übernommen.")
                if result.get("codex_apply_error"):
                    st.warning(f"Automatische Übernahme nicht möglich: {result['codex_apply_error']}")

                automation = result.get("automation", {})
                final_review = automation.get("final_review") or automation.get("initial_review") or {}
                if automation.get("auto_review_enabled"):
                    review_status = final_review.get("status", "-")
                    review_summary = final_review.get("summary", "-")
                    if automation.get("status") in {"pass", "improved_pass"}:
                        st.success(f"Automatische Prüfung: {review_status} – {review_summary}")
                    elif automation.get("status") in {"review_fail", "improved_fail"}:
                        st.warning(f"Automatische Prüfung: {review_status} – {review_summary}")
                    else:
                        st.info(f"Automatische Prüfung: {review_status} – {review_summary}")

            if ui_settings.get("show_result_metrics", True):
                top1, top2, top3 = st.columns(3)
                top1.metric("Modell", result.get("model", model))
                default_mode_label = "3-Stufen Pipeline" if result["mode"] == "pipeline" else ("Queue" if result["mode"] == "queue" else "One-shot")
                top2.metric("Modus", result.get("mode_name", default_mode_label))
                top3.metric("Code Länge", f"{len(result['code_response'])} Zeichen")

                workflow_stats = collect_workflow_stats(result)
                perf1, perf2, perf3 = st.columns(3)
                perf1.metric(
                    "Input-Tokens",
                    format_tokens(workflow_stats.get("input_tokens", 0)),
                )
                perf2.metric(
                    "Output-Tokens",
                    format_tokens(workflow_stats.get("output_tokens", 0)),
                )
                perf3.metric(
                    "Dauer",
                    format_duration_ns(workflow_stats.get("total_duration", 0)),
                )
            else:
                workflow_stats = collect_workflow_stats(result)

            automation = result.get("automation", {})
            if automation.get("auto_review_enabled") and ui_settings.get("show_result_auto_review", True):
                final_review = automation.get("final_review") or automation.get("initial_review") or {}
                with st.expander("Automatische Prüfung", expanded=is_advanced):
                    review_col1, review_col2 = st.columns(2)
                    with review_col1:
                        st.markdown(f"**Status:** `{final_review.get('status', '-')}`")
                        st.markdown(f"**Ablaufstatus:** `{automation.get('status', '-')}`")
                        st.markdown(f"**Zusammenfassung:** {final_review.get('summary', '-')}")
                    with review_col2:
                        issues = final_review.get("issues", [])
                        if issues:
                            st.markdown("**Punkte**")
                            for issue in issues:
                                st.markdown(f"- {issue}")
                        else:
                            st.markdown("**Punkte:** Keine automatisch erkannten Punkte.")
                    if is_advanced and ui_settings.get("show_result_prompts", True):
                        initial_review = automation.get("initial_review", {})
                        if initial_review:
                            st.markdown("**Review-Antwort**")
                            st.code(initial_review.get("raw_response", ""), language="text")
                        if automation.get("improvement"):
                            st.markdown("**Verbesserter Output**")
                            st.code(result.get("code_response", ""), language="text")
                            if automation.get("final_review", {}).get("raw_response"):
                                st.markdown("**Finale Review-Antwort**")
                                st.code(automation.get("final_review", {}).get("raw_response", ""), language="text")


            if (result.get("codex_exec") or result.get("codex_apply") or result.get("codex_handoff")) and ui_settings.get("show_result_codex_section", True):
                with st.expander("Externer Executor / Git-Übernahme", expanded=is_advanced):
                    codex_exec = result.get("codex_exec", {})
                    if codex_exec:
                        summary_left, summary_right = st.columns(2)
                        with summary_left:
                            st.markdown(f"**Executor:** `{codex_exec.get('executor', st.session_state.get('external_executor', '-'))}`")
                            st.markdown(f"**Returncode:** `{codex_exec.get('returncode', '-')}`")
                            st.markdown(f"**Ausgeführt am:** `{codex_exec.get('executed_at', codex_exec.get('finished_at', '-'))}`")
                            st.markdown(f"**Arbeitsordner:** `{codex_exec.get('worktree_path', '-')}`")
                        with summary_right:
                            project_files = codex_exec.get("project_changed_files") or codex_exec.get("changed_files", [])
                            artifact_files = codex_exec.get("artifact_changed_files", [])
                            st.markdown(f"**Relevante Projektdateien:** `{len(project_files)}`")
                            if project_files:
                                for changed_path in project_files:
                                    st.markdown(f"- `{changed_path}`")
                            else:
                                st.caption("Keine relevanten Projektdateien geändert.")
                            if artifact_files:
                                st.markdown(f"**Run-/Artefakt-Dateien:** `{len(artifact_files)}`")
                                for changed_path in artifact_files:
                                    st.markdown(f"- `{changed_path}`")

                        diff_summary = codex_exec.get("diff_summary", {})
                        diff_stat_text = codex_exec.get("diff_stat") or diff_summary.get("diff_stat", "")
                        if diff_stat_text:
                            st.markdown("**Diff-Stat**")
                            st.code(diff_stat_text, language="text")

                        last_message_path = codex_exec.get("worktree_stdout_path") or codex_exec.get("stdout_path")
                        if last_message_path:
                            try:
                                st.markdown("**Letzte Executor-Ausgabe**")
                                st.code(safe_read_preview_text(Path(str(last_message_path))), language="text")
                            except Exception:
                                pass

                    if result.get("codex_apply"):
                        st.markdown(f"**Übernommen nach:** `{result['codex_apply'].get('target_branch', '-')}`")
                        st.markdown(f"**Commit:** `{result['codex_apply'].get('commit_sha', '-')}`")
                        staged_files = result["codex_apply"].get("staged_files", [])
                        if staged_files:
                            st.markdown("**Übernommene Dateien**")
                            for staged_file in staged_files:
                                st.markdown(f"- `{staged_file}`")

                    codex_action_col1, codex_action_col2 = st.columns(2)
                    with codex_action_col1:
                        selected_executor_label = st.session_state.get("external_executor", "Kein externer Executor")
                        can_run_executor = (
                            bool(result.get("codex_handoff"))
                            and bool(st.session_state.get("selected_run_id"))
                            and executor_available(selected_executor_label)
                            and selected_executor_label != "Kein externer Executor"
                        )
                        if st.button("Ausgewählten Executor erneut ausführen", use_container_width=True, disabled=not can_run_executor):
                            try:
                                execute_selected_executor_for_run(
                                    str(st.session_state.get("selected_run_id")),
                                    selected_executor_label,
                                    st.session_state.get("claude_ollama_model", DEFAULT_CLAUDE_OLLAMA_MODEL),
                                )
                                updated_exec = refresh_codex_exec_result(str(st.session_state.get("selected_run_id")))
                                updated_result = dict(result)
                                updated_result["codex_exec"] = updated_exec
                                updated_result["workflow_stats"] = collect_workflow_stats(updated_result)
                                st.session_state["last_result"] = updated_result
                                st.session_state["_codex_exec_notice"] = "Der ausgewählte Executor wurde im aktiven Worktree erneut ausgeführt."
                                st.rerun()
                            except Exception as exc:
                                st.exception(exc)
                    with codex_action_col2:
                        can_apply_changes = bool(st.session_state.get("selected_run_id")) and bool(result.get("codex_exec")) and int(result.get("codex_exec", {}).get("returncode", 1)) == 0
                        if st.button("Relevante Projektänderungen in Basis-Branch übernehmen", use_container_width=True, disabled=not can_apply_changes):
                            try:
                                apply_result = apply_worktree_changes_to_base(str(st.session_state.get("selected_run_id")))
                                updated_result = dict(result)
                                updated_result["codex_apply"] = apply_result
                                updated_result["workflow_stats"] = collect_workflow_stats(updated_result)
                                st.session_state["last_result"] = updated_result
                                st.session_state["_codex_exec_notice"] = "Executor-Änderungen wurden in den Basis-Branch übernommen."
                                st.rerun()
                            except Exception as exc:
                                st.exception(exc)

            if result["mode"] == "pipeline":
                if is_advanced and ui_settings.get("show_result_prompts", True):
                    tab1, tab2, tab3 = st.tabs(["Code", "Analyse", "Lösung"])
                    with tab1:
                        st.markdown("**Code**")
                        st.code(result["code_response"], language="text")
                        st.markdown("**Code-Prompt**")
                        st.code(result["code_prompt"], language="text")
                    with tab2:
                        st.markdown("**Prompt**")
                        st.code(result["analyse_prompt"], language="text")
                        st.markdown("**Antwort**")
                        st.code(result["analyse_response"], language="text")
                        st.caption(f"FINAL_TASK Analyse: {result['final_task_1']}")
                    with tab3:
                        st.markdown("**Prompt**")
                        st.code(result["loesung_prompt"], language="text")
                        st.markdown("**Antwort**")
                        st.code(result["loesung_response"], language="text")
                        st.caption(f"FINAL_TASK Lösung: {result['final_task_2']}")
                else:
                    st.markdown("**Code**")
                    st.code(result["code_response"], language="text")
            elif result["mode"] == "queue":
                if is_advanced and ui_settings.get("show_result_prompts", True):
                    tab1, tab2, tab3 = st.tabs(["Code", "Queue-Plan", "Schritte"])
                    with tab1:
                        st.markdown("**Code / finales Ergebnis**")
                        st.code(result["code_response"], language="text")
                        st.markdown("**Finalisierungs-Prompt**")
                        st.code(result["code_prompt"], language="text")
                    with tab2:
                        st.markdown("**Queue-Zusammenfassung**")
                        st.code(result.get("queue_summary", "-"), language="text")
                        st.markdown("**Queue-Schritte**")
                        st.code(format_queue_steps_text(result.get("queue_steps", [])) or "-", language="text")
                        st.markdown("**Plan-Prompt**")
                        st.code(result.get("queue_plan_prompt", ""), language="text")
                        st.markdown("**Plan-Antwort**")
                        st.code(result.get("queue_plan_response", ""), language="text")
                    with tab3:
                        if result.get("queue_step_runs"):
                            for step_run in result.get("queue_step_runs", []):
                                with st.expander(f"Schritt {step_run.get('index', '-')} - {step_run.get('step', '-')}", expanded=False):
                                    st.markdown("**Prompt**")
                                    st.code(step_run.get("prompt", ""), language="text")
                                    st.markdown("**Antwort**")
                                    st.code(step_run.get("response", ""), language="text")
                        else:
                            st.info("Keine Queue-Schritte vorhanden.")
                else:
                    st.markdown("**Code / finales Ergebnis**")
                    st.code(result["code_response"], language="text")
            else:
                if is_advanced and ui_settings.get("show_result_prompts", True):
                    tab1, tab2 = st.tabs(["Code", "Prompt"])
                    with tab1:
                        st.code(result["code_response"], language="text")
                    with tab2:
                        st.code(result["code_prompt"], language="text")
                else:
                    st.code(result["code_response"], language="text")

            if result.get("codex_exec") and ui_settings.get("show_result_codex_section", True):
                codex_exec = result.get("codex_exec", {})
                with st.expander("Executor-Ergebnis", expanded=False):
                    codex_info_col1, codex_info_col2 = st.columns(2)
                    with codex_info_col1:
                        st.markdown(f"**Returncode:** `{codex_exec.get('returncode', '-')}`")
                        st.markdown(f"**Ausgeführt am:** `{codex_exec.get('executed_at', '-')}`")
                        st.markdown(f"**Arbeitsordner:** `{codex_exec.get('worktree_path', '-')}`")
                    with codex_info_col2:
                        st.markdown(f"**Handoff:** `{codex_exec.get('handoff_path', '-')}`")
                        st.markdown(f"**Result-Datei:** `{codex_exec.get('result_path', '-')}`")
                    st.markdown("**Letzte Executor-Nachricht (stdout)**")
                    st.code(codex_exec.get("stdout", ""), language="text")
                    if codex_exec.get("stderr"):
                        st.markdown("**Executor stderr**")
                        st.code(codex_exec.get("stderr", ""), language="text")

            if ui_settings.get("show_result_action_buttons", True):
                save_col, open_col, download_col, vscode_col, handoff_col = st.columns(5)
                with save_col:
                    if st.button("Output nach workspace/output speichern", use_container_width=True):
                        out_path = save_output_file(
                            result["code_response"],
                            st.session_state.get("last_output_filename", normalize_output_filename(st.session_state.get("output_base_name", "generated_code"), st.session_state.get("output_extension", ".py"))),
                        )
                        st.success(f"Gespeichert: {out_path}")
                with open_col:
                    if st.button("Output Ordner öffnen", use_container_width=True):
                        try:
                            open_folder_in_explorer(OUTPUT_ROOT)
                        except Exception as exc:
                            st.exception(exc)
                with download_col:
                    st.download_button(
                        "Code herunterladen",
                        data=result["code_response"],
                        file_name=st.session_state.get("last_output_filename", normalize_output_filename(st.session_state.get("output_base_name", "generated_code"), st.session_state.get("output_extension", ".py"))),
                        mime="text/plain",
                        use_container_width=True,
                    )
                with vscode_col:
                    if st.button("Run in VS Code öffnen", use_container_width=True, disabled=not bool(result.get("codex_handoff"))):
                        try:
                            if result.get("codex_handoff"):
                                open_in_vscode(Path(str(result["codex_handoff"].get("worktree_path", ""))))
                        except Exception as exc:
                            st.exception(exc)
                with handoff_col:
                    if st.button("Handoff Ordner öffnen", use_container_width=True, disabled=not bool(result.get("codex_handoff"))):
                        try:
                            if result.get("codex_handoff"):
                                open_folder_in_explorer(Path(str(result["codex_handoff"].get("handoff_path", ""))).parent)
                        except Exception as exc:
                            st.exception(exc)
    if "runs" in tabs_by_key:
        with tabs_by_key["runs"]:
            st.subheader("Runs")
            repo_root = find_git_repo_root(APP_ROOT)
            if repo_root:
                st.caption(f"Git-Repo: {repo_root}")
            else:
                st.caption("Kein Git-Repo erkannt. Scratch-Runs sind trotzdem möglich.")

            with st.expander("Neuen Run anlegen", expanded=True):
                run_type_input = st.radio("Run-Typ", options=["Repo-Run", "Scratch-Run"], horizontal=True, key="run_type_input")
                run_create_col1, run_create_col2 = st.columns([1.8, 1.0])
                with run_create_col1:
                    run_name_input = st.text_input("Run-Name", placeholder="z. B. csv-dedupe", key="run_name_input")
                with run_create_col2:
                    if run_type_input == "Repo-Run":
                        default_branch_value = git_default_branch(repo_root) if repo_root else "main"
                        run_base_branch = st.text_input("Basis-Ref", value=default_branch_value, key="run_base_branch")
                        if repo_root:
                            st.caption(f"Erkannter Standard-Branch: {git_default_branch(repo_root)}")
                            st.caption("Erlaubt sind z. B. main, origin/main, refs/heads/main oder HEAD.")
                        else:
                            st.warning("Repo-Runs benötigen ein Git-Repository.")
                    else:
                        run_base_branch = ""
                        st.caption(f"Scratch-Ziel: {PROJECTS_ROOT}")
                        st.caption("Erstellt einen eigenständigen Projektordner ohne Git-Worktree.")
                if st.button("Run anlegen", use_container_width=True, type="primary"):
                    if not run_name_input.strip():
                        st.error("Bitte zuerst einen Run-Namen eingeben.")
                    else:
                        try:
                            if run_type_input == "Repo-Run":
                                if not repo_root:
                                    raise PipelineError("Repo-Run nicht möglich: kein Git-Repository erkannt.")
                                meta = create_worktree_run(run_name_input.strip(), run_base_branch.strip() or git_default_branch(repo_root) or "HEAD")
                            else:
                                meta = create_scratch_run(run_name_input.strip())
                            st.session_state["selected_run_id"] = meta["run_id"]
                            st.success(f"Run erstellt: {meta['run_id']}")
                            st.rerun()
                        except Exception as exc:
                            st.exception(exc)

            runs = list_worktree_runs()
            total_runs, active_runs, missing_runs = run_summary_counts(runs)
            c1, c2, c3 = st.columns(3)
            c1.metric("Runs gesamt", str(total_runs))
            c2.metric("Arbeitsordner vorhanden", str(active_runs))
            c3.metric("Fehlend", str(missing_runs))

            if runs:
                run_options = [run["run_id"] for run in runs]
                current_run_id = st.session_state.get("selected_run_id")
                if current_run_id not in run_options:
                    current_run_id = run_options[0]
                selected_run_id = st.selectbox(
                    "Run auswählen",
                    options=run_options,
                    index=run_options.index(current_run_id),
                    format_func=lambda run_id: format_run_option_label(get_worktree_run(run_id) or {"run_id": run_id}),
                )
                st.session_state["selected_run_id"] = selected_run_id
                selected_run = get_worktree_run(selected_run_id)

                if selected_run:
                    info_left, info_right = st.columns(2)
                    with info_left:
                        st.markdown(f"**Run-ID:** `{selected_run.get('run_id', '-')}`")
                        st.markdown(f"**Name:** `{selected_run.get('name', '-')}`")
                        st.markdown(f"**Branch:** `{selected_run.get('branch', '-')}`")
                        st.markdown(f"**Status:** `{selected_run.get('status', '-')}`")
                    with info_right:
                        st.markdown(f"**Erstellt:** `{selected_run.get('created_at', '-')}`")
                        st.markdown(f"**Run-Typ:** `{selected_run.get('run_type', 'repo')}`")
                        st.markdown(f"**Basis-Branch:** `{selected_run.get('base_branch', '-') or '-'}`")
                        st.markdown(f"**{get_run_target_label(selected_run)}:** `{get_run_target_path(selected_run) or '-'}`")
                        st.markdown(f"**Meta:** `{selected_run.get('meta_path', '-')}`")

                    action_col1, action_col2, action_col3, action_col4 = st.columns(4)
                    with action_col1:
                        if st.button(f"{get_run_target_label(selected_run)} öffnen", use_container_width=True):
                            try:
                                open_folder_in_explorer(get_run_target_path(selected_run))
                            except Exception as exc:
                                st.exception(exc)
                    with action_col2:
                        if st.button("In VS Code öffnen", use_container_width=True, disabled=not command_exists("code")):
                            try:
                                open_in_vscode(get_run_target_path(selected_run))
                            except Exception as exc:
                                st.exception(exc)
                    with action_col3:
                        if st.button("Run-Meta öffnen", use_container_width=True):
                            try:
                                open_folder_in_explorer(Path(str(selected_run.get("meta_path", ""))))
                            except Exception as exc:
                                st.exception(exc)
                    with action_col4:
                        confirm_delete_run = st.checkbox("Run löschen bestätigen", key=f"confirm_delete_run_{selected_run_id}")
                        if st.button("Run löschen", use_container_width=True, disabled=not confirm_delete_run):
                            try:
                                remove_worktree_run(selected_run_id)
                                st.session_state.pop("selected_run_id", None)
                                st.success(f"Run gelöscht: {selected_run_id}")
                                st.rerun()
                            except Exception as exc:
                                st.exception(exc)

                    if ui_settings.get("show_run_preview_files", True):
                        preview_tabs = st.tabs(["task.md", "review.md", "result.json", "meta.json"])
                        preview_mapping = {
                            "task.md": Path(str(selected_run.get("task_path", ""))),
                            "review.md": Path(str(selected_run.get("review_path", ""))),
                            "result.json": Path(str(selected_run.get("result_path", ""))),
                            "meta.json": RUNS_ROOT / selected_run_id / "meta.json",
                        }
                        for preview_tab, file_name in zip(preview_tabs, preview_mapping.keys()):
                            with preview_tab:
                                preview_file = preview_mapping[file_name]
                                if preview_file.exists() and preview_file.is_file():
                                    try:
                                        st.code(safe_read_preview_text(preview_file), language=file_language(preview_file))
                                    except Exception as exc:
                                        st.error(f"Datei konnte nicht gelesen werden: {preview_file}")
                                        st.exception(exc)
                                elif preview_file.exists():
                                    st.warning(f"Pfad ist keine Datei: {preview_file}")
                                else:
                                    st.info("Datei nicht vorhanden.")
                else:
                    st.info("Noch keine Runs vorhanden.")

    if "profiles" in tabs_by_key:
        with tabs_by_key["profiles"]:
            st.subheader("Profile")

            manage_col, delete_col = st.columns(2)

            with manage_col:
                with st.expander("Profile verwalten", expanded=True):
                    st.markdown("**Neues Profil erstellen**")
                    create_col1, create_col2 = st.columns([1.4, 1.1])
                    with create_col1:
                        new_profile_label = st.text_input("Profilname", placeholder="z. B. Code Explain")
                    existing_profile_keys = sorted(profile_labels.keys(), key=lambda key: profile_labels.get(key, key).lower())
                    template_options = ["Standard-Vorlage"] + existing_profile_keys
                    with create_col2:
                        template_choice = st.selectbox(
                            "Vorlage",
                            options=template_options,
                            format_func=lambda value: value if value == "Standard-Vorlage" else profile_labels.get(value, value),
                        )
                    preview_key = slugify_profile_key(new_profile_label) if new_profile_label.strip() else ""
                    if preview_key:
                        st.caption(f"Technischer Profilname: {preview_key}")
                    if st.button("Profil erstellen", use_container_width=True):
                        if not new_profile_label.strip():
                            st.error("Bitte zuerst einen Profilnamen eingeben.")
                        else:
                            try:
                                source_profile_key = None if template_choice == "Standard-Vorlage" else template_choice
                                created_root = create_profile_structure(preview_key, new_profile_label.strip(), source_profile_key)
                                updated_settings = dict(st.session_state["ui_settings"])
                                visible_profiles = list(updated_settings.get("visible_profiles", []))
                                if preview_key not in visible_profiles:
                                    visible_profiles.append(preview_key)
                                updated_settings["visible_profiles"] = visible_profiles
                                st.session_state["ui_settings"] = updated_settings
                                save_ui_settings(updated_settings)
                                st.session_state["selected_profile_key"] = preview_key
                                st.success(f"Profil erstellt: {created_root.name}")
                                st.rerun()
                            except Exception as exc:
                                st.exception(exc)

                    st.caption("Nach dem Anlegen kannst du die Prompt-Dateien im Tab Dateien direkt bearbeiten oder neue .txt-Dateien im Profilordner erstellen.")

            with delete_col:
                with st.expander("Profile löschen", expanded=True):
                    deletable_profile_keys = [key for key in sorted(profile_labels.keys(), key=lambda key: profile_labels.get(key, key).lower()) if key not in PROTECTED_PROFILE_KEYS]
                    if deletable_profile_keys:
                        delete_profile_key = st.selectbox(
                            "Profil",
                            options=deletable_profile_keys,
                            format_func=lambda key: profile_labels.get(key, key),
                            key="delete_profile_key",
                        )
                        st.caption(f"Technischer Name: {delete_profile_key}")
                        st.caption(f"Ordner: {PROFILES_ROOT / delete_profile_key}")
                        st.warning("Beim Löschen wird der gesamte Profilordner entfernt.")
                        confirm_delete_profile = st.checkbox(
                            "Profilordner wirklich löschen",
                            key="confirm_delete_profile",
                        )
                        if st.button("Profil löschen", use_container_width=True, disabled=not confirm_delete_profile):
                            try:
                                delete_profile_structure(delete_profile_key)
                                updated_profile_labels = load_profile_labels()
                                updated_settings = dict(st.session_state["ui_settings"])
                                available_after_delete = set(updated_profile_labels.keys())
                                visible_profiles = [key for key in updated_settings.get("visible_profiles", []) if key in available_after_delete]
                                if not visible_profiles:
                                    visible_profiles = get_default_visible_profiles(available_after_delete)
                                updated_settings["visible_profiles"] = visible_profiles
                                st.session_state["ui_settings"] = updated_settings
                                save_ui_settings(updated_settings)

                                current_selected = st.session_state.get("selected_profile_key", "code_generate")
                                if current_selected == delete_profile_key or current_selected not in available_after_delete:
                                    fallback_key = "code_generate" if "code_generate" in available_after_delete else sorted(available_after_delete)[0]
                                    st.session_state["selected_profile_key"] = fallback_key

                                st.success(f"Profil gelöscht: {delete_profile_key}")
                                st.rerun()
                            except Exception as exc:
                                st.exception(exc)
                    else:
                        st.info("Es sind nur Standardprofile vorhanden. Diese werden hier nicht gelöscht.")

            st.markdown("**Vorhandene Profile**")
            existing_rows: list[str] = []
            for existing_key in sorted(profile_labels.keys(), key=lambda key: profile_labels.get(key, key).lower()):
                protection_note = " (Standardprofil)" if existing_key in PROTECTED_PROFILE_KEYS else ""
                existing_rows.append(
                    f"- **{profile_labels.get(existing_key, existing_key)}**{protection_note}  \n"
                    f"  Technischer Name: `{existing_key}`  \n"
                    f"  Ordner: `{PROFILES_ROOT / existing_key}`"
                )
            if existing_rows:
                st.markdown("\n\n".join(existing_rows))
            else:
                st.info("Keine Profile gefunden.")

    if "files" in tabs_by_key:
        with tabs_by_key["files"]:
            st.subheader("Dateibrowser")

            roots = {
                "Prompt-Profile": PROFILES_ROOT,
                "Skripte": SCRIPTS_ROOT,
                "Workspace": WORKSPACE_ROOT,
                "Gesamter GUI-Ordner": APP_ROOT,
            }
            root_name = st.selectbox("Bereich", options=list(roots.keys()))
            current_root = roots[root_name]
            filter_text = st.text_input("Filter", placeholder="z. B. debug, prompt, ps1")

            with st.expander("Neue Textdatei erstellen", expanded=False):
                directory_paths = [current_root] + [p for p in sorted(current_root.rglob("*"), key=lambda p: str(p).lower()) if p.is_dir()]
                directory_options = ["." if path == current_root else str(path.relative_to(current_root)) for path in directory_paths]
                create_dir = st.selectbox("Zielordner", options=directory_options, key=f"new_file_dir_{root_name}")
                new_file_col1, new_file_col2 = st.columns([3, 1])
                with new_file_col1:
                    new_file_name = st.text_input("Dateiname", placeholder="z. B. neues_prompt", key=f"new_file_name_{root_name}")
                with new_file_col2:
                    new_file_ext_mode = st.selectbox(
                        "Endungsart",
                        options=["Vorgabe", "Eigene..."],
                        key=f"new_file_ext_mode_{root_name}",
                    )

                if new_file_ext_mode == "Vorgabe":
                    new_file_ext = st.selectbox(
                        "Endung",
                        options=sorted(TEXT_EXTENSIONS),
                        index=sorted(TEXT_EXTENSIONS).index(".txt") if ".txt" in TEXT_EXTENSIONS else 0,
                        key=f"new_file_ext_{root_name}",
                    )
                else:
                    custom_new_file_ext = st.text_input(
                        "Eigene Endung",
                        key=f"new_file_ext_custom_{root_name}",
                        placeholder="z. B. .cfg oder cfg",
                    )
                    new_file_ext = normalize_extension(custom_new_file_ext, default=".txt")

                new_file_content = st.text_area("Startinhalt", height=180, key=f"new_file_content_{root_name}")
                if st.button("Textdatei erstellen", use_container_width=True, key=f"create_text_file_{root_name}"):
                    if not new_file_name.strip():
                        st.error("Bitte einen Dateinamen eingeben.")
                    else:
                        target_dir = current_root if create_dir == "." else current_root / create_dir
                        target_file = target_dir / f"{Path(new_file_name.strip()).stem}{normalize_extension(new_file_ext, default='.txt')}"
                        if target_file.exists():
                            st.error(f"Datei existiert bereits: {target_file.name}")
                        else:
                            try:
                                write_text_file(target_file, new_file_content)
                                st.success(f"Datei erstellt: {target_file.relative_to(current_root)}")
                                st.rerun()
                            except Exception as exc:
                                st.exception(exc)

            browse_files = list_files(current_root, TEXT_EXTENSIONS)
            if filter_text.strip():
                browse_files = [p for p in browse_files if filter_text.lower() in str(p).lower()]

            if browse_files:
                selected_relative = st.selectbox("Datei", options=path_options(browse_files, current_root))
                selected_file = current_root / selected_relative
                st.caption(f"Pfad: {selected_file}")
                content = read_text_file(str(selected_file))
                edited_content = st.text_area("Inhalt", value=content, height=520)
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Datei speichern", use_container_width=True):
                        write_text_file(selected_file, edited_content)
                        if current_root == PROFILES_ROOT and selected_file.parts:
                            try:
                                profile_index = selected_file.parts.index("profiles") + 1
                                ensure_profile_label(selected_file.parts[profile_index])
                            except Exception:
                                pass
                        st.success("Datei gespeichert.")
                with c2:
                    st.download_button(
                        "Datei herunterladen",
                        data=edited_content,
                        file_name=selected_file.name,
                        mime="text/plain",
                        use_container_width=True,
                    )
            else:
                st.info("Keine passenden Dateien gefunden.")

    if "scripts" in tabs_by_key:
        with tabs_by_key["scripts"]:
            st.subheader("Skripte ausführen")
            script_files = list_files(SCRIPTS_ROOT, SCRIPT_EXTENSIONS)
            if script_files:
                selected_script_rel = st.selectbox("Skript", options=path_options(script_files, SCRIPTS_ROOT))
                selected_script = SCRIPTS_ROOT / selected_script_rel
                st.caption(f"Pfad: {selected_script}")
                st.code(read_text_file(str(selected_script)), language=file_language(selected_script))
        
                if st.button("Skript starten", type="primary", use_container_width=True):
                    try:
                        with st.spinner("Skript wird ausgeführt..."):
                            process = run_script(selected_script)
                        st.markdown("**Exit Code**")
                        st.code(str(process.returncode), language="text")
                        st.markdown("**STDOUT**")
                        st.code(process.stdout or "", language="text")
                        st.markdown("**STDERR**")
                        st.code(process.stderr or "", language="text")
                    except Exception as exc:
                        st.exception(exc)
            else:
                st.info("Keine Skripte im scripts-Ordner gefunden.")
