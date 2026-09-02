# =============================================================================
# Datei: tests/test_kalibrierung.py
#
# Nullpunktkalibrierung ('*CAL?', Handbuch 6-114) ueber 'wt.calibrate_zero()'.
#
# Zwei Eigenheiten machen diesen Aufruf pruefenswert, und beide sind der Grund
# fuer eine eigene Datei:
#
#   1. '*CAL?' ENDET AUF '?' und ist damit fuer 'WTSession._validate()' ein
#      Query. Die Nur-Lesen-Sperre der Sitzung greift also NICHT - sie muesste
#      hier stillschweigend versagen. Fachlich ist der Aufruf aber ein
#      Geraeteeingriff: er unterbricht die Erfassung und verstellt die
#      Nullpunkte. Die Sperre steht deshalb von Hand in der Fassade, und genau
#      das wird unten nachgewiesen - nicht nur an der Ausnahme, sondern daran,
#      dass NICHTS auf die Leitung gegangen ist.
#
#   2. DAS GERAET ARBEITET zwischen Empfang und Antwort. Der gewoehnliche
#      Timeout ist dafuer zu knapp; 'query_slow()' hebt ihn an und nimmt ihn im
#      'finally' zurueck. Ein haengengebliebener langer Timeout waere der
#      unangenehmste Rest: die naechste unbeantwortete Abfrage wartete
#      minutenlang. Deshalb wird die Ruecknahme im Erfolgs- UND im Fehlerfall
#      geprueft.
# =============================================================================

from __future__ import annotations

import logging

import pytest
from conftest import Geraetemodell, ItemTableTransport, base_responses

from wt_treiber_lib import WT3000, WTConfig, WTError
from wt_treiber_lib.wt3000_core import DeviceError, ProtocolError, ReadOnlyViolation
from wt_treiber_lib.wt3000_transport import FakeTransport


def fassade(transport: FakeTransport, **kwargs) -> WT3000:
    """Fassade auf einem Fake-Transport, ohne Fernsteuerung.

    'read_only=False' ist hier die Voreinstellung und nicht wie sonst 'True':
    jeder Fall dieser Datei ausser dem Sperrtest braucht eine schreibfaehige
    Sitzung, und eine Voreinstellung, die man in fast jedem Aufruf umstellt,
    ist die falsche.
    """
    kwargs.setdefault("read_only", False)
    return WT3000.from_transport(transport, WTConfig(use_remote=False), **kwargs)


def modell(**responses) -> ItemTableTransport:
    """Geraetemodell mit ueberschriebenen Einzelantworten."""
    tabelle = base_responses()
    tabelle.update(responses)
    return ItemTableTransport({1: "U,1"}, number=1, responses=tabelle)


# ---------------------------------------------------------------------------
# Der Normalfall
# ---------------------------------------------------------------------------


def test_kalibrierung_sendet_cal_und_kehrt_zurueck():
    transport = modell()
    with fassade(transport) as wt:
        assert wt.calibrate_zero() is None
    assert "*CAL?" in transport.written


def test_ein_fuehrendes_plus_gilt_als_erfolg():
    """'+0' ist dieselbe Antwort wie '0'.

    Das Geraet schreibt Zahlen an anderen Knoten mit Vorzeichen; ob es das
    hier tut, ist nicht belegt. Ein Treiber, der an '+0' scheiterte, meldete
    eine misslungene Kalibrierung, die gelungen ist - der teuerste der beiden
    moeglichen Irrtuemer.
    """
    with fassade(modell(**{"*CAL": "+0"})) as wt:
        wt.calibrate_zero()


def test_erfolg_wird_protokolliert(caplog):
    with caplog.at_level(logging.INFO, logger="wt3000.device"):
        with fassade(modell()) as wt:
            wt.calibrate_zero()
    assert any("normal beendet" in eintrag.message for eintrag in caplog.records)


# ---------------------------------------------------------------------------
# Die Nur-Lesen-Sperre - der Kern dieser Datei
# ---------------------------------------------------------------------------


def test_nur_lesen_sitzung_loest_keine_kalibrierung_aus():
    transport = modell()
    with fassade(transport, read_only=True) as wt:
        with pytest.raises(ReadOnlyViolation, match="Nullpunktkalibrierung"):
            wt.calibrate_zero()

    # Der eigentliche Nachweis: die Ausnahme kam VOR dem Senden. Ein Treiber,
    # der erst sendet und dann klagt, haette das Geraet bereits kalibriert.
    assert "*CAL?" not in transport.written


