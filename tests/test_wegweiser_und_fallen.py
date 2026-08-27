# =============================================================================
# Datei: tests/test_wegweiser_und_fallen.py
#
# Zwei Schritte aus dem Umbauplan (docs/API-Ueberblick-und-Lesbarkeit.md):
#
#   E6  Wo es mehrere Wege zum selben Ziel gibt, nennt der Docstring den
#       empfohlenen. Ohne diese Pruefsaetze verschwindet so ein Hinweis beim
#       naechsten Umformulieren, ohne dass es jemandem auffaellt.
#
#   E9  Vier Fallen, die bisher nur im Quelltext standen, melden sich jetzt
#       selbst. Geprueft wird, dass sie sich melden - UND dass sie es nicht
#       tun, wenn kein Anlass besteht. Eine Warnung, die immer kommt, liest
#       nach der dritten Messung niemand mehr.
# =============================================================================

from __future__ import annotations

import logging

import pytest
from conftest import ItemTableTransport, base_responses

from wt3000_scpi import (
    WT3000,
    ItemSpec,
    Quantity,
    WTConfig,
    build_integration_profile,
)
from wt3000_scpi.wt3000_itemspec import build_item_table


def geraet() -> ItemTableTransport:
    return ItemTableTransport({1: "U,1", 2: "I,1", 3: "P,1"}, number=3)


