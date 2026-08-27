# WT3000 — Schnellstart

Fünf Rezepte für Messautomationsskripte. Jedes ist vollständig und lauffähig: kopieren, IP
eintragen, starten. Wer eines davon versteht, kommt mit den übrigen vier ohne weitere Erklärung
zurecht.

**Alles kommt aus einem Import.** Ein `from wt3000_scpi.wt3000_irgendwas import ...` ist im
Anwenderskript nie nötig — wenn doch, ist das ein Fehler der Bibliothek, kein Fehler des Skripts.

```python
from wt3000_scpi import WT3000
```

> Jeder Python-Block dieser Seite wird von `tests/test_schnellstart_doku.py` gegen ein simuliertes
> Gerät **ausgeführt** — mit heruntergedrehtem Takt, sonst wortwörtlich. Ein Rezept, das nicht mehr
> läuft, lässt die Testsuite rot werden.
>
> **Lieber ein fertiges Skript zum Starten?** Dieselben Rezepte liegen als lauffähige Dateien in
> [`examples/`](../examples/README.md) — `python examples/01_geraet_ansehen.py`.

---

## Vorher: die IP

Der Treiber sucht die Verbindungsdaten in dieser Reihenfolge — der erste Treffer gewinnt:

1. das Argument: `WT3000.connect(ip="192.168.10.20")`
2. die Umgebungsvariable `WT3000_IP`
3. eine Datei `wt3000.json` im Arbeitsverzeichnis oder einem Verzeichnis darüber
4. die Vorgabe (leer → Fehlermeldung mit Verweis auf diese Kette)

Für ein festes Labor ist Nummer 3 das Bequemste — dann steht in keinem Skript eine IP:

```json
{ "ip": "192.168.10.20", "timeout_ms": 5000 }
```

## Vorher: die zwei Schlösser

Beide sind in der Voreinstellung **zu**. Wer nur misst, fasst keines an.

| | Vorgabe | öffnen mit | wirkt auf |
|---|---|---|---|
| `read_only` | `True` | `read_only=False` | die Sitzung — lässt kein Set-Kommando durch |
| `allow_changes` | `False` | `allow_changes=True` | die Fachobjekte — lehnen Schreibaufrufe vorher ab |

```python
with WT3000.connect() as wt:                                    # nur messen (Rezept 1, 2)
with WT3000.connect(read_only=False, allow_changes=True) as wt:  # auch stellen (Rezept 3, 4, 5)
```

Vier Gruppen bleiben auch dann gesperrt, weil sie den eingemessenen Zustand festlegen:
`WIRING`, `RANGE`, `SCALING`, `CFACTOR`. Die gibt man einzeln und sichtbar frei — siehe
„Stolpersteine“ unten.

---

## Rezept 1 — Gerät ansehen

*Wann:* zuerst. Prüft die Verbindung und zeigt, womit man es zu tun hat — Modell, Optionen,
Verdrahtung, bestückte Elemente. Verändert nichts.

```python
from wt3000_scpi import WT3000

with WT3000.connect(ip="192.168.10.20") as wt:
    for zeile in wt.device.describe():
        print(zeile)

    print("SIGMA sind: ", wt.ranges.expand_scope("SIGMA"))
    print("Update-Rate:", wt.input.get_update_rate(), "s")
```

Ausgabe (Elemente 2 und 3 der Kürze halber weggelassen):

```
Geraet:      WT3000 (YOKOGAWA)
Seriennr.:   C1B234567    Firmware: F2.11
Optionen:    B5, C5, C7, CC, DT, G6
Verdrahtung: V3A3, P1W2
Elemente:    (1, 2, 3, 4)
  Nicht ansprechbar (Option fehlt): :FLICker (FL), :AOUTput (DA), :MOTor (Modellvariante -MV)
  Element 1: 30-A-Element
  Element 4: 30-A-Element
  Unit SIGMA: V3A3 auf Elementen (1, 2, 3)
  Unit SIGMB: P1W2 auf Elementen (4,)
SIGMA sind:  (1, 2, 3)
Update-Rate: 1.0 s
```

Die Zeile „Nicht ansprechbar“ ist die nützlichste der Ausgabe: sie sagt vorab, welche
Kommandogruppen an *diesem* Gerät mangels Option ins Leere laufen würden — statt dass man es
später an einem Timeout merkt, der wie ein Verbindungsabbruch aussieht.

---

## Rezept 2 — Messen, was am Gerät eingestellt ist

*Wann:* der übliche Einstieg. **Das Skript stellt nichts um** — es misst genau die Größen, die
jemand am Bedienfeld eingestellt hat, und schreibt sie in eine CSV. Ungefährlich und deshalb der
richtige erste Versuch am realen Gerät.

