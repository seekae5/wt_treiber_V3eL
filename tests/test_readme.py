# =============================================================================
# Datei: tests/test_readme.py
#
# Das README ist die Seite, die jemand als ERSTE sieht - und sein Codeblock
# ist der erste Python-Code, den er von diesem Projekt liest. Scheitert der,
# ist der Eindruck verdorben, bevor die Bibliothek eine Gelegenheit hatte.
#
# Deshalb wird er ausgefuehrt, so wie die Rezepte des Schnellstarts und die
# Skripte aus examples/ auch. Dazu werden die Verweise geprueft: ein README,
# das auf eine geloeschte Datei zeigt, ist schlimmer als eines ohne Verweise.
# =============================================================================

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import Geraetemodell

import wt_treiber_lib
from wt_treiber_lib import WT3000, WTConfig

WURZEL = Path(__file__).resolve().parents[1]
README = WURZEL / "README.md"


def bloecke(sprache: str = "python") -> list[str]:
    text = README.read_text(encoding="utf-8")
    return re.findall(rf"```{sprache}\n(.*?)```", text, re.S)


@pytest.fixture
def fassade(monkeypatch):
    """'WT3000.connect()' auf das Geraetemodell umlenken.

    Damit laeuft der Block WORTWOERTLICH - einschliesslich seines
    'WT3000.connect(ip="192.168.10.20")', das im Test keine Leitung braucht.
    """

    def verbinden(ip=None, read_only=True, allow_changes=False, **_uebrige):
        return WT3000.from_transport(
            Geraetemodell(),
            WTConfig(use_remote=False),
            read_only=read_only,
            allow_changes=allow_changes,
            owns_transport=True,
        )

    monkeypatch.setattr(WT3000, "connect", staticmethod(verbinden))
    monkeypatch.setattr(wt_treiber_lib.WT3000, "connect", staticmethod(verbinden))


# ---------------------------------------------------------------------------
# Der Codeblock laeuft
# ---------------------------------------------------------------------------


def test_das_erste_beispiel_laeuft(fassade, tmp_path, monkeypatch):
    """Der Block ganz oben - ohne ihn zu veraendern.

    Er schreibt mit einem blossen Dateinamen ('messreihe.csv', keine Path-
    Instanz): das ist die Schreibweise, die jeder zuerst versucht, und sie
    muss deshalb genau so funktionieren.
    """
    monkeypatch.chdir(tmp_path)
    quelltext = re.sub(r"max_samples=\d+", "max_samples=2", bloecke()[0])

    raum: dict = {"__name__": "__main__"}
    exec(compile(quelltext, "<README>", "exec"), raum)

    assert (tmp_path / "messreihe.csv").exists()
    assert (tmp_path / "messreihe.csv.meta.json").exists(), (
        "das README verspricht 'sidecar=True' - dann muss auch eines entstehen"
    )


def test_das_erste_beispiel_schreibt_nichts_am_geraet(fassade, tmp_path, monkeypatch):
    """Das README sagt es im Kommentar zu - also wird es nachgewiesen.

    Geprueft wird am Draht: alles, was kein Query ist, waere ein Set-Kommando.
    """
    modell = Geraetemodell()
    monkeypatch.setattr(
        WT3000,
        "connect",
        staticmethod(
            lambda ip=None, read_only=True, allow_changes=False, **_u: WT3000.from_transport(
                modell, WTConfig(use_remote=False), read_only=read_only,
                allow_changes=allow_changes, owns_transport=True,
            )
        ),
    )
    monkeypatch.chdir(tmp_path)
    quelltext = re.sub(r"max_samples=\d+", "max_samples=2", bloecke()[0])
    exec(compile(quelltext, "<README>", "exec"), {"__name__": "__main__"})

    gesendet = [befehl for befehl in modell.written if not befehl.strip().endswith("?")]
    assert not gesendet, f"das erste Beispiel hat gesendet: {gesendet}"


@pytest.mark.parametrize("nummer", [1, 2])
def test_die_uebrigen_ausschnitte_sind_gueltiges_python(nummer):
    """Ausschnitte, die fuer sich nicht laufen - aber uebersetzbar sein muessen.

    Ein Tippfehler in einem Codeblock faellt sonst niemandem auf.
    """
    compile(bloecke()[nummer], f"<README-Ausschnitt {nummer}>", "exec")


def test_die_json_beispiele_sind_gueltiges_json():
    import json

    for block in bloecke("json"):
        json.loads(block)


# ---------------------------------------------------------------------------
# Die Verweise stimmen
# ---------------------------------------------------------------------------


def test_jeder_verweis_zeigt_auf_eine_vorhandene_datei():
    text = README.read_text(encoding="utf-8")
    ziele = re.findall(r"\]\((?!https?://)([^)#]+)", text)
    assert ziele, "das README hat keine Verweise mehr - das kann nicht stimmen"

    fehlend = [z for z in ziele if not (WURZEL / z).exists()]
    assert not fehlend, f"das README zeigt ins Leere: {fehlend}"


@pytest.mark.parametrize(
    "pfad",
    ["docs/Schnellstart.md", "docs/API-Ueberblick-und-Lesbarkeit.md", "examples/README.md"],
)
def test_die_drei_wegweiser_sind_genannt(pfad):
    """Wer das README liest, muss von dort aus weiterkommen."""
    assert pfad in README.read_text(encoding="utf-8")


def test_die_beschriebene_verzeichnisstruktur_gibt_es():
    """Der Aufbau-Abschnitt zaehlt Verzeichnisse auf - sie muessen existieren."""
    for pfad in ("src/wt_treiber_lib", "examples", "docs", "tests", "tools/hardware"):
        assert (WURZEL / pfad).is_dir(), f"README nennt {pfad}, das es nicht gibt"
    assert (WURZEL / "live_messwerte.py").is_file()


# ---------------------------------------------------------------------------
# Die Zusagen des READMEs
# ---------------------------------------------------------------------------


def test_die_genannte_mindestversion_stimmt_mit_pyproject_ueberein():
    pyproject = (WURZEL / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10"' in pyproject
    assert "3.10" in README.read_text(encoding="utf-8")


def test_die_genannte_version_stimmt_mit_dem_paket_ueberein():
    assert wt_treiber_lib.__version__ in README.read_text(encoding="utf-8")


def test_die_vier_gesperrten_gruppen_stimmen():
    """Das README zaehlt sie namentlich auf - sie duerfen nicht abdriften."""
    from wt_treiber_lib.wt3000_input import DEFAULT_PROTECTED

    text = README.read_text(encoding="utf-8")
    for gruppe in DEFAULT_PROTECTED:
        assert f"`{gruppe}`" in text, f"README nennt die gesperrte Gruppe {gruppe} nicht"
