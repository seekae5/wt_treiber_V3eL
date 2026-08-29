# WT3000-Treiber: API-Überblick und Lesbarkeitsanalyse

**Stand:** 2026-08-27 · **Paket:** `wt_treiber_lib` 0.3.0 · **Basis:** Kopie von `wt_treiber_V3e`
**Zweck dieser Datei:** Bestandsaufnahme und Umbauplan.

> **Suchst du den Einstieg statt der Analyse? → [Schnellstart](Schnellstart.md)** — fünf
> lauffähige Rezepte auf einer Seite.
>
> **Umsetzungsstand:** **E1**–**E6**, **E8**, **E9**, die **Sidecar-Lücke** und das
> **README** sind **erledigt**. Offen bleiben **E7** (Messparameter-Objekt), **E11**
> (Typaliasse), die internen Variablennamen und das `verify`-Feld im Sidecar. Siehe
> Teil F. Testsuite danach: **1020 Tests grün**, `ruff` sauber. Die Befunde D1–D6 und D8–D10 sind entsprechend gekennzeichnet und beschreiben
> ab Teil D den Zustand *vor* dem Eingriff, damit die Begründung nachvollziehbar bleibt.

Zielbild der Kopie `wt_treiber_V3eL`: Jemand mit wenig Programmiererfahrung soll schnell ein
Messautomationsskript für das WT3000 schreiben können. Diese Datei hält fest, **was die Bibliothek
heute anbietet** (Teil A–C), **was den Einstieg heute schwer macht** (Teil D) und **welche
Verbesserungen sich daraus ableiten** (Teil E).

---

## Teil A — Aufbau in einem Absatz

Das Paket ist in vier Schichten azyklisch geschichtet (Reihenfolge aus `__init__.MODULES`):

| Schicht | Module | Rolle |
|---|---|---|
| 1 Transport/Sitzung | `wt3000_transport`, `wt3000_core` | tmctl-DLL, `WTConfig`, `WTSession`, Sperre „nur lesen“ |
| 2 SCPI-Fachmodule | `wt3000_common`, `wt3000_numeric`, `wt3000_rangeio`, `wt3000_input`, `wt3000_deviceconfig`, `wt3000_itemspec` | je eine SCPI-Gruppe, zustandsarm |
| 3 Abläufe | `wt3000_ranging`, `wt3000_measure`, `wt3000_sinks`, `wt3000_backup` | Messschleife, Bereichsplan, Ausgabe, Sicherung |
| 4 Fassade + Beispiele | `wt3000_device` (`WT3000`), `stage2…stage5b` | der Einstiegspunkt für Anwender |

**Für den Anwender zählt praktisch nur Schicht 4:** die Klasse `WT3000`. Sie verdrahtet alles
andere aus dem beim Verbinden gelesenen Gerätesteckbrief (`DeviceInfo`) selbst.

```python
from wt_treiber_lib import WT3000

with WT3000.connect(ip="192.168.10.20") as wt:  # rein lesend
    wt.device.log_summary()
    print(wt.input.get_wiring())
```

Schreiben verlangt bewusst **zwei** geöffnete Schlösser:

```python
with WT3000.connect(read_only=False, allow_changes=True) as wt:
    ...
```

---

## Teil B — Die Einstiegspunkte der Fassade

Alles, was der Anwender braucht, hängt an einem `wt`-Objekt. Zwölf Zugänge, davon acht Fachobjekte:

| Zugang | Typ | Wofür |
|---|---|---|
| `wt.device` | `DeviceInfo` | Steckbrief: Identität, Optionen, Verdrahtung, bestückte Elemente |
| `wt.input` | `InputConfig` | Eingangskonfiguration: Wiring, Bereiche, Filter, Skalierung, Sync, Update-Rate |
| `wt.ranges` | `RangeAccess` | Messbereiche und Autorange, scope-basiert (Element / SIGMA / ALL) |
| `wt.items` | `ItemAccess` | Item-Tabelle: **welche Größen** überhaupt gemessen werden |
| `wt.measure` | `MeasureControl` | Messwerte lesen, aufzeichnen, Messung starten/beenden |
| `wt.integration` | `IntegrationConfig` | Wh-/Ah-Messung (`:INTEGrate`) |
| `wt.computation` | `ComputationConfig` | Averaging, Wirkungsgrad, Frequenzquelle, S/Q-Formel, Sync-Modus |
| `wt.harmonics` | `HarmonicsConfig` | Oberschwingungsanalyse (braucht Option /G5 oder /G6) |
| `wt.session` | `WTSession` | Notausgang für SCPI-Kommandos ohne eigene Methode |
| `wt.config` | `WTConfig` | die benutzten Verbindungsparameter |
| `wt.read_only` / `wt.allow_changes` | `bool` | Zustand der beiden Schlösser |
| `wt.backup()` / `wt.restore_backup()` / `wt.applied_ranges()` / `wt.refresh_device()` / `wt.ensured_protocol_state()` | Methoden | Abläufe, siehe Teil C |

---

## Teil C — Funktionsübersicht nach Aufgabe

Spalte **Sperre**: `–` = immer erlaubt (nur Lesen) · `AC` = braucht `allow_changes=True` (und damit
`read_only=False`) · `AC+G` = braucht zusätzlich `with wt.input.unlocked(GRUPPE):`

### C.1 Verbinden und trennen

| Aufgabe | Aufruf | Sperre | Bemerkung |
|---|---|---|---|
| Verbinden (Normalfall) | `WT3000.connect(ip=..., read_only=True)` | – | IP auch aus `WT3000_IP` oder `wt3000.json` |
| Verbinden mit Schreibrecht | `WT3000.connect(read_only=False, allow_changes=True)` | – | `allow_changes=True` + `read_only=True` ist ein Fehler |
| Mit fertiger Konfiguration | `WT3000.from_config(WTConfig(...), ...)` | – | Fassade schließt den Transport |
| Gerätefrei (Test) | `WT3000.from_transport(FakeTransport({...}))` | – | kein Gerät, keine DLL nötig |
| Parameterherkunft | `WTConfig.from_environment()` | – | Rang: Parameter → Umgebung → `wt3000.json` → Vorgabe |
| Trennen | `with`-Block verlassen, sonst `wt.close()` | – | schaltet HOLD ab, nimmt REMOTE zurück, stoppt laufende Messung |

### C.2 Gerät kennenlernen (Steckbrief)

| Aufgabe | Aufruf | Sperre | Bemerkung |
|---|---|---|---|
| Steckbrief als Textzeilen | `wt.device.describe()` | – | Modell, Serie, Optionen, Verdrahtung, Elemente |
| Steckbrief ins Protokoll | `wt.device.log_summary()` | – | wird beim Verbinden automatisch gerufen |
| Bestückte Elemente | `wt.device.elements` → `(1,2,3,4)` | – | `elements_assumed=True` = geraten, nicht gelesen |
| Ist Element bestückt? | `wt.device.has_element(2)` | – | |
| Verdrahtungsmuster | `wt.device.wiring` → `('V3A3','P1W2')` | – | |
| Wiring-Units mit Elementen | `wt.device.wiring_units` | – | `WiringUnit(name='SIGMA', pattern=…, elements=…)` |
| SIGMA-Zuordnung | `wt.device.sigma_members` → `{'SIGMA': (1,2,3), 'SIGMB': (4,)}` | – | Grundlage von `wt.ranges.expand_scope()` |
| Option verbaut? | `wt.device.has_option("G6")` | – | `/G6` und `G6` gleichwertig |
| Kommandogruppe ansprechbar? | `wt.device.supports(":HARMonics")` | – | **unbekannt zählt als „erlaubt“**, nicht als „fehlt“ |
| Vorabprüfung mit Fehler | `wt.device.require_option(":HARMonics")` | – | verhindert Schein-Timeout bei fehlender Option |
| Nach Umverdrahtung auffrischen | `wt.refresh_device()` | – | nach `set_wiring()` automatisch |

### C.3 Elementauswahl, Wiring

| Aufgabe | Aufruf | Sperre | Bemerkung |
|---|---|---|---|
| Verdrahtung lesen | `wt.input.get_wiring()` | – | |
| Wiring-Units lesen | `wt.input.get_wiring_units()` | – | |
| Modultyp je Element | `wt.input.get_module(1)` / `get_modules()` | – | 30 = 30-A-Element, 2 = 2-A, 0 = nicht bestückt |
| Unabhängige Elemente? | `wt.input.get_independent()` | – | entscheidet, ob Einzelelemente stellbar sind |
| Verdrahtung setzen | `wt.input.set_wiring([Wiring.V3A3, Wiring.P1W2])` | **AC+G** `GROUP_WIRING` | löst `refresh_device()` aus |
| Zielangabe je Setter | `scope=1` / `"SIGMA"` / `"ALL"` (Vorgabe) | | derselbe Begriff wie bei `wt.ranges` und im `RangeSpec`; `ALL` = die bestückten Elemente **dieses** Objekts |
| Scope auflösen | `wt.ranges.expand_scope("SIGMA")` → `(1,2,3)` | – | |

### C.4 Messbereich (Range) — **drei Wege, siehe Befund D4**

**Weg 1 — `wt.input`** (prüft gegen die erlaubten Stufen, liest zur Kontrolle zurück):

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Spannungsbereich lesen | `wt.input.get_voltage_range(1)` → `float` V | – |
| Strombereich lesen | `wt.input.get_current_range(1)` → `(A, V_sensor)` | – |
| Spannungsbereich setzen | `wt.input.set_voltage_range(300.0, scope="ALL")` | **AC+G** `GROUP_RANGE` |
| Strombereich setzen (direkt) | `wt.input.set_current_range(5.0, scope=1)` | **AC+G** `GROUP_RANGE` |
| Strombereich setzen (Sensor) | `wt.input.set_current_range_sensor(10.0, scope=1)` | **AC+G** `GROUP_RANGE` |
| Erlaubte Stufen nachschlagen | `VOLTAGE_RANGES`, `CURRENT_RANGES`, `SENSOR_RANGES` | – |

**Weg 2 — `wt.ranges`** (roh, scope-basiert, keine Stufenprüfung, gibt das Kommando zurück):

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Bereich lesen | `wt.ranges.get_range(Quantity.VOLTAGE, 1)` → `RangeValue(value, sensor)` | – |
| Alle Bereiche | `wt.ranges.get_ranges(Quantity.CURRENT)` → `{element: RangeValue}` | – |
| Rohabzug | `wt.ranges.dump(Quantity.VOLTAGE)` | – |
| Bereich setzen | `wt.ranges.set_range(Quantity.VOLTAGE, "ALL", 300.0)` | **AC** |
| Sensorbereich setzen | `wt.ranges.set_range(Quantity.CURRENT, 1, 10.0, sensor=True)` | **AC** |