def test_die_sitzungssperre_allein_wuerde_cal_durchlassen():
    """Der Grund, warum die Sperre oben von Hand steht.

    Dieser Satz haelt die Eigenschaft fest, die den Handgriff noetig macht:
    'WTSession' selbst sieht in '*CAL?' einen harmlosen Query. Faellt das
    eines Tages weg - etwa weil '_validate()' eine Liste eingreifender Querys
    bekommt -, schlaegt dieser Test an und die doppelte Absicherung kann
    besprochen werden.
    """
    transport = modell()
    with fassade(transport, read_only=True) as wt:
        assert wt.session.query("*CAL?") == "0"


def test_allow_changes_wird_nicht_verlangt():
    """Eine Kalibrierung ist kein Einstellwert.

    'allow_changes' ist die Sperre der Fachobjekte gegen unbeabsichtigtes
    Verstellen. Sie hier zu verlangen hiesse, zwei Schloesser fuer eine Tuer
    zu fordern - 'read_only=False' ist die Aussage, um die es geht.
    """
    with fassade(modell(), allow_changes=False) as wt:
        wt.calibrate_zero()


# ---------------------------------------------------------------------------
# Vorbehalte: laufende Messung, laufende Integration
# ---------------------------------------------------------------------------


class StilleSenke:
    """Senke, die nichts festhaelt - fuer den blossen Nachweis eines Laufs."""

    def open(self, columns, metadata=None) -> None:
        return None

    def write(self, sample) -> None:
        return None

    def close(self) -> None:
        return None


def test_laufende_hintergrundmessung_wird_abgewiesen():
    transport = Geraetemodell()
    with fassade(transport) as wt:
        messung = wt.measure.start(StilleSenke(), interval_s=5.0)
        try:
            with pytest.raises(WTError, match="Hintergrundmessung"):
                wt.calibrate_zero()
            assert "*CAL?" not in transport.written
        finally:
            messung.stop()


def test_laufende_integration_wird_nur_gewarnt_nicht_abgewiesen(caplog):
    """Kein erfundener Vorbehalt.

    Das Handbuch nennt an '*CAL?' keine Bedingung ueber den
    Integrationszustand. Ein Treiber, der hier abwiese, blockierte einen
    Aufruf, der vielleicht zulaessig ist - dieselbe Begruendung wie bei
    'IntegrationConfig.set_mode()'. Das Geraet entscheidet, der Treiber warnt.
    """
    transport = Geraetemodell()
    transport.responses[":INTEGRATE:STATE"] = "START"
    with caplog.at_level(logging.WARNING, logger="wt3000.device"):
        with fassade(transport) as wt:
            wt.calibrate_zero()

    assert "*CAL?" in transport.written
    assert any("Integrationslauf" in eintrag.message for eintrag in caplog.records)


def test_unlesbarer_integrationszustand_verhindert_die_kalibrierung_nicht(caplog):
    """Der Zustand ist ein Hinweis, keine Voraussetzung.

    Scheitert schon das Lesen, waere es das Falsche, deshalb die Kalibrierung
    zu verweigern: der Aufrufer bekaeme eine Fehlermeldung ueber einen Knoten,
    nach dem er nie gefragt hat.
    """
    transport = modell()
    # 'fail_commands' wird nur im Konstruktor normalisiert; ein spaeter
    # ergaenzter Eintrag muss deshalb schon in der Vergleichsform stehen -
    # ohne '?' und in Grossschrift.
    transport.fail_commands.add(":INTEGRATE:STATE")
    with caplog.at_level(logging.DEBUG, logger="wt3000.device"):
        with fassade(transport) as wt:
            wt.calibrate_zero()

    # Der Fehlschlag ist tatsaechlich eingetreten - sonst prueft dieser Satz
    # nur, dass eine gelungene Abfrage nicht stoert.
    assert any("nicht lesbar" in eintrag.message for eintrag in caplog.records)
    assert "*CAL?" in transport.written


# ---------------------------------------------------------------------------
# Die Antwort des Geraets
# ---------------------------------------------------------------------------


def test_geraetefehler_wird_zur_deviceerror():
    with fassade(modell(**{"*CAL": "1"})) as wt:
        with pytest.raises(DeviceError, match="fehlgeschlagen"):
            wt.calibrate_zero()


def test_unerwartete_antwort_wird_zur_protocolerror():
    with fassade(modell(**{"*CAL": "JA"})) as wt:
        with pytest.raises(ProtocolError, match="'JA'"):
            wt.calibrate_zero()


