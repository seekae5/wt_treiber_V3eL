# =============================================================================
# Datei: tests/test_motor.py
# Geraetefreie Tests der Motorauswertung ':MOTor' (Handbuch 6.17).
#
# Drei Dinge unterscheiden diese Gruppe von ihren Nachbarn, und um sie geht es
# hier:
#
#   1. DER EINGANGSTYP GATET DIE UEBRIGEN PARAMETER. RANGe und AUTO gelten nur
#      bei ANALog, PRANge/PULSe/RATE nur bei PULSe. Wer sie zum falschen Typ
#      setzt, bekommt hier eine Meldung, die den noetigen Aufruf NENNT - statt
#      eines 'Geraet meldet X' aus der Rueckleseprobe.
#   2. 'capture()' fragt deshalb nur ab, was zum eingestellten Typ gehoert.
#      Das ist kein Geiz, sondern Vorsicht: das Handbuchbeispiel zu
#      ':MOTor:SPEed?' fuehrt auf einem analogen Geraet die Pulsknoten gar
#      nicht auf, und ein Timeout mitten in einer Sicherung waere das
#      Gegenteil eines Sicherheitsnetzes.
#   3. DIE OPTIONSERKENNUNG IST DER SONDERFALL DES TREIBERS. Am eingemessenen
#      Geraet meldete '*OPT?' KEIN MTR, obwohl ':MOTor:PM?' antwortete;
#      zuverlaessig war der Modellcode '-MV'. Beide Wege werden geprueft.
# =============================================================================

from __future__ import annotations

import pytest
from conftest import (
    ItemTableTransport,
    base_responses,
    computation_responses,
    harmonics_responses,
    input_responses,
    integrate_responses,
    motor_base_responses,
    motor_responses,
)

from wt_treiber_lib import (
    MOTOR_ANALOG_RANGES_V,
    WT3000,
    MotorConfig,
    MotorInputType,
    MotorLineFilter,
    MotorSettings,
    WTConfig,
    WTError,
    build_motor_profile,
)
from wt_treiber_lib.wt3000_core import WTSession
from wt_treiber_lib.wt3000_deviceconfig import (
    DeviceConfigLocked,
    parse_motor_pair,
    parse_motor_unit,
)
from wt_treiber_lib.wt3000_transport import FakeTransport


def motor(transport: FakeTransport, allow_changes: bool = True, **kwargs) -> MotorConfig:
    """MotorConfig auf einer schreibfaehigen Sitzung."""
    session = WTSession(transport, WTConfig(use_remote=False), read_only=False)
    return MotorConfig(session, allow_changes=allow_changes, **kwargs)


def gesendet(transport: FakeTransport) -> list[str]:
    """Nur die Set-Kommandos."""
    return [c for c in transport.written if not c.endswith("?")]


# ---------------------------------------------------------------------------
# Die Optionspruefung - der Sonderfall dieses Treibers
# ---------------------------------------------------------------------------


def test_ohne_motorvariante_ist_die_gruppe_nicht_erreichbar():
    """Die Fassade weist ab, BEVOR ein Kommando in den Timeout laeuft."""
    with WT3000.from_transport(
        FakeTransport(base_responses()), WTConfig(use_remote=False)
    ) as wt:
        assert wt.device.supports(":MOTor") is False
        with pytest.raises(WTError, match="MOTor"):
            wt.motor


def test_die_meldung_nennt_modell_und_optionsantwort():
    """Ohne beides waere die Meldung nicht ohne Rueckfrage einzuordnen."""
    with WT3000.from_transport(
        FakeTransport(base_responses()), WTConfig(use_remote=False)
    ) as wt:
        with pytest.raises(WTError) as fehler:
            wt.motor
    text = str(fehler.value)
    assert "MTR" in text and "-MV" in text
    assert "WT3000" in text


def test_der_modellcode_reicht_auch_ohne_mtr():
    """Genau die Konstellation des eingemessenen Geraets.

    '*OPT?' meldet kein MTR, der Modellcode traegt aber '-MV' - und die Gruppe
    antwortet. Wer sich hier auf '*OPT?' verliesse, sperrte eine vorhandene
    Funktion aus.
    """
    with WT3000.from_transport(
        FakeTransport(motor_base_responses()), WTConfig(use_remote=False)
    ) as wt:
        assert wt.device.has_option("MTR") is False
        assert wt.device.is_motor_model is True
        assert isinstance(wt.motor, MotorConfig)


