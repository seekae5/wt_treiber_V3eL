# =============================================================================
# Datei: tests/test_package_layout.py
# Tests des Paketlayouts: alle Module sind importierbar, Geschwisterimporte
# sind relativ und die Schichten zeigen nur nach unten.
# =============================================================================

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

import pytest

import wt_treiber_lib

PACKAGE_DIR = Path(wt_treiber_lib.__file__).parent

# Erlaubte Importe je Modul - die Schichtung aus dem Kopf von __init__.py.
LAYERS: dict[str, set[str]] = {
    # Der Transport ist paketunabhaengig und damit geraetefrei testbar.
    "wt3000_transport": set(),
    # Der Kern darf nur den Transport importieren.
    "wt3000_core": {"wt3000_transport"},
    "wt3000_common": {"wt3000_core"},
    "wt3000_numeric": {"wt3000_core"},
    "wt3000_rangeio": {"wt3000_core", "wt3000_common"},
    "wt3000_input": {"wt3000_core", "wt3000_common"},
    # Geraetegruppen nutzen gemeinsame Regeln aus wt3000_common und importieren
    # keine Geschwister derselben Schicht.
    "wt3000_deviceconfig": {"wt3000_core", "wt3000_common"},
    "wt3000_itemspec": {"wt3000_core", "wt3000_common", "wt3000_numeric"},
    "wt3000_ranging": {"wt3000_core", "wt3000_common", "wt3000_rangeio"},
    "wt3000_measure": {
        "wt3000_core",
        "wt3000_common",
        "wt3000_numeric",
        "wt3000_itemspec",
    },
    # Ausgabeformate setzen SampleSink um. Die Messschleife darf sie nicht
    # zurueckimportieren und bleibt dadurch formatunabhaengig.
    "wt3000_sinks": {"wt3000_core", "wt3000_numeric", "wt3000_measure"},
    # Der Sitzungs-Sicherungspunkt steht auf Layer 3 und darf
    # deshalb aus den Fachmodulen darunter importieren - auch aus den beiden
    # Geschwistern 'wt3000_itemspec' und 'wt3000_ranging', genau wie
    # 'wt3000_measure' es mit 'wt3000_itemspec' tut.
    #
    # Bewusst NICHT enthalten: 'wt3000_device'. Der Steckbrief ('DeviceInfo')
    # ist Layer 4, und ein Backup, das ihn importierte, zoege die ganze Fassade
    # in Layer 3 hinein. Deshalb fuehrt 'SessionBackup.device' eine schlichte
    # Abbildung, die die Fassade ueber 'device_fingerprint()' fuellt.
    "wt3000_backup": {
        "wt3000_core",
        "wt3000_common",
        "wt3000_numeric",
        "wt3000_rangeio",
        "wt3000_input",
        "wt3000_deviceconfig",
        "wt3000_itemspec",
        "wt3000_ranging",
    },
    # Die Fassade buendelt alle tieferen Fachmodule, importiert aber weder
    # Stufenskripte noch ein anderes Layer-4-Modul.
    "wt3000_device": {
        "wt3000_transport",
        "wt3000_core",
        "wt3000_common",
        "wt3000_numeric",
        "wt3000_rangeio",
        "wt3000_input",
        "wt3000_deviceconfig",
        "wt3000_itemspec",
        "wt3000_ranging",
        "wt3000_measure",
        "wt3000_sinks",
        # Die Fassade buendelt den Sicherungspunkt.
        "wt3000_backup",
    },
    # Stufenskripte sind ebenfalls Teil der geprueften Schichtung.
    # Die Eintraege bilden den heutigen Bestand ab, sie sind also beim Anlegen
    # sofort gruen. Das ist Absicht - sie sichern, was schon gilt.
    #
    # Bewusst NICHT enthalten und der eigentliche Zweck dieser fuenf Zeilen:
    #
    #   * 'wt3000_device'. Die Fassade ist Layer 4, genau wie die Stufen. Ein
    #     Stufenskript, das sie importiert, waere ein Querimport innerhalb
    #     derselben Schicht. Der Eintrag 'wt3000_device' oben haelt dieselbe
    #     Regel fuer die Gegenrichtung fest ("aus keinem Stufenskript und aus
    #     keinem zweiten Layer-4-Modul"); ab hier gilt sie in beide Richtungen.
    #
    #   * jedes andere Stufenskript. Gemeinsames gehoert nach 'wt3000_common'
    #     (Layer 1) oder in die Fassade, nie quer. Das wird ab Schritt 8 des
    #     Plans wichtig, wenn alle sieben main() eine gemeinsame Signatur
    #     bekommen und die Versuchung entsteht, "gemeinsamen Code" zwischen
    #     zwei Stufen zu teilen.
    "stage2_read_numeric": {"wt3000_core", "wt3000_common", "wt3000_numeric"},
    "stage3_own_itemtable": {
        "wt3000_core",
        "wt3000_common",
        "wt3000_numeric",
        "wt3000_itemspec",
    },
    "stage4_measure": {
        "wt3000_core",
        "wt3000_common",
        "wt3000_numeric",
        "wt3000_itemspec",
        "wt3000_measure",
        "wt3000_sinks",
    },
    "stage5_input_config": {"wt3000_core", "wt3000_common", "wt3000_input"},
    "stage5b_range_probe": {
        "wt3000_core",
        "wt3000_common",
        "wt3000_rangeio",
        "wt3000_ranging",
    },
}


