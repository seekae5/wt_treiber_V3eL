# =============================================================================
# Datei: tests/test_beispiele.py
# Faehrt jedes Skript aus examples/ vollstaendig gegen ein simuliertes Geraet.
#
# examples/ ist die Vorlage, aus der ein Anwender kopiert. Ein Beispiel, das an
# einer geaenderten Signatur scheitert, kostet genau das Vertrauen, das die
# Sammlung herstellen soll - und faellt sonst niemandem auf, weil niemand
# regelmaessig sechs Skripte von Hand startet.
#
# Ersetzt wird nur der Draht: 'TmctlTransport' im Namensraum der Fassade, das
# Ausgabeverzeichnis und die Wartezeiten. Der Ablauf selbst laeuft, wie er in
# der Datei steht.
# =============================================================================

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from conftest import Geraetemodell

from wt_treiber_lib import IntegrationState, Quantity, wt3000_device

BEISPIELE = Path(__file__).resolve().parents[1] / "examples"


# ---------------------------------------------------------------------------
# Beispiel laden und fahren
# ---------------------------------------------------------------------------

#: Reihenfolge wie in examples/README.md.
SKRIPTE = (
    "01_geraet_ansehen",
    "02_messreihe_csv",
    "03_eigene_groessen",
    "04_bereiche_setzen",
    "05_hintergrundmessung",
    "06_integration_wh",
)


def lade(name: str):
    """Ein Beispiel als Modul laden - ueber den Dateipfad, wie geraeteskript().

    Jeder Aufruf liefert ein FRISCHES Modulobjekt: die Tests setzen darin
    Modulkonstanten um, und ein geteiltes Objekt truege sie weiter.

    'examples/' muss dabei auf sys.path liegen, weil jedes Beispiel mit
    'import _pfad' beginnt. Beim gewoehnlichen Start ('python examples/01_....py')
    legt der Interpreter das Skriptverzeichnis von selbst dorthin; hier wird
    genau das nachgestellt - und hinterher wieder abgeraeumt, damit die uebrige
    Suite keinen zusaetzlichen Importweg vorfindet.
    """
    spec = importlib.util.spec_from_file_location(f"beispiel_{name}", BEISPIELE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)

    sys.path.insert(0, str(BEISPIELE))
    try:
        spec.loader.exec_module(modul)
    finally:
        sys.path.remove(str(BEISPIELE))
        sys.modules.pop("_pfad", None)
    return modul


@pytest.fixture
def beispiellauf(monkeypatch, tmp_path):
    """main() eines Beispiels gegen das Geraetemodell fahren.

    Drei Ersetzungen, und keine davon beruehrt den Ablauf:

      TmctlTransport   im Namensraum der FASSADE - das ist der einzige Weg,
                       auf dem 'WT3000.connect()' zu einer echten Verbindung
                       kaeme. Damit laeuft das Beispiel mit seinem eigenen,
                       unveraenderten 'WT3000.connect(ip=IP)'.
      AUSGABE          sonst landen CSV, Sidecar und Backup im Arbeitsbaum -
                       jeder Testlauf hinterliesse Dateien.
      Wartezeiten      ANZAHL/max_duration und die Platzhalter aus Beispiel 05.
                       Sie messen im Sekundentakt; das waeren Minuten
                       Testlaufzeit fuer eine Suite, die sonst in Sekunden
                       durchlaeuft.
    """

    def _fahren(name: str) -> tuple[object, Geraetemodell]:
        modell = Geraetemodell()
        monkeypatch.setattr(wt3000_device, "TmctlTransport", lambda _config: modell)
        monkeypatch.setenv("WT3000_IP", "10.0.0.5")
        monkeypatch.setenv("WT3000_USE_REMOTE", "0")

        modul = lade(name)
        if hasattr(modul, "AUSGABE"):
            monkeypatch.setattr(modul, "AUSGABE", tmp_path)
        # Takt und Laenge herunterdrehen - das Einzige, was am Ablauf geaendert
        # wird. Was dieser Test prueft, haengt an keinem davon.
        for konstante, wert in (("INTERVALL_S", 0.0), ("ANZAHL", 2), ("SEKUNDEN", 0)):
            if hasattr(modul, konstante):
                monkeypatch.setattr(modul, konstante, wert)
        for platzhalter in (
            "pruefstand_hochfahren",
            "warten_bis_temperatur_erreicht",
            "pruefstand_abfahren",
        ):
            if hasattr(modul, platzhalter):
                monkeypatch.setattr(modul, platzhalter, lambda: None)

        assert modul.main() == 0, f"{name}.main() meldet einen Fehler"
        return modul, modell

    return _fahren


# ---------------------------------------------------------------------------
# Die Sammlung selbst
# ---------------------------------------------------------------------------


