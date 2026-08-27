# =============================================================================
# Datei: tests/test_schnellstart_doku.py
# Fuehrt die Codebloecke aus docs/Schnellstart.md gegen ein simuliertes Geraet
# aus. Zweck: kein Rezept in der Einstiegsdokumentation, das nicht laeuft.
#
# Der Schnellstart ist die Seite, die ein Anwender ZUERST liest und aus der er
# kopiert. Ein Beispiel, das an einer geaenderten Signatur scheitert, kostet ihn
# genau das Vertrauen, das die Seite herstellen soll - und faellt sonst
# niemandem auf, weil Markdown nicht kompiliert wird. Hier faellt es auf.
#
# Geprueft wird die Mechanik: Namen, Signaturen, Verschachtelung, der ganze
# Aufrufweg bis zur geschriebenen Datei. NICHT geprueft wird, ob die Messwerte
# fachlich plausibel sind - dafuer ist das Geraetemodell nicht da.
# =============================================================================

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import ItemTableTransport

import wt3000_scpi
from wt3000_scpi import WT3000, WTConfig

SCHNELLSTART = Path(__file__).resolve().parents[1] / "docs" / "Schnellstart.md"


# ---------------------------------------------------------------------------
# Geraetemodell
# ---------------------------------------------------------------------------


class Geraetemodell(ItemTableTransport):
    """Item-Tabelle (vom Elternteil) plus Bereiche, HOLD und Protokollknoten.

    Schreibvorgaenge wirken auf die Antworttabelle zurueck. Ohne diese
    Rueckkopplung liesse sich zwar das Senden pruefen, aber weder das
    Verifizieren noch die Wiederherstellung - und genau die beiden sind es,
    die 'applied_ranges()' und 'items.applied()' im Schnellstart zusagen.
    """

    SCOPES = {":ALL": (1, 2, 3, 4), ":SIGMA": (1, 2, 3), ":SIGMB": (4,)}

    #: Knoten, deren geschriebener Wert schlicht uebernommen wird.
    EINFACHE_KNOTEN = (
        ":NUMERIC:HOLD",
        ":COMMUNICATE:HEADER",
        ":COMMUNICATE:VERBOSE",
        ":NUMERIC:FORMAT",
    )

    def __init__(self) -> None:
        items = {1: "U,1", 2: "I,1", 3: "P,1", 4: "U,2", 5: "I,2", 6: "P,2"}
        super().__init__(items, number=6)
        # base_responses() kennt den Knoten nicht; ensured_protocol_state() fragt ihn.
        self.responses.setdefault(":COMMUNICATE:VERBOSE", "0")

    def _ziele(self, suffix: str) -> tuple[int, ...]:
        if suffix in self.SCOPES:
            return self.SCOPES[suffix]
        if suffix.startswith(":ELEMENT"):
            return (int(suffix.removeprefix(":ELEMENT")),)
        return ()

    def write(self, command: str) -> None:
        # 'FakeTransport.query()' ruft write() mit dem Query auf. Ein '...?'
        # traegt keinen Parameter und darf hier nicht als Stellbefehl
        # missverstanden werden - sonst schlaegt das Modell beim blossen Lesen
        # eines Bereichs fehl.
        if command.strip().endswith("?"):
            super().write(command)
            return

        knoten, _, parameter = command.strip().partition(" ")
        gross = knoten.upper()

        for basis, wandeln in (
            (":INPUT:VOLTAGE:RANGE", self._spannungswert),
            (":INPUT:CURRENT:RANGE", self._stromwert),
            (":INPUT:VOLTAGE:AUTO", self._schalterwert),
            (":INPUT:CURRENT:AUTO", self._schalterwert),
        ):
            if gross.startswith(basis):
                wert = wandeln(parameter)
                for element in self._ziele(gross.removeprefix(basis)):
                    self.responses[f"{basis}:ELEMENT{element}"] = wert
                self.written.append(command)
                return

        if gross in self.EINFACHE_KNOTEN:
            self.responses[gross] = parameter
            self.written.append(command)
            return

        super().write(command)

    # -- Antwortformate des Geraets -----------------------------------------

    @staticmethod
    def _spannungswert(parameter: str) -> str:
        return f"{float(parameter):.3E}"

    @staticmethod
    def _stromwert(parameter: str) -> str:
        """Direkteingang in Ampere oder Sensoreingang in Volt."""
        sensor = parameter.upper().startswith("EXTERNAL")
        zahl = float(parameter.split(",")[-1])
        return f"EXTERNAL,{zahl:.2E}" if sensor else f"{zahl:.3E}"

    @staticmethod
    def _schalterwert(parameter: str) -> str:
        return "1" if parameter.upper() == "ON" else "0"