def test_umgekehrt_reicht_auch_mtr_allein():
    """Ein Geraet, das MTR meldet, ohne '-MV' im Modellcode."""
    antworten = motor_base_responses(options="G6,MTR")
    antworten["*IDN"] = "YOKOGAWA,WT3000,C1B234567,F2.11"
    with WT3000.from_transport(FakeTransport(antworten), WTConfig(use_remote=False)) as wt:
        assert wt.device.is_motor_model is False
        assert isinstance(wt.motor, MotorConfig)


def test_die_fassade_reicht_die_elementliste_durch():
    """Sync-Quellen werden gegen die BESTUECKTEN Elemente geprueft."""
    antworten = motor_base_responses(wiring="V3A3,NONE", modules="30,30,30,0")
    with WT3000.from_transport(FakeTransport(antworten), WTConfig(use_remote=False)) as wt:
        assert wt.motor.elements == (1, 2, 3)


# ---------------------------------------------------------------------------
# Die Sperre
# ---------------------------------------------------------------------------


def test_ohne_freigabe_wird_nichts_gesendet():
    transport = FakeTransport(motor_responses())
    cfg = motor(transport, allow_changes=False)
    with pytest.raises(DeviceConfigLocked, match="Motorauswertung"):
        cfg.set_poles(4)
    assert gesendet(transport) == []


def test_lesen_ist_immer_erlaubt():
    transport = FakeTransport(motor_responses())
    cfg = motor(transport, allow_changes=False)
    assert cfg.poles() == 2
    assert cfg.speed_type() is MotorInputType.ANALOG


# ---------------------------------------------------------------------------
# Der Eingangstyp gatet die uebrigen Parameter
# ---------------------------------------------------------------------------


def test_analogparameter_am_pulseingang_werden_abgewiesen():
    """Und die Meldung nennt den Aufruf, der fehlt."""
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    cfg = motor(transport)

    with pytest.raises(WTError) as fehler:
        cfg.set_speed_range_v(20.0)

    text = str(fehler.value)
    assert "PULSe" in text and "ANALog" in text
    assert "set_speed_type(MotorInputType.ANALOG)" in text, (
        "die Meldung muss den noetigen Aufruf nennen, nicht nur den Widerspruch"
    )
    assert gesendet(transport) == [], "vor dem Abweisen darf nichts hinausgehen"


def test_pulsparameter_am_analogeingang_werden_abgewiesen():
    transport = FakeTransport(motor_responses(torque_type="ANALOG"))
    cfg = motor(transport)
    with pytest.raises(WTError, match="set_torque_type"):
        cfg.set_torque_pulse_range(50.0, -50.0)
    assert gesendet(transport) == []


def test_die_impulszahl_gilt_nur_am_pulseingang():
    transport = FakeTransport(motor_responses(speed_type="ANALOG"))
    with pytest.raises(WTError, match="set_speed_type"):
        motor(transport).set_speed_pulses(60)


def test_die_drehmoment_nennwerte_gelten_nur_am_pulseingang():
    transport = FakeTransport(motor_responses(torque_type="ANALOG"))
    with pytest.raises(WTError, match="set_torque_type"):
        motor(transport).set_torque_rate_upper(50.0, 15000.0)


def test_typunabhaengige_parameter_gehen_immer():
    """Skalierung und Einheit haengen an keinem Eingangstyp."""
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    cfg = motor(transport)
    cfg.set_speed_scaling(1.0)
    cfg.set_speed_unit("rpm")
    assert gesendet(transport) == [
        ":MOTor:SPEed:SCALing 1",
        ':MOTor:SPEed:UNIT "rpm"',
    ]


# ---------------------------------------------------------------------------
# Drehzahl (SPEed)
# ---------------------------------------------------------------------------


def test_drehzahl_lesen():
    cfg = motor(FakeTransport(motor_responses()))
    assert cfg.speed_type() is MotorInputType.ANALOG
    assert cfg.speed_range_v() == 20.0
    assert cfg.speed_auto() is False
    assert cfg.speed_scaling() == 1.0
    assert cfg.speed_unit() == "rpm"