def test_readme_nennt_jedes_skript():
    """Ein Beispiel, das im Index fehlt, findet niemand."""
    vorhanden = {p.stem for p in BEISPIELE.glob("*.py") if not p.stem.startswith("_")}
    assert vorhanden == set(SKRIPTE), (
        f"examples/ enthaelt {sorted(vorhanden)}, geprueft wird {sorted(SKRIPTE)}"
    )

    index = (BEISPIELE / "README.md").read_text(encoding="utf-8")
    fehlend = [name for name in SKRIPTE if f"{name}.py" not in index]
    assert not fehlend, f"examples/README.md nennt nicht: {fehlend}"


@pytest.mark.parametrize("name", SKRIPTE)
def test_beispiel_benutzt_die_fassade(name):
    """Der Zweck der Sammlung, als Pruefsatz.

    Die Stufenskripte bauen Transport und Sitzung von Hand zusammen; genau das
    sollen die Beispiele NICHT vorleben. Wer hier kuenftig 'WTSession(...)'
    schreibt, hat ein Stufenskript geschrieben und kein Beispiel.
    """
    quelle = (BEISPIELE / f"{name}.py").read_text(encoding="utf-8")
    assert "WT3000.connect(" in quelle
    assert "WTSession(" not in quelle, f"{name} baut die Sitzung selbst - dafuer ist die Fassade da"
    assert "TmctlTransport(" not in quelle, f"{name} baut den Transport selbst"
    # Kein Import aus einem Fachmodul: die Zusage aus dem Kopf von __init__.py.
    assert "wt_treiber_lib.wt3000_" not in quelle, f"{name} importiert an der Fassade vorbei"


@pytest.mark.parametrize("name", SKRIPTE)
def test_beispiel_laeuft_durch(name, beispiellauf):
    beispiellauf(name)


# ---------------------------------------------------------------------------
# Die Zusagen der Kopfzeilen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["01_geraet_ansehen", "02_messreihe_csv"])
def test_die_ersten_beiden_schreiben_nichts(name, beispiellauf):
    """Beide sagen im Kopf 'SCHREIBT NICHTS' zu.

    Das ist die Eigenschaft, wegen der man sie am eingemessenen Geraet zuerst
    laufen laesst - sie wird deshalb nachgewiesen und nicht nur behauptet.
    Geprueft wird am Draht: alles, was kein Query ist, waere ein Set-Kommando.
    """
    _modul, modell = beispiellauf(name)
    gesendet = [befehl for befehl in modell.written if not befehl.strip().endswith("?")]
    assert not gesendet, f"{name} hat gesendet: {gesendet}"


def test_02_legt_csv_und_sidecar_an(beispiellauf, tmp_path):
    modul, _modell = beispiellauf("02_messreihe_csv")
    csv_datei = tmp_path / "messreihe.csv"
    assert csv_datei.exists()
    assert (tmp_path / "messreihe.csv.meta.json").exists()

    kopf = csv_datei.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert kopf[:4] == ["timestamp_iso", "elapsed_s", "sample", "condition"]
    assert kopf[-1] == "status_flags"
    # Die Spalten des GERAETS - 02 uebernimmt sie, statt sie zu setzen.
    assert kopf[4:-1] == ["U1", "I1", "P1", "U2", "I2", "P2"]


def test_03_stellt_die_item_tabelle_zurueck(beispiellauf, tmp_path):
    """'hier steht die Item-Tabelle wieder wie vorgefunden' - nachgewiesen."""
    _modul, modell = beispiellauf("03_eigene_groessen")
    assert modell.items[1] == "U,1"
    assert modell.items[4] == "U,2"
    assert modell.number == 6
    # Und das Profil war ueberhaupt wirksam - sonst prueft der Vergleich nichts.
    assert any("LAMBDA,SIGMA" in befehl for befehl in modell.written)
    assert (tmp_path / "itemtabelle_backup.json").exists()


def test_04_stellt_die_bereiche_zurueck(beispiellauf):
    """'hier stehen die Bereiche wieder wie vorgefunden' - nachgewiesen."""
    _modul, modell = beispiellauf("04_bereiche_setzen")
    for element in (1, 2, 3, 4):
        assert modell.responses[f":INPUT:VOLTAGE:RANGE:ELEMENT{element}"] == "1.000E+03"
    assert any(
        befehl.startswith(f"{Quantity.VOLTAGE.value}:RANGe") for befehl in modell.written
    )


def test_06_stoppt_die_integration_auch_bei_erfolg(beispiellauf):
    """'running()' garantiert den Stopp - ein Zaehlvorgang darf nicht weiterlaufen."""
    _modul, modell = beispiellauf("06_integration_wh")
    assert ":INTEGrate:STARt" in modell.written
    assert ":INTEGrate:STOP" in modell.written
    assert modell.responses[":INTEGRATE:STATE"] == IntegrationState.STOP.value
    # Der Zaehlerstand bleibt: RESet ist unwiderruflich und gesperrt.
    assert not any("RESet" in befehl for befehl in modell.written)