```python
from pathlib import Path
from wt3000_scpi import WT3000

ziel = Path("messungen")
ziel.mkdir(parents=True, exist_ok=True)          # der Treiber legt kein Verzeichnis an

with WT3000.connect(ip="192.168.10.20") as wt:
    # OHNE 'table' wird die Item-Tabelle des Geraets uebernommen - gemessen
    # wird also, was am Bedienfeld eingestellt ist. Wer die Spalten vorher
    # sehen will, holt sie sich mit 'tabelle = wt.items.read()'.
    stats = wt.measure.record_csv(
        ziel / "messreihe.csv",
        interval_s=1.0,        # Takt DIESER Schleife, nicht die Geraeterate
        max_samples=60,        # ohne Limit laeuft sie bis Strg+C
        use_hold=False,        # HOLD ist ein Set-Kommando - hier nicht erlaubt
        sidecar=True,          # legt messreihe.csv.meta.json daneben
    )

stats.log_summary(1.0)
print(f"{stats.measured_samples} echte Messpunkte, {stats.duplicates} Wiederholungen")
```

`sidecar=True` ist die Zeile, die man nicht vergessen sollte: erst damit ist die CSV ohne
Zusatzwissen interpretierbar — Gerät, Verdrahtung, Item-Tabelle, Laufparameter und Prüfsummen
stehen in der Datei daneben. Nachträglich prüfen lässt sich das mit
`verify_sidecar(Path("messungen/messreihe.csv"))`.

**Ergebnis:**

```
timestamp_iso,elapsed_s,sample,condition,U1,I1,P1,...,status_flags
2026-08-27T10:14:03.512+02:00,0.000,1,0,229.87,4.981,1144.9,...,
```

---

## Rezept 3 — Eigene Größen messen

*Wann:* wenn die Spalten der CSV feststehen sollen, unabhängig davon, was am Gerät eingestellt ist.
Dafür wird die Item-Tabelle geschrieben — und deshalb **beide Schlösser geöffnet**.

```python
from pathlib import Path
from wt3000_scpi import WT3000

ziel = Path("messungen")
ziel.mkdir(parents=True, exist_ok=True)

# Die Spalten als Namen - dieselben, die spaeter in der CSV-Kopfzeile stehen.
# Achtung: der Summenwert heisst 'PSIGMA', nicht 'P_SIGMA'; der Unterstrich
# trennt ausschliesslich die Ordnung ab ('PHI1_1').
SPALTEN = ["U1", "I1", "P1", "U2", "I2", "P2", "PSIGMA", "LAMBDASIGMA"]

with WT3000.connect(ip="192.168.10.20", read_only=False, allow_changes=True) as wt:
    with wt.ensured_protocol_state():
        # Setzt die Tabelle, prueft sie zurueck und stellt am Blockende in
        # JEDEM Fall den Ausgangszustand wieder her - auch bei Strg+C.
        with wt.items.applied(
            wt.items.from_keys(SPALTEN), backup_file=ziel / "itemtabelle_backup.json"
        ) as tabelle:
            stats = wt.measure.record_csv(
                ziel / "eigene_groessen.csv",
                tabelle,
                interval_s=1.0,
                max_samples=30,
                sidecar=True,
            )

stats.log_summary(1.0)
```

Wer Ordnungen oder Sonderfaelle braucht, nimmt statt der Namen weiterhin
`ItemSpec` unmittelbar — `wt.items.applied([ItemSpec("PHI", "1", "1"), ...])`.

Statt einer eigenen Liste tun es oft die fertigen Profile:

```python
wt.items.standard_profile()      # U, I, P, S, Q, LAMBDA, PHI je Element + SIGMA
wt.items.integration_profile()   # TIME, WH, AH, ... fuer eine Wh-/Ah-Messung
wt.items.harmonics_profile(orders=(1, 3, 5, 7))   # Oberschwingungen
```

> `ensured_protocol_state()` stellt `:COMMunicate:HEADer 0`, `:VERBose 0` und
> `:NUMeric:FORMat FLOat` her — ohne die scheitert das Auslesen — und nimmt beides am Blockende
> zurück. Steht der Zustand schon richtig, tut der Block nichts. Er wird **absichtlich nicht**
> automatisch gerufen: ein Messaufruf, der unangekündigt am Gerätezustand dreht, wäre das
> Gegenteil dessen, wofür die zwei Schlösser da sind.

---

## Rezept 4 — Messbereiche setzen und danach zurückstellen

