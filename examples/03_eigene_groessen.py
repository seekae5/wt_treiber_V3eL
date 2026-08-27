#!/usr/bin/env python
# =============================================================================
# 03 - Eigene Groessen messen
#
# Wenn die Spalten der CSV feststehen sollen, unabhaengig davon, was am
# Bedienfeld eingestellt ist. Dafuer wird die Item-Tabelle GESCHRIEBEN.
#
# SCHREIBT: Item-Tabelle, NUMber, ':NUMeric:HOLD' und - falls noetig - die drei
# Protokollknoten. Ranges, Wiring, Filter und Skalierung bleiben unberuehrt.
# Beides wird am Blockende zurueckgestellt, auch bei Fehler oder Strg+C.
#
#     python examples/03_eigene_groessen.py
# =============================================================================

from __future__ import annotations

import _pfad  # noqa: F401  - macht wt3000_scpi ohne Installation importierbar

from wt3000_scpi import WT3000, ItemSpec, WTError, output_dir

# --- hier anpassen -----------------------------------------------------------

IP: str | None = None
INTERVALL_S: float = 1.0
ANZAHL: int | None = 30
AUSGABE = output_dir("messungen")

#: Die gewuenschten Spalten. ItemSpec(Funktion, Element) - das Element ist
#: eine ZEICHENKETTE, auch bei einer Zahl.
#:
#: Statt einer eigenen Liste tun es oft die fertigen Profile:
#:     wt.items.standard_profile()      U, I, P, S, Q, LAMBDA, PHI + SIGMA
#:     wt.items.integration_profile()   siehe Beispiel 06
#:     wt.items.harmonics_profile()     Oberschwingungen
PROFIL = [
    ItemSpec("U", "1"), ItemSpec("I", "1"), ItemSpec("P", "1"),
    ItemSpec("U", "2"), ItemSpec("I", "2"), ItemSpec("P", "2"),
    ItemSpec("P", "SIGMA"), ItemSpec("LAMBDA", "SIGMA"),
]


def main() -> int:
    """Rueckgabe 0 = erfolgreich."""
    AUSGABE.mkdir(parents=True, exist_ok=True)
    csv_datei = AUSGABE / "eigene_groessen.csv"

    try:
        # BEIDE Schloesser offen - die Item-Tabelle wird geschrieben.
        with WT3000.connect(ip=IP, read_only=False, allow_changes=True) as wt:

            # ':COMMunicate:HEADer 0', ':VERBose 0', ':NUMeric:FORMat FLOat'.
            # Ohne die scheitert das Auslesen. Steht der Zustand schon richtig,
            # tut dieser Block nichts.
            with wt.ensured_protocol_state():

                # Sichern, Schreibprobe an EINEM Item, anwenden, verifizieren -
                # und im finally den Ausgangszustand zurueck. Das 'backup_file'
                # ist die Rueckfallebene, falls die Verbindung mittendrin
                # abreisst und der Rueckweg gar nicht mehr laeuft.
                with wt.items.applied(
                    PROFIL, backup_file=AUSGABE / "itemtabelle_backup.json"
                ) as tabelle:
                    print(f"Spalten: {', '.join(i.key for i in tabelle.items)}")

                    stats = wt.measure.record_csv(
                        csv_datei,
                        tabelle,
                        interval_s=INTERVALL_S,
                        max_samples=ANZAHL,
                        sidecar=True,
                    )
                # hier steht die Item-Tabelle wieder wie vorgefunden

        stats.log_summary(INTERVALL_S)
        print(f"\nMessdaten: {csv_datei}")

    except WTError as fehler:
        print(f"Fehler: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