def test_drehzahl_eingangsart_setzen():
    # Die Antwort muss zum gesetzten Wert passen: 'FakeTransport' fuehrt eine
    # feste Tabelle, ein Schreibvorgang aendert sie nicht. Genau darum geht es
    # hier aber - dass die Rueckleseprobe ueberhaupt stattfindet.
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    motor(transport).set_speed_type(MotorInputType.PULSE)
    assert gesendet(transport) == [":MOTor:SPEed:TYPE PULSe"]


def test_eine_nicht_uebernommene_eingangsart_faellt_auf():
    """Die Rueckleseprobe ist der Kern des Schreibpfads.

    Das Geraet meldet hier weiter ANALOG - der Aufruf muss scheitern und darf
    den Aufrufer nicht im Glauben lassen, die Umstellung sei erfolgt.
    """
    transport = FakeTransport(motor_responses(speed_type="ANALOG"))
    with pytest.raises(WTError, match="Geraet meldet"):
        motor(transport).set_speed_type(MotorInputType.PULSE)


@pytest.mark.parametrize("volts", MOTOR_ANALOG_RANGES_V)
def test_jede_dokumentierte_bereichsstufe_wird_angenommen(volts):
    transport = FakeTransport(motor_responses(speed_range=f"{volts:.1f}E+00"))
    motor(transport).set_speed_range_v(volts)
    assert gesendet(transport) == [f":MOTor:SPEed:RANGe {volts:g}"]


def test_eine_zwischenstufe_wird_abgewiesen():
    """Vor dem Senden - ein ungueltiger Wert soll keinen Geraetefehler erzeugen."""
    transport = FakeTransport(motor_responses())
    with pytest.raises(WTError, match="keine Stufe"):
        motor(transport).set_speed_range_v(15.0)
    assert gesendet(transport) == []


def test_pulsbereich_der_drehzahl():
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    cfg = motor(transport)
    assert cfg.speed_pulse_range() == (10000.0, 0.0)
    cfg.set_speed_pulse_range(10000.0, 0.0)
    assert ":MOTor:SPEed:PRANge 10000,0" in gesendet(transport)


def test_der_obere_wert_steht_zuerst():
    """Das Handbuch verlangt die Reihenfolge - eine vertauschte faellt auf."""
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    with pytest.raises(WTError, match="Reihenfolge"):
        motor(transport).set_speed_pulse_range(0.0, 10000.0)


def test_impulse_je_umdrehung():
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    cfg = motor(transport)
    assert cfg.speed_pulses() == 60
    cfg.set_speed_pulses(60)
    assert ":MOTor:SPEed:PULSe 60" in gesendet(transport)


@pytest.mark.parametrize("count", [0, 10000])
def test_unzulaessige_impulszahl(count):
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    with pytest.raises(WTError, match="ausserhalb"):
        motor(transport).set_speed_pulses(count)


# ---------------------------------------------------------------------------
# Drehmoment (TORQue)
# ---------------------------------------------------------------------------


def test_drehmoment_lesen():
    cfg = motor(FakeTransport(motor_responses()))
    assert cfg.torque_type() is MotorInputType.ANALOG
    assert cfg.torque_range_v() == 20.0
    assert cfg.torque_scaling() == 1.0
    assert cfg.torque_unit() == "Nm"


def test_drehmoment_darf_negativ_werden():
    """Anders als die Drehzahl - ein Motor kann bremsen."""
    transport = FakeTransport(motor_responses(torque_type="PULSE"))
    motor(transport).set_torque_pulse_range(50.0, -50.0)
    assert ":MOTor:TORQue:PRANge 50,-50" in gesendet(transport)


def test_drehzahl_darf_nicht_negativ_werden():
    transport = FakeTransport(motor_responses(speed_type="PULSE"))
    with pytest.raises(WTError, match="ausserhalb"):
        motor(transport).set_speed_pulse_range(100.0, -1.0)