*Wann:* wenn die Messung feste Bereiche braucht. Der Plan wird gesetzt, geprüft und am Blockende
garantiert zurückgestellt — auch bei einem Fehler oder Strg+C mitten in der Messung.

```python
from pathlib import Path
from wt3000_scpi import WT3000, Quantity, RangePlan, RangeSpec, AutoRangeSpec

ziel = Path("messungen")
ziel.mkdir(parents=True, exist_ok=True)

plan = RangePlan.of(
    RangeSpec(Quantity.VOLTAGE, "ALL", 600.0),         # scope: Element, "SIGMA" oder "ALL"
    RangeSpec(Quantity.CURRENT, 4, 10.0),
    AutoRangeSpec(Quantity.CURRENT, "SIGMA", True),    # Autorange fuer Element 1-3 EIN
)
print("\n".join(plan.describe()))

with WT3000.connect(ip="192.168.10.20", read_only=False, allow_changes=True) as wt:
    with wt.applied_ranges(plan, backup_file=ziel / "bereiche_backup.json") as bericht:
        stats = wt.measure.record_csv(
            ziel / "mit_bereichen.csv", max_samples=30, sidecar=True
        )
    # hier stehen die Bereiche wieder wie vorgefunden
    print("Abweichungen nach dem Ruecksetzen:", bericht.restore_problems or "keine")
```

Ein fester Bereich schaltet Autorange für dieselbe Größe von selbst aus — das erledigt der Plan.
Welche Stufen das Gerät annimmt, muss man nicht raten:

```python
from wt3000_scpi import VOLTAGE_RANGES, CURRENT_RANGES, SENSOR_RANGES, UPDATE_RATES_S

VOLTAGE_RANGES[3]        # Crest-Faktor 3: (15.0, 30.0, ..., 600.0, 1000.0) in V
CURRENT_RANGES[(30, 3)]  # 30-A-Element, CF 3: (0.5, 1.0, ..., 30.0) in A
SENSOR_RANGES[3]         # externer Stromsensor, CF 3: (0.05, ..., 10.0) in V
UPDATE_RATES_S           # (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0)
```

`allow_snapping=True` an `applied_ranges()` erlaubt dem Gerät, einen Zwischenwert auf die nächste
gültige Stufe zu runden; ohne den Schalter gilt eine Abweichung als Fehler.

---

## Rezept 5 — Im Hintergrund messen, währenddessen den Prüfstand fahren

*Wann:* wenn das Skript während der Messung etwas anderes tun muss und das Ende nicht vorab
feststeht.

```python
from pathlib import Path
from wt3000_scpi import WT3000, CsvSink, ErrorPolicy

ziel = Path("messungen")
ziel.mkdir(parents=True, exist_ok=True)

with WT3000.connect(ip="192.168.10.20", read_only=False, allow_changes=True) as wt:
    tabelle = wt.items.read()

    with wt.measure.start(
        CsvSink(ziel / "pruefstandslauf.csv"),
        tabelle,
        interval_s=0.5,
        error_policy=ErrorPolicy.unattended(),   # Aussetzer ueberstehen statt abbrechen
        sidecar=True,
    ) as messung:

        pruefstand_hochfahren()                  # eigener Code
        warten_bis_temperatur_erreicht()
        pruefstand_abfahren()

        stats = messung.stop()

stats.log_summary(0.5)
print(f"{stats.missing} ausgefallene Zyklen, {stats.reconnects}x neu verbunden")
```

> **Während `start()` läuft, gehört die Sitzung dem Mess-Thread.** Jeder Zugriff auf `wt.input`,
> `wt.ranges` oder `wt.items` aus dem Haupt-Thread endet in einer `ConcurrentAccessError` — das ist
> der häufigste Anfängerfehler bei Prüfstandsabläufen. Deshalb steht `wt.items.read()` oben
> **vor** dem `start()`.
>
> Wer *während* der Messung am Gerät stellen muss, nimmt `stream()` statt `start()`: dort läuft
> der Takt im eigenen Thread, und zwischen zwei Datensätzen ist die Sitzung frei.

```python
for sample in wt.measure.stream(tabelle, interval_s=1.0, max_samples=20):
    print(sample.number, sample.values[0])
    if sample.values[0].value > 250.0:
        wt.input.set_voltage_auto_range(True)     # geht hier - bei start() nicht
        break
```

---

## Ohne Gerät ausprobieren

Der Treiber läuft vollständig ohne WT3000 und ohne `tmctl.dll`. Damit lässt sich ein Skript
schreiben und durchspielen, bevor man ins Labor geht:

