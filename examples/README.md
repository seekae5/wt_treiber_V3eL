# Beispiele

Sechs Skripte, die aufeinander aufbauen. Alle benutzen die Fassade `WT3000` — sie sind die
Vorlage, aus der man für ein eigenes Messautomationsskript kopiert.

```bash
python examples/01_geraet_ansehen.py
```

Die IP kommt aus `WT3000_IP` oder aus einer `wt3000.json` in der Projektwurzel; wer sie lieber im
Skript stehen hat, trägt sie oben unter `IP` ein. Alles Weitere, was man verstellen möchte, steht
in jedem Beispiel im Block **„hier anpassen“** am Kopf der Datei.

| Datei | Was es tut | Schreibt am Gerät |
|---|---|---|
| [`01_geraet_ansehen.py`](01_geraet_ansehen.py) | Verbindung prüfen, Steckbrief und Messbereiche zeigen | **nichts** |
| [`02_messreihe_csv.py`](02_messreihe_csv.py) | misst, was am Bedienfeld eingestellt ist → CSV + Metadaten | **nichts** |
| [`03_eigene_groessen.py`](03_eigene_groessen.py) | eigene Spalten festlegen (`ItemSpec`) und aufzeichnen | Item-Tabelle, HOLD |
| [`04_bereiche_setzen.py`](04_bereiche_setzen.py) | Messbereiche nach Plan setzen und danach zurückstellen | Bereiche, Autorange |
| [`05_hintergrundmessung.py`](05_hintergrundmessung.py) | Messung im Hintergrund, währenddessen den Prüfstand fahren | Item-Tabelle, HOLD |
| [`06_integration_wh.py`](06_integration_wh.py) | Energie zählen (Wh/Ah) und den Verlauf mitschreiben | Integration, Item-Tabelle |

**Die ersten beiden sind am realen Gerät ungefährlich** — sie öffnen keines der beiden Schlösser
und können deshalb nichts verstellen. Ab 03 wird geschrieben; jedes dieser Beispiele stellt den
Ausgangszustand am Blockende wieder her, auch bei einem Fehler oder Strg+C.

Nicht in dieser Reihe, aber verwandt:

- [`../live_messwerte.py`](../live_messwerte.py) — dasselbe wie 02, aber mit Kommandozeile
  (`--ip`, `--intervall`, `--anzahl`) und laufender Konsolenausgabe.
- `../src/wt_treiber_lib/stage2…stage5b.py` — die Stufenskripte aus der Entstehungszeit der Bibliothek.
  Sie lösen dieselben Aufgaben **ohne** die Fassade und sind dadurch drei- bis viermal so lang.
  Als Vorlage für eigenen Code sind sie nicht gedacht; ihr Wert liegt in den Begründungen in den
  Kommentaren.

## Zum Weiterlesen

- [`../docs/Schnellstart.md`](../docs/Schnellstart.md) — dieselben Rezepte als eine Seite zum
  Überfliegen, dazu Fehlerbehandlung und eine Stolpersteintabelle.
- [`../docs/API-Ueberblick-und-Lesbarkeit.md`](../docs/API-Ueberblick-und-Lesbarkeit.md) — die
  vollständige Funktionsübersicht nach Aufgabe.
- [`../README.md`](../README.md) — Installation, Verbindungsdaten und der Überblick.

## Zur Zeile `import _pfad`

Sie macht `wt_treiber_lib` aus `src/` importierbar, ohne dass das Paket installiert sein muss — damit
ein Beispiel sofort läuft, statt zuerst an einem `ImportError` zu scheitern. Nach

```bash
pip install -e .
```

ist sie überflüssig, und in einem eigenen Messskript hat sie nichts zu suchen.