def test_nennwerte_des_drehmomentsignals():
    transport = FakeTransport(motor_responses(torque_type="PULSE"))
    cfg = motor(transport)
    assert cfg.torque_rate_upper() == (50.0, 15000.0)
    assert cfg.torque_rate_lower() == (-50.0, 5000.0)

    cfg.set_torque_rate_upper(50.0, 15000.0)
    assert ":MOTor:TORQue:RATE:UPPer 50,15000" in gesendet(transport)


@pytest.mark.parametrize("frequenz", [0.5, 200e6])
def test_unzulaessige_signalfrequenz(frequenz):
    transport = FakeTransport(motor_responses(torque_type="PULSE"))
    with pytest.raises(WTError, match="Frequenz"):
        motor(transport).set_torque_rate_upper(50.0, frequenz)


# ---------------------------------------------------------------------------
# Pm, Filter, Polzahl, Synchronisation
# ---------------------------------------------------------------------------


def test_mechanische_leistung():
    transport = FakeTransport(motor_responses())
    cfg = motor(transport)
    assert cfg.pm_scaling() == 1.0
    assert cfg.pm_unit() == "W"
    cfg.set_pm_scaling(1.0)
    assert ":MOTor:PM:SCALing 1" in gesendet(transport)


@pytest.mark.parametrize("factor", [0.00001, 100000.0])
def test_unzulaessiger_skalierungsfaktor(factor):
    transport = FakeTransport(motor_responses())
    with pytest.raises(WTError, match="ausserhalb"):
        motor(transport).set_pm_scaling(factor)


def test_einheitentext_hat_acht_zeichen_platz():
    transport = FakeTransport(motor_responses(pm_unit='"kW"'))
    motor(transport).set_pm_unit("kW")
    assert ':MOTor:PM:UNIT "kW"' in gesendet(transport)


def test_zu_langer_einheitentext_wird_abgewiesen():
    transport = FakeTransport(motor_responses())
    with pytest.raises(WTError, match="Zeichen"):
        motor(transport).set_pm_unit("123456789")


def test_ein_anfuehrungszeichen_im_text_wird_abgewiesen():
    """Es begrenzt die SCPI-Zeichenkette und kann nicht Teil des Textes sein."""
    transport = FakeTransport(motor_responses())
    with pytest.raises(WTError, match="Anfuehrungszeichen"):
        motor(transport).set_pm_unit('N"m')


def test_der_motorfilter_hat_einen_eigenen_frequenzsatz():
    """OFF, 100 Hz, 50 kHz - NICHT die 500 Hz / 5,5 kHz der Messeingaenge."""
    transport = FakeTransport(motor_responses(line_filter="100"))
    cfg = motor(transport)
    assert cfg.line_filter() is MotorLineFilter.HZ100

    with pytest.raises(WTError, match="unzulaessig"):
        cfg.set_line_filter("500HZ")


def test_der_filter_nimmt_auch_eine_frequenzzahl():
    """Ein Backup fuehrt die Grenzfrequenz als Zahl."""
    transport = FakeTransport(motor_responses(line_filter="50000"))
    motor(transport).set_line_filter(50000)
    assert ":MOTor:FILTer:LINE 50KHZ" in gesendet(transport)


def test_polzahl():
    transport = FakeTransport(motor_responses(poles="4"))
    cfg = motor(transport)
    cfg.set_poles(4)
    assert ":MOTor:POLE 4" in gesendet(transport)
    assert cfg.poles() == 4


@pytest.mark.parametrize("count", [0, 100])
def test_unzulaessige_polzahl(count):
    with pytest.raises(WTError, match="ausserhalb"):
        motor(FakeTransport(motor_responses())).set_poles(count)


def test_synchronisationsquelle():
    transport = FakeTransport(motor_responses(sync="U1"))
    cfg = motor(transport)
    cfg.set_sync_source("U1")
    assert ":MOTor:SYNChronize U1" in gesendet(transport)
    assert cfg.sync_source() == "U1"


def test_synchronisation_darf_auch_extern_oder_keine_sein():
    for quelle, antwort in (("EXTernal", "EXTERNAL"), ("NONE", "NONE")):
        transport = FakeTransport(motor_responses(sync=antwort))
        motor(transport).set_sync_source(quelle)
        assert any("SYNChronize" in c for c in gesendet(transport))