**Weg 3 — Plan mit garantiertem Rückweg** (der eigentlich gemeinte Weg für Messreihen):

```python
from wt_treiber_lib import Quantity, RangePlan, RangeSpec, AutoRangeSpec

plan = RangePlan.of(
    RangeSpec(Quantity.VOLTAGE, "ALL", 300.0),
    RangeSpec(Quantity.CURRENT, 1, 10.0, sensor=True),
    AutoRangeSpec(Quantity.CURRENT, 4, False),
)
with wt.applied_ranges(plan, backup_file=Path("bereiche.json")) as report:
    ...  # hier stehen die Bereiche nach Plan
# hier ist der Ausgangszustand nachweislich zurückgestellt
```

Ablauf innen: sichern → Schreibprobe an einem Wert → anwenden → verifizieren → Nutzblock →
im `finally` wiederherstellen → Gegenprobe. `report.problems` / `report.restore_problems` sind leer,
wenn alles gepasst hat. `allow_snapping=True` erlaubt dem Gerät das Runden auf die nächste Stufe.

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Nur sichern | `wt.range_backup()` → `RangeBackup` | – |
| Sicherung als JSON | `wt.range_backup().save(pfad)` | – |
| Sicherungen vergleichen | `backup_a.diff(backup_b)` | – |

### C.5 Autorange — **drei Schreibweisen, siehe Befund D4**

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Zustand lesen | `wt.input.get_voltage_auto(1)` / `get_current_auto(1)` | – |
| Zustand lesen (scope) | `wt.ranges.get_auto(Quantity.VOLTAGE, 1)` / `get_autos(...)` | – |
| Setzen (Weg 1) | `wt.input.set_voltage_auto_range(True, scope="ALL")` | **AC** (`GROUP_AUTO` ist *nicht* geschützt) |
| Setzen (Weg 1, Strom) | `wt.input.set_current_auto_range(True, scope="ALL")` | **AC** |
| Setzen (Weg 2) | `wt.ranges.set_auto(Quantity.VOLTAGE, "ALL", True)` | **AC** |
| Setzen (Weg 3, im Plan) | `AutoRangeSpec(Quantity.VOLTAGE, "ALL", True)` | **AC** |

> Ein fester Bereich impliziert Autorange AUS — das erledigt `apply_plan()` von selbst.

### C.6 Weitere Eingangseinstellungen (alle über `wt.input`)

| Aufgabe | Lesen | Setzen | Sperre |
|---|---|---|---|
| Line-Filter | `get_line_filter(1)` | `set_line_filter(LineFilter.HZ500, scope="ALL")` | AC+G `GROUP_FILTER` |
| Frequenzfilter | `get_frequency_filter(1)` | `set_frequency_filter(True, ...)` | AC+G `GROUP_FILTER` |
| Messmodus U / I | `get_voltage_mode(1)` / `get_current_mode(1)` | `set_voltage_mode(MeasMode.RMS, ...)` | AC+G `GROUP_MODE` |
| Sync-Quelle | `get_sync_source(1)` | `set_sync_source(SyncSource.U1, ...)` | AC+G `GROUP_SYNC` |
| Crest-Faktor | `get_crest_factor()` | `set_crest_factor(3)` | AC+G `GROUP_CFACTOR` |
| Skalierung ein/aus | `get_scaling_state(1)` | `set_scaling_state(True, ...)` | AC+G `GROUP_SCALING` |
| VT / CT / SF / SR | `get_vt_ratio(1)`, `get_ct_ratio(1)`, `get_power_factor(1)`, `get_sensor_ratio(1)` | `set_vt_ratio(...)` usw. | AC+G `GROUP_SCALING` |
| Update-Rate (`:RATE`) | `get_update_rate()` | `set_update_rate(0.5)` | AC+G `GROUP_RATE` |
| Rohabzug `:INPut?` | `get_raw_input_dump()` | — | – |
| Gesamten Zustand sichern | `InputSnapshot.capture(wt.input)` → `.save(pfad)` / `.diff(...)` | `restore_input_snapshot(...)` | AC+G |

Erlaubte Update-Raten: `0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0` s.

### C.7 Item-Tabelle — **was** gemessen wird

Die Item-Tabelle bestimmt, welche Größen `:NUMeric` liefert und damit die **Spalten** der Ausgabe.

| Aufgabe | Aufruf | Sperre | Bemerkung |
|---|---|---|---|
| Aktuelle Tabelle vom Gerät | `wt.items.read()` → `ItemTable` | – | **der einfachste Weg: messen, was ohnehin eingestellt ist** |
| Spaltennamen | `[item.key for item in tabelle.items]` | – | z. B. `U1`, `P_SIGMA`, `I4` |
| Einheiten | `tabelle.units` / `tabelle.unit_map()` | – | |
| Standardprofil | `wt.items.standard_profile()` | – | U, I, P, S, Q, λ, φ je Element 1–3 + FU3 + SIGMA + DC-Element 4 |
| Integrationsprofil | `wt.items.integration_profile()` | – | TIME, WH/WHP/WHM, AH/AHP/AHM, WS, WQ |
| Oberschwingungsprofil | `wt.items.harmonics_profile(orders=(1,3,5,…), elements=("1","2","3"))` | – | |
| Eigene Tabelle bauen | `wt.items.build([ItemSpec("U","1"), ItemSpec("P","SIGMA"), …])` | – | `ItemSpec(function, element=None, order=None)` — **Element als Zeichenkette** |
| Tabelle schreiben | `wt.items.apply(ziel)` | **AC** | Schreibprobe an EINEM Item, dann alles, dann Verify |
| Nur prüfen | `wt.items.verify(ziel)` → Liste der Abweichungen | – | leer = in Ordnung |
| Tabelle sichern | `tabelle.save(pfad)` / `ItemTable.load(pfad)` | – | |
| **Setzen mit garantiertem Rückweg** | `with wt.items.applied(specs, backup_file=…) as tabelle:` | **AC** | Gegenstück zu `applied_ranges()` |

### C.8 Messwerte lesen und Messung steuern

| Aufgabe | Aufruf | Sperre | Bemerkung |
|---|---|---|---|
| Ein Datensatz als Liste | `wt.measure.read_values(tabelle)` → `list[NumericValue]` | – | Reihenfolge = Item-Reihenfolge |
| Ein Datensatz als Dict | `wt.measure.read_mapped(tabelle)` → `{'U1': NumericValue, …}` | – | ohne Argument wird die Tabelle **jedes Mal neu gelesen** |
| Werte einfrieren | `with wt.measure.hold(): …` | AC | `:NUMeric:HOLD`; in Nur-Lesen-Sitzung stillschweigend aus |
| **Blockierend aufzeichnen** | `wt.measure.record(senke, tabelle, interval_s=1.0, max_samples=60)` | – | Ende per Limit oder Strg+C |
| **CSV in einem Aufruf** | `wt.measure.record_csv(Path("m.csv"), tabelle, interval_s=1.0, max_samples=60, sidecar=True)` | – | häufigster Fall |
| **Hintergrundmessung starten** | `messung = wt.measure.start(senke, tabelle)` | – | Sitzung gehört dann dem Mess-Thread |
| … beenden | `stats = messung.stop(timeout=10)` | – | auch `with wt.measure.start(...) as messung:` |
| … warten / Zustand | `messung.wait()`, `messung.is_running`, `messung.stats`, `messung.error` | – | |
| … laufende Messung finden | `wt.measure.active`, `wt.measure.stop_active()` | – | `close()` ruft `stop_active()` selbst |
| **Generator, Takt beim Aufrufer** | `for sample in wt.measure.stream(tabelle, max_samples=10):` | – | Strg+C wirkt normal; Gerät zwischen zwei Samples frei |

**Die drei Wege unterscheiden sich nur darin, wer den Takt treibt:**

| | Blockiert | Strg+C | Gerät während des Laufs frei | Senke |
|---|---|---|---|---|
| `record()` / `record_csv()` | ja | ja | nein | ja |
| `start()` | nein | – (Thread) | **nein** → `ConcurrentAccessError` | ja |
| `stream()` | ja (im Rumpf) | ja | **ja** | nein, selbst schreiben |

**Gemeinsame Parameter** von `record` / `record_csv` / `start` / `stream`:
`interval_s`, `max_samples`, `max_duration_s`, `use_hold`, `record_condition`, `log_every`,
`check_update_rate`, `mark_duplicates`, `error_policy`, `metadata_path`, `parameters`,
`sidecar`, `include_device`.

> `interval_s` ist der Takt **der Schleife**, nicht die Geräterate (`:RATE`, über
> `wt.input.set_update_rate()`). Beide werden gegeneinander geprüft; Zyklen ohne
> Geräteaktualisierung erscheinen als `SampleMark.DUPLICATE`.

> ⚠️ **Was während `start()` nicht geht.** Solange die Hintergrundmessung läuft, gehört die
> Sitzung dem Mess-Thread. Jeder Gerätezugriff aus dem Haupt-Thread — `wt.input`, `wt.ranges`,
> `wt.items`, `wt.integration` — endet in einer `ConcurrentAccessError`. Das ist der häufigste
> Fehler in Prüfstandsabläufen.
>
> Zwei Auswege, je nachdem was gebraucht wird:
>
> * **nur lesen, vor dem Start:** alles Nötige (`wt.items.read()`, Steckbrief, Bereiche) vor
>   `start()` holen und in Variablen halten;
> * **während der Messung stellen:** `stream()` statt `start()` — dort läuft der Takt im Thread
>   des Aufrufers, und zwischen zwei Datensätzen ist die Sitzung frei.
>
> Ebenso wichtig ist die Reihenfolge der Klammern: die Messung muss **innerhalb** der
> Konfigurationsklammer enden, sonst stellt `applied_ranges()` die Bereiche zurück, während noch
> gemessen wird.
>
> ```python
> with wt.applied_ranges(plan):
>     with wt.measure.start(sink, tabelle) as messung:
>         ...
>     # hier ist die Messung nachweislich beendet
> # und erst hier werden die Bereiche zurückgestellt
> ```

> **Ohne Limit läuft die Messung unbegrenzt.** `record()`, `start()` und `stream()` melden das
> seit E9 einmal als Warnung ins Protokoll und nennen, wodurch der Lauf dann endet (Strg+C,
> `stop()`, `break`). Absicht ist es trotzdem — eine Dauerüberwachung soll genau das tun.

