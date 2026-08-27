# WT3000-Treiber: API-Überblick und Lesbarkeitsanalyse

**Stand:** 2026-08-27 · **Paket:** `wt3000_scpi` 0.3.0 · **Basis:** Kopie von `wt_treiber_V3e`
**Zweck dieser Datei:** Bestandsaufnahme und Umbauplan.

> **Umsetzungsstand:** **E1** (Paket-Export vervollständigt) und **E2** (Namenskollision
> `ConfigLocked` aufgelöst) sind **erledigt** — siehe Teil F. Testsuite danach: **861 Tests grün**,
> `ruff` sauber. Die Befunde D2 und D5 sind entsprechend als erledigt gekennzeichnet und
> beschreiben ab Teil D den Zustand *vor* dem Eingriff, damit die Begründung nachvollziehbar bleibt.

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
from wt3000_scpi import WT3000

with WT3000.connect(ip="192.168.10.20") as wt:      # rein lesend
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
| Zielangabe je Setter | `target=1` / `"SIGMA"` / `"ALL"` (Vorgabe) | | `ALL` = die bestückten Elemente **dieses** Objekts |
| Scope auflösen | `wt.ranges.expand_scope("SIGMA")` → `(1,2,3)` | – | |

### C.4 Messbereich (Range) — **drei Wege, siehe Befund D4**

**Weg 1 — `wt.input`** (prüft gegen die erlaubten Stufen, liest zur Kontrolle zurück):

| Aufgabe | Aufruf | Sperre |
|---|---|---|
| Spannungsbereich lesen | `wt.input.get_voltage_range(1)` → `float` V | – |
| Strombereich lesen | `wt.input.get_current_range(1)` → `(A, V_sensor)` | – |
| Spannungsbereich setzen | `wt.input.set_voltage_range(300.0, target="ALL")` | **AC+G** `GROUP_RANGE` |
| Strombereich setzen (direkt) | `wt.input.set_current_range(5.0, target=1)` | **AC+G** `GROUP_RANGE` |
| Strombereich setzen (Sensor) | `wt.input.set_current_range_sensor(10.0, target=1)` | **AC+G** `GROUP_RANGE` |
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
from wt3000_scpi import Quantity, RangePlan, RangeSpec, AutoRangeSpec

plan = RangePlan.of(
    RangeSpec(Quantity.VOLTAGE, "ALL", 300.0),
    RangeSpec(Quantity.CURRENT, 1, 10.0, sensor=True),
    AutoRangeSpec(Quantity.CURRENT, 4, False),
)
with wt.applied_ranges(plan, backup_file=Path("bereiche.json")) as report:
    ...        # hier stehen die Bereiche nach Plan
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
| Setzen (Weg 1) | `wt.input.set_voltage_auto_range(True, target="ALL")` | **AC** (`GROUP_AUTO` ist *nicht* geschützt) |
| Setzen (Weg 1, Strom) | `wt.input.set_current_auto_range(True, target="ALL")` | **AC** |
| Setzen (Weg 2) | `wt.ranges.set_auto(Quantity.VOLTAGE, "ALL", True)` | **AC** |
| Setzen (Weg 3, im Plan) | `AutoRangeSpec(Quantity.VOLTAGE, "ALL", True)` | **AC** |

> Ein fester Bereich impliziert Autorange AUS — das erledigt `apply_plan()` von selbst.

### C.6 Weitere Eingangseinstellungen (alle über `wt.input`)

| Aufgabe | Lesen | Setzen | Sperre |
|---|---|---|---|
| Line-Filter | `get_line_filter(1)` | `set_line_filter(LineFilter.HZ500, target="ALL")` | AC+G `GROUP_FILTER` |
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
from wt3000_scpi import ConfigLocked, ReadOnlyViolation

try:
    wt.input.set_voltage_range(300.0)
except ReadOnlyViolation:
    print("Sitzung ist nur lesend - read_only=False setzen")
except ConfigLocked as fehler:
    print(f"Sperre des Fachobjekts: {fehler}")   # nennt selbst den Ausweg
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
from wt3000_scpi import GROUP_RANGE
with wt.input.unlocked(GROUP_RANGE):
    wt.input.set_voltage_range(300.0)