def modul_dateien() -> list[Path]:
    return sorted(p for p in PACKAGE_DIR.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize("name", wt_treiber_lib.MODULES)
def test_jedes_fachmodul_ist_importierbar(name):
    """Importieren darf keine tmctl.dll und kein Geraet voraussetzen."""
    importlib.import_module(f"wt_treiber_lib.{name}")


@pytest.mark.parametrize("pfad", modul_dateien(), ids=lambda p: p.stem)
def test_kein_absoluter_geschwisterimport(pfad):
    """Genau der Unterschied, der Wurzel und Build/-Klon getrennt hat."""
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ImportFrom) and knoten.level == 0:
            assert not (knoten.module or "").startswith("wt3000_"), (
                f"{pfad.name}: 'from {knoten.module} import ...' muss relativ sein"
            )
        if isinstance(knoten, ast.Import):
            for alias in knoten.names:
                assert not alias.name.startswith("wt3000_"), (
                    f"{pfad.name}: 'import {alias.name}' muss relativ sein"
                )


def test_layers_deckt_jedes_modul_ab():
    """NEU (Schritt 0a, Befund A-11): die Deckung selbst ist jetzt geprueft.

    Der Befund war nicht, dass fuenf Eintraege fehlten - sondern dass das
    niemandem auffiel. 'test_importrichtung_zeigt_nach_unten' ist ueber
    sorted(LAYERS) parametrisiert und prueft damit genau so viele Module, wie
    jemand eingetragen hat: ein neues Modul ohne Eintrag laesst die Suite
    gruen. Dieser Pruefsatz schliesst den Kreis, indem er LAYERS gegen den
    tatsaechlichen Bestand haelt.
    """
    vorhanden = {p.stem for p in modul_dateien()}
    fehlend = vorhanden - set(LAYERS)
    verwaist = set(LAYERS) - vorhanden
    assert not fehlend, (
        f"Ohne Eintrag in LAYERS und damit ungeprueft: {sorted(fehlend)}. "
        "Jedes Paketmodul braucht eine Zeile - auch ein Stufenskript."
    )
    assert not verwaist, f"LAYERS nennt Module, die es nicht gibt: {sorted(verwaist)}"


@pytest.mark.parametrize("name", sorted(LAYERS))
def test_importrichtung_zeigt_nach_unten(name):
    quelle = (PACKAGE_DIR / f"{name}.py").read_text(encoding="utf-8")
    genutzt = {
        knoten.module
        for knoten in ast.walk(ast.parse(quelle))
        if isinstance(knoten, ast.ImportFrom)
        and knoten.level == 1
        and knoten.module is not None
    }
    unerlaubt = genutzt - LAYERS[name]
    assert not unerlaubt, f"{name} importiert aus einer hoeheren Schicht: {unerlaubt}"


STUFENSKRIPTE = (
    "stage2_read_numeric",
    "stage3_own_itemtable",
    "stage4_measure",
    "stage5_input_config",
    "stage5b_range_probe",
)


def test_stufenskripte_fuehren_beim_import_nichts_aus():
    """Layer 4 darf erst ueber main() aktiv werden, nicht beim Import."""
    for name in STUFENSKRIPTE:
        modul = importlib.import_module(f"wt_treiber_lib.{name}")
        assert callable(modul.main)