### C.9 Messdaten ausgeben und abspeichern

| Ziel | Senke | Bemerkung |
|---|---|---|
| CSV-Datei | `CsvSink(pfad, delimiter=",", unit_row=False, if_exists="overwrite")` | `if_exists`: `overwrite` / `error` / `append` (prüft Kopf) / `unique` |
| JSON Lines | `JsonlSink(pfad, if_exists=...)` | Metadaten als erste Zeile |
| Konsole / eigener Code | `CallbackSink(funktion)` | läuft im Messtakt — nichts Aufwendiges hineinlegen |
| Mehrere gleichzeitig | `MultiSink(CsvSink(a), CallbackSink(anzeigen))` | |
| Auf Abschnitte verteilen | `RotatingSink(fabrik, basis, RotationPolicy(max_rows=…, max_bytes=…, max_seconds=…))` | mind. eine Grenze nötig |
| Eindeutiger Dateiname | `unique_path(pfad)` | |

Jede Senke erfüllt denselben Vertrag `SampleSink`: `open(columns, metadata)` → `write(sample)` → `close()`.
Eigene Senken sind damit möglich, ohne von einer Basisklasse zu erben (`Protocol`).

**Ein Datensatz (`Sample`):** `timestamp` (Moment des HOLD ON), `elapsed_s` (monoton),
`number` (ab 1), `condition` (`:STATus:CONDition?`), `values` (`list[NumericValue]`),
`mark` (`OK` / `DUPLICATE` / `MISSING`), `status_flags(spaltennamen)`.

**Ein Messwert (`NumericValue`):** `value`, `status` (`ValueStatus.OK` / `NO_DATA` / `OVERRANGE` / …),
`is_usable`.

**Statistik (`LoopStatistics`):** `samples`, `measured_samples` (ohne Dubletten/Ausfälle),
`overruns`, `duplicates`, `missing`, `reconnects`, `update_rate_s`, `cycle_times`,
`status_counts`, `log_summary(interval_s)`.

### C.10 Metadaten (Sidecar) — CSV ohne Zusatzwissen lesbar machen

| Aufgabe | Aufruf | Bemerkung |
|---|---|---|
| Sidecar mitschreiben | `record_csv(..., sidecar=True)` | `messung.csv` → `messung.csv.meta.json` |
| Ablageort selbst wählen | `record(..., metadata_path=pfad)` | geht vor `sidecar=True` |
| Gerätesteckbrief aufnehmen | `include_device=True` | Vorgabe: automatisch, wenn ein Sidecar entsteht |
| Freitext ergänzen | `parameters={"comment": "Lauf 3"}` | landet in den Metadaten |
| Nachträglich prüfen | `verify_sidecar(datenpfad)` | Prüfsummen; wirft `SidecarMismatch` |
| Pfad ableiten | `sidecar_path(datenpfad)` | |

Das Sidecar entsteht **nach** dem Lauf — erst dann stehen Prüfsummen, Abschnitte und Ergebnis fest.
Ein misslungenes Sidecar macht eine gelungene Messreihe nicht nachträglich zum Fehlschlag.

Im Abschnitt `parameters` stehen die Laufparameter, die die **Deutung** der Daten bestimmen —
seit Schritt 8 vollständig, siehe Teil F:

```json
"parameters": {
  "sample_interval_s": 1.0, "max_samples": 60, "max_duration_s": null,
  "use_hold": true, "record_condition": true,
  "check_update_rate": true, "mark_duplicates": true,
  "error_policy": { "max_consecutive": 5, "reconnect_after": 2, "max_reconnects": 10 }
}
```

`mark_duplicates` und `error_policy` sind dabei die wichtigsten: ohne sie ließe sich eine Datei
ohne `DUPLICATE`- oder `MISSING`-Zeilen nicht von einer unterscheiden, in der beides nur nicht
gekennzeichnet wurde.

### C.11 Integration (Wh / Ah)

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Zustand / Modus lesen | `wt.integration.state()`, `.mode()`, `.is_running()`, `.timer_seconds()` | – |
| Alles erfassen | `wt.integration.capture()` → `IntegrationSettings` | – |
| Modus setzen | `wt.integration.set_mode(IntegrationMode.…)` | AC |
| Timer setzen | `wt.integration.set_timer(hours=1, minutes=0, seconds=0)` | AC |
| Echtzeitfenster | `wt.integration.set_real_time_window(start, ende)` | AC |
| Starten / Stoppen | `wt.integration.start()` / `.stop()` | AC |
| Zähler verwerfen | `wt.integration.reset()` | **AC + `unlocked(GROUP_RESET)`** — unwiderruflich |
| **Mit garantiertem Stopp** | `with wt.integration.running(): …` | AC |
| Auf Ende warten | `wt.integration.wait_until_finished(timeout_s=None, poll_interval_s=1.0)` | – |
| Restzeit | `wt.integration.remaining_seconds(elapsed)` | – (`elapsed` = Item `TIME` in Sekunden) |

> Die aufgelaufenen Werte werden **nicht** hier gelesen, sondern wie alle Messwerte über die
> Item-Tabelle: `wt.items.integration_profile()`.

### C.12 Rechenfunktionen und Oberschwingungen

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Averaging lesen/setzen | `wt.computation.averaging()` / `.set_averaging(typ, anzahl, ein=True)` | AC |
| Averaging kurz aus | `with wt.computation.averaging_disabled(): …` | AC |
| Frequenzquelle | `wt.computation.frequency_item(1)` / `.set_frequency_item(1, "U3")` | AC |
| Wirkungsgrad | `wt.computation.efficiency(1)` / `.set_efficiency(...)` | AC |
| S/Q-Formel, Sync-Modus | `.sq_formula()`, `.set_sq_formula(...)`, `.sync_mode()`, `.set_sync_mode(...)` | AC |
| Oberschwingungen: Band, Ordnungen | `wt.harmonics.band()`, `.set_order_range(1, 50)` | AC |
| PLL-Quelle, THD-Formel, IEC | `.pll_source()`, `.set_thd_formula(...)`, `.set_iec_grouping("U", ...)` | AC |

`wt.harmonics` prüft beim ersten Zugriff `require_option(":HARMonics")` (/G5 oder /G6) — ohne
Option gäbe es sonst einen Schein-Timeout.

### C.13 Sichern und Wiederherstellen des ganzen Zustands

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Alles sichern | `wt.backup(path=Path("sicherung.json"))` → `SessionBackup` | – (reine Queries) |
| Zurückschreiben und prüfen | `wt.restore_backup(sicherung)` → Liste verbliebener Abweichungen | AC (öffnet alle Input-Gruppen selbst) |
| Gerätevergleich | `sicherung.check_device({...})` | – |

Erfasst werden Steckbrief, Eingangskonfiguration, Bereiche, Item-Tabelle samt Tail, Integration,
Rechenfunktionen und (falls Option verbaut) Oberschwingungen.

### C.14 Protokollzustand, Diagnose, Fehler

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Voraussetzungen prüfen | `wt.check_protocol_state()` | – |
| Ist-Zustand der drei Knoten | `wt.protocol_state()` | – |
| **Herstellen und zurücknehmen** | `with wt.ensured_protocol_state() as geändert: …` | AC |
| Statusregister auswerten | `wt.log_condition()` | – |
| Fehlerqueue lesen | `wt.session.read_error_queue()` / `assert_no_error("Kontext")` | – |

Sollzustand: `:COMMunicate:HEADer 0`, `:COMMunicate:VERBose 0`, `:NUMeric:FORMat FLOat`.
Wird **nicht** automatisch von `record()` hergestellt — der Aufruf gehört sichtbar in den Ablauf.

**Fehlerklassen** (alle von `WTError`):

| Klasse | Bedeutung |
|---|---|
| `TmctlError` | Abriss auf der Leitung (DLL-Ebene) |
| `ProtocolError` | verstümmelte Antwort |
| `DeviceError` | das Gerät beanstandet ein Kommando |
| `ReadOnlyViolation` | Set-Kommando in einer Nur-Lesen-Sitzung (**Schloss 1**, die Sitzung) |
| **`ConfigLocked`** | **gemeinsame Basis der drei Sperren darunter (Schloss 2, die Fachobjekte)** |
| `InputLocked` | `wt.input` hat abgewiesen: kein `allow_changes` oder geschützte Gruppe |
| `DeviceConfigLocked` | `wt.integration` / `wt.computation` / `wt.harmonics` hat abgewiesen |
| `ChangesNotAllowed` | `wt.ranges` hat abgewiesen |
| `ConcurrentAccessError` | Gerätezugriff, während der Mess-Thread die Sitzung hält |
| `VerificationError` | Rücklesekontrolle fehlgeschlagen |
| `MeasurementAborted` | die `ErrorPolicy` hat den Lauf beendet |
| `SidecarMismatch`, `AppendMismatch`, `SinkNotOpen`, `IntegrationStateError` | Ausgabe-/Ablaufseite |

Für „irgendeine Sperre hat abgewiesen“ genügt ein Zweig — er fängt alle drei:

```python
from wt_treiber_lib import ConfigLocked, ReadOnlyViolation

try:
    wt.input.set_voltage_range(300.0)
except ReadOnlyViolation:
    print("Sitzung ist nur lesend - read_only=False setzen")
except ConfigLocked as fehler:
    print(f"Sperre des Fachobjekts: {fehler}")  # nennt selbst den Ausweg
```

**Fehlerstrategie bei Kommunikationsabbrüchen** — `ErrorPolicy`:
ohne Policy beendet der erste Fehler den Lauf (Vorgabe, bewusst). Mit Policy wird ein
fehlgeschlagener Zyklus zu einer Zeile mit `SampleMark.MISSING` und NO_DATA in jeder Spalte.
`ErrorPolicy.unattended()` = `max_consecutive=5, reconnect_after=2, max_reconnects=10` — für
Langzeitläufe ohne Aufsicht. Nur `TmctlError` und `ProtocolError` fallen darunter.

### C.15 Das Sperrsystem in einer Tabelle

| Schloss | Wo gesetzt | Wirkung | Vorgabe |
|---|---|---|---|
| `read_only` | `WT3000.connect(read_only=…)` | die **Sitzung** lehnt jedes Nicht-Query-Kommando ab | `True` (gesperrt) |
| `allow_changes` | `WT3000.connect(allow_changes=…)` | die **Fachobjekte** lehnen Schreibaufrufe schon vor dem Senden ab | `False` (gesperrt) |
| `protected_groups` | fest in `wt3000_input.DEFAULT_PROTECTED` | vier Gruppen bleiben auch bei `allow_changes=True` gesperrt | `WIRING, RANGE, SCALING, CFACTOR` |
| `protected_groups` (Integration) | `wt3000_deviceconfig.DEFAULT_PROTECTED` | `RESET` bleibt gesperrt | `RESET` |