def test_die_syncsp_quelle_kennt_weder_extern_noch_keine():
    """Handbuch 6-82: {U<x>|I<x>}. Die Asymmetrie ist keine Vereinfachung.

    Die Synchrondrehzahl wird aus einer GEMESSENEN Frequenz gerechnet, und
    eine externe Taktquelle liefert keine.
    """
    transport = FakeTransport(motor_responses())
    cfg = motor(transport)
    for quelle in ("EXTernal", "NONE"):
        with pytest.raises(WTError, match="SyncSp-Quelle"):
            cfg.set_sync_speed_source(quelle)
    assert gesendet(transport) == []


def test_eine_sync_quelle_auf_unbestuecktem_element_wird_abgewiesen():
    transport = FakeTransport(motor_responses())
    cfg = motor(transport, elements=(1, 2, 3))
    with pytest.raises(WTError, match="nicht bestueckt"):
        cfg.set_sync_source("U4")


# ---------------------------------------------------------------------------
# Momentaufnahme: nur erheben, was zum Eingangstyp gehoert
# ---------------------------------------------------------------------------


def test_am_analogeingang_werden_die_pulsknoten_gar_nicht_abgefragt():
    """Der Kern der Vorsichtsmassnahme.

    Das Handbuchbeispiel zu ':MOTor:SPEed?' fuehrt auf einem analogen Geraet
    die Pulsknoten nicht auf. Ob sie einzeln antworten, ist ungeprueft - also
    wird nicht gefragt.
    """
    transport = FakeTransport(motor_responses())
    settings = motor(transport).capture()

    abgefragt = [c for c in transport.written if c.endswith("?")]
    assert not any("PRANGE" in c.upper() for c in abgefragt)
    assert not any("PULSE" in c.upper() for c in abgefragt)
    assert not any("RATE" in c.upper() for c in abgefragt)

    assert settings.speed.range_v == 20.0
    assert settings.speed.pulse_upper is None
    assert settings.speed_pulses is None
    assert settings.torque_rate_upper is None


def test_am_pulseingang_werden_die_analogknoten_gar_nicht_abgefragt():
    transport = FakeTransport(motor_responses(speed_type="PULSE", torque_type="PULSE"))
    settings = motor(transport).capture()

    abgefragt = [c.upper() for c in transport.written if c.endswith("?")]
    assert not any(":SPEED:RANGE" in c or ":TORQUE:RANGE" in c for c in abgefragt)
    assert not any(":AUTO" in c for c in abgefragt)

    assert settings.speed.range_v is None
    assert settings.speed.auto is None
    assert settings.speed.pulse_upper == 10000.0
    assert settings.speed_pulses == 60
    assert settings.torque_rate_upper == (50.0, 15000.0)
    assert settings.torque_rate_lower == (-50.0, 5000.0)


def test_die_momentaufnahme_ist_vollstaendig():
    settings = motor(FakeTransport(motor_responses())).capture()
    assert settings.pm_scaling == 1.0
    assert settings.pm_unit == "W"
    assert settings.line_filter is MotorLineFilter.OFF
    assert settings.poles == 2
    assert settings.sync_source == "NONE"
    assert settings.sync_speed_source == "I1"


def test_capture_veraendert_nichts():
    transport = FakeTransport(motor_responses())
    motor(transport, allow_changes=False).capture()
    assert gesendet(transport) == []


# ---------------------------------------------------------------------------
# Serialisierung und Wiederherstellung
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("typ", ["ANALOG", "PULSE"])
def test_die_momentaufnahme_uebersteht_die_rundreise(typ):
    settings = motor(
        FakeTransport(motor_responses(speed_type=typ, torque_type=typ))
    ).capture()
    assert MotorSettings.from_dict(settings.to_dict()) == settings


def test_die_momentaufnahme_laesst_sich_beschreiben():
    zeilen = motor(FakeTransport(motor_responses())).capture().describe()
    text = "\n".join(zeilen)
    assert "Motorauswertung" in text
    assert "Drehzahl" in text and "Drehmoment" in text
    assert "Polzahl: 2" in text


