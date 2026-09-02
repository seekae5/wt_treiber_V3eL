# WT3000 `:MOTor` Quick Start

Diese Anleitung zeigt, wie die Klassen, Funktionen und Methoden des Treibers für die
SCPI-Gruppe `:MOTor` verwendet werden. Sie richtet sich an Anwender, die Drehzahl,
Drehmoment, mechanische Leistung, Synchrondrehzahl und Schlupf mit einem motorfähigen
Yokogawa WT3000 erfassen möchten.

> `wt.motor` **konfiguriert** die Motorauswertung. Die berechneten Messwerte werden
> anschließend über die numerische Item-Tabelle gelesen. Dafür gibt es
> `wt.items.motor_profile()`.

## Inhalt

1. [Voraussetzungen und Sicherheit](#1-voraussetzungen-und-sicherheit)
2. [In 60 Sekunden: Motorfähigkeit prüfen und Einstellungen lesen](#2-in-60-sekunden-motorfähigkeit-prüfen-und-einstellungen-lesen)
3. [Die bereitgestellten Klassen und Funktionen](#3-die-bereitgestellten-klassen-und-funktionen)
4. [Übersicht aller unterstützten `:MOTor`-Commands](#4-übersicht-aller-unterstützten-motor-commands)
5. [Analoge Drehzahl- und Drehmomentsignale konfigurieren](#5-analoge-drehzahl--und-drehmomentsignale-konfigurieren)
6. [Pulssignale konfigurieren](#6-pulssignale-konfigurieren)
7. [Motorgrößen messen und in CSV schreiben](#7-motorgrößen-messen-und-in-csv-schreiben)
8. [Einstellungen sichern und wiederherstellen](#8-einstellungen-sichern-und-wiederherstellen)
9. [Validierung und typische Fehlermeldungen](#9-validierung-und-typische-fehlermeldungen)
10. [Erkenntnisse, Grenzen und offene Geräteprüfungen](#10-erkenntnisse-grenzen-und-offene-geräteprüfungen)

---

## 1. Voraussetzungen und Sicherheit

### Motorfähiges Gerät

Die Gruppe `:MOTor` ist nicht auf jedem WT3000 verfügbar. Der Treiber akzeptiert zwei
Erkennungswege:

- der Modellcode aus `*IDN?` enthält die Modellvariante `-MV`, oder
- `*OPT?` meldet den Optionscode `MTR`.

Ohne einen dieser Hinweise weist `wt.motor` den Zugriff vor dem ersten Motor-Query mit
`WTError` ab. Das ist beabsichtigt: Ein nicht unterstütztes `:MOTor`-Kommando könnte sonst
in einen Timeout laufen und wie ein Verbindungsfehler aussehen.

### Lesen und Schreiben

Lesen ist mit den sicheren Vorgaben möglich:

```python
with WT3000.connect(ip="192.168.10.20") as wt:
    einstellungen = wt.motor.capture()
```

Zum Ändern müssen beide Schreibsperren geöffnet werden:

```python
with WT3000.connect(
    ip="192.168.10.20",
    read_only=False,
    allow_changes=True,
) as wt:
    wt.motor.set_poles(4)
```

| Sperre | Vorgabe | Zum Schreiben |
|---|---:|---:|
| Sitzung `read_only` | `True` | `False` |
| Fachobjekt `allow_changes` | `False` | `True` |

Für `:MOTor` ist keine zusätzliche Gruppensperre wie bei `RANGE` oder `WIRING` nötig.
Trotzdem verändert jeder `set_...()`-Aufruf die Gerätekonfiguration.

---

## 2. In 60 Sekunden: Motorfähigkeit prüfen und Einstellungen lesen

Dieses Beispiel sendet ausschließlich Queries und verändert das Gerät nicht:

```python
from wt_treiber_lib import WT3000, WTError

IP = "192.168.10.20"

try:
    with WT3000.connect(ip=IP) as wt:
        print("Modell:", wt.device.model)
        print("Motorvariante -MV:", wt.device.is_motor_model)
        print(":MOTor verfügbar:", wt.device.supports(":MOTor"))

        if not wt.device.supports(":MOTor"):
            raise WTError("Dieses Gerät stellt die Motorauswertung nicht bereit.")

        einstellungen = wt.motor.capture()
        for zeile in einstellungen.describe():
            print(zeile)

except WTError as fehler:
    print("WT3000-Fehler:", fehler)
```

Einzelwerte können ebenfalls direkt gelesen werden:

```python
typ = wt.motor.speed_type()
bereich_v = wt.motor.speed_range_v()       # nur sinnvoll bei ANALOG
skalierung = wt.motor.speed_scaling()
einheit = wt.motor.speed_unit()
polzahl = wt.motor.poles()
```

`capture()` ist für einen vollständigen und typgerechten Überblick vorzuziehen. Die Methode
fragt zuerst `TYPE` ab und liest anschließend nur die Knoten, die für `ANALog` oder `PULSe`
gültig sind.

---

## 3. Die bereitgestellten Klassen und Funktionen

Alles für den normalen Gebrauch wird direkt aus `wt_treiber_lib` importiert:

```python
from wt_treiber_lib import (
    MOTOR_ANALOG_RANGES_V,
    MotorConfig,
    MotorInputType,
    MotorLineFilter,
    MotorSettings,
    MotorSignalSettings,
    WT3000,
    build_motor_profile,
)
```

| Name | Aufgabe | Üblicher Zugriff |
|---|---|---|
| `MotorConfig` | Liest und setzt die gesamte `:MOTor`-Konfiguration | `wt.motor` |
| `MotorInputType` | Eingangstyp `ANALOG` oder `PULSE` | Argument für `set_speed_type()` und `set_torque_type()` |
| `MotorLineFilter` | Motor-Line-Filter `OFF`, `100 Hz` oder `50 kHz` | Argument für `set_line_filter()` |
| `MotorSignalSettings` | Unveränderlicher Snapshot eines Signalzweigs | Bestandteil von `MotorSettings` |
| `MotorSettings` | Unveränderlicher Snapshot der gesamten Motorgruppe | Ergebnis von `wt.motor.capture()` |
| `MOTOR_ANALOG_RANGES_V` | Erlaubte Analogbereiche `(1, 2, 5, 10, 20)` V | Validierung oder Benutzeroberfläche |
| `build_motor_profile()` | Erzeugt Motor- und elektrische Messgrößen als `ItemSpec`-Folge | direkt oder über `wt.items.motor_profile()` |

### Wichtigste Trennung

```text
wt.motor                    stellt Sensoren und Motorauswertung ein
    |
    +-- Drehzahl/Drehmoment, Skalierung, Filter, Polzahl, Sync

wt.items.motor_profile()    legt fest, welche Ergebnisse gelesen werden
    |
    +-- SPEED, TORQUE, PM, SYNCSP, SLIP sowie U, I und P
```

---

## 4. Übersicht aller unterstützten `:MOTor`-Commands

SCPI-Kommandos sind nicht von Groß-/Kleinschreibung abhängig. Die Schreibweise in dieser
Tabelle entspricht der Langform des Handbuchs und des Treibers.

### 4.1 Sammelabfragen und allgemeine Motoreinstellungen

| SCPI-Command | Lesen mit | Setzen mit | Werte/Hinweis |
|---|---|---|---|
| `:MOTor?` | `motor.capture()` | – | Gesamtzustand; der Treiber liest die gültigen Blattknoten einzeln |
| `:MOTor:FILTer?` | `motor.line_filter()` | – | Sammelabfrage wird nicht direkt verwendet |
| `:MOTor:FILTer[:LINE]` | `motor.line_filter()` | `motor.set_line_filter(value)` | `OFF`, `100HZ`, `50KHZ`; auch `100` und `50000` sind erlaubt |
| `:MOTor:PM?` | `motor.pm_scaling()`, `motor.pm_unit()` | – | Sammelabfrage wird nicht direkt verwendet |
| `:MOTor:PM:SCALing` | `motor.pm_scaling()` | `motor.set_pm_scaling(factor)` | `0.0001` bis `99999.9999` |
| `:MOTor:PM:UNIT` | `motor.pm_unit()` | `motor.set_pm_unit(text)` | freie Beschriftung, höchstens 8 Zeichen |
| `:MOTor:POLE` | `motor.poles()` | `motor.set_poles(count)` | Polzahl `1` bis `99` |
| `:MOTor:SYNChronize` | `motor.sync_source()` | `motor.set_sync_source(source)` | `U<x>`, `I<x>`, `EXTernal`, `NONE` |
| `:MOTor:SSPeed` | `motor.sync_speed_source()` | `motor.set_sync_speed_source(source)` | nur `U<x>` oder `I<x>` |

`<x>` ist eine tatsächlich bestückte Elementnummer. Der Treiber prüft die Quelle gegen
`wt.device.elements`, bevor er ein Set-Kommando sendet.

### 4.2 Drehzahlzweig `:MOTor:SPEed`

| SCPI-Command | Lesen mit | Setzen mit | Gültig bei / Werte |
|---|---|---|---|
| `:MOTor:SPEed?` | Teil von `motor.capture()` | – | Sammelabfrage wird nicht direkt verwendet |
| `:MOTor:SPEed:TYPE` | `motor.speed_type()` | `motor.set_speed_type(kind)` | `MotorInputType.ANALOG` oder `.PULSE` |
| `:MOTor:SPEed:RANGe` | `motor.speed_range_v()` | `motor.set_speed_range_v(volts)` | nur `ANALOG`; `1`, `2`, `5`, `10`, `20` V |
| `:MOTor:SPEed:AUTO` | `motor.speed_auto()` | `motor.set_speed_auto(enabled)` | nur `ANALOG`; `True`/`False` |
| `:MOTor:SPEed:PRANge` | `motor.speed_pulse_range()` | `motor.set_speed_pulse_range(upper, lower)` | nur `PULSE`; beide Werte `0` bis `99999.9999` |
| `:MOTor:SPEed:PULSe` | `motor.speed_pulses()` | `motor.set_speed_pulses(count)` | nur `PULSE`; `1` bis `9999` Impulse/Umdrehung |
| `:MOTor:SPEed:SCALing` | `motor.speed_scaling()` | `motor.set_speed_scaling(factor)` | beide Typen; `0.0001` bis `99999.9999` |
| `:MOTor:SPEed:UNIT` | `motor.speed_unit()` | `motor.set_speed_unit(text)` | beide Typen; höchstens 8 Zeichen, z. B. `rpm` |

### 4.3 Drehmomentzweig `:MOTor:TORQue`

| SCPI-Command | Lesen mit | Setzen mit | Gültig bei / Werte |
|---|---|---|---|
| `:MOTor:TORQue?` | Teil von `motor.capture()` | – | Sammelabfrage wird nicht direkt verwendet |
| `:MOTor:TORQue:TYPE` | `motor.torque_type()` | `motor.set_torque_type(kind)` | `MotorInputType.ANALOG` oder `.PULSE` |
| `:MOTor:TORQue:RANGe` | `motor.torque_range_v()` | `motor.set_torque_range_v(volts)` | nur `ANALOG`; `1`, `2`, `5`, `10`, `20` V |
| `:MOTor:TORQue:AUTO` | `motor.torque_auto()` | `motor.set_torque_auto(enabled)` | nur `ANALOG`; `True`/`False` |
| `:MOTor:TORQue:PRANge` | `motor.torque_pulse_range()` | `motor.set_torque_pulse_range(upper, lower)` | nur `PULSE`; `-10000` bis `10000` |
| `:MOTor:TORQue:RATE?` | `motor.torque_rate_upper()`, `motor.torque_rate_lower()` | – | Sammelabfrage wird nicht direkt verwendet |
| `:MOTor:TORQue:RATE:UPPer` | `motor.torque_rate_upper()` | `motor.set_torque_rate_upper(value, frequency_hz)` | nur `PULSE`; Wert und zugehörige Frequenz |
| `:MOTor:TORQue:RATE:LOWer` | `motor.torque_rate_lower()` | `motor.set_torque_rate_lower(value, frequency_hz)` | nur `PULSE`; Wert und zugehörige Frequenz |
| `:MOTor:TORQue:SCALing` | `motor.torque_scaling()` | `motor.set_torque_scaling(factor)` | beide Typen; `0.0001` bis `99999.9999` |
| `:MOTor:TORQue:UNIT` | `motor.torque_unit()` | `motor.set_torque_unit(text)` | beide Typen; höchstens 8 Zeichen, z. B. `Nm` |

Für `PRANge` gilt immer die Reihenfolge `(oberer Wert, unterer Wert)`. Beim Drehmoment sind
negative Werte zulässig, beispielsweise für Bremsbetrieb. Die Frequenz eines
Drehmoment-Nennwerts muss zwischen `1 Hz` und `100 MHz` liegen.

---

## 5. Analoge Drehzahl- und Drehmomentsignale konfigurieren

Die Eingangstypen müssen **zuerst** gesetzt werden. Erst danach sind `RANGe` und `AUTO`
gültig.

Das Beispiel sichert ausschließlich die Motorgruppe und stellt sie auch bei einer Ausnahme
wieder her:

```python
from wt_treiber_lib import (
    MotorInputType,
    MotorLineFilter,
    WT3000,
)

IP = "192.168.10.20"

with WT3000.connect(
    ip=IP,
    read_only=False,
    allow_changes=True,
) as wt:
    motor = wt.motor
    vorher = motor.capture()

    try:
        # Eingangstyp immer zuerst setzen.
        motor.set_speed_type(MotorInputType.ANALOG)
        motor.set_torque_type(MotorInputType.ANALOG)

        motor.set_speed_range_v(20.0)
        motor.set_speed_auto(False)
        motor.set_speed_scaling(1.0)
        motor.set_speed_unit("rpm")

        motor.set_torque_range_v(20.0)
        motor.set_torque_auto(False)
        motor.set_torque_scaling(1.0)
        motor.set_torque_unit("Nm")

        motor.set_pm_scaling(1.0)
        motor.set_pm_unit("W")
        motor.set_line_filter(MotorLineFilter.HZ100)
        motor.set_poles(4)

        # U1/I1 müssen zu einem bestückten Element gehören.
        motor.set_sync_source("NONE")
        motor.set_sync_speed_source("I1")

        for zeile in motor.capture().describe():
            print(zeile)

        # Hier messen oder weitere Aktionen ausführen.

    finally:
        motor.restore(vorher)
```

### Warum Autorange am Prüfstand oft ausgeschaltet bleibt

Ein automatischer Bereichswechsel kann in ein Messintervall fallen. Für vergleichbare
Betriebspunkte sind feste, ausreichend große Bereiche meist leichter auszuwerten. Ob Autorange
für den konkreten Sensor sinnvoll ist, muss der Messaufbau entscheiden.

---

## 6. Pulssignale konfigurieren

Bei `PULSE` werden die Analogparameter `RANGe` und `AUTO` nicht verwendet. Dafür gelten
`PRANge`, beim Drehzahlsignal `PULSe` und beim Drehmomentsignal die beiden `RATE`-Paare.

```python
from wt_treiber_lib import MotorInputType

motor.set_speed_type(MotorInputType.PULSE)
motor.set_speed_pulse_range(10000.0, 0.0)  # oben, unten
motor.set_speed_pulses(60)                 # Impulse je Umdrehung
motor.set_speed_scaling(1.0)
motor.set_speed_unit("rpm")

motor.set_torque_type(MotorInputType.PULSE)
motor.set_torque_pulse_range(50.0, -50.0)  # Bremsmoment ist negativ möglich
motor.set_torque_rate_upper(50.0, 15000.0) # 50 Nm entsprechen 15 kHz
motor.set_torque_rate_lower(-50.0, 5000.0) # -50 Nm entsprechen 5 kHz
motor.set_torque_scaling(1.0)
motor.set_torque_unit("Nm")
```

Der Treiber fragt den aktuellen Eingangstyp vor einem typgebundenen Set-Kommando ab. Ein
Aufruf wie `set_speed_pulses(60)` bei `TYPE=ANALog` wird daher mit einer verständlichen
Fehlermeldung abgewiesen, bevor das ungültige Kommando gesendet wird.

---

## 7. Motorgrößen messen und in CSV schreiben

### Das Motorprofil

`wt.items.motor_profile()` erzeugt standardmäßig folgende Tabelle:

1. `SPEED` – Drehzahl, ohne Elementangabe
2. `TORQUE` – Drehmoment, ohne Elementangabe
3. `PM` – mechanische Leistung, ohne Elementangabe
4. `SYNCSP` – Synchrondrehzahl, ohne Elementangabe
5. `SLIP` – Schlupf, ohne Elementangabe
6. `U`, `I`, `P` für die Elemente 1, 2 und 3
7. `U`, `I`, `P` für `SIGMA`, wenn `include_sigma=True`

Die fünf Motorgrößen beziehen sich auf den Motor und benötigen deshalb keine Elementnummer.

### Vollständige Messreihe

Das Anwenden einer eigenen Item-Tabelle ist ein Schreibvorgang. `wt.items.applied()` sichert
die vorhandene Tabelle, setzt und verifiziert das Motorprofil und stellt die ursprüngliche
Tabelle am Blockende garantiert wieder her.

```python
from pathlib import Path

from wt_treiber_lib import WT3000

IP = "192.168.10.20"
ZIEL = Path("messungen/motor.csv")
ZIEL.parent.mkdir(parents=True, exist_ok=True)

with WT3000.connect(
    ip=IP,
    read_only=False,
    allow_changes=True,
) as wt:
    if not wt.device.supports(":MOTor"):
        raise RuntimeError("Dieses WT3000 unterstützt :MOTor nicht.")

    specs = wt.items.motor_profile(
        elements=("1", "2", "3"),
        include_sigma=True,
    )

    with wt.items.applied(
        specs,
        backup_file=Path("messungen/itemtabelle_vor_motor.json"),
    ) as tabelle:
        print("Messspalten:", ", ".join(item.key for item in tabelle.items))

        stats = wt.measure.record_csv(
            ZIEL,
            tabelle,
            interval_s=1.0,
            max_samples=60,
            sidecar=True,
        )

print(f"{stats.measured_samples} Messpunkte geschrieben")
```

Nur die mechanische Seite wird mit `elements=()` erzeugt:

```python
specs = wt.items.motor_profile(elements=(), include_sigma=False)
```

Das ist möglich, für Wirkungsgradberechnungen fehlen dann jedoch die elektrischen Leistungen.

### Einheiten der Messwerte

Die Einheiten von `SPEED`, `TORQUE` und `PM` sind freie Gerätebeschriftungen und werden mit
folgenden Methoden gelesen:

```python
print("SPEED:", wt.motor.speed_unit())
print("TORQUE:", wt.motor.torque_unit())
print("PM:", wt.motor.pm_unit())
```

Die Beschriftung verändert das Rechenergebnis nicht. Sie muss trotzdem zur Interpretation der
Messdatei passen. Die Einheit von `SYNCSP` und die Darstellung von `SLIP` sind im vorliegenden
Handbuchauszug noch nicht ausreichend bestätigt.

---

## 8. Einstellungen sichern und wiederherstellen

### Nur die Motorgruppe

```python
vorher: MotorSettings = wt.motor.capture()

try:
    wt.motor.set_poles(4)
    # arbeiten oder messen
finally:
    wt.motor.restore(vorher)
```

`restore()` setzt zuerst die Eingangstypen und danach nur die Parameter zurück, die beim
Snapshot für diesen Typ tatsächlich gelesen wurden. Ein `None`-Feld wird nicht geraten und
nicht geschrieben.

### Snapshot als Dictionary

```python
daten = wt.motor.capture().to_dict()
snapshot = MotorSettings.from_dict(daten)
```

Diese Darstellung ist serialisierbar und wird auch vom Sitzungs-Backup verwendet.

### Gesamte Sitzung als JSON sichern

```python
from pathlib import Path

backup = wt.backup(Path("messungen/wt3000_vor_motor.json"))
```

Wenn `:MOTor` verfügbar ist, enthält dieses Backup automatisch `MotorSettings`. Eine spätere
Wiederherstellung benötigt eine schreibfähige Verbindung:

```python
abweichungen = wt.restore_backup(
    Path("messungen/wt3000_vor_motor.json")
)

if abweichungen:
    for abweichung in abweichungen:
        print(abweichung)
```

Ein gesamtes Sitzungs-Backup umfasst zusätzlich Eingänge, Bereiche, Item-Tabelle,
Rechenfunktionen, Integration und – sofern vorhanden – Oberschwingungen. Für eine lokale
Änderung nur an `:MOTor` ist der direkte `MotorSettings`-Snapshot daher meist der kleinere und
übersichtlichere Rückweg.

---

## 9. Validierung und typische Fehlermeldungen

Jeder Setter arbeitet nach demselben Muster:

1. lokale Werteprüfung,
2. gegebenenfalls Prüfung von Eingangstyp oder Element,
3. SCPI-Set-Kommando senden,
4. Wert zurücklesen und vergleichen,
5. Gerätefehlerqueue prüfen.

| Problem | Ursache | Abhilfe |
|---|---|---|
| Zugriff auf `wt.motor` endet mit `WTError` | Weder Modellvariante `-MV` noch `MTR` erkannt | Steckbrief mit `wt.device.describe()` und reale Geräteausstattung prüfen |
| `DeviceConfigLocked` | `allow_changes=False` | Verbindung mit `allow_changes=True` öffnen |
| Sitzung lehnt Set-Kommando ab | `read_only=True` | Zusätzlich `read_only=False` setzen |
| „Parameter gilt nur für ANALog/PULSe“ | Falscher Eingangstyp | Zuerst `set_speed_type()` beziehungsweise `set_torque_type()` aufrufen |
| „Element ... ist nicht bestückt“ | Ungültige Sync-Quelle | Eine Quelle aus `wt.device.elements` wählen |
| Bereichsstufe wird abgewiesen | Analogbereich liegt nicht in `(1, 2, 5, 10, 20)` V | Eine dokumentierte Stufe verwenden |
| Einheit wird abgewiesen | Mehr als 8 Zeichen oder ein `"` im Text | Kürzere, SCPI-taugliche Beschriftung verwenden |
| Rückleseprüfung schlägt fehl | Gerät hat den Wert nicht übernommen oder meldet ihn anders | Fehlerqueue und Hardwareprotokoll prüfen; Ausgangszustand wiederherstellen |

### Empfohlene Reihenfolge

```text
1. Gerätefähigkeit prüfen
2. MotorSettings mit capture() sichern
3. TYPE für SPEED und TORQUE setzen
4. typabhängige Parameter setzen
5. Skalierungen, Einheiten, Filter, Polzahl und Sync setzen
6. Einstellungen mit capture() gegenlesen
7. Item-Tabelle mit motor_profile() temporär anwenden
8. messen
9. Item-Tabelle und MotorSettings wiederherstellen
```

---

## 10. Erkenntnisse, Grenzen und offene Geräteprüfungen

### Was die Implementierung bereits gut absichert

- Die strukturgleichen Drehzahl- und Drehmomentzweige teilen intern denselben geprüften
  Codepfad, besitzen nach außen aber verständliche, ausgeschriebene Methoden.
- ANALOG- und PULSE-Parameter werden nicht vermischt.
- `capture()` vermeidet Queries auf typfremde Knoten und reduziert dadurch das Risiko eines
  Timeouts mitten in einem Backup.
- Alle Set-Methoden werden standardmäßig durch Rücklesen und Abfrage der Fehlerqueue geprüft.
- Snapshots, JSON-Rundreise, Restore-Reihenfolge, Motorprofil und Fassadenzugriff sind in der
  gerätefreien Testsuite umfassend berücksichtigt. `tests/test_motor.py` enthält 61
  Testfunktionen.

### Noch am realen WT3000 zu bestätigen

1. Das Handbuch zeigt Analogbereiche als `20V`; der Treiber sendet aktuell die reine Zahl
   `20`. Die Syntaxbeschreibung lässt diese Interpretation zu, sie ist im Quelltext aber
   ausdrücklich mit `ZU VERIFIZIEREN` markiert.
2. Das Handbuch zeigt bei einem analogen `:MOTor:SPEed?` keine Pulsknoten. Der Treiber fragt
   deshalb nur typgerechte Blattknoten ab. Ob typfremde Einzelqueries tatsächlich timeouten,
   ist noch nicht am Gerät bestätigt.
3. Die numerischen Funktionen `SPEED`, `TORQUE`, `PM`, `SYNCSP` und `SLIP` sind im Motorprofil
   mit `verify=True` markiert. Beim Bauen der Item-Tabelle wird deshalb eine Warnung
   protokolliert, bis sie am Originalgerät bestätigt sind.
4. Die Einheit von `SYNCSP` sowie die genaue Darstellung von `SLIP` – Verhältnis oder Prozent –
   sind noch offen. Der Treiber erfindet dafür bewusst keine Einheit.

### Zwei Randfälle der Fähigkeitserkennung

- Ein Gerät mit `MTR`, aber ohne `-MV`, darf `wt.motor` verwenden. Bei der separaten
  Wirkungsgradkonfiguration erhält `ComputationConfig` derzeit jedoch nur das Merkmal
  `is_motor_model`. Dadurch kann `PM` als Wirkungsgradglied in genau dieser Konstellation
  abgewiesen werden, obwohl `wt.motor` erreichbar ist.
- Wenn `*OPT?` nicht beantwortet wird und der Modellcode kein `-MV` enthält, behandelt die
  Motor-Sonderprüfung die Fähigkeit als nicht vorhanden. Andere optionale Gruppen behandeln
  eine unbekannte Optionslage großzügiger. Vor einer Änderung dieser Logik sollte das Verhalten
  mit einem echten Gerät geklärt werden.

### Stand der lokalen Prüfung dieser Anleitung

Die Motorimplementierung und die vorhandenen Tests wurden statisch geprüft. Die 61 vorhandenen
Motor-Tests konnten bei der Erstellung dieser Anleitung nicht erneut ausgeführt werden, weil in
der vorhandenen Projektumgebung das Modul `pytest` nicht installiert war. Das ist kein
festgestellter Fehler der Motorfunktionen, aber auch kein neuer grüner Testlauf.

---

## Kurzreferenz

```python
# Lesen
s = wt.motor.capture()

# Eingangstyp
wt.motor.set_speed_type(MotorInputType.ANALOG)
wt.motor.set_torque_type(MotorInputType.PULSE)

# ANALOG
wt.motor.set_speed_range_v(20.0)
wt.motor.set_speed_auto(False)

# PULSE
wt.motor.set_speed_pulse_range(10000.0, 0.0)
wt.motor.set_speed_pulses(60)
wt.motor.set_torque_rate_upper(50.0, 15000.0)

# Allgemein
wt.motor.set_speed_scaling(1.0)
wt.motor.set_torque_scaling(1.0)
wt.motor.set_pm_scaling(1.0)
wt.motor.set_line_filter(MotorLineFilter.HZ100)
wt.motor.set_poles(4)
wt.motor.set_sync_source("NONE")
wt.motor.set_sync_speed_source("I1")

# Messgrößen
specs = wt.items.motor_profile()
```

Weiterführend:

- [`Schnellstart.md`](Schnellstart.md) – allgemeine Verbindung und Messabläufe
- [`API-Ueberblick-und-Lesbarkeit.md`](API-Ueberblick-und-Lesbarkeit.md) – Gesamtüberblick
- [`WT3000_Communication_Commands.md`](WT3000_Communication_Commands.md) – zugrunde liegende
  SCPI-Kommandoreferenz
