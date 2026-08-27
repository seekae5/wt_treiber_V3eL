#!/usr/bin/env python
# =============================================================================
# 04 - Messbereiche fuer die Messung setzen und danach zurueckstellen
#
# Wenn die Messreihe feste Bereiche braucht. Der Plan wird gesetzt, gegen das
# Geraet verifiziert und am Blockende garantiert zurueckgestellt - auch bei
# einem Fehler oder Strg+C mitten in der Messung.
#
# SCHREIBT: Messbereiche und Autorange nach Plan, danach zurueck auf den
# Ausgangsstand. ACHTUNG - das ist der eingemessene Zustand des Geraets. Vor
# dem ersten Lauf am realen Geraet lohnt ein Blick auf das 'backup_file'.
#
#     python examples/04_bereiche_setzen.py
# =============================================================================

from __future__ import annotations

import _pfad  # noqa: F401  - macht wt3000_scpi ohne Installation importierbar

from wt3000_scpi import (
    WT3000,
    AutoRangeSpec,
    Quantity,
    RangePlan,
    RangeSpec,
    WTError,
    output_dir,
)

# --- hier anpassen -----------------------------------------------------------

IP: str | None = None
ANZAHL: int | None = 30
AUSGABE = output_dir("messungen")

#: Der Zielzustand. 'scope' ist eine Elementnummer, "SIGMA", "SIGMB" oder "ALL".
#:
#: Welche Stufen das Geraet annimmt, steht in VOLTAGE_RANGES, CURRENT_RANGES
#: und SENSOR_RANGES - je nach Crest-Faktor und Elementtyp. Ein fester Bereich
#: schaltet Autorange derselben Groesse von selbst aus.
PLAN = RangePlan.of(
    RangeSpec(Quantity.VOLTAGE, "ALL", 600.0),
    AutoRangeSpec(Quantity.CURRENT, "SIGMA", True),
)


def main() -> int:
    """Rueckgabe 0 = erfolgreich."""
    AUSGABE.mkdir(parents=True, exist_ok=True)
    csv_datei = AUSGABE / "mit_bereichen.csv"

    print("Vorgabe:")
    for zeile in PLAN.describe():
        print(f"  {zeile}")

    try:
        with WT3000.connect(ip=IP, read_only=False, allow_changes=True) as wt:

            # 'allow_snapping=True' erlaubt dem Geraet, einen Zwischenwert auf
            # die naechste gueltige Stufe zu runden. Ohne den Schalter gilt
            # eine Abweichung als Fehler und der Block bricht ab.
            with wt.applied_ranges(
                PLAN, backup_file=AUSGABE / "bereiche_backup.json"
            ) as bericht:
                print(f"{bericht.commands_written} Kommandos geschrieben")

                # Ohne 'table' wird die Item-Tabelle des Geraets uebernommen.
                stats = wt.measure.record_csv(
                    csv_datei, max_samples=ANZAHL, sidecar=True
                )
            # hier stehen die Bereiche wieder wie vorgefunden

            print(
                "Abweichungen nach dem Ruecksetzen:",
                bericht.restore_problems or "keine",
            )

        stats.log_summary(1.0)
        print(f"\nMessdaten: {csv_datei}")

    except WTError as fehler:
        print(f"Fehler: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