```

---

## Teil D — Befunde: was den Einstieg heute schwer macht

Die Bibliothek ist inhaltlich stark: Sperren, Rückwege im `finally`, Verifikation nach jedem
Schreiben, sehr gute Fehlermeldungen, ausführliche Docstrings mit Begründungen. **Die Schwäche
liegt nicht in der Funktion, sondern im Zugang.** Die Befunde sind nach Wirkung sortiert.

### D1 — Es gibt keine Dokumentation außerhalb des Quelltextes 🔴

Kein `README`, kein `docs/`, kein Schnellstart. Das gesamte Wissen steckt in Docstrings — für
jemanden mit wenig Programmiererfahrung praktisch unsichtbar, solange er nicht weiß, in welcher
Datei er nachschlagen muss. Das ist die **größte Einzelhürde**, und sie liegt vollständig außerhalb
des Codes.

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

### D3 — Die Beispiele im Paket zeigen den umständlichen Weg 🔴

`stage2…stage5b` liegen **im Paket** (`src/wt3000_scpi/`) und benutzen durchweg die tiefe API:
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

Wer im Paket nach einer Vorlage sucht, findet die alte Form zuerst — und kopiert sie. Nur
`live_messwerte.py` (Projektwurzel) benutzt die Fassade und ist damit das eigentliche Vorbild.

### D4 — Drei Wege zum selben Ziel, ohne erkennbare Empfehlung 🟠

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

### D6 — „Element“ heißt an vier Stellen anders und hat zwei Typen 🟠

| Modul | Parametername | Typ | Beispiel |
|---|---|---|---|
| `wt3000_input` | `target` | `int \| str` | `target=1`, `target="ALL"` |
| `wt3000_rangeio` / `RangeSpec` | `scope` | `str \| int` | `scope="SIGMA"`, `scope=1` |
| `ItemSpec` | `element` | **`str \| None`** | `element="1"` — **Zeichenkette!** |
| `DeviceInfo` / `RangeAccess` | `elements` | `tuple[int, ...]` | `(1, 2, 3, 4)` |

Für dieselbe Sache — „welches Element meine ich“ — gibt es drei Parameternamen und zwei Typen.
`ItemSpec("U", 1)` statt `ItemSpec("U", "1")` ist ein naheliegender Fehler.

### D7 — Vier Messmethoden mit je 14–18 identischen Parametern 🟠

`record`, `record_csv`, `start`, `stream` wiederholen dieselbe Parameterliste. Die Signaturen
füllen im Editor mehr als einen Bildschirm; der Einsteiger sieht keine kurze Form und weiß nicht,
welche drei Parameter er tatsächlich braucht (`tabelle`, `interval_s`, ein Limit). Wirkungsvolle
Vorgaben wie `use_hold=True` oder `check_update_rate=True` verschwinden im Rauschen.

### D8 — Der Weg von „ich will U, I, P“ zu Messwerten ist lang 🟠

Die Item-Tabelle ist der schwerste Begriff der Bibliothek und steht dem Anfänger als erstes im Weg.
Um eigene Größen zu messen, muss er `ItemSpec` → `build()` → `apply()` → `verify()` → `restore()`
verstehen (oder `wt.items.applied()` finden). Es gibt keinen Aufruf der Art
`wt.measure.messen(["U1", "I1", "P1"])`.

Der einfache Ausweg **existiert** — `wt.items.read()`, „miss, was am Gerät eingestellt ist“ — steht
aber nur in einem Kommentar in `live_messwerte.py` und in keinem Docstring als *der* Einstieg.

### D9 — Nicht offensichtliche Fallen 🟡

- `wt.measure.read_mapped()` **ohne** Argument liest die Item-Tabelle bei **jedem Aufruf** neu vom
  Gerät. In einer Schleife ist das eine unnötige Abfrage je Durchlauf.
- Während `wt.measure.start()` läuft, gehört die Sitzung dem Mess-Thread: jeder Zugriff auf
  `wt.input` / `wt.ranges` endet in `ConcurrentAccessError`. Steht im Docstring, ist aber der
  häufigste Anfängerfehler bei Prüfstandsabläufen.
- `wt.device.supports()` liefert **`True`**, wenn `*OPT?` fehlgeschlagen ist („unbekannt ≠ fehlt“).
  Sachlich richtig, für „darf ich?“ aber überraschend.
- `record()` ohne Limit läuft **unbegrenzt**. Absicht, aber im fremden Skript selten gewollt.
- `if_exists="overwrite"` ist die Vorgabe von `CsvSink` — eine vorhandene Messdatei wird
  überschrieben (immerhin protokolliert).
- `ItemSpec(..., verify=True)` markiert Funktionen, die **am Originalgerät noch nicht bestätigt**
  sind (das ganze Integrations- und Oberschwingungsprofil). Der Anwender sieht diese Kennzeichnung
  nirgends im Ergebnis.

### D10 — Sprachmix 🟡

Doku und Kommentare deutsch, öffentliche Bezeichner englisch (`get_wiring`, `record_csv`,
`max_samples`), interne Variablen teils deutsch (`senke`, `tabelle`, `messung`, `lauf_parameter`,
`zu_aendern`). Für die Zielgruppe (deutschsprachige Messtechnik) ist der englische API-Name in
Ordnung — die Uneinheitlichkeit im Inneren erschwert aber das Lesen fremden Codes.
Auch die Umlautvermeidung („Geraet“, „Messbereiche zurueckstellen“) ist in Docstrings, die dem
Anwender im Editor angezeigt werden, ein Lesehindernis.

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
verlangt, aus `wt3000_scpi` importierbar ist**. Die Regel steht im Kopf der Datei:

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

### E3 🔴 Ein Schnellstart, der auf eine Seite passt — *klein*

`docs/Schnellstart.md` (oder `README.md`) mit genau fünf lauffähigen Rezepten, in dieser
Reihenfolge:

1. Verbinden und Gerät ansehen (nur lesend)
2. Messen, was am Gerät eingestellt ist → CSV *(der Einstieg — `wt.items.read()`)*
3. Eigene Größen messen *(Profil oder `ItemSpec`-Liste)*
4. Bereiche für die Messung setzen und danach zurückstellen *(`applied_ranges`)*
5. Messung im Hintergrund starten, Prüfstand fahren, beenden *(`start()`/`stop()`)*

Jedes Rezept vollständig, kopierfähig, mit einem Satz „wann nimmt man das“. Kein Fließtext über
Architektur — die Schichten interessieren den Anwender nicht.

### E4 🔴 Die Stufenskripte umbauen oder verschieben — *mittel*

Drei Möglichkeiten, in dieser Vorzugsreihenfolge:

1. **`examples/` in der Projektwurzel**, geschrieben **mit der Fassade**, sprechend benannt
   (`01_geraet_ansehen.py`, `02_messreihe_csv.py`, `03_bereiche_setzen.py`,
   `04_hintergrundmessung.py`, `05_integration_wh.py`) — `live_messwerte.py` wird `00_…` und ist
   das Muster.
2. Die alten `stage*`-Skripte nach `tools/legacy/` verschieben und im Kopf vermerken, dass sie den
   Weg **vor** der Fassade zeigen.
3. Mindestens: in jedem `stage*`-Kopf drei Zeilen ergänzen, wie dasselbe mit `WT3000` aussieht.

Solange die umständliche Form im Paket der auffälligste Beispielcode ist, arbeitet die Dokumentation
gegen sich selbst.

### E5 🟠 Einen kurzen Weg zu Messwerten anbieten — *mittel*

Der Einstiegssatz sollte ein Einzeiler sein. Zwei Ergänzungen, additiv, ohne Bruch:

```python
# a) messen, was eingestellt ist - ohne Item-Tabelle im Skript
stats = wt.measure.record_csv(Path("m.csv"), max_samples=60)      # table optional
                                                                   # → wt.items.read()

