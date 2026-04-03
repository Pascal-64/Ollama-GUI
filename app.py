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
    "One-shot": {"kind": "oneshot", "subdir": "oneshot"},
}
DEFAULT_UI_SETTINGS = {
    "ui_mode": "standard",
    "visible_profiles": ["code_generate", "code_debug", "code_refactor"],
    "show_project_structure": True,
    "show_active_prompt_files": True,
    "show_active_run": True,
    "show_result_prompts": True,
    "show_files_tab": True,
    "show_scripts_tab": True,
}


KEEP_ALIVE_OPTIONS = ["30m", "1h", "2h", "8h", "12h", "24h"]

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
    for path in [PROMPTS_ROOT, PROFILES_ROOT, SCRIPTS_ROOT, WORKSPACE_ROOT, OUTPUT_ROOT, LOGS_ROOT, CONFIG_ROOT]:
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


def open_folder_in_explorer(path: Path) -> None:
    target = str(path.resolve())
    if sys.platform.startswith("win"):
        os.startfile(target)
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
    else:
        metas = [result.get("code_meta", {})]

    return {
        "input_tokens": sum(metric_value(meta, "prompt_eval_count") for meta in metas),
        "output_tokens": sum(metric_value(meta, "eval_count") for meta in metas),
        "total_duration": sum(metric_value(meta, "total_duration") for meta in metas),
        "steps": len(metas),
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


ensure_structure()
profile_labels = bootstrap_profiles()

if "ui_settings" not in st.session_state:
    st.session_state["ui_settings"] = load_ui_settings()

st.session_state.setdefault("output_base_name", "generated_code")
st.session_state.setdefault("output_extension", ".py")
st.session_state.setdefault("output_extension_mode", "Vorgabe")
st.session_state.setdefault("output_extension_custom", "")
st.session_state.setdefault("keep_alive_value", "30m")

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

                stats = collect_run_stats(st.session_state.get("last_result"))
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
                else:
                    st.code(f"Code: {profile_config['code'].relative_to(APP_ROOT)}", language="text")

            run_btn = st.button("Code erzeugen", type="primary", use_container_width=True)

        if run_btn:
            if not user_input.strip():
                st.error("Bitte zuerst einen Prompt eingeben.")
            else:
                try:
                    with st.spinner("Code wird erzeugt..."):
                        if profile_config["kind"] == "pipeline":
                            result = run_pipeline_mode(
                                user_input=user_input.strip(),
                                host=ollama_host,
                                model=model,
                                analyse_file=profile_config["analyse"],
                                loesung_file=profile_config["loesung"],
                                code_file=profile_config["code"],
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
                    st.session_state["last_result"] = result
                    st.session_state["last_output_filename"] = output_filename
                except Exception as exc:
                    st.exception(exc)

        result = st.session_state.get("last_result")
        if result:
            st.divider()
            st.subheader("Ergebnis")

            top1, top2, top3 = st.columns(3)
            top1.metric("Modell", result.get("model", model))
            top2.metric("Modus", result.get("mode_name", "3-Stufen Pipeline" if result["mode"] == "pipeline" else "One-shot"))
            top3.metric("Code Länge", f"{len(result['code_response'])} Zeichen")

            perf1, perf2, perf3 = st.columns(3)
            perf1.metric(
                "Input-Tokens",
                format_tokens(metric_value(result["code_meta"], "prompt_eval_count")),
            )
            perf2.metric(
                "Output-Tokens",
                format_tokens(metric_value(result["code_meta"], "eval_count")),
            )
            perf3.metric(
                "Dauer",
                format_duration_ns(metric_value(result["code_meta"], "total_duration")),
            )

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
            else:
                if is_advanced and ui_settings.get("show_result_prompts", True):
                    tab1, tab2 = st.tabs(["Code", "Prompt"])
                    with tab1:
                        st.code(result["code_response"], language="text")
                    with tab2:
                        st.code(result["code_prompt"], language="text")
                else:
                    st.code(result["code_response"], language="text")

            save_col, open_col, download_col = st.columns(3)
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