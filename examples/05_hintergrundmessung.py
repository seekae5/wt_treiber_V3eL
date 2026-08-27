#!/usr/bin/env python
# =============================================================================
# 05 - Im Hintergrund messen, waehrenddessen den Pruefstand fahren
#
# Wenn das Skript waehrend der Messung etwas anderes tun muss und das Ende
# nicht vorab feststeht.
#
# WAEHREND DES LAUFS GEHOERT DIE SITZUNG DEM MESS-THREAD. Jeder Zugriff auf
# 'wt.input', 'wt.ranges' oder 'wt.items' aus dem Haupt-Thread endet dann in
# einer ConcurrentAccessError - das ist der haeufigste Fehler in
# Pruefstandsablaeufen. Deshalb steht 'wt.items.read()' unten VOR dem Start.
#
# Wer waehrend der Messung am Geraet stellen muss, nimmt 'wt.measure.stream()':
# dort laeuft der Takt im eigenen Thread und die Sitzung ist zwischen zwei
# Datensaetzen frei.
#
#     python examples/05_hintergrundmessung.py
# =============================================================================

from __future__ import annotations

import time

import _pfad  # noqa: F401  - macht wt3000_scpi ohne Installation importierbar

from wt3000_scpi import WT3000, CsvSink, ErrorPolicy, WTError, output_dir

# --- hier anpassen -----------------------------------------------------------

IP: str | None = None
INTERVALL_S: float = 0.5
AUSGABE = output_dir("messungen")


# --- der eigene Ablauf -------------------------------------------------------
# Hier steht im Ernstfall die Anlagensteuerung. Die drei Platzhalter warten
# nur, damit das Beispiel fuer sich lauffaehig bleibt.


def pruefstand_hochfahren() -> None:
    print("  Pruefstand faehrt hoch ...")
    time.sleep(1.0)


def warten_bis_temperatur_erreicht() -> None:
    print("  warte auf Betriebstemperatur ...")
    time.sleep(2.0)


def pruefstand_abfahren() -> None:
    print("  Pruefstand faehrt ab ...")
    time.sleep(1.0)


def main() -> int:
    """Rueckgabe 0 = erfolgreich."""
    AUSGABE.mkdir(parents=True, exist_ok=True)
    csv_datei = AUSGABE / "pruefstandslauf.csv"

    try:
        with WT3000.connect(ip=IP, read_only=False, allow_changes=True) as wt:
            # VOR dem Start - danach gehoert die Sitzung dem Mess-Thread.
            tabelle = wt.items.read()

            with wt.measure.start(
                CsvSink(csv_datei),
                tabelle,
                interval_s=INTERVALL_S,
                # Ohne Policy beendet der erste Kommunikationsfehler den Lauf.
                # 'unattended' haelt bis zu fuenf Aussetzer hintereinander aus
                # und baut die Verbindung notfalls neu auf; die Luecken stehen
                # als MISSING-Zeilen sichtbar in der Datei.
                error_policy=ErrorPolicy.unattended(),
                sidecar=True,
            ) as messung:

                print("Messung laeuft im Hintergrund.")
                pruefstand_hochfahren()
                warten_bis_temperatur_erreicht()
                pruefstand_abfahren()

                stats = messung.stop()
            # Das 'with' garantiert das Ende der Messung - auch wenn oben
            # etwas schiefgeht. Erst danach darf die Sitzung wieder benutzt
            # oder eine Konfigurationsklammer geschlossen werden.

        stats.log_summary(INTERVALL_S)
        print(f"\nMessdaten: {csv_datei}")
        print(f"{stats.missing} ausgefallene Zyklen, {stats.reconnects}x neu verbunden")

    except WTError as fehler:
        print(f"Fehler: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
