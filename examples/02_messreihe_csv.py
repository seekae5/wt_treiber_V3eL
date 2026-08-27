#!/usr/bin/env python
# =============================================================================
# 02 - Messreihe in eine CSV
#
# Der uebliche Einstieg. Misst genau die Groessen, die am Bedienfeld
# eingestellt sind ('wt.items.read()'), und schreibt sie in eine CSV samt
# Metadaten daneben.
#
# SCHREIBT NICHTS AM GERAET. Die Sitzung ist rein lesend; die Item-Tabelle
# wird uebernommen, nicht gesetzt. Damit ist dieses Beispiel am eingemessenen
# Geraet ungefaehrlich.
#
#     python examples/02_messreihe_csv.py
# Abbruch jederzeit mit Strg+C - die bis dahin geschriebenen Zeilen bleiben.
# =============================================================================

from __future__ import annotations

import _pfad  # noqa: F401  - macht wt3000_scpi ohne Installation importierbar

from wt3000_scpi import WT3000, WTError, output_dir

# --- hier anpassen -----------------------------------------------------------

IP: str | None = None

#: Takt DIESER Schleife. Nicht die Rate des Geraets - die steht auf ':RATE'.
#: Ist er kleiner, entstehen Wiederholungen; sie sind als DUPLICATE erkennbar.
INTERVALL_S: float = 1.0

#: None = laeuft bis Strg+C.
ANZAHL: int | None = 60

#: Zielverzeichnis. 'output_dir' loest gegen die Projektwurzel auf.
AUSGABE = output_dir("messungen")


def main() -> int:
    """Rueckgabe 0 = erfolgreich."""
    AUSGABE.mkdir(parents=True, exist_ok=True)
    csv_datei = AUSGABE / "messreihe.csv"

    try:
        with WT3000.connect(ip=IP) as wt:
            # Die Tabelle des Geraets uebernehmen. Das ist der Unterschied zu
            # Beispiel 03: hier bestimmt das Bedienfeld die Spalten.
            #
            # 'record_csv()' holt sie sich auch von selbst, wenn man 'table'
            # weglaesst - hier steht sie ausdruecklich da, damit vor dem Start
            # sichtbar ist, WAS gemessen wird.
            tabelle = wt.items.read()
            print(f"{len(tabelle.items)} Items: "
                  f"{', '.join(item.key for item in tabelle.items)}")
            print(f"Takt {INTERVALL_S} s, Abbruch mit Strg+C")

            stats = wt.measure.record_csv(
                csv_datei,
                tabelle,
                interval_s=INTERVALL_S,
                max_samples=ANZAHL,
                # HOLD friert den Datensatz vor dem Lesen ein und macht den
                # Zeitstempel scharf. Es ist ein Set-Kommando und in einer
                # Nur-Lesen-Sitzung nicht erlaubt - siehe Beispiel 03.
                use_hold=False,
                # Erst damit ist die CSV ohne Zusatzwissen interpretierbar:
                # Geraet, Verdrahtung, Item-Tabelle und Pruefsummen landen in
                # 'messreihe.csv.meta.json' daneben.
                sidecar=True,
            )

        stats.log_summary(INTERVALL_S)
        print(f"\nMessdaten: {csv_datei}")
        print(f"Metadaten: {csv_datei.with_suffix(csv_datei.suffix + '.meta.json')}")
        print(f"{stats.measured_samples} Messpunkte, {stats.duplicates} Wiederholungen")

    except WTError as fehler:
        print(f"Fehler: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
