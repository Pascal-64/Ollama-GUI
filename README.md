# Ollama GUI

Lokale Streamlit-Oberfläche für Ollama mit Profilen, verschiedenen Modi, Dateiübersicht und Skript-Ausführung.

## Zweck

Das Projekt bündelt mehrere lokale Arbeitsabläufe in einer Oberfläche:

- Eingaben an ein lokal laufendes Ollama-Modell schicken
- unterschiedliche **Profile** verwenden, zum Beispiel:
  - Code erzeugen
  - Code debuggen
  - Code refactoren
  - Erklären
- verschiedene **Modi** verwenden, zum Beispiel:
  - 3-Stufen Pipeline
  - One-shot
  - Step by Step Force
- Prompt-Dateien direkt im Projekt verwalten
- Ausgaben lokal speichern
- Skripte direkt aus der Oberfläche starten

Die App ist für lokale Nutzung gedacht und arbeitet gegen einen Ollama-Host, standardmäßig `http://localhost:11434`.

---

## Voraussetzungen

Installiert sein sollten:

- Python 3.10 oder neuer
- [Ollama](https://ollama.com/)
- mindestens ein lokal verfügbares Modell, zum Beispiel:
  - `llama3.2`
  - `qwen2.5-coder:7b`
  - `qwen2.5-coder:14b`

---

## Projektstruktur

Beispielhafte Struktur:

```text
ollama-gui/
├─ app.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ .streamlit/
│  └─ config.toml
├─ config/
│  ├─ ui_settings.json
│  └─ profile_labels.json
├─ prompts/
│  └─ profiles/
│     ├─ code_generate/
│     ├─ code_debug/
│     ├─ code_refactor/
│     └─ erklaere/
├─ scripts/
│  ├─ powershell/
│  └─ python/
├─ workspace/
│  ├─ input/
│  ├─ output/
│  └─ temp/
└─ logs/
```

Wichtig:

- `prompts/profiles/` enthält die Profile und ihre Prompt-Dateien
- `workspace/output/` enthält gespeicherte Ergebnisse
- `logs/` enthält Laufzeit- oder Diagnoseausgaben
- `config/` enthält UI- und Profilkonfiguration

---

## Installation

### 1. Repository klonen

```bash
git clone https://github.com/DEINNAME/DEIN-REPO.git
cd DEIN-REPO
```

### 2. Virtuelle Umgebung anlegen

**Windows PowerShell**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows CMD**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 4. Ollama starten

Falls Ollama noch nicht läuft:

```bash
ollama serve
```

### 5. Modell herunterladen

Beispiel:

```bash
ollama pull llama3.2
```

oder

```bash
ollama pull qwen2.5-coder:14b
```

### 6. GUI starten

```bash
python -m streamlit run app.py
```

---

## Nutzung

## Modelle

Die GUI arbeitet mit lokal verfügbaren Ollama-Modellen. In der Oberfläche kannst du das Zielmodell auswählen, sofern die API erreichbar ist.

Typischer Ablauf:

1. Ollama läuft lokal
2. Modell in der GUI auswählen
3. Profil auswählen
4. Modus auswählen
5. Eingabe formulieren
6. Ergebnis erzeugen
7. Output speichern oder herunterladen

## Profile

Ein Profil bestimmt, **welche Prompt-Dateien** verwendet werden.

Typische Profile:

- **Code erzeugen**
- **Code debuggen**
- **Code refactoren**
- **Erkläre**

Eigene Profile können zusätzlich angelegt werden.

## Modi

### 3-Stufen Pipeline
Die Eingabe wird in mehreren Schritten verarbeitet, zum Beispiel:
1. Analyse
2. Präzisierung / Zwischenaufgabe
3. finale Antwort

Gut für unklare oder knappe Eingaben.

### One-shot
Die Eingabe wird direkt an ein einzelnes Prompt gegeben.

Schneller, aber weniger robust bei unklaren Anforderungen.

### Step by Step Force
Erzwingt einen schrittweisen Aufbau der Antwort über mehrere Stufen.

Sinnvoll, wenn die Antwort systematischer und nachvollziehbarer aufgebaut werden soll.

---

## Profile und Prompt-Dateien

Jedes Profil hat pro Modus einen eigenen Ordner.

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

Für ein Erklär-Profil können die Dateinamen gleich bleiben, auch wenn der Inhalt nicht auf Code, sondern auf Erklärung ausgerichtet ist. Entscheidend ist die vom Code erwartete Dateistruktur.

---

## Git-Strategie

Versioniert werden sollten:

- `app.py`
- `requirements.txt`
- `.streamlit/config.toml`
- `prompts/`
- `scripts/`
- `config/` soweit keine sensiblen Daten enthalten sind
- `README.md`
- `.gitignore`

Nicht versioniert werden sollten:

- virtuelle Umgebungen
- Logs
- generierte Outputs
- temporäre Dateien
- lokale Secrets

Die `.gitignore` in diesem Repository ist dafür bereits vorbereitet.

---

## Hinweise

- Die App ist auf lokale Nutzung ausgelegt.
- Der Ollama-Host ist standardmäßig `http://localhost:11434`.
- Wenn die Modellliste leer ist, läuft Ollama meist nicht oder die API ist nicht erreichbar.
- Wenn ein neues Modell mit `ollama pull ...` geladen wurde, sollte die Modellliste in der GUI aktualisiert werden.
- Bei eigenen Profilen muss die erwartete Prompt-Dateistruktur vollständig vorhanden sein.

---

## Nächste sinnvolle Ausbaustufen

- bessere Anzeige von Fehlermeldungen
- Import/Export von Profilen
- Vorlagen für neue Profile
- profilabhängige Standard-Dateiendungen
- Trennung zwischen Code-Profilen und Wissens-/Erklär-Profilen