# b) eigene Größen ohne ItemSpec-Vokabular
tabelle = wt.items.von_namen(["U1", "I1", "P1", "P_SIGMA"])
```

`von_namen()` (bzw. `from_keys()`) ist reine Übersetzung: Spaltenname → `ItemSpec`. Die
`key`-Schreibweise kennt der Anwender bereits aus jeder CSV-Kopfzeile, die die Bibliothek erzeugt —
damit schließt sich der Kreis zwischen Ausgabe und Konfiguration.

### E6 🟠 Einen empfohlenen Weg je Aufgabe benennen — *klein bis mittel*

Für jede Aufgabe mit mehreren Wegen (Bereich, Autorange, Messen) im Docstring **eine** Zeile
voranstellen:

> **Empfohlen:** `wt.applied_ranges(plan)` — setzt, prüft und stellt zurück.
> `wt.ranges.set_range()` ist der rohe Einzelzugriff ohne Rückweg.

Zusätzlich eine Übersichtstabelle wie C.4/C.5 dieser Datei in die Doku. Kein Code muss entfernt
werden — nur die Rangfolge muss sichtbar sein.

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

### E8 🟠 Benennung vereinheitlichen — *mittel, teils brechend*

- Ein Begriff für „welches Element“: `scope` überall (oder `target` überall), mit einem Typalias
  `Scope = int | str`. `target=` als veralteter Zweitname eine Version lang mitführen.
- `ItemSpec.element` soll `int | str` annehmen und intern in die Zeichenkette wandeln —
  `ItemSpec("U", 1)` muss funktionieren.
- Interne Variablen einheitlich benennen (durchgängig deutsch **oder** englisch, nicht gemischt).
- Umlaute in Docstrings zulassen (die Dateien sind UTF-8) — „Gerät“ liest sich für die Zielgruppe
  deutlich besser als „Geraet“.

### E9 🟡 Die Fallen aus D9 sichtbar machen — *klein*

- `read_mapped()` die Tabelle einmal merken lassen (oder im Docstring ausdrücklich warnen).
- `record()`/`start()` ohne jedes Limit einmal per `_log.warning` melden: „kein Limit gesetzt —
  Ende nur mit Strg+C“ (macht `stage4` bereits; gehört in die Fassade).
- In der Doku ein Kasten „Was während `start()` nicht geht“ mit dem Verweis auf `stream()`.
- `verify=True`-Items in der Ausgabe kennzeichnen (Sidecar-Feld „ungeprüfte Funktionen“).

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
| 2 | E3 Schnellstart, E10 Meldungsregel | nein (nur Doku) | offen |
| 3 | E4 Beispiele mit der Fassade | nein (neue Dateien) | offen |
| 4 | E6 empfohlener Weg je Aufgabe, E9 Fallen | nein | offen |
| 5 | E5 Kurzweg zu Messwerten, E11 Typaliasse | nein (additiv) | offen |
| 6 | E7 Messparameter-Objekt | nein (additiv) | offen |
| 7 | E8 Benennung vereinheitlichen | **teilweise** — eigener Schritt, mit Übergangsnamen | offen |

Die Schritte 1–6 sind rein additiv: bestehende Skripte laufen unverändert weiter. Erst Schritt 7
berührt Signaturen und gehört deshalb ans Ende, mit einer Version Übergangsfrist.

### Was Schritt 1 konkret geändert hat

| Datei | Änderung |
|---|---|
| `src/wt3000_scpi/wt3000_core.py` | neue Basisklasse `ConfigLocked` (+ `__all__`) |
| `src/wt3000_scpi/wt3000_input.py` | `ConfigLocked` → `InputLocked`, erbt aus `wt3000_core` |
| `src/wt3000_scpi/wt3000_deviceconfig.py` | `ConfigLocked` → `DeviceConfigLocked`, erbt aus `wt3000_core` |
| `src/wt3000_scpi/wt3000_rangeio.py` | `ChangesNotAllowed` erbt jetzt aus `ConfigLocked` statt `WTError` |
| `src/wt3000_scpi/__init__.py` | Export von 60 auf 114 Namen, nach Aufgabe gegliedert, Regel im Kopf |
| `tests/test_package_layout.py` | 15 neue Prüfsätze für beide Regeln |

Kein Verhalten geändert, keine Signatur geändert, nichts entfernt. **861 Tests grün**,
`ruff check` sauber.

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