def fassade(transport: ItemTableTransport | None = None, **kwargs) -> WT3000:
    kwargs.setdefault("read_only", True)
    return WT3000.from_transport(
        transport if transport is not None else geraet(),
        WTConfig(use_remote=False),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# E6 - Wo mehrere Wege sind, steht der empfohlene im Docstring
# ---------------------------------------------------------------------------

#: (Aufgabe, empfohlener Aufruf, die Alternativen daneben).
#
# Die Liste ist zugleich die Antwort auf die Frage, die ein Anwender beim
# Ueberfliegen der API stellt: "es gibt drei Methoden dafuer - welche nehme
# ich?". Steht sie hier, steht sie auch im Docstring.
WEGE = (
    (
        "Messbereich stellen",
        "WT3000.applied_ranges",
        ("RangeAccess.set_range", "InputConfig.set_voltage_range",
         "InputConfig.set_current_range", "InputConfig.set_current_range_sensor"),
    ),
    (
        "Autorange schalten",
        None,  # der empfohlene Weg ist derselbe Kontextmanager wie oben
        ("RangeAccess.set_auto", "InputConfig.set_voltage_auto_range",
         "InputConfig.set_current_auto_range"),
    ),
    (
        "Item-Tabelle setzen",
        "ItemAccess.applied",
        ("ItemAccess.apply",),
    ),
    (
        "Integration fahren",
        "IntegrationConfig.running",
        ("IntegrationConfig.start",),
    ),
)


def docstring(pfad: str) -> str:
    """'Klasse.methode' aufloesen - ueber den Paketexport, nicht ueber Module."""
    import wt3000_scpi

    klasse, _, methode = pfad.partition(".")
    objekt = getattr(getattr(wt3000_scpi, klasse), methode)
    # Ein Kontextmanager ist eingepackt; das Original traegt den Docstring.
    objekt = getattr(objekt, "__wrapped__", objekt)
    return objekt.__doc__ or ""


@pytest.mark.parametrize(
    "pfad",
    [p for _aufgabe, empfohlen, _alt in WEGE for p in ([empfohlen] if empfohlen else [])],
)
def test_der_empfohlene_weg_ist_als_solcher_gekennzeichnet(pfad):
    assert "EMPFOHLENER WEG" in docstring(pfad), (
        f"{pfad} ist der empfohlene Weg, sagt es aber nicht"
    )


@pytest.mark.parametrize(
    "pfad", [p for _aufgabe, _empf, alternativen in WEGE for p in alternativen]
)
def test_jede_alternative_verweist_auf_den_empfohlenen_weg(pfad):
    text = docstring(pfad)
    assert "STATTDESSEN EMPFOHLEN" in text, (
        f"{pfad} ist eine von mehreren Moeglichkeiten und muss auf die "
        "empfohlene verweisen - sonst raet der Anwender"
    )


def test_der_einstieg_ins_messen_ist_gekennzeichnet():
    """Die zwei Aufrufe, mit denen ein Anfaenger anfangen soll."""
    assert "EMPFOHLENER EINSTIEG" in docstring("ItemAccess.read")
    assert "EMPFOHLENER WEG" in docstring("MeasureControl.record_csv")


# ---------------------------------------------------------------------------
# E9 - Falle 1: read_mapped() ohne Tabelle liest sie jedes Mal neu
# ---------------------------------------------------------------------------


def test_ein_einzelner_aufruf_ohne_tabelle_warnt_nicht(caplog):
    """Fuer einen Blick ist der bequeme Weg der richtige."""
    with caplog.at_level(logging.WARNING, logger="wt3000.device"):
        with fassade() as wt:
            wt.measure.read_mapped()
    assert "read_mapped()" not in caplog.text


def test_wiederholtes_lesen_ohne_tabelle_meldet_sich_genau_einmal(caplog):
    with caplog.at_level(logging.WARNING, logger="wt3000.device"):
        with fassade() as wt:
            for _ in range(5):
                wt.measure.read_mapped()
    treffer = [s for s in caplog.messages if "read_mapped()" in s]
    assert len(treffer) == 1, f"erwartet genau eine Meldung, bekommen: {treffer}"
    assert "wt.items.read()" in treffer[0], "die Meldung muss den Ausweg nennen"


def test_mit_uebergebener_tabelle_bleibt_es_still(caplog):
    with caplog.at_level(logging.WARNING, logger="wt3000.device"):
        with fassade() as wt:
            tabelle = wt.items.read()
            for _ in range(5):
                wt.measure.read_mapped(tabelle)
    assert "read_mapped()" not in caplog.text


def test_die_tabelle_wird_bewusst_nicht_gepuffert():
    """Ein Puffer lieferte nach einer Tabellenaenderung falsche Namen.

    Das ist der Grund, warum die Falle nur gemeldet und nicht 'behoben' wird -
    festgehalten, damit die naechste Optimierung sie nicht doch einbaut.
    """
    modell = geraet()
    with fassade(modell) as wt:
        vorher = wt.measure.read_mapped()
        assert list(vorher) == ["U1", "I1", "P1"]

        # Das Geraet steht jetzt anders da als beim ersten Aufruf.
        modell.items[2] = "P,2"
        nachher = wt.measure.read_mapped()

    assert list(nachher) == ["U1", "P2", "P1"], (
        "read_mapped() ohne Tabelle muss die AKTUELLE Tabelle sehen"
    )


# ---------------------------------------------------------------------------
# E9 - Falle 2: eine Messung ohne Limit laeuft unbegrenzt
# ---------------------------------------------------------------------------


def test_stream_ohne_limit_warnt(caplog):
    with caplog.at_level(logging.WARNING, logger="wt3000.device"):
        with fassade() as wt:
            wt.measure.stream(wt.items.read(), interval_s=0.0)
    treffer = [s for s in caplog.messages if s.startswith("stream() ohne Limit")]
    assert len(treffer) == 1
    assert "max_samples=" in treffer[0], "die Meldung muss den Ausweg nennen"


@pytest.mark.parametrize(
    "grenze", [{"max_samples": 1}, {"max_duration_s": 0.1}]
)
def test_mit_limit_bleibt_es_still(grenze, caplog):
    with caplog.at_level(logging.WARNING, logger="wt3000.device"):
        with fassade() as wt:
            wt.measure.stream(wt.items.read(), interval_s=0.0, **grenze)
    assert "ohne Limit" not in caplog.text


def test_die_warnung_gilt_fuer_alle_drei_wege():
    """record(), start() und stream() sind derselbe Fehler - dieselbe Meldung."""
    import inspect

    from wt3000_scpi import MeasureControl

    for name, ende in (("record", "Strg+C"), ("start", "stop()"), ("stream", "break")):
        quelle = inspect.getsource(getattr(MeasureControl, name))
        assert "_warn_ohne_limit" in quelle, f"{name}() warnt nicht ohne Limit"
        assert ende in quelle, f"{name}() nennt nicht, wodurch die Messung endet"


# ---------------------------------------------------------------------------
# E9 - Falle 3: ungepruefte Funktionen in einem Messprofil
# ---------------------------------------------------------------------------


def test_ungepruefte_funktionen_werden_beim_bauen_gemeldet(caplog):
    """'ItemSpec.verify' wurde bisher gesetzt und von niemandem gelesen.

    Wer 'integration_profile()' benutzte, erfuhr nirgends, dass ein Teil der
    Spalten auf einer Annahme beruht - und ein NAN in der CSV sieht aus wie
    ein Messproblem, nicht wie eine offene Frage des Treibers.
    """
    with caplog.at_level(logging.WARNING, logger="wt3000.itemspec"):
        build_item_table(list(build_integration_profile()))

    treffer = [s for s in caplog.messages if "nicht bestaetigt" in s]
    assert len(treffer) == 1, "genau eine Meldung je Tabelle, nicht eine je Item"
    assert "WH" in treffer[0] and "TIME" in treffer[0]
    assert "NAN" in treffer[0], "der Hinweis auf die Folge gehoert in die Meldung"


def test_ein_geprueftes_profil_meldet_nichts(caplog):
    """Das Standardprofil ist am Geraet nachgemessen - es gibt nichts zu sagen."""
    with caplog.at_level(logging.WARNING, logger="wt3000.itemspec"):
        build_item_table([ItemSpec("U", "1"), ItemSpec("P", "SIGMA")])
    assert "nicht bestaetigt" not in caplog.text


# ---------------------------------------------------------------------------
# E9 - Falle 4: waehrend start() gehoert die Sitzung dem Mess-Thread
# ---------------------------------------------------------------------------


def test_der_docstring_von_start_nennt_die_sperre_und_den_ausweg():
    """Der haeufigste Fehler in Pruefstandsablaeufen - er gehoert benannt."""
    text = docstring("MeasureControl.start")
    assert "ConcurrentAccessError" in text
    assert "stream()" in text, "ohne den Ausweg ist die Warnung nur ein Verbot"


def test_scope_wird_weiterhin_streng_aufgeloest():
    """Gegenprobe, dass die Docstring-Aenderungen nichts am Verhalten drehen."""
    with fassade() as wt:
        assert wt.ranges.expand_scope("SIGMA") == (1, 2, 3)
        assert wt.ranges.get_range(Quantity.VOLTAGE, 1).value == 1000.0


def test_basisantworten_unveraendert():
    """Haelt fest, dass die Vorrichtung dieses Moduls dieselbe ist wie sonst."""
    assert base_responses()[":INPUT:WIRING"] == "V3A3,P1W2"