# ---------------------------------------------------------------------------
# Die Bloecke aus der Markdown-Datei
# ---------------------------------------------------------------------------

#: Bloecke, die fuer sich allein laufen - Ueberschrift zur Fehlermeldung.
EIGENSTAENDIG: dict[int, str] = {
    2: "Rezept 1 - Geraet ansehen",
    3: "Rezept 2 - messen, was eingestellt ist",
    4: "Rezept 3 - eigene Groessen",
    6: "Rezept 4 - Bereiche setzen",
    7: "Stellwerte nachschlagen",
    8: "Rezept 5 - Hintergrundmessung",
    10: "Ohne Geraet ausprobieren",
    11: "Fehler lesen",
}

#: Bloecke, die ein offenes 'wt' und eine 'tabelle' ringsum voraussetzen.
FRAGMENTE: dict[int, str] = {
    5: "Fertige Profile",
    9: "stream() waehrend der Messung",
}

#: Namen, die die Rezepte als Platzhalter fuer Anlagentechnik benutzen.
PLATZHALTER = ("pruefstand_hochfahren", "warten_bis_temperatur_erreicht", "pruefstand_abfahren")


def bloecke() -> list[str]:
    text = SCHNELLSTART.read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, re.S)


def beschleunigt(quelltext: str) -> str:
    """Takt und Laenge herunterdrehen - das EINZIGE, was am Text geaendert wird.

    Die Rezepte messen 30 bis 60 Datensaetze im Sekundentakt; das waeren zwei
    Minuten Testlaufzeit fuer eine Suite, die sonst in Sekunden durchlaeuft.
    Geaendert werden deshalb genau zwei Zahlen. Alles, was dieser Test
    tatsaechlich prueft - Namen, Signaturen, Verschachtelung, der Weg bis zur
    geschriebenen Datei - bleibt davon unberuehrt.
    """
    quelltext = re.sub(r"interval_s=[\d.]+", "interval_s=0.0", quelltext)
    return re.sub(r"max_samples=\d+", "max_samples=2", quelltext)


