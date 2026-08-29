# =============================================================================
# Datei: tools_import_check.py
# UEBERARBEITET (Punkt 3, TOOLS-1): Die vier Pruefbloecke dieser Datei liegen
# jetzt als regulaere Testfaelle in tests/ (test_input_parsers.py,
# test_scope_and_items.py). Damit entfaellt hier auch der Zugriff auf die
# private Funktion wt3000_input._check_allowed().
#
# Was bleibt, ist ein Smoke-Check der Installation: laesst sich das Paket
# ueberhaupt importieren, ohne dass tmctl.dll oder ein Geraet vorhanden ist?
# Das ist die eine Frage, die man vor dem Aufruf eines Stufenskripts auf einem
# frisch aufgesetzten Rechner beantwortet haben will - und die einzige, fuer
# die sich ein Skript ausserhalb der Testsuite lohnt.
#
#     python tools_import_check.py
#     pytest                       # die eigentliche Pruefung
# =============================================================================

from __future__ import annotations

import importlib
import sys


def main() -> int:
    """Alle Fachmodule importieren. Rueckgabewert 0 = erfolgreich."""
    try:
        paket = importlib.import_module("wt_treiber_lib")
    except ImportError as fehler:
        print(f"FEHLER: wt_treiber_lib ist nicht importierbar: {fehler}")
        print("Abhilfe: 'pip install -e .' im Projektverzeichnis ausfuehren.")
        return 1

    fehlgeschlagen: list[str] = []
    for name in paket.MODULES:
        try:
            importlib.import_module(f"wt_treiber_lib.{name}")
        except Exception as fehler:  # bewusst breit: auch Syntax-/Namensfehler
            fehlgeschlagen.append(f"{name}: {fehler}")

    if fehlgeschlagen:
        print("FEHLER beim Import:")
        for eintrag in fehlgeschlagen:
            print(f"  {eintrag}")
        return 1

    print(f"wt_treiber_lib {paket.__version__}: {len(paket.MODULES)} Module importierbar.")
    print("Fachliche Pruefung: 'pytest' im Projektverzeichnis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
