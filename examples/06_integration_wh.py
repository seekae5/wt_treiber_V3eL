#!/usr/bin/env python
# =============================================================================
# 06 - Energie messen (Wh / Ah)
#
# Die Integrationsfunktion des Geraets zaehlt Energie und Ladung auf. Zwei
# Dinge gehoeren dazu, und sie sind getrennt:
#
#   wt.integration            STEUERT den Zaehlvorgang (Modus, Timer, Start,
#                             Stopp, Reset)
#   integration_profile()     macht die aufgelaufenen Werte LESBAR - sie
#                             kommen wie alle Messwerte ueber die Item-Tabelle
#
# SCHREIBT: Integrationsmodus und Timer, Item-Tabelle, Start/Stopp. Die
# Item-Tabelle wird zurueckgestellt; der Zaehlerstand bleibt stehen. Ihn zu
# verwerfen ist ':INTEGrate:RESet' - unwiderruflich und deshalb zusaetzlich
# gesperrt (Freigabe ueber 'wt.integration.unlocked(GROUP_RESET)').
#
#     python examples/06_integration_wh.py
# =============================================================================

from __future__ import annotations

import _pfad  # noqa: F401  - macht wt_treiber_lib ohne Installation importierbar

from wt_treiber_lib import WT3000, IntegrationMode, WTError, output_dir

# --- hier anpassen -----------------------------------------------------------

IP: str | None = None

#: Laufzeit des Zaehlvorgangs.
STUNDEN, MINUTEN, SEKUNDEN = 0, 0, 30

#: Takt, in dem der Zwischenstand mitgeschrieben wird.
INTERVALL_S: float = 1.0

AUSGABE = output_dir("messungen")


def main() -> int:
    """Rueckgabe 0 = erfolgreich."""
    AUSGABE.mkdir(parents=True, exist_ok=True)
    csv_datei = AUSGABE / "integration.csv"
    dauer_s = STUNDEN * 3600 + MINUTEN * 60 + SEKUNDEN

    try:
        with WT3000.connect(ip=IP, read_only=False, allow_changes=True) as wt:
            wt.integration.log_summary()

            with wt.ensured_protocol_state():
                # TIME, U/I/P je Element und die Integrationsgroessen
                # (WH, WHP, WHM, AH, AHP, AHM, WS, WQ).
                with wt.items.applied(wt.items.integration_profile()) as tabelle:

                    wt.integration.set_mode(IntegrationMode.NORMAL)
                    wt.integration.set_timer(
                        hours=STUNDEN, minutes=MINUTEN, seconds=SEKUNDEN
                    )

                    # Startet und stoppt in jedem Fall - auch bei Strg+C.
                    # Ohne diese Klammer zaehlt das Geraet nach einem Abbruch
                    # munter weiter, ganz ohne PC.
                    with wt.integration.running():
                        print(f"Integration laeuft ({dauer_s} s) ...")
                        stats = wt.measure.record_csv(
                            csv_datei,
                            tabelle,
                            interval_s=INTERVALL_S,
                            max_duration_s=dauer_s,
                            sidecar=True,
                        )

                    print(f"Zustand danach: {wt.integration.state().value}")

        stats.log_summary(INTERVALL_S)
        print(f"\nMessdaten: {csv_datei}")
        print("Der Zaehlerstand bleibt am Geraet stehen - "
              "verwerfen mit wt.integration.unlocked(GROUP_RESET) + reset().")

    except WTError as fehler:
        print(f"Fehler: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