def test_restore_setzt_den_eingangstyp_zuerst():
    """Er entscheidet, welche der uebrigen Parameter das Geraet annimmt.

    Wuerde er zuletzt gesetzt, liefen die typgebundenen Aufrufe davor gegen
    den alten Typ - dieselbe Ueberlegung, aus der 'restore_input_snapshot()'
    Crest-Faktor und Wiring vorzieht.
    """
    transport = FakeTransport(motor_responses())
    cfg = motor(transport)
    cfg.restore(cfg.capture())

    befehle = gesendet(transport)
    typen = [i for i, c in enumerate(befehle) if ":TYPE" in c]
    andere = [i for i, c in enumerate(befehle) if ":SCALing" in c or ":RANGe" in c]
    assert typen and andere
    assert max(typen) < min(andere), f"Reihenfolge stimmt nicht: {befehle}"


def test_restore_schreibt_nicht_was_nie_gelesen_wurde():
    """Ausgelassene Felder waren fuer den Eingangstyp nicht gueltig."""
    transport = FakeTransport(motor_responses())
    cfg = motor(transport)
    cfg.restore(cfg.capture())

    befehle = " ".join(gesendet(transport)).upper()
    assert "PRANGE" not in befehle
    assert "PULSE " not in befehle
    assert "RATE" not in befehle


def test_restore_im_pulsbetrieb_schreibt_die_pulsknoten():
    transport = FakeTransport(motor_responses(speed_type="PULSE", torque_type="PULSE"))
    cfg = motor(transport)
    cfg.restore(cfg.capture())

    befehle = " ".join(gesendet(transport))
    assert ":MOTor:SPEed:PRANge" in befehle
    assert ":MOTor:SPEed:PULSe" in befehle
    assert ":MOTor:TORQue:RATE:UPPer" in befehle
    assert ":MOTor:TORQue:RATE:LOWer" in befehle


# ---------------------------------------------------------------------------
# Die Parser einzeln
# ---------------------------------------------------------------------------


def test_zahlenpaar_lesen():
    assert parse_motor_pair("50.0000,15.000E+03") == (50.0, 15000.0)
    assert parse_motor_pair("10000.0000,0.0000") == (10000.0, 0.0)


def test_ein_einzelwert_ist_kein_paar():
    with pytest.raises(WTError, match="Zahlenpaar"):
        parse_motor_pair("50.0000")


def test_einheitentext_wird_aus_den_anfuehrungszeichen_geschaelt():
    assert parse_motor_unit('"rpm"') == "rpm"
    assert parse_motor_unit(':MOTOR:SPEED:UNIT "Nm"') == "Nm"
    assert parse_motor_unit('""') == ""


# ---------------------------------------------------------------------------
# Das Messprofil - die Ergebnisse lesbar machen
# ---------------------------------------------------------------------------


def test_das_profil_fuehrt_die_fuenf_motorgroessen_ohne_element():
    """Sie beziehen sich auf den Motor, nicht auf ein Messelement."""
    specs = build_motor_profile()
    motorgroessen = [s for s in specs if s.function in
                     {"SPEED", "TORQUE", "PM", "SYNCSP", "SLIP"}]
    assert len(motorgroessen) == 5
    assert all(s.element is None for s in motorgroessen)
    assert all(s.verify for s in motorgroessen), (
        "am Original-WT3000 nicht bestaetigt - das gehoert gekennzeichnet"
    )


def test_das_profil_nimmt_die_elektrische_seite_mit():
    """Ohne sie laesst sich am Pruefstand kein Wirkungsgrad bilden."""
    keys = [i.key for i in _tabelle(build_motor_profile())]
    for erwartet in ("SPEED", "TORQUE", "PM", "U1", "I1", "P1", "PSIGMA"):
        assert erwartet in keys


def test_die_elektrische_seite_laesst_sich_weglassen():
    specs = build_motor_profile(elements=())
    assert len(specs) == 5


def test_die_einheiten_der_motorgroessen_bleiben_offen():
    """Sie sind am Geraet frei beschriftbar - eine geratene waere schlimmer."""
    from wt_treiber_lib.wt3000_numeric import unit_of

    for funktion in ("SPEED", "TORQUE", "PM"):
        assert unit_of(funktion) is None