Gruppen-Freigabe für die Dauer eines Blocks:

```python
from wt_treiber_lib import GROUP_RANGE

with wt.input.unlocked(GROUP_RANGE):
    wt.input.set_voltage_range(300.0)
```

---

## Teil D — Befunde: was den Einstieg heute schwer macht

Die Bibliothek ist inhaltlich stark: Sperren, Rückwege im `finally`, Verifikation nach jedem
Schreiben, sehr gute Fehlermeldungen, ausführliche Docstrings mit Begründungen. **Die Schwäche
liegt nicht in der Funktion, sondern im Zugang.** Die Befunde sind nach Wirkung sortiert.

### D1 — Es gibt keine Dokumentation außerhalb des Quelltextes 🔴 ✅ **erledigt (E3)**

Kein `README`, kein `docs/`, kein Schnellstart. Das gesamte Wissen steckte in Docstrings — für
jemanden mit wenig Programmiererfahrung praktisch unsichtbar, solange er nicht weiß, in welcher
Datei er nachschlagen muss. Das war die **größte Einzelhürde**, und sie lag vollständig außerhalb
des Codes.

**Jetzt:** [`docs/Schnellstart.md`](Schnellstart.md) — fünf vollständige Rezepte, dazu IP-Auflösung,
die zwei Schlösser, Fehlerbehandlung, eine Stolpersteintabelle und ein Wegweiser hierher.
Jeder Python-Block wird von `tests/test_schnellstart_doku.py` gegen ein simuliertes Gerät
**ausgeführt** — die Seite kann also nicht unbemerkt veralten. Ein `README.md` in der Wurzel,
das auf beide Dokumente zeigt, fehlt noch.

### D2 — Zentrale Bausteine sind nicht aus dem Paket importierbar 🔴 ✅ **erledigt (E1)**

`__init__.py` exportierte 60 Namen — aber **nicht** die, die die Fassade als Argumente verlangt.
Geprüft (Spalte „vorher“ / „nachher“):

| Name | Wofür gebraucht | vorher | nachher |
|---|---|---|---|
| `RangePlan`, `RangeSpec`, `AutoRangeSpec` | Argument von `wt.applied_ranges(plan)` | ❌ | ✅ |
| `RangeBackup`, `RangeReport`, `ElementRangeState` | Rückgabe von `wt.range_backup()` / `applied_ranges()` | ❌ | ✅ |
| `ItemSpec` | Argument von `wt.items.build(specs)` / `applied(specs)` | ❌ | ✅ |
| `ItemTable`, `NumericItem` | Rückgabe von `wt.items.read()`, Argument fast überall | ❌ | ✅ |
| `GROUP_RANGE`, `GROUP_RATE`, `GROUP_FILTER`, … (alle 9 + `INPUT_GROUPS`) | Argument von `wt.input.unlocked(...)` | ❌ | ✅ |
| `InputConfig`, `RangeAccess`, `InputSnapshot`, `ElementSettings`, `WiringUnit` | Typ von `wt.input` / `wt.ranges` | ❌ | ✅ |
| `RangeValue` | Rückgabe von `wt.ranges.get_range()` | ❌ | ✅ |
| `VOLTAGE_RANGES`, `CURRENT_RANGES`, `SENSOR_RANGES`, `UPDATE_RATES_S` | die erlaubten Stellwerte | ❌ | ✅ |
| `NumericHold`, `ExistingFile` | Rückgabe von `wt.measure.hold()`, `if_exists=`-Parameter | ❌ | ✅ |
| `applied_ranges`, `restore_input_snapshot`, `output_dir`, `setup_logging` | Abläufe/Hilfen | ❌ | ✅ |
| `GROUP_INTEGRATE`, `GROUP_RUN`, `GROUP_COMPUTATION`, `GROUP_HARMONICS` | Argument von `unlocked(...)` | ❌ | ✅ |

**Folge (vorher):** Der Anwender musste `from wt3000_scpi.wt3000_ranging import RangePlan, RangeSpec`
schreiben — also die interne Modulschichtung kennen, die ihn nichts angeht. Genau das, was eine
Fassade verhindern soll. Die Fassade war gebaut, aber der Weg zu ihren Argumenten führte an ihr
vorbei.

**Jetzt:** `__all__` umfasst 114 Namen. Die Regel steht im Kopf von `__init__.py` und ist
maschinell abgesichert: `test_argumente_der_fassade_sind_aus_dem_paket_importierbar` liest die
Annotationen aller öffentlichen Methoden von `WT3000`, `DeviceInfo`, `ItemAccess`,
`MeasureControl`, `InputConfig`, `RangeAccess`, `IntegrationConfig`, `ComputationConfig` und
`HarmonicsConfig` und verlangt für jeden **paketeigenen** Typ darin einen Eintrag in `__all__`.
Wer künftig einen neuen Typ in eine Signatur schreibt und ihn nicht exportiert, sieht es dort —
und nicht der Anwender, der ihn zu benutzen versucht.

### D3 — Die Beispiele im Paket zeigen den umständlichen Weg 🔴 ✅ **erledigt (E4)**

`stage2…stage5b` liegen **im Paket** (`../src/wt_treiber_lib/`) und benutzen durchweg die tiefe API:
`TmctlTransport` + `WTSession` + `InputConfig(...)` von Hand, verschachtelte `try/finally`,
Backup/Restore selbst nachgebaut. `stage4_measure.py` braucht dafür **140 Zeilen** und vier
Verschachtelungsebenen. Dasselbe leistet die Fassade in etwa zwölf Zeilen:

```python
with WT3000.connect(read_only=False, allow_changes=True) as wt:
    with wt.ensured_protocol_state():
        with wt.items.applied(wt.items.standard_profile(), backup_file=sicherung) as tabelle:
            stats = wt.measure.record_csv(csv_pfad, tabelle, interval_s=1.0,
                                          max_samples=60, sidecar=True)
    stats.log_summary(1.0)
```

Wer im Paket nach einer Vorlage sucht, fand die alte Form zuerst — und kopierte sie. Nur
`live_messwerte.py` (Projektwurzel) benutzte die Fassade und war damit das eigentliche Vorbild.

**Jetzt:** [`examples/`](../examples/README.md) mit sechs nummerierten, lauffähigen Skripten, alle
über die Fassade. Jedes trägt im Kopf, **was es am Gerät schreibt**; die ersten beiden schreiben
nichts und sind am eingemessenen Gerät der richtige erste Versuch. Die fünf `stage*`-Skripte
bleiben, wo sie sind — sie werden von der Testsuite geprüft und tragen wertvolle Begründungen —,
haben aber jetzt einen Kopfblock „**KEINE VORLAGE FÜR EIGENEN CODE**“ mit Verweis auf das passende
Beispiel.

### D4 — Drei Wege zum selben Ziel, ohne erkennbare Empfehlung 🟠 ✅ **erledigt (E6)**

**Messbereich setzen** geht über `wt.input.set_voltage_range()`, `wt.ranges.set_range()` oder
`RangeSpec` im Plan. Die drei unterscheiden sich in Dingen, die der Einsteiger nicht ahnt:

| | Stufenprüfung vorab | Rücklesekontrolle | Rückweg garantiert | Sperre |
|---|---|---|---|---|
| `wt.input.set_voltage_range` | ✅ gegen `VOLTAGE_RANGES` | ✅ | ❌ | AC **+ `unlocked(GROUP_RANGE)`** |
| `wt.ranges.set_range` | ❌ | ❌ (erst im Plan) | ❌ | AC |
| `RangeSpec` in `applied_ranges` | ✅ `validate()` | ✅ `verify_plan()` | ✅ | AC |

**Autorange** hat ebenso drei Schreibweisen. Dass `GROUP_AUTO` nicht in `DEFAULT_PROTECTED` steht,
`GROUP_RANGE` aber schon, ist sachlich richtig, aber ohne Doku nicht erschließbar: derselbe
Aufrufstil führt einmal durch und einmal zu `ConfigLocked`.

**Jetzt:** jeder Docstring sagt, wo man hingehört. Der empfohlene Einstieg trägt
`EMPFOHLENER WEG`, jede Alternative `STATTDESSEN EMPFOHLEN` mit einem Satz, was sie *nicht*
leistet (meist: keinen Rückweg). Betroffen sind vier Aufgaben — Messbereich, Autorange,
Item-Tabelle, Integration —, insgesamt elf Methoden. Abgesichert durch
`tests/test_wegweiser_und_fallen.py`, damit die Hinweise beim nächsten Umformulieren nicht
stillschweigend verschwinden.

### D5 — Zwei verschiedene Klassen heißen `ConfigLocked` 🟠 ✅ **erledigt (E2)**

`wt3000_input.ConfigLocked` und `wt3000_deviceconfig.ConfigLocked` waren **verschiedene Klassen**
(geprüft: `CL1 is CL2` → `False`). Exportiert wurde nur die aus `wt3000_input`. Ein
`except ConfigLocked:` mit dem Paket-Import fing also **keinen** Integrations-Sperrfehler ab —
still, plausibel und falsch.

**Jetzt:** eine gemeinsame Basis `ConfigLocked` in `wt3000_core` (Layer 1, also unterhalb beider
Fachmodule — der Import zeigt wie gefordert nach unten). Drei Unterklassen benennen, **wer**
abgewiesen hat:

```
WTError
├── ReadOnlyViolation          Schloss 1: die Sitzung (bewusst außerhalb der Familie)
└── ConfigLocked               Schloss 2: die Fachobjekte
    ├── InputLocked            wt.input
    ├── DeviceConfigLocked     wt.integration / wt.computation / wt.harmonics
    └── ChangesNotAllowed      wt.ranges   (Name unverändert)
```

`ALL_GROUPS` und `DEFAULT_PROTECTED` tragen weiterhin in beiden Modulen denselben Namen, sind aber
**bewusst nicht exportiert** — die Kollision kann den Anwender damit nicht mehr treffen. Exportiert
ist stattdessen `INPUT_GROUPS` (die vollständige Gruppenliste der Eingangskonfiguration) sowie jede
einzelne `GROUP_*`-Konstante, und deren Namen sind über beide Module hinweg eindeutig.

Abgesichert durch `test_kein_modul_definiert_configlocked_ein_zweites_mal` (prüft per AST, dass
kein Fachmodul die Klasse erneut definiert), `test_jede_sperre_erbt_von_der_gemeinsamen_basis` und
`test_die_sitzungssperre_bleibt_ausserhalb_der_familie`.

