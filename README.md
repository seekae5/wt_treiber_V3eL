# wt_treiber_lib

Python-Treiber für das **Yokogawa WT3000** (Leistungsmessgerät) über SCPI und die TMCTL-Bibliothek.
Gedacht für Messautomationsskripte: verbinden, messen, in eine CSV schreiben — und den
Gerätezustand hinterher so hinterlassen, wie er vorgefunden wurde.

```python
from wt_treiber_lib import WT3000

with WT3000.connect(ip="192.168.10.20") as wt:
    for zeile in wt.device.describe():
        print(zeile)

    # Misst, was am Bedienfeld eingestellt ist - und schreibt nichts am Geraet.
    stats = wt.measure.record_csv("messreihe.csv", max_samples=60, sidecar=True)

print(f"{stats.measured_samples} Messpunkte")
```

**→ Danach: [docs/Schnellstart.md](docs/Schnellstart.md)** — fünf Rezepte auf einer Seite, oder
gleich lauffähig in [examples/](examples/README.md).

---

## Was diese Bibliothek anders macht

**Zwei Schlösser, beide zu in der Voreinstellung.** Wer nur misst, kann am eingemessenen Gerät
nichts verstellen — auch nicht versehentlich:

```python
WT3000.connect()                                        # rein lesend
WT3000.connect(read_only=False, allow_changes=True)     # darf stellen
```

Vier Gruppen bleiben selbst dann gesperrt, weil sie den eingemessenen Zustand ausmachen
(`WIRING`, `RANGE`, `SCALING`, `CFACTOR`); sie werden einzeln und sichtbar freigegeben.

**Jede Änderung hat einen Rückweg.** Messbereiche, Item-Tabelle, Protokollzustand und Integration
werden als Kontextmanager gesetzt. Die Rückstellung steht im `finally` und läuft auch bei einem
Fehler oder Strg+C:

```python
with wt.applied_ranges(plan):
    wt.measure.record_csv("messung.csv", max_samples=60)
# hier stehen die Bereiche wieder wie vorgefunden
```

**Nach jedem Schreiben wird zurückgelesen**, vor jedem großen Schreibvorgang geht eine Probe an
einem einzelnen Wert hinaus. Fehlermeldungen nennen den Ausweg, nicht nur das Problem.

**Metadaten neben die Daten.** `sidecar=True` legt neben die CSV eine `.meta.json` mit Gerät,
Verdrahtung, Item-Tabelle, Laufparametern und Prüfsummen. Erst damit ist eine Messdatei Wochen
später noch ohne Zusatzwissen zu deuten.

**Ohne Gerät benutzbar.** `FakeTransport` erfüllt denselben Vertrag wie die echte Verbindung —
ein Skript lässt sich vollständig durchspielen, bevor man ins Labor geht. Die gesamte Testsuite
läuft ohne WT3000 und ohne `tmctl.dll`.

---

## Installation

Python **3.10 oder neuer**. Keine Laufzeitabhängigkeiten.

```bash
pip install -e .
```

Zum Messen wird zusätzlich gebraucht:

- **Windows** — `TmctlTransport` lädt die DLL über `ctypes.WinDLL`, das es nur dort gibt
- **`tmctl64.dll`** von Yokogawa, im `PATH` oder über `dll_path` angegeben
- ein per Ethernet erreichbares WT3000

Alles andere — Import, Tests, Skriptentwicklung gegen `FakeTransport` — läuft auf jedem
Betriebssystem.

## Verbindungsdaten

Die IP wird in dieser Reihenfolge gesucht, der erste Treffer gewinnt:

1. `WT3000.connect(ip="192.168.10.20")`
2. die Umgebungsvariable `WT3000_IP`
3. eine `wt3000.json` im Arbeitsverzeichnis oder einem Verzeichnis darüber
4. keine — dann bricht der Verbindungsaufbau mit einer Meldung ab, die auf diese Kette verweist

Für ein festes Labor ist Nummer 3 das Bequemste; dann steht in keinem Skript eine IP:

```json
{ "ip": "192.168.10.20", "timeout_ms": 5000 }
```

Dieselbe Kette gilt für `WT3000_DLL_PATH`, `WT3000_TIMEOUT_MS`, `WT3000_USE_REMOTE` und die
übrigen Felder von `WTConfig`.

---

## Wegweiser

| Ich will … | … nachsehen in |
|---|---|
| in fünf Minuten die erste Messreihe | [docs/Schnellstart.md](docs/Schnellstart.md) |
| ein Skript zum Kopieren | [examples/](examples/README.md) — sechs nummerierte, lauffähige Beispiele |
| die vollständige Funktionsliste nach Aufgabe | [docs/API-Ueberblick-und-Lesbarkeit.md](docs/API-Ueberblick-und-Lesbarkeit.md), Teil C |
| wissen, warum etwas so gebaut ist | die Docstrings — sie begründen und halten Messungen am realen Gerät fest |

Die Beispiele sind nach steigendem Eingriff geordnet: **01 und 02 schreiben nichts am Gerät** und
sind der richtige erste Versuch am eingemessenen Aufbau.

## Aufbau

```
src/wt_treiber_lib/   die Bibliothek
examples/            sechs lauffaehige Beispielskripte
docs/                Schnellstart und API-Ueberblick
tests/               geraetefreie Testsuite
tools/hardware/      Messskripte, die ein echtes Geraet brauchen
live_messwerte.py    Anwenderskript mit Kommandozeile
```

Die Bibliothek ist azyklisch in vier Schichten gegliedert — Transport, SCPI-Fachmodule, Abläufe,
Fassade. **Für den Anwender zählt nur die oberste:** die Klasse `WT3000`. Ein Import aus
`wt_treiber_lib.wt3000_*` ist im eigenen Skript nie nötig; alles kommt aus `wt_treiber_lib`.

Die Dateien `src/wt_treiber_lib/stage2…stage5b.py` stammen aus der Entstehungszeit der Bibliothek und
lösen dieselben Aufgaben **ohne** die Fassade. Als Vorlage für eigenen Code sind sie nicht gedacht
— das sagen auch ihre Kopfzeilen; ihr Wert liegt in den Begründungen in ihren Kommentaren.

## Entwicklung

```bash
pip install -e ".[dev]"
pytest
ruff check src tests examples
mypy
```

Die Suite läuft in unter zehn Sekunden, ohne Gerät und ohne DLL. Sie prüft nicht nur die
Bibliothek: **jedes Beispiel und jeder Codeblock aus Schnellstart und README wird ausgeführt**, die
Dokumentation kann also nicht unbemerkt veralten.

Der Quelltext ist deutschsprachig kommentiert und durchgehend in ASCII-Umschreibung geschrieben
(`Geraet`, nicht `Gerät`) — ein Prüfsatz hält das fest. Öffentliche Bezeichner sind englisch.

## Stand

Version 1.0.0. Am realen WT3000 eingemessen sind die Grundgrößen, Verdrahtung, Messbereiche und
die Messschleife. Integrations- und Oberschwingungsfunktionen sind implementiert, aber am
Originalgerät noch nicht durchgängig bestätigt — `build_item_table()` sagt beim Bauen eines
solchen Profils, wie viele Spalten davon betroffen sind und dass sie `NAN` liefern können, ohne
dass ein Messfehler vorliegt.

Stellen, die noch am Gerät zu belegen sind, tragen im Quelltext den Vermerk `ZU VERIFIZIEREN`.