def test_die_spaltennamen_fuehren_auf_ihre_spec_zurueck():
    """Die Rundreise aus E5 gilt auch fuer die elementlosen Motorgroessen."""
    from wt_treiber_lib import spec_from_key

    for spec, item in zip(build_motor_profile(), _tabelle(build_motor_profile())):
        zurueck = spec_from_key(item.key)
        assert (zurueck.function, zurueck.element, zurueck.order) == (
            spec.function.upper(),
            spec.element,
            spec.order,
        )


def _tabelle(specs):
    from wt_treiber_lib.wt3000_itemspec import build_item_table

    return build_item_table(list(specs)).items


def test_die_fassade_bietet_das_profil_an():
    with WT3000.from_transport(
        FakeTransport(motor_base_responses()), WTConfig(use_remote=False)
    ) as wt:
        assert wt.items.motor_profile() == build_motor_profile()


# ---------------------------------------------------------------------------
# Sitzungs-Backup
# ---------------------------------------------------------------------------


def alle_antworten(**kwargs) -> dict:
    """Antworttabelle einer Fassade, die ALLES sichern kann - inklusive Motor."""
    responses = motor_base_responses(**kwargs)
    responses.update(input_responses())
    responses.update(integrate_responses())
    responses.update(computation_responses())
    responses.update(harmonics_responses())
    return responses


def vollgeraet(**kwargs) -> ItemTableTransport:
    """Ein Geraet, das ALLES beantwortet - Item-Tabelle als Zustand inbegriffen.

    'wt.backup()' liest auch die Item-Tabelle; ein FakeTransport mit fester
    Antworttabelle traegt das nicht (siehe Kopf von ItemTableTransport).
    """
    transport = ItemTableTransport({1: "U,1", 2: "I,1"}, number=2)
    transport.responses.update(alle_antworten(**kwargs))
    return transport


def test_das_backup_erfasst_die_motorgruppe():
    with WT3000.from_transport(vollgeraet(), WTConfig(use_remote=False)) as wt:
        sicherung = wt.backup()

    assert "Motorauswertung" in sicherung.parts()
    assert sicherung.motor is not None
    assert sicherung.motor.poles == 2
    assert "Motorauswertung" in chr(10).join(sicherung.describe())


def test_das_backup_uebersteht_die_datei_rundreise(tmp_path):
    """Ein Backup, das sich nicht laden laesst, ist kein Sicherheitsnetz."""
    from wt_treiber_lib import SessionBackup

    ziel = tmp_path / "sicherung.json"
    with WT3000.from_transport(vollgeraet(), WTConfig(use_remote=False)) as wt:
        original = wt.backup(ziel)

    assert SessionBackup.load(ziel).motor == original.motor


def test_ohne_motorvariante_wird_die_gruppe_ausgelassen(caplog):
    """Ohne sie antwortet die Gruppe gar nicht.

    Ein Timeout mitten in der Sicherung waere das Gegenteil eines
    Sicherheitsnetzes - dieselbe Ueberlegung wie beim Auslassen von
    ':HARMonics' ohne die Rechenoption.
    """
    import logging

    transport = vollgeraet()
    transport.responses[transport._key("*IDN")] = "YOKOGAWA,WT3000,C1B234567,F2.11"

    with caplog.at_level(logging.INFO, logger="wt3000.device"):
        with WT3000.from_transport(transport, WTConfig(use_remote=False)) as wt:
            sicherung = wt.backup()

    assert sicherung.motor is None
    assert "Motorauswertung" not in sicherung.parts()
    assert any("MOTor" in s and "nicht mitgesichert" in s for s in caplog.messages), (
        "das Auslassen gehoert ins Protokoll - sonst faellt es niemandem auf"
    )


def test_ein_geladenes_backup_wird_zurueckgeschrieben():
    transport = vollgeraet()
    with WT3000.from_transport(
        transport, WTConfig(use_remote=False), read_only=False, allow_changes=True
    ) as wt:
        sicherung = wt.backup()
        vorher = len(gesendet(transport))
        wt.motor.restore(sicherung.motor)
        neu = gesendet(transport)[vorher:]

    assert any(":MOTor:POLE" in c for c in neu)
    assert any(":MOTor:SPEed:TYPE" in c for c in neu)