**Rückwärtskompatibel:** `from wt3000_scpi.wt3000_deviceconfig import ConfigLocked` liefert jetzt
die Basis und fängt `DeviceConfigLocked` — alle bestehenden Tests und Skripte laufen unverändert.

### D6 — „Element“ heißt an vier Stellen anders und hat zwei Typen 🟠 ✅ **erledigt (E8)**

| Modul | Parametername | Typ | Beispiel |
|---|---|---|---|
| `wt3000_input` | `target` | `int \| str` | `target=1`, `target="ALL"` |
| `wt3000_rangeio` / `RangeSpec` | `scope` | `str \| int` | `scope="SIGMA"`, `scope=1` |
| `ItemSpec` | `element` | **`str \| None`** | `element="1"` — **Zeichenkette!** |
| `DeviceInfo` / `RangeAccess` | `elements` | `tuple[int, ...]` | `(1, 2, 3, 4)` |

Für dieselbe Sache — „welches Element meine ich“ — gab es drei Parameternamen und zwei Typen.
`ItemSpec("U", 1)` statt `ItemSpec("U", "1")` war ein naheliegender Fehler.

**Jetzt** heißt es überall `scope` und trägt überall den Typ `Scope`:

| Stelle | vorher | nachher |
|---|---|---|
| die 15 Setter in `wt3000_input` | `target: int \| str` | `scope: Scope` |
| `RangeAccess.set_range` / `set_auto` / `expand_scope` | `scope: str \| int` | `scope: Scope` |
| `RangeSpec`, `AutoRangeSpec` | `scope: str \| int` | `scope: Scope` |
| die Helfer in `wt3000_common` | `scope: str \| int` | `scope: Scope` |
| `wt3000_input.target_node()` | — | heißt `scope_node()` |
| `ItemSpec("U", 1)` | stille Fehlkonfiguration | gleichwertig zu `ItemSpec("U", "1")` |

`Scope = int | str` steht in `wt3000_common` — dem gemeinsamen Vokabularmodul, das den Begriff
`scope` ohnehin schon führte — und ist aus dem Paket importierbar.

**Übergangsfrist:** `target=` wirkt weiter. Ein harter Umbenenner hätte jedes bestehende Skript
mit einem `TypeError` gebrochen, und zwar mitten im Lauf — also genau dann, wenn am Gerät schon
etwas eingestellt ist. Stattdessen nimmt ein Dekorator den alten Namen an, meldet ihn als
`DeprecationWarning` **und** im Protokoll (mit dem neuen Namen im Text) und weist `scope=` und
`target=` zugleich als Fehler ab. `functools.wraps` erhält Signatur und Docstring, die
Editor-Hilfe zeigt also `scope`.

`ItemSpec` wandelt Zahlen beim Erzeugen in Text; Gleichheit und Hashwert stimmen dadurch überein
(`{ItemSpec("P", 2), ItemSpec("P", "2")}` hat ein Element). `True`/`False` werden abgewiesen —
`bool` ist ein Subtyp von `int`, und `ItemSpec("U", True)` ist ein Vertipper, kein Element 1.

### D7 — Vier Messmethoden mit je 14–18 identischen Parametern 🟠

`record`, `record_csv`, `start`, `stream` wiederholen dieselbe Parameterliste. Die Signaturen
füllen im Editor mehr als einen Bildschirm; der Einsteiger sieht keine kurze Form und weiß nicht,
welche drei Parameter er tatsächlich braucht (`tabelle`, `interval_s`, ein Limit). Wirkungsvolle
Vorgaben wie `use_hold=True` oder `check_update_rate=True` verschwinden im Rauschen.

### D8 — Der Weg von „ich will U, I, P“ zu Messwerten ist lang 🟠 ✅ **erledigt (E5)**

Die Item-Tabelle ist der schwerste Begriff der Bibliothek und steht dem Anfänger als erstes im Weg.
Um eigene Größen zu messen, muss er `ItemSpec` → `build()` → `apply()` → `verify()` → `restore()`
verstehen (oder `wt.items.applied()` finden). Es gibt keinen Aufruf der Art
`wt.measure.messen(["U1", "I1", "P1"])`.

Der einfache Ausweg **existierte** — `wt.items.read()`, „miss, was am Gerät eingestellt ist“ —
stand aber nur in einem Kommentar in `live_messwerte.py` und in keinem Docstring als *der* Einstieg.

**Jetzt** sind es zwei Zeilen bis zur ersten Messreihe, und die Item-Tabelle steht keinem mehr im
Weg, der sie noch nicht braucht:

```python
wt.measure.record_csv(pfad, max_samples=60)                    # was eingestellt ist
tabelle = wt.items.from_keys(["U1", "I1", "P1", "PSIGMA"])     # eigene Spalten
```

`table` ist an `record()`, `record_csv()`, `start()` und `stream()` optional geworden; ohne Angabe
wird die Tabelle des Geräts übernommen und **einmal je Lauf** gelesen (nicht je Datensatz — ein
eigener Prüfsatz hält das fest). `from_keys()` nimmt genau die Namen, die in der CSV-Kopfzeile
stehen. Beides ist additiv: die alte Aufrufform bleibt gültig, `table` steht unverändert an
zweiter Stelle.

### D9 — Nicht offensichtliche Fallen 🟡 ✅ **erledigt (E9)**

| Falle | vorher | jetzt |
|---|---|---|
| `read_mapped()` **ohne** Argument liest die Item-Tabelle bei **jedem Aufruf** neu vom Gerät — in einer Schleife eine unnötige Abfrage je Durchlauf | nur im Quelltext sichtbar | Docstring nennt es; der **zweite** Aufruf ohne Tabelle meldet sich einmalig im Protokoll und nennt den Ausweg |
| Während `start()` läuft, gehört die Sitzung dem Mess-Thread; `wt.input`/`wt.ranges` enden in `ConcurrentAccessError` | im Docstring | zusätzlich ein Warnkasten in C.8 **mit beiden Auswegen** und der Klammer-Reihenfolge, dazu im Schnellstart und in Beispiel 05 |
| `record()`/`start()`/`stream()` ohne Limit laufen **unbegrenzt** | nur `stage4` meldete es | alle drei melden es einmal und nennen, wodurch der Lauf endet (Strg+C / `stop()` / `break`) |
| `ItemSpec(..., verify=True)` markiert Funktionen, die **am Originalgerät nicht bestätigt** sind (das ganze Integrations- und Oberschwingungsprofil) | **gesetzt und von niemandem gelesen** — toter Schalter | `build_item_table()` meldet einmal je Tabelle, wie viele Items betroffen sind, welche Funktionen es sind und dass sie NAN liefern können, ohne dass ein Messfehler vorliegt |

Zwei Punkte bleiben bewusst, wie sie sind:

- `wt.device.supports()` liefert **`True`**, wenn `*OPT?` fehlgeschlagen ist („unbekannt ≠ fehlt“).
  Sachlich richtig und im Docstring ausführlich begründet; für „darf ich?“ trotzdem überraschend.
- `if_exists="overwrite"` ist die Vorgabe von `CsvSink` — eine vorhandene Messdatei wird
  überschrieben (immerhin protokolliert). Die Vorgabe zu ändern wäre eine Verhaltensänderung und
  gehört nicht in einen Lesbarkeitsschritt; sie steht in der Stolpersteintabelle des Schnellstarts.

**Nicht gepuffert, mit Absicht.** Der naheliegende „Fix“ für die erste Zeile wäre, die Tabelle in
`read_mapped()` zu merken. Das wäre schlimmer als das Problem: ändert sich die Item-Tabelle
zwischen zwei Aufrufen, lieferte ein Puffer stillschweigend falsche Namen zu richtigen Werten.
Ein eigener Prüfsatz hält das fest, damit die nächste Optimierung ihn nicht doch einbaut.

### D10 — Sprachmix 🟡 ⏸ **teilweise — zwei Teile bewusst zurückgestellt**

Doku und Kommentare deutsch, öffentliche Bezeichner englisch (`get_wiring`, `record_csv`,
`max_samples`), interne Variablen teils deutsch (`senke`, `tabelle`, `messung`, `lauf_parameter`,
`zu_aendern`).

**Entschieden und umgesetzt:** öffentliche Bezeichner bleiben englisch (Entscheidung vom
2026-08-27); neue Namen folgen dem — `InputLocked`, `DeviceConfigLocked`, `from_keys`,
`spec_from_key`, `Scope`, `scope_node`.

**Zurückgestellt: die Umlautfrage.** Erst gemessen, dann entschieden:

| | Anzahl |
|---|---|
| echte Umlaute im Paket (vor E8) | **5** — verteilt auf 3 Dateien, ohne Muster |
| ASCII-Umschreibungen in String-Literalen (inkl. Docstrings) | **2864** |
| Tests, die auf Meldungstext matchen (`match=`) | **74** |

Eine Umstellung auf echte Umlaute wäre ein mechanischer Eingriff an rund 2900 Stellen mit 74
Testtreffern als Minenfeld — und sie beträfe auch Fehlermeldungen, die jemand in seiner
Logauswertung stehen haben kann. Der Nutzen ist kosmetisch. **Stattdessen wurde die vorhandene
Konvention durchgesetzt:** die fünf Ausreißer sind auf ASCII gezogen, das Paket ist jetzt
durchgehend einheitlich, und ein Prüfsatz hält das fest. Ein Nebeneinander beider Schreibweisen
ist die einzige Variante, die niemandem nutzt — das ist jetzt ausgeschlossen. Wer umstellen will,
stellt alles um, in einem eigenen Schritt und unter Aussparung der Meldungsliterale.

**Zurückgestellt: die internen Variablennamen.** `senke`, `tabelle`, `messung` sind für den
Anwender der Bibliothek unsichtbar — sie stehen in Rümpfen, nicht in Signaturen. Der Umbau wäre
großflächig und trüge nichts zum Ziel dieser Kopie bei. Er bleibt offen, mit niedriger Priorität.

### D11 — Stärken, die erhalten bleiben müssen ✅

Damit die Umarbeitung nichts kaputt macht, hier ausdrücklich die tragenden Eigenschaften:

- **Fehlermeldungen nennen den Ausweg**, nicht nur das Problem
  („Freigabe ausdrücklich über: `with cfg.unlocked('RANGE'): ...`“).
- **Jeder Rückweg steht im `finally`** — `applied_ranges`, `items.applied`, `integration.running`,
  `ensured_protocol_state`, `NumericHold`. Auch bei Strg+C.