```python
from wt3000_scpi import WT3000, WTConfig, FakeTransport

antworten = {
    "*IDN": "YOKOGAWA,WT3000,C1B234567,F2.11",
    "*OPT": "G6,DT",
    ":INPUT:WIRING": "V3A3,P1W2",
    ":INPUT:MODULE": "30,30,30,30",
    # ... je Abfrage ein Eintrag; eine fehlende faellt als KeyError auf
}

with WT3000.from_transport(FakeTransport(antworten), WTConfig(use_remote=False)) as wt:
    print(wt.device.model)
```

Eine fehlende Antwort wird bewusst **nicht** erfunden, sondern gemeldet — so fällt auf, was das
Skript wirklich abfragt. Ein vollständigeres Gerätemodell steht in `tests/conftest.py`
(`base_responses()`, `ItemTableTransport`).

---

## Fehler lesen

Die Meldungen dieses Treibers nennen den Ausweg, nicht nur das Problem. Es lohnt sich, sie
auszugeben statt sie zu verschlucken:

```python
from wt3000_scpi import WT3000, WTError, ConfigLocked, ReadOnlyViolation

try:
    with WT3000.connect() as wt:
        ...
except ReadOnlyViolation:
    print("Sitzung ist nur lesend - read_only=False setzen")
except ConfigLocked as fehler:
    print(f"Sperre eines Fachobjekts: {fehler}")   # nennt die noetige Freigabe
except WTError as fehler:
    print(f"Fehler: {fehler}")
```

`ConfigLocked` ist die gemeinsame Basis und fängt alle drei Sperren: `InputLocked` (`wt.input`),
`DeviceConfigLocked` (`wt.integration`, `wt.computation`, `wt.harmonics`) und `ChangesNotAllowed`
(`wt.ranges`). `ReadOnlyViolation` steht bewusst daneben — das ist das *andere* Schloss.

Mehr Protokoll zeigt, was tatsächlich über die Leitung geht:

```python
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")
```

---

## Stolpersteine

| Symptom | Ursache | Abhilfe |
|---|---|---|
| `ConfigLocked: Gruppe 'RANGE' ist geschuetzt` | `allow_changes=True` genügt für die vier eingemessenen Gruppen nicht | `with wt.input.unlocked(GROUP_RANGE): ...` — oder `wt.applied_ranges(plan)` nehmen, das braucht keine Freigabe |
| `ConcurrentAccessError` | Gerätezugriff, während `start()` läuft | alles Nötige vor `start()` lesen, oder `stream()` nehmen |
| `FileNotFoundError` beim Schreiben der CSV | der Treiber legt kein Verzeichnis an | `ziel.mkdir(parents=True, exist_ok=True)` |
| Messung endet nie | `record()`/`start()` ohne Limit läuft unbegrenzt | `max_samples=` oder `max_duration_s=` setzen |
| Viele `DUPLICATE`-Zeilen | `interval_s` ist kleiner als die Geräterate `:RATE` | `wt.input.get_update_rate()` prüfen; `stats.duplicates` zählt sie mit |
| Vorhandene CSV weg | `if_exists="overwrite"` ist die Vorgabe | `if_exists="error"`, `"unique"` oder `"append"` |
| Alle Werte `NAN` bei `FU` | die Frequenzquelle steht auf einem anderen Element | `wt.computation.frequency_item(1)` prüfen |
| Timeout bei `wt.harmonics` | Option /G5 oder /G6 fehlt | `wt.device.supports(":HARMonics")` vorher fragen |

---

## Wohin als Nächstes

| Ich will … | … nachsehen in |
|---|---|
| die vollständige Funktionsliste nach Aufgabe | [API-Überblick, Teil C](API-Ueberblick-und-Lesbarkeit.md#teil-c--funktionsübersicht-nach-aufgabe) |
| Wh/Ah messen (Integration) | Teil C.11 — `wt.integration.running()` + `wt.items.integration_profile()` |
| Oberschwingungen | Teil C.12 — `wt.harmonics` + `wt.items.harmonics_profile()` |
| den ganzen Gerätezustand sichern | Teil C.13 — `wt.backup(pfad)` / `wt.restore_backup(pfad)` |
| in mehrere Dateien schreiben | Teil C.9 — `RotatingSink` + `RotationPolicy` |
| ein eigenes Ausgabeformat | Teil C.9 — der Vertrag `SampleSink` ist drei Methoden lang |
| lauffähige Skripte statt Ausschnitte | [`examples/`](../examples/README.md) — sechs nummerierte Beispiele |
| ein Anwenderskript mit Kommandozeile | [`live_messwerte.py`](../live_messwerte.py) in der Projektwurzel |
| wissen, was das Projekt überhaupt ist | [`README.md`](../README.md) in der Projektwurzel |
