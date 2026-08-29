#!/usr/bin/env python
# =============================================================================
# 01 - Geraet ansehen
#
# Der erste Versuch am realen Geraet. Prueft die Verbindung und zeigt, womit
# man es zu tun hat: Modell, Optionen, Verdrahtung, bestueckte Elemente,
# eingestellte Messbereiche.
#
# SCHREIBT NICHTS. Die Sitzung ist rein lesend - jedes Set-Kommando wuerde an
# der Sperre der Sitzung scheitern, bevor es das Geraet erreicht.
#
#     python examples/01_geraet_ansehen.py
# =============================================================================

from __future__ import annotations

import _pfad  # noqa: F401  - macht wt_treiber_lib ohne Installation importierbar

from wt_treiber_lib import WT3000, Quantity, WTError

# --- hier anpassen -----------------------------------------------------------

#: None = IP aus der Umgebung (WT3000_IP) oder aus 'wt3000.json'.
IP: str | None = None


def main() -> int:
    """Rueckgabe 0 = erfolgreich."""
    try:
        with WT3000.connect(ip=IP) as wt:
            # Der Steckbrief wird beim Verbinden ohnehin erhoben; describe()
            # gibt ihn Zeile fuer Zeile heraus, damit er auch ohne
            # eingerichtetes Logging sichtbar wird.
            for zeile in wt.device.describe():
                print(zeile)

            print()
            print(f"Bestueckte Elemente: {wt.device.elements}")
            print(f"SIGMA umfasst:       {wt.ranges.expand_scope('SIGMA')}")
            print(f"SIGMB umfasst:       {wt.ranges.expand_scope('SIGMB')}")
            print(f"Update-Rate:         {wt.input.get_update_rate()} s")

            print()
            print("Messbereiche:")
            spannung = wt.ranges.get_ranges(Quantity.VOLTAGE)
            strom = wt.ranges.get_ranges(Quantity.CURRENT)
            for element in wt.device.elements:
                print(
                    f"  Element {element}: "
                    f"U {spannung[element].describe(Quantity.VOLTAGE):>16}   "
                    f"I {strom[element].describe(Quantity.CURRENT):>16}"
                )

            # Sagt VORAB, welche Kommandogruppen an diesem Geraet mangels
            # Option ins Leere liefen - besser als spaeter ein Timeout, der
            # wie ein Verbindungsabbruch aussieht.
            if not wt.device.supports(":HARMonics"):
                print("\nHinweis: Oberschwingungsanalyse ist hier nicht verfuegbar.")

    except WTError as fehler:
        print(f"Fehler: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