@pytest.fixture
def fassade(monkeypatch):
    """'WT3000.connect()' auf das Geraetemodell umlenken.

    Damit laufen die Rezepte WORTWOERTLICH - einschliesslich ihres
    'WT3000.connect(ip="192.168.10.20", ...)', das im Test keine Leitung
    braucht und trotzdem dieselbe Fassade liefert.
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
    monkeypatch.setattr(wt3000_scpi.WT3000, "connect", staticmethod(verbinden))
    return verbinden


def test_die_erwarteten_bloecke_sind_noch_da():
    """Haelt die Nummerierung oben gegen die Datei.

    Ohne diesen Pruefsatz genuegt ein eingefuegtes Beispiel, um die Indizes zu
    verschieben - die Tests darunter pruefen dann klaglos den falschen Block.
    """
    vorhanden = bloecke()
    erwartet = set(EIGENSTAENDIG) | set(FRAGMENTE)
    fehlend = {i for i in erwartet if i >= len(vorhanden)}
    assert not fehlend, (
        f"docs/Schnellstart.md hat nur {len(vorhanden)} Python-Bloecke; "
        f"die Nummern {sorted(fehlend)} gibt es nicht mehr. Wurde ein Beispiel "
        "eingefuegt oder entfernt? Dann EIGENSTAENDIG/FRAGMENTE nachziehen."
    )
    # Stichprobe auf den Inhalt, nicht nur auf die Anzahl.
    assert "wt.device.describe()" in vorhanden[2]
    assert "record_csv" in vorhanden[3]
    assert "RangePlan.of" in vorhanden[6]
    assert "wt.measure.start" in vorhanden[8]


@pytest.mark.parametrize("nummer", sorted(EIGENSTAENDIG), ids=EIGENSTAENDIG.get)
def test_eigenstaendiges_rezept_laeuft(nummer, fassade, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    quelltext = beschleunigt(bloecke()[nummer])
    raum = {"__name__": "__main__", **{name: (lambda: None) for name in PLATZHALTER}}
    exec(compile(quelltext, f"<Schnellstart Block {nummer}>", "exec"), raum)


@pytest.mark.parametrize("nummer", sorted(FRAGMENTE), ids=FRAGMENTE.get)
def test_fragment_laeuft_in_einer_sitzung(nummer, fassade, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    quelltext = beschleunigt(bloecke()[nummer])
    with fassade(read_only=False, allow_changes=True) as wt:
        raum = {"wt": wt, "tabelle": wt.items.read()}
        exec(compile(quelltext, f"<Schnellstart Block {nummer}>", "exec"), raum)


# ---------------------------------------------------------------------------
# Die Zusagen der Seite
# ---------------------------------------------------------------------------


def test_rezept_2_schreibt_csv_und_sidecar(fassade, tmp_path, monkeypatch):
    """Die Seite verspricht 'messreihe.csv' UND 'messreihe.csv.meta.json'.

    Ein Rezept, das ohne Fehler durchlaeuft, aber nichts ablegt, waere fuer den
    Anwender dasselbe wie ein kaputtes.
    """
    monkeypatch.chdir(tmp_path)
    exec(compile(beschleunigt(bloecke()[3]), "<Rezept 2>", "exec"), {"__name__": "__main__"})

    csv_datei = tmp_path / "messungen" / "messreihe.csv"
    assert csv_datei.exists()
    assert (tmp_path / "messungen" / "messreihe.csv.meta.json").exists()

    kopf = csv_datei.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert kopf[:4] == ["timestamp_iso", "elapsed_s", "sample", "condition"]
    assert kopf[-1] == "status_flags"
    # Die Spalten dazwischen sind die Items des Geraets - genau die, die das
    # Rezept ueber 'wt.items.read()' uebernimmt statt sie zu setzen.
    assert kopf[4:-1] == ["U1", "I1", "P1", "U2", "I2", "P2"]


def test_rezept_4_stellt_die_bereiche_hinterher_zurueck(fassade, tmp_path, monkeypatch):
    """Die Zusage des Rezepts steht als Kommentar mitten im Code.

    'hier stehen die Bereiche wieder wie vorgefunden' - das ist die
    Eigenschaft, wegen der man 'applied_ranges()' ueberhaupt nimmt, und
    deshalb wird sie hier nachgewiesen und nicht nur behauptet.
    """
    monkeypatch.chdir(tmp_path)

    from wt3000_scpi import Quantity

    modell = Geraetemodell()
    vorher = {
        element: modell.responses[f":INPUT:VOLTAGE:RANGE:ELEMENT{element}"]
        for element in (1, 2, 3, 4)
    }

    def verbinden(ip=None, read_only=True, allow_changes=False, **_uebrige):
        return WT3000.from_transport(
            modell, WTConfig(use_remote=False),
            read_only=read_only, allow_changes=allow_changes, owns_transport=True,
        )

    monkeypatch.setattr(WT3000, "connect", staticmethod(verbinden))
    exec(compile(beschleunigt(bloecke()[6]), "<Rezept 4>", "exec"), {"__name__": "__main__"})

    nachher = {
        element: modell.responses[f":INPUT:VOLTAGE:RANGE:ELEMENT{element}"]
        for element in (1, 2, 3, 4)
    }
    assert nachher == vorher, "applied_ranges() hat den Ausgangszustand nicht zurueckgestellt"
    # Und der Plan war ueberhaupt wirksam - sonst prueft der Vergleich nichts.
    assert any(
        befehl.startswith(f"{Quantity.VOLTAGE.value}:RANGe") for befehl in modell.written
    )
