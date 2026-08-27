# =============================================================================
# Datei: tests/test_benennung.py
#
# Schritt E8 aus dem Umbauplan: EIN Begriff fuer "welches Element meine ich".
#
# Bis hierher hiess dieselbe Angabe in 'wt3000_input' 'target' und ueberall
# sonst 'scope', und die Typangabe stand einmal als 'int | str' und einmal als
# 'str | int'. Fuer den Anwender waren das drei Schreibweisen fuer eine Frage.
# Dazu nahm 'ItemSpec' das Element ausschliesslich als Zeichenkette an -
# 'ItemSpec("U", 1)' fuehrte stillschweigend zu einer Spec, die zu keiner
# gelesenen Tabelle passte.
#
# Diese Pruefsaetze halten den erreichten Zustand fest UND die Uebergangsfrist:
# 'target=' muss weiter wirken, sonst braeche jedes bestehende Messskript.
# =============================================================================

from __future__ import annotations

import inspect
import logging

import pytest
from conftest import ItemTableTransport

from wt3000_scpi import (
    WT3000,
    InputConfig,
    ItemSpec,
    RangeAccess,
    RangeSpec,
    Scope,
    WTConfig,
    WTError,
    GROUP_RANGE,
)
from wt3000_scpi.wt3000_input import scope_node


def fassade(**kwargs) -> WT3000:
    kwargs.setdefault("read_only", True)
    return WT3000.from_transport(
        ItemTableTransport({1: "U,1"}, number=1), WTConfig(use_remote=False), **kwargs
    )


# ---------------------------------------------------------------------------
# Ein Begriff, ein Typ
# ---------------------------------------------------------------------------

#: Jede oeffentliche Stelle, an der ein Element/eine Unit/'ALL' angegeben wird.
STELLEN = (
    (InputConfig, "set_voltage_range"),
    (InputConfig, "set_current_range"),
    (InputConfig, "set_current_range_sensor"),
    (InputConfig, "set_voltage_auto_range"),
    (InputConfig, "set_current_auto_range"),
    (InputConfig, "set_line_filter"),
    (InputConfig, "set_frequency_filter"),
    (InputConfig, "set_scaling_state"),
    (InputConfig, "set_vt_ratio"),
    (InputConfig, "set_ct_ratio"),
    (InputConfig, "set_power_factor"),
    (InputConfig, "set_sensor_ratio"),
    (InputConfig, "set_sync_source"),
    (InputConfig, "set_voltage_mode"),
    (InputConfig, "set_current_mode"),
    (RangeAccess, "set_range"),
    (RangeAccess, "set_auto"),
    (RangeAccess, "expand_scope"),
)


@pytest.mark.parametrize(
    ("klasse", "methode"), STELLEN, ids=[f"{k.__name__}.{m}" for k, m in STELLEN]
)
def test_die_zielangabe_heisst_ueberall_scope(klasse, methode):
    parameter = inspect.signature(getattr(klasse, methode)).parameters
    assert "scope" in parameter, f"{klasse.__name__}.{methode}() kennt kein 'scope'"
    assert "target" not in parameter, (
        f"{klasse.__name__}.{methode}() traegt noch den alten Namen in der Signatur - "
        "'target' darf nur ueber den Uebergangs-Dekorator ankommen"
    )


@pytest.mark.parametrize(
    ("klasse", "methode"), STELLEN, ids=[f"{k.__name__}.{m}" for k, m in STELLEN]
)
def test_die_zielangabe_traegt_ueberall_denselben_typ(klasse, methode):
    """'int | str' und 'str | int' sind dasselbe - aber nicht fuer den Leser."""
    annotation = inspect.signature(getattr(klasse, methode)).parameters["scope"].annotation
    assert annotation == "Scope", (
        f"{klasse.__name__}.{methode}(): 'scope' ist mit {annotation!r} annotiert, "
        "erwartet wird der gemeinsame Alias 'Scope'"
    )


def test_auch_der_bereichsplan_benutzt_den_begriff():
    assert RangeSpec.__annotations__["scope"] == "Scope"
    assert Scope == (int | str)


def test_der_alias_ist_aus_dem_paket_importierbar():
    """Ein Typ, den Signaturen fuehren, gehoert in die Paketoberflaeche (E1)."""
    import wt3000_scpi

    assert "Scope" in wt3000_scpi.__all__


def test_der_hilfsname_heisst_ebenfalls_scope():
    """'target_node' hiess als einziger Baustein noch nach dem alten Begriff."""
    assert scope_node(3) == ":ELEMent3"
    assert scope_node("SIGMB") == ":SIGMB"
    assert scope_node("ALL") == ":ALL"


# ---------------------------------------------------------------------------
# Die Uebergangsfrist: 'target=' wirkt weiter
# ---------------------------------------------------------------------------