- **Nach jedem Schreiben wird zurückgelesen**, vor jedem großen Schreiben geht eine Probe hinaus.
- **Zwei Schlösser, beide zu in der Vorgabe.** Wer nur misst, kann nichts verstellen.
- **`FakeTransport`** erlaubt vollständige Skripterprobung ohne Gerät und ohne DLL.
- **Die Docstrings begründen Entscheidungen** und halten Messergebnisse am realen Gerät fest
  (z. B. warum `:INTEGrate:RTIMe?` *kein* Restzeitzähler ist). Dieses Wissen darf beim Kürzen
  nicht verloren gehen — es gehört in die Doku verschoben, nicht gelöscht.

---

## Teil E — Vorschläge zur Verbesserung von Lesbarkeit und Anwendbarkeit

Priorität: 🔴 groß · 🟠 mittel · 🟡 klein. Aufwandsschätzung grob.
Sortiert nach **Wirkung je Aufwand**.

### E1 🔴 Paket-Export vervollständigen — ✅ **umgesetzt**

`__init__.py` um die in D2 aufgeführten Namen ergänzt, so dass **jedes Argument, das die Fassade
verlangt, aus `wt_treiber_lib` importierbar ist**. Die Regel steht im Kopf der Datei:

> Wer nur `from wt3000_scpi import ...` schreibt, kommt an jede Anwenderfunktion. Ein Import aus
> `wt3000_scpi.wt3000_*` ist im Messautomationsskript nie nötig.

`__all__`: 60 → **114 Namen**, gegliedert nach Aufgabe statt nach Herkunftsmodul. Kein Verhalten
geändert, nichts entfernt. Gegenprobe in `tests/test_package_layout.py` (siehe D2).

### E2 🔴 Namenskollision `ConfigLocked` auflösen — ✅ **umgesetzt**

Gemeinsame Basis `ConfigLocked` in `wt3000_core`, drei sprechende Unterklassen bei ihren Modulen:
`InputLocked`, `DeviceConfigLocked`, `ChangesNotAllowed`. `except ConfigLocked:` fängt ab jetzt
alle drei; `ReadOnlyViolation` bleibt bewusst außerhalb der Familie, weil es das *andere* Schloss
ist. `ALL_GROUPS` / `DEFAULT_PROTECTED` bleiben unexportiert. Details und Vererbungsbaum in D5.

> Statt `IntegrationLocked` (Vorschlag der ersten Fassung) heißt die Klasse
> **`DeviceConfigLocked`**: `wt3000_deviceconfig` beherbergt drei Fachobjekte — Integration,
> Rechenfunktionen und Oberschwingungen — und `IntegrationLocked` hätte für zwei davon gelogen.

### E3 🔴 Ein Schnellstart, der auf eine Seite passt — ✅ **umgesetzt**

[`docs/Schnellstart.md`](Schnellstart.md) mit genau den fünf vorgesehenen Rezepten:

1. Verbinden und Gerät ansehen (nur lesend)
2. Messen, was am Gerät eingestellt ist → CSV *(der Einstieg — `wt.items.read()`)*
3. Eigene Größen messen *(`ItemSpec`-Liste oder fertiges Profil)*
4. Bereiche für die Messung setzen und danach zurückstellen *(`applied_ranges`)*
5. Messung im Hintergrund starten, Prüfstand fahren, beenden *(`start()`/`stop()`)*

Jedes Rezept vollständig und kopierfähig, mit einem Satz „wann nimmt man das“. Kein Fließtext über
Architektur — die Schichten interessieren den Anwender nicht; die Schichtung steht hier in Teil A
für den, der sie sucht.

**Über den Plan hinaus:** die Rezepte werden ausgeführt statt nur geschrieben.
`tests/test_schnellstart_doku.py` (13 Prüfsätze, ~2 s) extrahiert jeden Python-Block aus der
Markdown-Datei und führt ihn gegen ein simuliertes Gerät aus. Geändert wird dabei nur der Takt
(`interval_s`, `max_samples`), damit die Suite nicht zwei Minuten misst — alles Übrige läuft
wortwörtlich. Zwei Prüfsätze gehen weiter und weisen die Zusagen der Seite nach: dass Rezept 2
CSV **und** Sidecar mit dem versprochenen Spaltenkopf ablegt, und dass Rezept 4 die Bereiche
hinterher tatsächlich zurückstellt.

Gegenprobe gemacht: `wt.items.read()` im Rezept versuchsweise in `wt.items.lies_tabelle()`
geändert → zwei Prüfsätze rot, mit Zeilennummer im Block. Der Beispielcode kann also nicht
stillschweigend veralten.

### E4 🔴 Die Stufenskripte umbauen oder verschieben — ✅ **umgesetzt (Weg 1 + Weg 3)**

Umgesetzt wurden Möglichkeit 1 und 3; **Möglichkeit 2 bewusst nicht.**

**Weg 1 — [`examples/`](../examples/README.md)**, sechs Skripte über die Fassade:

| Datei | Schreibt am Gerät |
|---|---|
| `01_geraet_ansehen.py` | nichts |
| `02_messreihe_csv.py` | nichts |
| `03_eigene_groessen.py` | Item-Tabelle, HOLD |
| `04_bereiche_setzen.py` | Bereiche, Autorange |
| `05_hintergrundmessung.py` | Item-Tabelle, HOLD |
| `06_integration_wh.py` | Integration, Item-Tabelle |

Jedes trägt im Kopf, was es schreibt, hat einen Block „hier anpassen“ und stellt den
Ausgangszustand zurück. `examples/README.md` ist der Index. Statt der geplanten fünf sind es
sechs — die Integration hat ein eigenes Beispiel bekommen, weil die Trennung *steuern*
(`wt.integration`) und *lesen* (`integration_profile()`) sonst nirgends vorgeführt wird.

**Weg 3 —** jedes `stage*`-Skript trägt jetzt im Kopf:

> KEINE VORLAGE FUER EIGENEN CODE. […] Wer ein eigenes Messskript schreibt, faengt stattdessen
> hier an: `examples/…`, `docs/Schnellstart.md`. Der Wert dieser Datei liegt in den Begruendungen
> in ihren Kommentaren, nicht in ihrem Aufbau.

**Weg 2 (Verschieben nach `tools/legacy/`) wurde verworfen.** Die `stage*`-Skripte hängen an
`tests/test_stage_durchlauf.py`, `test_stage_startup.py`, `test_stage_remote_release.py`, an den
`LAYERS`-Einträgen in `test_package_layout.py` und an der `stufenlauf`-Vorrichtung in
`conftest.py`. Ein Umzug wäre ein Eingriff in die Testabsicherung, und zwar für einen Gewinn, den
der Kopfblock schon liefert. Er bleibt als Option offen, gehört aber in einen eigenen Schritt.

**Abgesichert:** `tests/test_beispiele.py` (19 Prüfsätze, ~2 s) fährt **jedes** Beispiel
vollständig gegen ein simuliertes Gerät. Ersetzt wird nur der Draht (`TmctlTransport` im
Namensraum der Fassade), das Ausgabeverzeichnis und die Wartezeiten. Dazu Prüfsätze auf die
Zusagen der Kopfzeilen: dass 01 und 02 **am Draht nachweislich kein Set-Kommando senden**, dass 03
die Item-Tabelle zurückstellt, dass 04 die Bereiche zurückstellt und dass 06 die Integration in
jedem Fall stoppt. Ein weiterer hält fest, dass kein Beispiel `WTSession(`, `TmctlTransport(` oder
einen Import an der Fassade vorbei enthält — sonst wäre es wieder ein Stufenskript.

Gegenprobe gemacht: `wt.applied_ranges(` in Beispiel 04 versuchsweise umbenannt → zwei Prüfsätze
rot.

### E5 🟠 Einen kurzen Weg zu Messwerten anbieten — ✅ **umgesetzt**

```python
# a) messen, was eingestellt ist - ohne Item-Tabelle im Skript
stats = wt.measure.record_csv(pfad, max_samples=60)

# b) eigene Groessen ohne ItemSpec-Vokabular
tabelle = wt.items.from_keys(["U1", "I1", "P1", "PSIGMA"])
```

**(a)** `table` ist an `record()`, `record_csv()`, `start()` und `stream()` optional. Ohne Angabe
wird die Tabelle des Geräts übernommen, **einmal je Lauf** und mit einer Protokollzeile, die die
Spalten nennt — sonst wüsste hinterher niemand, was gemessen wurde. Bei `start()` läuft die
Abfrage ausdrücklich **vor** dem Thread-Start, sonst wäre sie eine `ConcurrentAccessError`.

**(b)** `from_keys()` heißt so und nicht `von_namen()` — englische Bezeichner, wie am 2026-08-27
entschieden. Der Begriff `key` ist bereits der der Bibliothek (`NumericItem.key`, die Schlüssel von
`read_mapped()`, die CSV-Kopfzeile).

**Zwei Dinge, die beim Bauen herauskamen:**

1. **Der Planentwurf schrieb `"P_SIGMA"` — das ist falsch.** Der echte Schlüssel lautet `PSIGMA`;
   der Unterstrich trennt ausschließlich die Ordnung ab (`PHI1_1`). Wäre das ungeprüft in die Doku
   gewandert, hätte der erste Anwender eine Spalte `P` mit der *Ordnung* `SIGMA` angefordert. Die
   Schreibweise steht jetzt als Warnung in `spec_from_key()`, in `from_keys()`, im Schnellstart und
   in Beispiel 03; ein Prüfsatz hält fest, dass die beiden Formen wirklich Verschiedenes bedeuten.

2. **Die Umkehrung rät nicht.** Der naheliegende Weg wäre, den Namen gegen eine Tabelle bekannter
   Funktionen zu zerlegen — die wäre unvollständig, denn das Gerät kennt weit mehr Funktionen als
   dieses Paket aufführt. Zerlegt wird stattdessen **von rechts** und nur an den beiden Stellen,
   die das Format vorsieht: alles nach dem ersten `_` ist die Ordnung, davor endet der Name auf
   einem Elementbezeichner aus einer **geschlossenen** Liste (`SIGMA`, `SIGMB`, `1`–`4`) oder auf
   keinem. Der Rest ist die Funktion und wird weder geprüft noch übersetzt — welche Funktionen das
   Gerät kennt, weiß das Gerät, und eine falsche fällt beim Verifizieren nach dem Schreiben auf.

