# =============================================================================
# Datei: tests/test_sidecar_vollstaendigkeit.py
#
# Das Sidecar hat einen Zweck: eine CSV ohne Zusatzwissen interpretierbar
# machen. Fehlt darin eine Angabe, die die DEUTUNG der Daten aendert, ist das
# kein Schoenheitsfehler - dann ist die Datei still falsch lesbar.
#
# Genau das war der Fall. 'MeasureControl._run_parameters()' schrieb die
# Laufparameter von Hand ab und liess dabei 'mark_duplicates', 'error_policy'
# und 'check_update_rate' aus. Die Feldliste existierte an fuenf Stellen
# (vier Signaturen plus diese Funktion) und musste von Hand synchron gehalten
# werden - sie war es nicht.
#
# Der strukturelle Fix waere ein Datenobjekt, aus dem sich die Liste ABLEITET
# (Schritt E7, zurueckgestellt). Bis dahin haelt dieses Modul die Zuordnung:
# ein neuer Parameter an 'record()' laesst die Suite rot werden, bis jemand
# entschieden hat, ob er ins Sidecar gehoert.
# =============================================================================

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from conftest import ItemTableTransport

from wt_treiber_lib import (
    WT3000,
    CallbackSink,
    ErrorPolicy,
    MeasureControl,
    WTConfig,
)

# ---------------------------------------------------------------------------
# Die Zuordnung, um die es geht
# ---------------------------------------------------------------------------

#: Laufparameter -> Schluessel im Sidecar. Sie aendern die Deutung der Daten.
IN_DIE_METADATEN: dict[str, str] = {
    "interval_s": "sample_interval_s",
    "max_samples": "max_samples",
    "max_duration_s": "max_duration_s",
    "use_hold": "use_hold",
    "record_condition": "record_condition",
    "check_update_rate": "check_update_rate",
    "mark_duplicates": "mark_duplicates",
    "error_policy": "error_policy",
}

#: Parameter, die bewusst NICHT in den Metadaten stehen - mit dem Grund.
#
# Die Grenze ist Absicht: ein Sidecar, das jede Stellschraube mitschreibt,
# macht die Angaben, auf die es ankommt, schwerer auffindbar.
BEWUSST_DRAUSSEN: dict[str, str] = {
    "self": "kein Parameter",
    "sink": "die Ausgabe, nicht der Lauf - sie steht als 'data_files' im Sidecar",
    "table": "steht vollstaendig als 'item_table' und 'columns' im Sidecar",
    "log_every": "Kadenz der Protokollzeilen; beruehrt weder Daten noch Deutung",
    "metadata_path": "der Ablageort des Sidecars selbst",
    "sidecar": "ob ueberhaupt eines entsteht",
    "include_device": "ob der Steckbrief erhoben wird; das Ergebnis steht als 'device'",
    "parameters": "die Durchreiche fuer eigene Zusatzangaben des Aufrufers",
}


def geraet() -> ItemTableTransport:
    return ItemTableTransport({1: "U,1", 2: "I,1"}, number=2)


