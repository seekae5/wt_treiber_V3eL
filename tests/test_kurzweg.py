# =============================================================================
# Datei: tests/test_kurzweg.py
#
# Schritt E5 aus dem Umbauplan: der kurze Weg zu Messwerten.
#
#   (a) 'table' ist an record(), record_csv(), start() und stream() optional -
#       ohne Angabe wird die Item-Tabelle des Geraets uebernommen.
#   (b) 'wt.items.from_keys([...])' baut eine Zieltabelle aus SPALTENNAMEN,
#       ohne dass der Aufrufer ItemSpec kennen muss.
#
# Der Kern von (b) ist die RUNDREISE: 'from_keys' muss die exakte Umkehrung
# von 'NumericItem.key' sein. Waere sie es nicht, bekaeme der Anwender fuer
# einen Namen aus seiner eigenen CSV eine andere Spalte zurueck - ein
# Abkuerzung, die stillschweigend etwas anderes misst, waere schlimmer als
# gar keine.
# =============================================================================

from __future__ import annotations

import logging

import pytest
from conftest import ItemTableTransport

from wt_treiber_lib import (
    WT3000,
    CallbackSink,
    ItemSpec,
    WTConfig,
    WTError,
    build_harmonics_profile,
    build_integration_profile,
    build_standard_profile,
    spec_from_key,
    specs_from_keys,
)
from wt_treiber_lib.wt3000_itemspec import build_item_table


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
# (b) Die Rundreise - der eigentliche Beweis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "profil",
    [build_standard_profile, build_integration_profile, build_harmonics_profile],
    ids=lambda f: f.__name__,
)
def test_jeder_spaltenname_fuehrt_zu_seiner_spec_zurueck(profil):
    """186 Items ueber alle drei mitgelieferten Profile, ohne eine Abweichung.

    Das ist die staerkste Aussage, die sich ueber 'from_keys()' treffen
    laesst: fuer JEDE Groesse, die dieses Paket selbst anbietet, liefert der
    Spaltenname exakt die Spec zurueck, aus der er entstanden ist -
    einschliesslich Element und Ordnung.
    """
    specs = profil()
    tabelle = build_item_table(list(specs))

    for spec, item in zip(specs, tabelle.items):
        zurueck = spec_from_key(item.key)
        assert (zurueck.function, zurueck.element, zurueck.order) == (
            spec.function.upper(),
            spec.element,
            spec.order,
        ), f"Spaltenname {item.key!r} fuehrt nicht auf {spec} zurueck"


@pytest.mark.parametrize(
    ("name", "erwartet"),
    [
        ("U1", ItemSpec("U", "1")),
        ("I4", ItemSpec("I", "4")),
        ("PSIGMA", ItemSpec("P", "SIGMA")),
        ("LAMBDASIGMB", ItemSpec("LAMBDA", "SIGMB")),
        ("PHI1_1", ItemSpec("PHI", "1", "1")),
        ("U2_TOTAL", ItemSpec("U", "2", "TOTAL")),
        ("UTHD3", ItemSpec("UTHD", "3")),
        # Ohne Elementbezeichner - das Geraet setzt dann Element 1.
        ("TIME", ItemSpec("TIME", None)),
        # Kleinschreibung ist zulaessig; SCPI unterscheidet sie nicht.
        ("psigma", ItemSpec("P", "SIGMA")),
    ],
)
def test_einzelne_namen(name, erwartet):
    assert spec_from_key(name) == erwartet


def test_der_summenwert_heisst_psigma_und_nicht_p_unterstrich_sigma():
    """Der haeufigste Vertipper - und er darf nicht still durchgehen.

    'P_SIGMA' zerfaellt nach der Regel in Funktion 'P' mit der ORDNUNG
    'SIGMA'. Das ist kein Summenwert, sondern Unsinn - und faellt spaetestens
    beim Verifizieren nach dem Schreiben auf. Dieser Pruefsatz haelt fest,
    dass die beiden Schreibweisen wirklich Verschiedenes bedeuten, damit die
    Warnung im Docstring nicht eines Tages ins Leere zeigt.
    """
    assert spec_from_key("PSIGMA") == ItemSpec("P", "SIGMA")
    assert spec_from_key("P_SIGMA") == ItemSpec("P", None, "SIGMA")
    assert spec_from_key("PSIGMA") != spec_from_key("P_SIGMA")