@pytest.mark.parametrize("name", STUFENSKRIPTE)
def test_import_legt_keine_datei_an(name, tmp_path, monkeypatch):
    """UEBERARBEITET (Schritt 0b, Befund A-10): die Zusage ist jetzt geprueft.

    Bis hierher stellte der Test darueber nur fest, dass 'main' aufrufbar ist -
    das ist keine Aussage darueber, ob der Import etwas TUT. Und er tut etwas:
    seit Schritt 0b legt jedes der fuenf Skripte 'OUTPUT_DIR = output_dir(...)'
    als Modulkonstante an, und output_dir() laeuft ueber find_project_root(),
    das vom Arbeitsverzeichnis aus aufwaerts 'exists()' auf drei Marker prueft.

    Das ist ein LESENDER Dateisystemzugriff und ausdruecklich zugelassen - die
    Alternative waere gewesen, den Pfad erst in main() aufzuloesen, und dann
    liesse er sich nicht mehr durch einen einzigen setattr ersetzen (siehe die
    Begruendung in Schritt 0b des Plans). Was NICHT passieren darf, ist ein
    schreibender Zugriff: kein mkdir, keine Protokolldatei, kein Backup. Genau
    diese Grenze haelt dieser Pruefsatz fest.
    """
    monkeypatch.chdir(tmp_path)
    for modul in list(sys.modules):
        if modul == f"wt_treiber_lib.{name}":
            del sys.modules[modul]

    vorher = set(tmp_path.rglob("*"))
    importlib.import_module(f"wt_treiber_lib.{name}")
    neu = set(tmp_path.rglob("*")) - vorher

    assert not neu, f"{name} hat beim Import angelegt: {sorted(p.name for p in neu)}"


# ---------------------------------------------------------------------------
# Die Suite bleibt geraetefrei
# ---------------------------------------------------------------------------


def test_testsuite_kann_keine_geraeteverbindung_oeffnen():
    """Belegt die Sperre aus tests/conftest.py.

    Der Kopf von conftest.py sagt zu, dass die Suite ohne Geraet und ohne
    tmctl.dll laeuft. Diese Zusage war lange nur Absicht: unter tests/ lag ein
    Skript, das eine echte Verbindung aufbaute und einen Messbereich schrieb.
    Seit es nach tools/hardware/ umgezogen ist, sichert conftest.py die Zusage
    aktiv ab - dieser Test haelt fest, dass die Sperre auch wirklich greift.
    """
    from wt_treiber_lib.wt3000_transport import TmctlTransport, WTConfig

    with pytest.raises(RuntimeError, match="ohne Geraet"):
        TmctlTransport(WTConfig())


def test_die_sperre_laesst_den_protokollvertrag_unberuehrt():
    """Der stillgelegte Konstruktor darf die Typpruefung nicht beschaedigen.

    'issubclass(TmctlTransport, Transport)' in test_fake_transport.py haengt an
    write/read/query/set_timeout/close - nicht am Konstruktor.
    """
    from wt_treiber_lib.wt3000_transport import TmctlTransport, Transport

    assert issubclass(TmctlTransport, Transport)


# ---------------------------------------------------------------------------
# Die Paketoberflaeche ist vollstaendig
#
# Zugesagt im Kopf von __init__.py: wer nur 'from wt_treiber_lib import ...'
# schreibt, kommt an jede Anwenderfunktion. Diese Zusage war bisher nicht
# geprueft und stimmte auch nicht - 'wt.applied_ranges(plan)' verlangte einen
# 'RangePlan', den das Paket nicht herausgab. Ab hier faellt so etwas auf.
# ---------------------------------------------------------------------------

#: Die Objekte, die ein Anwender ueber 'wt.<name>' in der Hand haelt.
FASSADENKLASSEN = (
    "WT3000",
    "DeviceInfo",
    "ItemAccess",
    "MeasureControl",
    "InputConfig",
    "RangeAccess",
    "IntegrationConfig",
    "ComputationConfig",
    "HarmonicsConfig",
)

_BEZEICHNER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def paketeigene_namen() -> dict[str, str]:
    """Jeder oeffentliche Name, der in einem Fachmodul beheimatet ist.

    Abbildung Name -> Modul. 'Path' oder 'Sequence' stehen nicht darin: sie
    kommen aus der Standardbibliothek, und ob die importierbar ist, hat dieses
    Paket nicht zu verantworten.
    """
    eigene: dict[str, str] = {}
    for modulname in wt_treiber_lib.MODULES:
        modul = importlib.import_module(f"wt_treiber_lib.{modulname}")
        for name, objekt in vars(modul).items():
            if name.startswith("_"):
                continue
            if getattr(objekt, "__module__", "").startswith("wt_treiber_lib"):
                eigene.setdefault(name, modulname)
    return eigene


def test_jeder_name_in_all_ist_auch_vorhanden():
    """Ein Tippfehler in __all__ faellt sonst erst beim 'import *' auf."""
    fehlend = [name for name in wt_treiber_lib.__all__ if not hasattr(wt_treiber_lib, name)]
    assert not fehlend, f"__all__ nennt Namen, die das Paket nicht hat: {fehlend}"