def lauf(tmp_path: Path, **kwargs) -> dict:
    """Eine Messung fahren und das Sidecar zurueckgeben."""
    ziel = tmp_path / "meta.json"
    with WT3000.from_transport(geraet(), WTConfig(use_remote=False)) as wt:
        wt.measure.record(
            CallbackSink(lambda _s: None),
            interval_s=0.0,
            max_samples=2,
            use_hold=False,
            metadata_path=ziel,
            **kwargs,
        )
    return json.loads(ziel.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Der Waechter gegen erneutes Auseinanderdriften
# ---------------------------------------------------------------------------


def test_jeder_parameter_von_record_ist_eingeordnet():
    """Der eigentliche Zweck dieses Moduls.

    Solange die Feldliste des Sidecars von Hand gefuehrt wird, kann sie von
    der Signatur abdriften - und genau das ist passiert. Ab hier faellt es
    auf: wer 'record()' um einen Parameter erweitert, muss ihn oben
    eintragen, entweder in IN_DIE_METADATEN oder mit Begruendung in
    BEWUSST_DRAUSSEN.
    """
    signatur = set(inspect.signature(MeasureControl.record).parameters)
    eingeordnet = set(IN_DIE_METADATEN) | set(BEWUSST_DRAUSSEN)

    unbekannt = signatur - eingeordnet
    assert not unbekannt, (
        f"record() hat Parameter, die niemand eingeordnet hat: {sorted(unbekannt)}. "
        "Gehoeren sie ins Sidecar? Dann in IN_DIE_METADATEN eintragen, sonst mit "
        "Begruendung in BEWUSST_DRAUSSEN."
    )
    verwaist = eingeordnet - signatur - {"self"}
    assert not verwaist, f"eingeordnet, aber nicht (mehr) in record(): {sorted(verwaist)}"


def test_alle_eingeordneten_parameter_stehen_auch_wirklich_drin(tmp_path):
    metadaten = lauf(tmp_path)
    fehlend = [
        schluessel
        for schluessel in IN_DIE_METADATEN.values()
        if schluessel not in metadaten["parameters"]
    ]
    assert not fehlend, f"im Sidecar fehlen: {fehlend}"


def test_was_draussen_bleiben_soll_bleibt_draussen(tmp_path):
    metadaten = lauf(tmp_path)
    assert "log_every" not in metadaten["parameters"]


# ---------------------------------------------------------------------------
# Warum es auf die drei nachgetragenen ankommt
# ---------------------------------------------------------------------------


def test_abgeschaltete_dublettenmarkierung_ist_am_sidecar_erkennbar(tmp_path):
    """Der Datenfehler, um den es ging.

    Ohne Markierung traegt kein Datensatz die Marke DUPLICATE, und
    'result.duplicates' steht auf 0. Waere die Einstellung nicht vermerkt,
    liesse sich "es gab keine Wiederholungen" nicht mehr von "Wiederholungen
    wurden nicht gekennzeichnet" unterscheiden - und beides sieht in der CSV
    gleich aus.
    """
    metadaten = lauf(tmp_path, mark_duplicates=False)

    assert metadaten["parameters"]["mark_duplicates"] is False
    # Der Befund, der ohne die Angabe irrefuehrend waere:
    assert metadaten["result"]["duplicates"] == 0


def test_eine_gesetzte_fehlerstrategie_steht_auswertbar_im_sidecar(tmp_path):
    """Als Objekt und nicht als repr() - das Sidecar ist JSON.

    Die Strategie entscheidet, ob ein ausgefallener Zyklus als MISSING-Zeile
    in der Datei steht oder den Lauf beendet. Ohne diese Angabe ist eine
    Luecke in den Daten nicht einzuordnen.
    """
    metadaten = lauf(tmp_path, error_policy=ErrorPolicy.unattended())

    policy = metadaten["parameters"]["error_policy"]
    assert isinstance(policy, dict), "erwartet ein Objekt, keine Zeichenkette"
    assert policy["max_consecutive"] == 5
    assert policy["reconnect_after"] == 2
    assert policy["max_reconnects"] == 10


def test_ohne_fehlerstrategie_steht_dort_null_und_nicht_nichts(tmp_path):
    """'null' ist eine Aussage: der erste Fehler haette den Lauf beendet."""
    metadaten = lauf(tmp_path)
    assert "error_policy" in metadaten["parameters"]
    assert metadaten["parameters"]["error_policy"] is None


def test_die_ratenpruefung_erklaert_das_ergebnisfeld(tmp_path):
    """'result.update_rate_s' bleibt leer, wenn nicht geprueft wurde."""
    metadaten = lauf(tmp_path, check_update_rate=False)
    assert metadaten["parameters"]["check_update_rate"] is False


# ---------------------------------------------------------------------------
# Das Sidecar bleibt als Ganzes brauchbar
# ---------------------------------------------------------------------------


def test_das_sidecar_ist_gueltiges_json_ohne_reste(tmp_path):
    """'default=str' rettet beim Schreiben alles - auch Unbeabsichtigtes.

    Deshalb die Gegenprobe, dass in den Parametern nur JSON-eigene Typen
    liegen: eine Zeichenkette 'ErrorPolicy(max_consecutive=5, ...)' waere
    zwar lesbar, aber von keinem Auswerteskript zu gebrauchen.
    """
    metadaten = lauf(tmp_path, error_policy=ErrorPolicy(), mark_duplicates=True)
    for schluessel, wert in metadaten["parameters"].items():
        assert isinstance(wert, (str, int, float, bool, dict, list, type(None))), (
            f"{schluessel} liegt als {type(wert).__name__} vor"
        )


@pytest.mark.parametrize("feld", ["sidecar_version", "run_id", "item_table", "columns", "units"])
def test_die_uebrigen_abschnitte_sind_unberuehrt(feld, tmp_path):
    """Der Nachtrag darf nichts verschoben haben."""
    assert feld in lauf(tmp_path)


def test_record_csv_ergaenzt_weiterhin_den_dateinamen(tmp_path):
    """Die Durchreiche 'parameters' muss neben den neuen Feldern bestehen."""
    ziel = tmp_path / "m.csv"
    with WT3000.from_transport(geraet(), WTConfig(use_remote=False)) as wt:
        wt.measure.record_csv(
            ziel, interval_s=0.0, max_samples=2, use_hold=False, sidecar=True
        )
    metadaten = json.loads((tmp_path / "m.csv.meta.json").read_text(encoding="utf-8"))
    assert metadaten["parameters"]["csv_file"] == "m.csv"
    assert metadaten["parameters"]["mark_duplicates"] is True