@pytest.mark.parametrize("murks", ["", "   ", "U1_"])
def test_unbrauchbare_namen_werden_abgewiesen(murks):
    with pytest.raises(WTError):
        spec_from_key(murks)


def test_leere_namensliste_ist_ein_fehler():
    with pytest.raises(WTError, match="Leere Namensliste"):
        specs_from_keys([])


def test_from_keys_baut_dieselbe_tabelle_wie_build():
    """Die Abkuerzung darf nichts anderes ergeben als der ausfuehrliche Weg."""
    namen = ["U1", "I1", "P1", "PSIGMA"]
    specs = [ItemSpec("U", "1"), ItemSpec("I", "1"), ItemSpec("P", "1"), ItemSpec("P", "SIGMA")]

    with fassade() as wt:
        assert wt.items.from_keys(namen).to_dict() == wt.items.build(specs).to_dict()


def test_die_namen_der_gebauten_tabelle_sind_die_eingegebenen():
    """Der Kreis schliesst sich: was man hineingibt, steht im Spaltenkopf."""
    namen = ["U1", "I1", "P1", "PSIGMA", "PHI1_1"]
    with fassade() as wt:
        tabelle = wt.items.from_keys(namen)
    assert [item.key for item in tabelle.items] == namen


# ---------------------------------------------------------------------------
# (a) 'table' ist optional
# ---------------------------------------------------------------------------


def test_record_ohne_tabelle_misst_die_des_geraets(caplog):
    gesehen: list = []
    with caplog.at_level(logging.INFO, logger="wt3000.device"):
        with fassade() as wt:
            wt.measure.record(
                CallbackSink(gesehen.append), interval_s=0.0, max_samples=2, use_hold=False
            )

    assert len(gesehen) == 2
    # Drei Werte je Datensatz - die drei Items des Modellgeraets.
    assert all(len(sample.values) == 3 for sample in gesehen)
    assert any("die des Geraets wird uebernommen" in s for s in caplog.messages), (
        "die uebernommene Tabelle gehoert ins Protokoll - sonst weiss hinterher "
        "niemand, welche Spalten gemessen wurden"
    )


def test_stream_ohne_tabelle_liefert_dieselben_spalten():
    with fassade() as wt:
        eigene = list(wt.measure.stream(wt.items.read(), interval_s=0.0, max_samples=1))
        selbst = list(wt.measure.stream(interval_s=0.0, max_samples=1))
    assert len(eigene[0].values) == len(selbst[0].values) == 3


def test_eine_uebergebene_tabelle_hat_weiterhin_vorrang(caplog):
    """Der neue Vorgabewert darf den ausdruecklichen Wunsch nicht ueberfahren."""
    with caplog.at_level(logging.INFO, logger="wt3000.device"):
        with fassade() as wt:
            tabelle = wt.items.read()
            wt.measure.record(
                CallbackSink(lambda _s: None),
                tabelle,
                interval_s=0.0,
                max_samples=1,
                use_hold=False,
            )
    assert "die des Geraets wird uebernommen" not in caplog.text


def test_die_alte_aufrufform_bleibt_gueltig():
    """'table' war Pflicht und stand an zweiter Stelle - das muss so bleiben.

    Bestehende Skripte uebergeben sie positionell. Waere sie an eine andere
    Stelle gerutscht, liefe jedes davon in einen Typfehler oder - schlimmer -
    in eine falsche Zuordnung.
    """
    import inspect

    from wt_treiber_lib import MeasureControl

    for name, stelle in (("record", 2), ("record_csv", 2), ("start", 2), ("stream", 1)):
        parameter = list(inspect.signature(getattr(MeasureControl, name)).parameters)
        assert parameter[stelle] == "table", f"{name}(): 'table' ist verrutscht"


def test_die_tabelle_wird_einmal_je_lauf_gelesen_und_nicht_je_datensatz():
    """Der Unterschied zu 'read_mapped()' ohne Tabelle - und der Grund, warum
    hier NICHT gewarnt wird: eine Abfrage je Lauf ist kein Fehler."""
    modell = geraet()
    with fassade(modell) as wt:
        vorher = sum(1 for b in modell.written if b.strip() == ":NUMeric:NORMal?")
        wt.measure.record(
            CallbackSink(lambda _s: None), interval_s=0.0, max_samples=5, use_hold=False
        )
        nachher = sum(1 for b in modell.written if b.strip() == ":NUMeric:NORMal?")

    assert nachher - vorher == 1, "die Item-Tabelle darf nicht je Datensatz gelesen werden"