@pytest.mark.parametrize("klassenname", FASSADENKLASSEN)
def test_argumente_der_fassade_sind_aus_dem_paket_importierbar(klassenname):
    """Kein Anwenderskript muss aus 'wt_treiber_lib.wt3000_*' importieren.

    Geprueft wird ueber die Annotationen: jeder paketeigene Typ, den eine
    oeffentliche Methode dieser Klassen ENTGEGENNIMMT oder HERAUSGIBT, muss in
    'wt_treiber_lib.__all__' stehen. Wer kuenftig einen neuen Typ in eine Signatur
    schreibt und ihn nicht exportiert, sieht es hier - und nicht der Anwender,
    der ihn zu benutzen versucht.

    'from __future__ import annotations' laesst die Annotationen als
    Zeichenketten stehen; deshalb werden die Bezeichner herausgeloest und
    einzeln nachgeschlagen, statt die Typen aufzuloesen. Das ist hier der
    robustere Weg: er kommt ohne Vorwaertsreferenzen und ohne Importe zur
    Laufzeit aus.
    """
    eigene = paketeigene_namen()
    exportiert = set(wt_treiber_lib.__all__)
    klasse = getattr(wt_treiber_lib, klassenname)

    fehlend: dict[str, set[str]] = {}
    for name, objekt in vars(klasse).items():
        if name.startswith("_"):
            continue
        # Bei einer Property traegt der Getter die Annotationen.
        funktion = objekt.fget if isinstance(objekt, property) else objekt
        if not callable(funktion):
            continue
        for annotation in getattr(funktion, "__annotations__", {}).values():
            for bezeichner in _BEZEICHNER.findall(str(annotation)):
                if bezeichner in eigene and bezeichner not in exportiert:
                    fehlend.setdefault(bezeichner, set()).add(name)

    assert not fehlend, "\n".join(
        f"{klassenname}.{sorted(stellen)} braucht {typ!r} "
        f"(aus wt_treiber_lib.{eigene[typ]}), das Paket exportiert es aber nicht"
        for typ, stellen in sorted(fehlend.items())
    )


# ---------------------------------------------------------------------------
# Die Sperren der Fachobjekte sind EINE Familie
#
# Vorher trugen wt3000_input und wt3000_deviceconfig je eine eigene Klasse
# namens 'ConfigLocked'; exportiert wurde nur eine davon. 'except ConfigLocked'
# aus dem Paketimport fing die Sperre der Integrationsgruppe deshalb NICHT ab.
# Der Fehler war still - der Aufrufer sah eine durchgereichte WTError und
# konnte nicht erkennen, dass sein except-Zweig danebengegriffen hatte.
# ---------------------------------------------------------------------------


def test_kein_modul_definiert_configlocked_ein_zweites_mal():
    """Die Basis liegt in wt3000_core - und nur dort."""
    from wt_treiber_lib import wt3000_core

    assert wt_treiber_lib.ConfigLocked is wt3000_core.ConfigLocked

    doppelt = []
    for modulname in wt_treiber_lib.MODULES:
        if modulname == "wt3000_core":
            continue
        quelle = (PACKAGE_DIR / f"{modulname}.py").read_text(encoding="utf-8")
        for knoten in ast.walk(ast.parse(quelle)):
            if isinstance(knoten, ast.ClassDef) and knoten.name == "ConfigLocked":
                doppelt.append(modulname)
    assert not doppelt, (
        f"{doppelt} definiert 'ConfigLocked' erneut. Der Name gehoert nach "
        "wt3000_core; eine eigene Sperre erbt davon unter eigenem Namen."
    )


@pytest.mark.parametrize(
    "name", ["InputLocked", "DeviceConfigLocked", "ChangesNotAllowed"]
)
def test_jede_sperre_erbt_von_der_gemeinsamen_basis(name):
    """'except ConfigLocked' muss jede Sperre der Fachobjekte fangen."""
    assert issubclass(getattr(wt_treiber_lib, name), wt_treiber_lib.ConfigLocked)


def test_die_sitzungssperre_bleibt_ausserhalb_der_familie():
    """read_only und allow_changes sind zwei Schloesser - und zwei Meldungen.

    'ReadOnlyViolation' kommt aus der SITZUNG, eine Schicht unter den
    Fachobjekten. Sie unter 'ConfigLocked' zu haengen hiesse, dem Aufrufer die
    Unterscheidung zu nehmen, welches der beiden Schloesser noch zu ist.
    """
    assert not issubclass(wt_treiber_lib.ReadOnlyViolation, wt_treiber_lib.ConfigLocked)