**Abgesichert:** `tests/test_kurzweg.py` (24 Prüfsätze). Der Kern ist die **Rundreise**: für alle
**186 Items** der drei mitgelieferten Profile — Standard, Integration, Oberschwingungen mit
Ordnungen — führt der Spaltenname exakt auf die Spec zurück, aus der er entstanden ist. Eine
Abkürzung, die stillschweigend etwas anderes misst, wäre schlimmer als gar keine.

### E6 🟠 Einen empfohlenen Weg je Aufgabe benennen — ✅ **umgesetzt**

Zwei greppbare Marker, konsequent durchgezogen:

| Marker | steht auf | Beispiel |
|---|---|---|
| `EMPFOHLENER WEG` | dem Einstieg, den man nehmen soll | `WT3000.applied_ranges`, `ItemAccess.applied`, `IntegrationConfig.running`, `MeasureControl.record_csv`, `wt3000_ranging.applied_ranges` |
| `EMPFOHLENER EINSTIEG` | dem Anfang für Anfänger | `ItemAccess.read` |
| `STATTDESSEN EMPFOHLEN` | jeder Alternative, mit einem Satz zu dem, was sie *nicht* leistet | `RangeAccess.set_range`/`set_auto`, `InputConfig.set_voltage_range`/`set_current_range`/`set_current_range_sensor`/`set_voltage_auto_range`/`set_current_auto_range`, `ItemAccess.apply`, `IntegrationConfig.start` |

Vier Aufgaben, elf Methoden, kein Code entfernt. Der Satz auf den Alternativen ist immer derselbe
in der Sache: *dieser Aufruf hat keinen Rückweg — was er verstellt, bleibt verstellt.*

Die Übersichtstabellen stehen bereits in C.4 und C.5 dieser Datei.

**Abgesichert:** `tests/test_wegweiser_und_fallen.py` führt die vier Aufgaben mit ihrem empfohlenen
Weg und ihren Alternativen als Datenstruktur und prüft jeden Docstring dagegen. Ein Hinweis, der
beim nächsten Umformulieren verschwindet, lässt die Suite rot werden — und die Liste im Test ist
zugleich die Antwort auf die Frage, die ein Anwender beim Überfliegen der API stellt: *es gibt
drei Methoden dafür, welche nehme ich?*

### E7 🟠 Messparameter bündeln — *mittel, API-Erweiterung*

Die 14–18 Parameter aus D7 in ein Datenobjekt fassen und als **Alternative** anbieten:

```python
@dataclass(frozen=True)
class Messlauf:
    interval_s: float = 1.0
    max_samples: int | None = None
    max_duration_s: float | None = None
    use_hold: bool = True
    ...
```

`record(sink, table, lauf=Messlauf(interval_s=0.5, max_samples=100))` bleibt neben der heutigen
Form bestehen. Vorteil: der Anwender sieht drei Argumente statt achtzehn, kann einen Laufparametersatz
benennen, wiederverwenden und protokollieren — und die Vorgaben stehen an **einer** Stelle statt
viermal.

### E8 🟠 Benennung vereinheitlichen — ✅ **umgesetzt (2 von 4 Punkten, 2 begründet zurückgestellt)**

**Umgesetzt:**

- **`scope` überall**, mit dem Alias `Scope = int | str` in `wt3000_common`. Die Richtung war nicht
  frei wählbar: `wt3000_common` — das gemeinsame Vokabularmodul — nannte es bereits `scope`
  (`canonical_scope`, `is_element_scope`, `scope_suffix`), `wt3000_input` war der einzige
  Ausreißer. 67 Vorkommen umbenannt, `target_node()` → `scope_node()`. `target=` wirkt eine
  Version lang weiter, siehe D6.
- **`ItemSpec("U", 1)` funktioniert**, ebenso `ItemSpec("U", 1, 5)` für die 5. Ordnung.

**Zurückgestellt, mit Messung statt Bauchgefühl:** interne Variablennamen und die Umlautfrage —
Begründung und Zahlen in D10.

**Abgesichert:** `tests/test_benennung.py` (50 Prüfsätze) hält die 18 öffentlichen Stellen
namentlich fest — Parametername *und* Typ —, prüft die Übergangsfrist in beide Richtungen
(alter Name wirkt und meldet sich, neuer Name schweigt, beide zugleich sind ein Fehler), belegt
dass `functools.wraps` die Editor-Hilfe intakt lässt, und stellt sicher, dass die Quelldateien
bei **einer** Schreibweise bleiben.

### E9 🟡 Die Fallen aus D9 sichtbar machen — ✅ **umgesetzt**

Alle vier Punkte, siehe die Vorher/Nachher-Tabelle in D9. Zwei Abweichungen vom Plan:

- **`read_mapped()` puffert bewusst nicht.** Der Plan bot „merken *oder* warnen“ an; gemerkt wird
  nicht, weil ein Puffer nach einer Tabellenänderung falsche Namen zu richtigen Werten lieferte.
  Gewarnt wird stattdessen beim **zweiten** Aufruf ohne Tabelle — einer ist ein Blick, zwei sind
  eine Schleife.
- **`verify=True` landet im Protokoll, nicht im Sidecar.** Der Plan sah ein Sidecar-Feld vor. Dafür
  müsste die Kennzeichnung von `ItemSpec` über `build_item_table()` bis in `ItemTable` und deren
  Serialisierung durchgereicht werden — eine Formatänderung mit `to_dict`/`from_dict`/`save`/`load`
  im Schlepptau, deutlich mehr als ein Lesbarkeitsschritt. `build_item_table()` meldet es
  stattdessen einmal je Tabelle. **Dieses eine Sidecar-Feld bleibt offen** — nicht zu verwechseln
  mit der Sidecar-Lücke bei den Laufparametern, die inzwischen geschlossen ist (Schritt 8).

Die Warnungen sind so gebaut, dass sie schweigen, wenn kein Anlass besteht — eine Meldung, die
immer kommt, liest nach der dritten Messung niemand mehr. Genau das prüfen die Gegenproben in
`tests/test_wegweiser_und_fallen.py` mit.

### E10 🟡 Fehlermeldungen als Muster festhalten — *klein*

Die vorhandene Qualität („was ist falsch — und was tut man dagegen“) als **verbindliche Regel** in
`docs/` schreiben, damit neue Meldungen sie einhalten. Das ist bereits die stärkste Eigenschaft der
Bibliothek für unerfahrene Anwender.

### E11 🟡 Typaliasse für die häufigen Rückgaben — *klein*

`Messwerte = dict[str, NumericValue]`, `Scope = int | str`, `Spalten = Sequence[str]`.
Verbessert die Anzeige in der Editor-Hilfe erheblich, ohne Verhaltensänderung.

---

## Teil F — Vorgeschlagene Reihenfolge

| Schritt | Inhalt | Bricht bestehenden Code? | Stand |
|---|---|---|---|
| 1 | E1 Paket-Export, E2 Namenskollision | nein | ✅ **erledigt** |
| 2 | E3 Schnellstart | nein (nur Doku) | ✅ **erledigt** |
| 2b | E10 Meldungsregel | nein (nur Doku) | offen |
| 3 | E4 Beispiele mit der Fassade | nein (neue Dateien) | ✅ **erledigt** |
| 4 | E6 empfohlener Weg je Aufgabe, E9 Fallen | nein | ✅ **erledigt** |
| 5 | E5 Kurzweg zu Messwerten | nein (additiv) | ✅ **erledigt** |
| 5b | E11 Typaliasse | nein (additiv) | offen |
| 9 | README als Einstiegsseite | nein (neue Datei) | ✅ **erledigt** |
| 6 | Sidecar-Lücke bei den Laufparametern | nein (mehr Inhalt im Sidecar) | ✅ **erledigt** |
| 6b | E7 Messparameter-Objekt | nein (additiv) | offen |
| 7 | E8 Benennung vereinheitlichen | nein — Übergangsfrist für `target=` | ✅ **erledigt** |

Die Schritte 1–6 sind rein additiv: bestehende Skripte laufen unverändert weiter. Erst Schritt 7
berührt Signaturen und gehört deshalb ans Ende, mit einer Version Übergangsfrist.

### Was Schritt 1 konkret geändert hat

| Datei | Änderung |
|---|---|
| `../src/wt_treiber_lib/wt3000_core.py` | neue Basisklasse `ConfigLocked` (+ `__all__`) |
| `../src/wt_treiber_lib/wt3000_input.py` | `ConfigLocked` → `InputLocked`, erbt aus `wt3000_core` |
| `../src/wt_treiber_lib/wt3000_deviceconfig.py` | `ConfigLocked` → `DeviceConfigLocked`, erbt aus `wt3000_core` |
| `../src/wt_treiber_lib/wt3000_rangeio.py` | `ChangesNotAllowed` erbt jetzt aus `ConfigLocked` statt `WTError` |
| `../src/wt_treiber_lib/__init__.py` | Export von 60 auf 114 Namen, nach Aufgabe gegliedert, Regel im Kopf |
| `tests/test_package_layout.py` | 15 neue Prüfsätze für beide Regeln |

### Was Schritt 2 konkret geändert hat

| Datei | Änderung |
|---|---|
| `docs/Schnellstart.md` | neu — fünf lauffähige Rezepte, IP, Schlösser, Fehler, Stolpersteine |
| `tests/test_schnellstart_doku.py` | neu — führt jeden Codeblock der Seite gegen ein simuliertes Gerät aus |

Kein Produktivcode berührt. **874 Tests grün**, `ruff check` sauber.

### Was Schritt 3 konkret geändert hat

| Datei | Änderung |
|---|---|
| `examples/01…06_*.py` | neu — sechs lauffähige Beispiele über die Fassade |
| `examples/README.md` | neu — Index mit Spalte „schreibt am Gerät“ |
| `examples/_pfad.py` | neu — macht `wt_treiber_lib` ohne Installation importierbar |
| `../src/wt_treiber_lib/stage2…stage5b.py` | Kopfblock „KEINE VORLAGE FÜR EIGENEN CODE“ + Verweis |
| `tests/test_beispiele.py` | neu — fährt jedes Beispiel gegen ein simuliertes Gerät |

An den `stage*`-Skripten wurde **nur der Kommentarkopf** angefasst, keine Zeile Code.
**893 Tests grün**, `ruff check` über `src`, `tests` und `examples` sauber.

### Was Schritt 4 konkret geändert hat