def test_ein_eintrag_in_der_fehlerqueue_laesst_die_kalibrierung_scheitern():
    """'*CAL? -> 0' allein genuegt nicht.

    Meldet das Geraet die Kalibrierung als beendet, legt aber einen Eintrag in
    die Fehlerqueue, ist der Nullpunkt nicht vertrauenswuerdig. Der Aufruf
    darf dann nicht still zurueckkehren.
    """
    tabelle = base_responses()
    transport = ItemTableTransport(
        {1: "U,1"},
        number=1,
        responses=tabelle,
        error_queue=['916,"Calibration error"'],
    )
    with fassade(transport) as wt:
        with pytest.raises(DeviceError, match="Nullpunktkalibrierung"):
            wt.calibrate_zero()


# ---------------------------------------------------------------------------
# Der angehobene Timeout
# ---------------------------------------------------------------------------


def test_timeout_wird_angehoben_und_zurueckgenommen():
    transport = modell()
    config = WTConfig(use_remote=False, timeout_ms=5000, calibration_timeout_ms=45000)
    with WT3000.from_transport(transport, config, read_only=False) as wt:
        vorher = len(transport.timeouts_ms)
        wt.calibrate_zero()
        waehrend = transport.timeouts_ms[vorher:]

    # Erst hoch, dann wieder auf den konfigurierten Wert - in dieser Folge.
    assert waehrend == [45000, 5000]


def test_der_timeout_wird_auch_nach_einem_fehlschlag_zurueckgenommen():
    """Das 'finally' ist der eigentliche Zweck von 'query_slow()'.

    Bliebe der lange Wert stehen, wartete die naechste unbeantwortete Abfrage
    minutenlang - und niemand koennte sich erklaeren, warum.
    """
    transport = modell()
    config = WTConfig(use_remote=False, timeout_ms=5000, calibration_timeout_ms=45000)
    with WT3000.from_transport(transport, config, read_only=False) as wt:
        vorher = len(transport.timeouts_ms)
        transport.fail_commands.add("*CAL")
        with pytest.raises(WTError, match="nicht geantwortet"):
            wt.calibrate_zero()
        assert 5000 in transport.timeouts_ms[vorher:]


def test_nach_einem_timeout_wird_die_leitung_abgeraeumt():
    """Die verspaetete '0' darf nicht in die naechste Abfrage rutschen.

    Das Geraet kalibriert nach einem Timeout weiter und antwortet spaeter.
    Ohne 'drain_after_failure()' laege diese Antwort im Puffer und wuerde als
    Ergebnis der naechsten - voellig anderen - Abfrage gelesen.
    """
    transport = modell()
    transport.fail_commands.add("*CAL")
    with fassade(transport) as wt:
        gelesen_vorher = transport.reads
        with pytest.raises(WTError, match="nicht geantwortet"):
            wt.calibrate_zero()
        # drain_after_failure() liest genau einmal nach.
        assert transport.reads > gelesen_vorher


def test_die_timeout_meldung_nennt_die_stellschraube():
    """Wer in den Timeout laeuft, soll wissen, woran er drehen kann."""
    transport = modell()
    transport.fail_commands.add("*CAL")
    with fassade(transport) as wt:
        with pytest.raises(WTError) as fehler:
            wt.calibrate_zero()
    assert "calibration_timeout_ms" in str(fehler.value)


# ---------------------------------------------------------------------------
# Die Konfiguration
# ---------------------------------------------------------------------------


def test_calibration_timeout_hat_eine_voreinstellung_ueber_dem_normalen_timeout():
    config = WTConfig()
    assert config.calibration_timeout_ms > config.timeout_ms


def test_calibration_timeout_kommt_aus_der_umgebung(monkeypatch):
    monkeypatch.setenv("WT3000_CALIBRATION_TIMEOUT_MS", "12345")
    assert WTConfig.from_environment().calibration_timeout_ms == 12345


# ---------------------------------------------------------------------------
# Abgrenzung zur Auto-Kalibrierung der Integration
# ---------------------------------------------------------------------------


def test_kalibrieren_und_auto_kalibrierung_sind_zwei_verschiedene_dinge():
    """':INTEGrate:ACAL' ist ein Schalter, '*CAL?' eine Handlung.

    Die Namensaehnlichkeit ist die einzige Gemeinsamkeit. Dieser Satz haelt
    fest, dass der eine Aufruf nicht den anderen ausloest - eine Verwechslung
    im Treiber saehe man am Geraet erst an den Messwerten.
    """
    transport = Geraetemodell()
    with fassade(transport, allow_changes=True) as wt:
        wt.integration.set_auto_calibration(True)
        assert "*CAL?" not in transport.written

        transport.written.clear()
        wt.calibrate_zero()
        assert not any(
            "ACAL" in befehl.upper() for befehl in transport.written
        )
