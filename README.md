# Ollama GUI

Lokale Streamlit-Oberfläche für Ollama mit Profilen, Modi, Runs und optionaler Executor-Übergabe für strukturierte Prompt-Verarbeitung.

## Überblick

Die GUI verarbeitet Eingaben nicht nur direkt in einem Schritt, sondern abhängig von **Profil** und **Modus** gezielt weiter. Der Fokus liegt auf lokaler Nutzung für:

- Code erzeugen
- Code debuggen
- Code refactoren
- eigene Profile und Prompt-Sets

Zusätzlich können Ergebnisse in **Runs** organisiert und bei Bedarf an externe Executor wie **Codex CLI** oder **Claude Code via Ollama** übergeben werden.

## Kernfunktionen

- lokale Modellnutzung über Ollama
- Modellliste laden und aktualisieren
- Modell im Hintergrund vorladen
- Keep-Alive-Auswahl
- Standardprofile und frei anlegbare eigene Profile
- Standard- und erweiterter UI-Modus
- Dateibrowser und Skript-Ausführung in der GUI
- automatische Prüfung und einmalige Verbesserung des Ergebnisses
- Runs mit Meta-Dateien und Arbeitsordnern
- optionales Executor-Handoff für Codex CLI oder Claude Code via Ollama

## Modi

- **3-Stufen Pipeline**  
  Analyse → Präzisierung → Ergebnis

- **Step by Step Force**  
  stärker geführte, mehrstufige Verarbeitung

- **Queue**  
  zerlegt lange Aufgaben in einzelne Schritte und arbeitet sie nacheinander ab

- **One-shot**  
  direkte Verarbeitung in einem Schritt

## Runs

Es gibt zwei grundlegende Arten von Läufen:

- **Repo-Run**  
  arbeitet mit Git-Worktree für bestehende Projekte

- **Scratch-Run**  
  arbeitet in einem separaten Projektordner für neue kleine Projekte oder Prototypen

Damit kann die GUI sowohl bestehende Repositories bearbeiten als auch neue kleine Projekte von null erzeugen.

## Voraussetzungen

- Python 3.11+
- Ollama lokal installiert
- mindestens ein verfügbares Modell, zum Beispiel:
  - `llama3.2`
  - `qwen2.5-coder:14b`

Optional für externe Executor:

- **Codex CLI**
- oder **Ollama CLI** für Claude Code via Ollama

## Installation

```bash
git clone https://github.com/Pascal-64/Ollama-GUI.git
cd Ollama-GUI
pip install -r requirements.txt
streamlit run app.py
```

Unter Windows kann alternativ eine vorhandene Startdatei wie `start_gui.bat` genutzt werden.

## Typischer Ablauf

1. Ollama starten
2. Modell auswählen
3. Profil wählen
4. Modus wählen
5. Prompt eingeben
6. Ergebnis erzeugen
7. optional prüfen, verbessern, speichern oder an einen Executor übergeben

## Hinweise

- Profile besitzen eigene Prompt-Dateien je Modus.
- Dateiendungen können per Dropdown gewählt oder frei eingegeben werden.
- Repo-Runs können Projektänderungen später per Git sauber zurück in den Basis-Branch übernehmen.
- Scratch-Runs sind für neue Mini-Projekte gedacht und haben keine Git-Übernahme in den Hauptstand.

## Status

Das Projekt ist funktionsfähig und wird laufend erweitert.