def test_der_alte_name_wirkt_weiter_und_meldet_sich(caplog):
    """Ein harter Umbenenner haette jedes bestehende Skript gebrochen.

    Und zwar mit einem TypeError mitten im Lauf - also genau dann, wenn am
    Geraet schon etwas eingestellt ist. Deshalb die Frist.
    """
    with fassade(read_only=False, allow_changes=True) as wt:
        with wt.input.unlocked(GROUP_RANGE):
            with caplog.at_level(logging.WARNING, logger="wt3000.input"):
                with pytest.warns(DeprecationWarning, match="target"):
                    wt.input.set_voltage_range(1000.0, target=1)

    assert any("heisst jetzt" in s for s in caplog.messages), (
        "die Meldung muss den neuen Namen nennen, nicht nur den alten ruegen"
    )


def test_beide_namen_zugleich_sind_ein_fehler():
    """Sonst waere unklar, welcher gilt - und der Aufrufer erfuehre es nie."""
    with fassade(read_only=False, allow_changes=True) as wt:
        with wt.input.unlocked(GROUP_RANGE):
            with pytest.raises(WTError, match="zugleich angegeben"):
                wt.input.set_voltage_range(1000.0, scope=1, target=1)


def test_der_neue_name_meldet_nichts(caplog):
    with fassade(read_only=False, allow_changes=True) as wt:
        with wt.input.unlocked(GROUP_RANGE):
            with caplog.at_level(logging.WARNING, logger="wt3000.input"):
                wt.input.set_voltage_range(1000.0, scope=1)
    assert "veraltet" not in caplog.text


def test_die_editorhilfe_zeigt_den_neuen_namen():
    """'functools.wraps' muss Signatur und Docstring durchreichen.

    Ohne das zeigte die Vervollstaendigung '(*args, **kwargs)' - und der
    Anwender bekaeme ausgerechnet dort keine Hilfe, wo er den neuen Namen
    lernen soll.
    """
    signatur = inspect.signature(InputConfig.set_voltage_range)
    assert list(signatur.parameters) == ["self", "volts", "scope"]
    assert "STATTDESSEN EMPFOHLEN" in (InputConfig.set_voltage_range.__doc__ or "")


# ---------------------------------------------------------------------------
# ItemSpec nimmt Zahlen
# ---------------------------------------------------------------------------


def test_element_darf_eine_zahl_sein():
    """Die Schreibweise, die jeder zuerst versucht."""
    assert ItemSpec("U", 1) == ItemSpec("U", "1")
    assert ItemSpec("U", 1).element == "1"


def test_ordnung_darf_eine_zahl_sein():
    """Die 5. Oberschwingung ist der Sache nach eine Zahl."""
    assert ItemSpec("U", 1, 5) == ItemSpec("U", "1", "5")
    assert ItemSpec("U", 1, 5).argument == "U,1,5"


def test_gleichheit_und_hashwert_stimmen_ueberein():
    """Sonst laege dieselbe Spec zweimal in einem set() oder dict."""
    assert hash(ItemSpec("P", 2)) == hash(ItemSpec("P", "2"))
    assert len({ItemSpec("P", 2), ItemSpec("P", "2")}) == 1


def test_wahrheitswerte_werden_abgewiesen():
    """'bool' ist ein Subtyp von 'int' - 'True' darf nicht Element '1' werden."""
    with pytest.raises(WTError, match="Wahrheitswert"):
        ItemSpec("U", True)
    with pytest.raises(WTError, match="Wahrheitswert"):
        ItemSpec("U", 1, False)


def test_zahl_und_zeichenkette_bauen_dieselbe_tabelle():
    with fassade() as wt:
        mit_zahl = wt.items.build([ItemSpec("U", 1), ItemSpec("P", 2)])
        mit_text = wt.items.build([ItemSpec("U", "1"), ItemSpec("P", "2")])
    assert mit_zahl.to_dict() == mit_text.to_dict()


def test_none_bleibt_none():
    """Kein Element heisst weiterhin 'das Geraet setzt Element 1'."""
    assert ItemSpec("TIME").element is None
    assert ItemSpec("TIME").argument == "TIME"


# ---------------------------------------------------------------------------
# Die Quelldateien bleiben ASCII
# ---------------------------------------------------------------------------


def test_der_quelltext_bleibt_bei_einer_schreibweise():
    """Die Hauskonvention ist die ASCII-Umschreibung ('Geraet', nicht 'Gerät').

    Nicht weil sie sich besser laese - sondern weil sie in 13000 Zeilen
    durchgehalten ist und die fuenf Ausreisser, die es gab, aussahen wie
    Absicht. Wer das umstellen will, stellt ALLES um; ein Nebeneinander ist
    die einzige Variante, die keinem nutzt. Die Begruendung steht in
    docs/API-Ueberblick-und-Lesbarkeit.md, Befund D10.
    """
    import re
    from pathlib import Path

    import wt3000_scpi

    paket = Path(wt3000_scpi.__file__).parent
    treffer = {
        p.name: sorted(set(re.findall(r"\S*[äöüÄÖÜß]\S*", p.read_text(encoding="utf-8"))))
        for p in sorted(paket.glob("*.py"))
    }
    treffer = {name: worte for name, worte in treffer.items() if worte}
    assert not treffer, f"gemischte Schreibweise: {treffer}"
