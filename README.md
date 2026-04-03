# Ollama-GUI

Lokale Streamlit-Oberfläche für Ollama mit Profilen, Modi, Dateibrowser, Profilverwaltung und Skript-Ausführung.

Das Projekt ist darauf ausgelegt, Prompts nicht nur direkt an ein Modell zu schicken, sondern sie abhängig vom gewählten **Profil** und **Modus** gezielt zu verarbeiten. Der Schwerpunkt liegt aktuell auf einer lokal laufenden GUI für **Code**, **Debugging**, **Refactoring** und frei definierbare eigene Profile.

---

## Zweck

Die GUI soll drei Dinge sauber zusammenbringen:

1. **lokale Modellnutzung über Ollama**
2. **steuerbare Prompt-Profile und Verarbeitungsmodi**
3. **praktische Arbeitsoberfläche** zum Erzeugen, Prüfen, Speichern und Verwalten von Dateien

Damit lässt sich dieselbe Oberfläche sowohl für einfache One-shot-Anfragen als auch für mehrstufige Prompt-Pipelines nutzen.

---

## Funktionen

### Modellnutzung
- lokale Nutzung von Ollama über `http://localhost:11434`
- verfügbare Modelle direkt aus Ollama laden
- Modell vorab im Hintergrund laden
- Modellliste aktualisieren
- Keep-Alive-Auswahl über Dropdown

### Profile
- Standardprofile:
  - `Code erzeugen`
  - `Code debuggen`
  - `Code refactoren`
- eigene Profile über die Oberfläche anlegen
- eigene Profile löschen
- Profilnamen getrennt von technischen Ordnernamen verwalten
- Profile können unterschiedliche Prompt-Sets je Modus besitzen

### Modi
- **3-Stufen Pipeline**
  - Analyse → Präzisierung → Ergebnis
- **One-shot**
  - direkte Verarbeitung in einem Schritt
- **Step by Step Force**
  - mehrstufige, stärker geführte Verarbeitung

### Oberfläche
- **Standard-Modus** für reduzierten Ablauf
- **Erweiterter Modus** für Verwaltung, Dateien und Diagnose
- Ergebnisbereich mit Modell, Modus, Tokenzahlen und Dauer
- Output direkt speichern, herunterladen oder Output-Ordner öffnen

### Dateien und Skripte
- Dateibrowser für Prompt-Dateien, Workspace und Skripte
- neue Dateien direkt in der GUI erstellen
- auswählbare **oder frei eingebbare** Dateiendungen
- Skripte direkt aus der GUI starten

---

## Voraussetzungen

- **Python 3.11+**
- **Ollama** lokal installiert
- mindestens ein lokal verfügbares Modell, zum Beispiel:
  - `llama3.2`
  - `qwen2.5-coder:14b`

Beispiel:

```bash
ollama pull qwen2.5-coder:14b
```

---

## Installation

### 1. Repository klonen

```bash
git clone https://github.com/Pascal-64/Ollama-GUI.git
cd Ollama-GUI
```

### 2. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 3. GUI starten

```bash
streamlit run app.py
```

Alternativ unter Windows über eine vorhandene Startdatei wie `start_gui.bat`, falls sie im Projekt enthalten ist.

---

## Typischer Ablauf

1. Ollama starten oder über die GUI prüfen, ob die API erreichbar ist.
2. Modell auswählen.
3. Profil wählen.
4. Modus wählen.
5. Prompt eingeben.
6. Ergebnis erzeugen.
7. Output speichern, herunterladen oder im Output-Ordner öffnen.

---

## Projektstruktur

Eine typische Struktur sieht so aus:

```text
Ollama-GUI/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ .streamlit/
├─ config/
│  ├─ ui_settings.json
│  └─ profile_labels.json
├─ prompts/
│  └─ profiles/
│     ├─ code_generate/
│     │  ├─ pipeline/
│     │  ├─ oneshot/
│     │  └─ step_by_step_force/
│     ├─ code_debug/
│     │  ├─ pipeline/
│     │  ├─ oneshot/
│     │  └─ step_by_step_force/
│     ├─ code_refactor/
│     │  ├─ pipeline/
│     │  ├─ oneshot/
│     │  └─ step_by_step_force/
│     └─ <eigene_profile>/
├─ scripts/
├─ workspace/
│  ├─ input/
│  ├─ output/
│  └─ temp/
└─ logs/
```

---

## Wie Profile funktionieren

Ein Profil ist technisch ein eigener Ordner unter:

```text
prompts/profiles/<profilname>/
```

Darin liegen die Prompt-Dateien für die unterstützten Modi.

Beispiel:

```text
prompts/profiles/code_generate/
├─ pipeline/
│  ├─ 01_analyse.txt
│  ├─ 02_loesung.txt
│  └─ 03_code.txt
├─ oneshot/
│  └─ 01_code_only.txt
└─ step_by_step_force/
   ├─ 01_analyse.txt
   ├─ 02_loesung.txt
   └─ 03_code.txt
```

Eigene Profile können über die Oberfläche erstellt und anschließend direkt im Dateibrowser bearbeitet werden.

---

## Hinweise zu Dateiendungen

An zwei Stellen können Dateien gespeichert oder erzeugt werden:

1. **Output-Datei im Code-Tab**
2. **Neue Datei im Dateien-Tab**

Beide Bereiche unterstützen:
- feste Endungen per Dropdown
- eigene freie Endungen per Eingabe

Beispiele:
- `test` + `.py` → `test.py`
- `config` + `ini` → `config.ini`
- `prompt` + `.myext` → `prompt.myext`

---

## Hinweise zu GitHub

Das Projekt kann direkt mit **GitHub Desktop** verwaltet werden. Für lokale Entwicklung ist das völlig ausreichend.

Sinnvoll ist dabei:
- Quellcode, Prompt-Dateien und Konfiguration versionieren
- Laufzeitdaten und Output-Dateien per `.gitignore` ausschließen

Typisch nicht committen:
- `__pycache__/`
- `.venv/`
- `logs/`
- `workspace/output/`
- `workspace/temp/`

---

## Nächste sinnvolle Ausbaustufen

- profilabhängige Button-Texte wie „Code erzeugen“ oder „Erklärung erzeugen“
- Import/Export für Profile
- bessere Vorschau für Ergebnis-Dateitypen
- klarere Trennung zwischen Code-, Erklär- und Analyse-Profilen
- optionale Vorlagen für neue Profile

---

## Status

Das Projekt ist funktional, aber weiterhin im Ausbau. Die Oberfläche und die Prompt-Profile werden iterativ erweitert.