| Datei | Änderung |
|---|---|
| `wt3000_input.py` | 5 Docstrings: `STATTDESSEN EMPFOHLEN` auf Bereichs- und Autorange-Settern |
| `wt3000_rangeio.py` | 2 Docstrings: dieselbe Kennzeichnung auf `set_range` / `set_auto` |
| `wt3000_ranging.py` | `applied_ranges()` als `EMPFOHLENER WEG` gekennzeichnet |
| `wt3000_deviceconfig.py` | `running()` empfohlen, `start()` verweist darauf |
| `wt3000_device.py` | 5 Docstrings; `read_mapped()` warnt beim 2. tabellenlosen Aufruf; neue `_warn_ohne_limit()` in `record()`, `start()`, `stream()` |
| `wt3000_itemspec.py` | `build_item_table()` meldet ungeprüfte Funktionen (`verify=True`) |
| `tests/test_wegweiser_und_fallen.py` | neu — 26 Prüfsätze für beide Regeln |

Verhaltensänderung: **ausschließlich zusätzliche Protokollzeilen.** Keine Signatur, kein
Rückgabewert, kein Kommando an das Gerät hat sich geändert. **919 Tests grün**, `ruff` sauber.

### Was Schritt 5 konkret geändert hat

| Datei | Änderung |
|---|---|
| `wt3000_itemspec.py` | neu: `spec_from_key()`, `specs_from_keys()` — die Umkehrung von `NumericItem.key` |
| `wt3000_device.py` | `ItemAccess.from_keys()`; `table` optional in `record`/`record_csv`/`start`/`stream` über den neuen Helfer `_tabelle()` |
| `__init__.py` | `spec_from_key`, `specs_from_keys` exportiert |
| `docs/Schnellstart.md`, `examples/02…04` | auf den kurzen Weg umgestellt |
| `tests/test_kurzweg.py` | neu — 24 Prüfsätze, darunter die Rundreise über 186 Items |

Additiv: die alte Aufrufform bleibt gültig, `table` steht unverändert an zweiter Stelle (ein
Prüfsatz hält die Parameterposition fest). **943 Tests grün**, `ruff` sauber.

### Was Schritt 7 konkret geändert hat

| Datei | Änderung |
|---|---|
| `wt3000_common.py` | neuer Alias `Scope = int \| str`, vier Signaturen darauf umgestellt |
| `wt3000_input.py` | 67× `target` → `scope`, `target_node()` → `scope_node()`, neuer Übergangs-Dekorator `_accept_target_alias` auf 15 Settern |
| `wt3000_rangeio.py`, `wt3000_ranging.py` | 6 Typangaben auf `Scope` vereinheitlicht |
| `wt3000_itemspec.py` | `ItemSpec` nimmt Zahlen für `element`/`order`, weist `bool` ab |
| `__init__.py` | `Scope` exportiert |
| 3 Paketdateien | die 5 versehentlichen echten Umlaute auf die ASCII-Hauskonvention gezogen |
| `tests/test_scope_and_items.py` | folgt der Umbenennung von `scope_node` |
| `tests/test_benennung.py` | neu — 50 Prüfsätze |

Der einzige Schritt bisher, der Signaturen berührt — aber **nicht brechend**: `target=` wirkt
weiter. Die zwei bestehenden Aufrufer in `tests/test_geraetebezug.py` sind bewusst **nicht**
umgestellt worden; sie sind der laufende Beleg dafür, dass die Übergangsfrist trägt (sichtbar als
zwei `DeprecationWarning` im Testlauf). **993 Tests grün**, `ruff` sauber.

Kein Verhalten geändert, keine Signatur geändert, nichts entfernt. **861 Tests grün**,
`ruff check` sauber.

---

### Was Schritt 8 konkret geändert hat — die Sidecar-Lücke

Beim Erklären von E7 nachgemessen und dabei gefunden: `MeasureControl._run_parameters()` schrieb
die Laufparameter von Hand ab und ließ dabei **drei von acht** aus. Zwei davon sind ein Datenfehler
und keine Auslassung:

| Parameter | Warum er in die Metadaten gehört |
|---|---|
| `mark_duplicates` | Ist es aus, trägt kein Datensatz die Marke `DUPLICATE` und `result.duplicates` steht auf 0. Ohne die Angabe lässt sich **„es gab keine Wiederholungen" nicht von „Wiederholungen wurden nicht gekennzeichnet" unterscheiden** — und beides sieht in der CSV gleich aus. |
| `error_policy` | Entscheidet, ob ein ausgefallener Zyklus als `MISSING`-Zeile in der Datei steht oder den Lauf beendet. Ohne die Angabe ist eine Lücke in den Daten nicht einzuordnen. |
| `check_update_rate` | Erklärt, ob `result.update_rate_s` überhaupt erhoben wurde. |

`log_every` bleibt bewusst draußen: es steuert die Kadenz der Protokollzeilen und berührt weder die
Daten noch ihre Deutung. Ein Sidecar, das jede Stellschraube mitschreibt, macht die Angaben, auf
die es ankommt, schwerer auffindbar.

`error_policy` steht als **Objekt** im JSON, nicht als `repr()` — eine Zeichenkette
`ErrorPolicy(max_consecutive=5, …)` wäre lesbar, aber von keinem Auswerteskript zu gebrauchen:

```json
"error_policy": { "max_consecutive": 5, "max_total": null,
                  "reconnect_after": 2, "max_reconnects": 10, "pause_s": 0.0 }
```

**Die Ursache war strukturell**, und dagegen hilft kein einmaliger Nachtrag: die Feldliste existiert
an fünf Stellen (vier Signaturen plus `_run_parameters`) und wird von Hand synchron gehalten. Der
saubere Fix ist E7 — ein Datenobjekt, aus dem sich die Liste *ableitet*. Bis dahin hält
`tests/test_sidecar_vollstaendigkeit.py` (14 Prüfsätze) die Zuordnung: es vergleicht die **Signatur
von `record()`** gegen zwei Listen — was ins Sidecar gehört und was mit Begründung nicht — und wird
rot, sobald ein Parameter in keiner von beiden steht.

Gegenprobe gemacht: `record()` versuchsweise um einen Parameter erweitert →

```
AssertionError: record() hat Parameter, die niemand eingeordnet hat: ['neue_stellschraube'].
Gehoeren sie ins Sidecar? Dann in IN_DIE_METADATEN eintragen, sonst mit Begruendung
in BEWUSST_DRAUSSEN.
```

Damit kann die Liste nicht mehr stillschweigend abdriften. **1007 Tests grün**, `ruff` sauber.

---

### Was Schritt 9 konkret geändert hat — das README

`README.md` in der Projektwurzel: der Einstieg für jemanden, der das Repository zum ersten Mal
öffnet. Inhalt in dieser Reihenfolge — was es ist, ein Beispiel, was die Bibliothek anders macht
(die zwei Schlösser, der Rückweg, das Sidecar, `FakeTransport`), Installation, die
IP-Auflösungskette, ein Wegweiser in die drei Dokumente, der Aufbau, Entwicklung, Stand.

**Beim Schreiben gefunden und behoben:** das erste Beispiel des READMEs schrieb
`record_csv("messreihe.csv", …)` — mit einem blossen Dateinamen, also der Schreibweise, die jeder
zuerst versucht. Das scheiterte mit einem `AttributeError: 'str' object has no attribute 'name'`
tief in der Senke, weit weg von der Stelle, an der der Fehler steht. Statt das Beispiel um ein
`Path(...)` zu verbiegen, nimmt `record_csv()` jetzt `Path | str` — eine Zeile Umwandlung.
Ein `AttributeError` im allerersten Beispiel wäre der schlechteste denkbare Einstieg gewesen.

**Abgesichert:** `tests/test_readme.py` (13 Prüfsätze) führt den Codeblock aus, weist nach dass er
CSV **und** Sidecar anlegt und **am Draht kein einziges Set-Kommando sendet** (das README sagt es
im Kommentar zu), übersetzt die übrigen Ausschnitte, prüft die JSON-Beispiele, und hält die
Behauptungen gegen die Wirklichkeit: jeder Verweis zeigt auf eine vorhandene Datei, die genannten
Verzeichnisse existieren, Mindest- und Paketversion stimmen mit `pyproject.toml` und
`__version__` überein, und die vier namentlich genannten gesperrten Gruppen stimmen mit
`DEFAULT_PROTECTED` überein.

Gegenprobe gemacht: ein Verweisziel versuchsweise auf eine nicht vorhandene Datei gezeigt →
`AssertionError: das README zeigt ins Leere: ['examples/GIBTSNICHT.md']`.

**Nebenbei aufgeräumt:** das Geräte­modell für Ablauftests stand doppelt in
`test_schnellstart_doku.py` und `test_beispiele.py` — eine Doppelung, die in Schritt 3 entstanden
war. Es liegt jetzt in `conftest.py` neben seinem Elternteil `ItemTableTransport`; drei Testmodule
teilen es.

Damit ist die Dokumentationskette geschlossen und **jede Stufe davon wird ausgeführt**:

| Ebene | Datei | wird geprüft von |
|---|---|---|
| Einstieg | `README.md` | `tests/test_readme.py` |
| Rezepte | `docs/Schnellstart.md` | `tests/test_schnellstart_doku.py` |
| Skripte | `examples/*.py` | `tests/test_beispiele.py` |
| Referenz | `docs/API-Ueberblick-und-Lesbarkeit.md` | — (Fließtext) |

---

## Teil G — Offene Fragen

1. ~~**Zielsprache der API:** deutsch oder englisch?~~ **Entschieden (2026-08-27):** englische
   Bezeichner behalten, deutsche Doku ausbauen. Neue Namen folgen dieser Regel — `InputLocked`
   und `DeviceConfigLocked` aus E2 sind die ersten.
2. **Dürfen `stage*`-Skripte aus dem Paket verschwinden,** oder werden sie anderweitig verwendet
   (z. B. per `python -m wt3000_scpi.stage4_measure` in bestehenden Abläufen)?
3. ~~**Ist die Testsuite die Rückversicherung für den Umbau, d. h. läuft sie grün?**~~
   **Beantwortet:** ja — **861 Tests, alle grün**, Laufzeit ~6 s, gerätefrei.

   Aber: das **`.venv` des Projekts ist unbrauchbar** — dort fehlt nicht nur `pytest`, sondern auch
   `pip` selbst (`No module named pip`). Geprüft wurde deshalb mit dem System-Python 3.14 und
   `PYTHONPATH=src`; `pytest` und `ruff` liegen jetzt unter `--user`, nicht im `.venv`.
   **Offen:** soll das `.venv` neu aufgesetzt werden?

   ```bash
   python -m venv --clear .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"
   ```
4. **`GROUP_RANGE` ist geschützt, `GROUP_AUTO` nicht.** Ist das gewollt, oder soll Autorange
   ebenfalls unter die Gruppensperre?
