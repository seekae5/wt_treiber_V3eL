# =============================================================================
# Datei: wt3000_itemspec.py
# Layer 3 (Erweiterung) - Eigene Item-Tabellen deklarieren, schreiben,
# verifizieren und vollstaendig zurueckstellen.
#
# Aendert nichts an wt3000_core.py oder wt3000_numeric.py.
# =============================================================================

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .wt3000_common import canonical_element
from .wt3000_core import DeviceError, WTError, WTSession
from .wt3000_numeric import ItemTable, NumericItem

_log = logging.getLogger("wt3000.itemspec")

# Order-Werte, die als gleichwertig zu "kein Order angegeben" gelten.
# Das Geraet ergaenzt bei manchen Funktionen TOTal von sich aus.
_DEFAULT_ORDERS: frozenset[str] = frozenset({"TOTAL", "TOT"})


@dataclass(frozen=True)
class ItemSpec:
    """Ein gewuenschtes Item der Zieltabelle.

    <Element> weggelassen -> Geraet setzt Element 1.
    <Order> weggelassen   -> Geraet setzt TOTal.

    ELEMENT UND ORDNUNG DUERFEN ZAHLEN SEIN. Beide sind SCPI-Parameter und
    damit letztlich Text, aber Element 1 und die 5. Oberschwingung sind der
    Sache nach Zahlen - und 'ItemSpec("U", 1)' ist die Schreibweise, die
    jeder zuerst versucht. Bis Schritt E8 fuehrte sie stillschweigend zu
    einer Spec, die keiner gelesenen Tabelle glich; jetzt sind

        ItemSpec("U", 1)        und  ItemSpec("U", "1")
        ItemSpec("U", 1, 5)     und  ItemSpec("U", "1", "5")

    dasselbe - einschliesslich Gleichheit und Hashwert. Umgewandelt wird beim
    Erzeugen, gespeichert wird immer Text.
    """

    function: str
    element: str | int | None = None
    order: str | int | None = None
    # True, wenn die Funktion auf dem Original-WT3000 nicht gesichert ist.
    verify: bool = False

    def __post_init__(self) -> None:
        # 'bool' ist ein Subtyp von 'int' - 'ItemSpec("U", True)' waere ein
        # Vertipper und soll nicht als Element '1' durchgehen.
        for feld in ("element", "order"):
            wert = getattr(self, feld)
            if isinstance(wert, bool):
                raise WTError(
                    f"ItemSpec: {feld}={wert!r} ist ein Wahrheitswert - "
                    "erwartet wird eine Elementnummer, ein Name oder None."
                )
            if isinstance(wert, int):
                object.__setattr__(self, feld, str(wert))

    @property
    def argument(self) -> str:
        """Parameterstring fuer ':NUMeric:NORMal:ITEM<x> <argument>'."""
        parts = [self.function]
        if self.element is not None:
            parts.append(self.element)
        if self.order is not None:
            parts.append(self.order)
        return ",".join(parts)


# ---------------------------------------------------------------------------
# Tabelle bauen
# ---------------------------------------------------------------------------


#: Elementbezeichner, die am ENDE eines Spaltennamens stehen koennen.
#
# Eine geschlossene Liste, und das ist der Kern von 'spec_from_key()': die
# Zerlegung eines Namens laeuft NICHT ueber eine Tabelle bekannter Funktionen
# (die waere unvollstaendig - das Geraet kennt weit mehr Funktionen, als
# dieses Paket auffuehrt), sondern ueber die Elemente, und die sind
# abschliessend bekannt. Damit ist die Zerlegung strukturell und nicht
# geraten. Laengster Treffer zuerst: 'SIGMB' vor 'SIGMA' spielt keine Rolle,
# aber die Reihenfolge haelt die Absicht fest.
_ELEMENT_SUFFIXE: tuple[str, ...] = ("SIGMA", "SIGMB", "1", "2", "3", "4")


def spec_from_key(key: str) -> ItemSpec:
    """Einen Spaltennamen in die zugehoerige 'ItemSpec' zurueckwandeln.

    Die Umkehrung von 'NumericItem.key' - also genau der Namen, die in der
    Kopfzeile jeder CSV stehen, die dieses Paket schreibt. Damit schliesst
    sich der Kreis zwischen Ausgabe und Konfiguration: was man in einer alten
    Messdatei liest, kann man ohne Uebersetzung wieder anfordern.

        spec_from_key("U1")      -> ItemSpec("U", "1")
        spec_from_key("PSIGMA")  -> ItemSpec("P", "SIGMA")
        spec_from_key("PHI1_1")  -> ItemSpec("PHI", "1", "1")
        spec_from_key("U")       -> ItemSpec("U")        (Geraet nimmt Element 1)

    ZUR SCHREIBWEISE: der Summenwert heisst 'PSIGMA' und NICHT 'P_SIGMA' -
    der Unterstrich trennt ausschliesslich die Ordnung ab. Wer sich vertut,
    bekommt hier eine Meldung und keine stillschweigend falsche Tabelle.

    KEIN RATEN. Zerlegt wird von RECHTS und nur an den beiden Stellen, die das
    Format vorsieht: alles nach dem ersten '_' ist die Ordnung, davor endet
    der Name auf einem Elementbezeichner aus '_ELEMENT_SUFFIXE' oder auf
    keinem. Der Rest ist die Funktion - sie wird weder geprueft noch
    uebersetzt, denn welche Funktionen dieses Geraet kennt, weiss das Geraet.
    Eine falsche Funktion faellt beim Verifizieren nach dem Schreiben auf
    ('wt.items.applied()' tut das von selbst).
    """
    text = key.strip().upper()
    if not text:
        raise WTError("Leerer Spaltenname")

    name, trenner, order = text.partition("_")
    if trenner and not order:
        raise WTError(
            f"Spaltenname {key!r} endet auf '_' - nach dem Unterstrich gehoert "
            "die Ordnung, z.B. 'PHI1_1' oder 'U1_TOTAL'."
        )

    for suffix in _ELEMENT_SUFFIXE:
        if name.endswith(suffix) and len(name) > len(suffix):
            return ItemSpec(name[: -len(suffix)], suffix, order or None)

    # Kein Elementbezeichner am Ende: das Geraet setzt dann Element 1.
    return ItemSpec(name, None, order or None)


def specs_from_keys(keys: Sequence[str]) -> tuple[ItemSpec, ...]:
    """Eine Liste von Spaltennamen in Specs wandeln. Siehe 'spec_from_key()'."""
    if not keys:
        raise WTError("Leere Namensliste - ohne Spalten keine Messung")
    return tuple(spec_from_key(k) for k in keys)


def build_item_table(specs: tuple[ItemSpec, ...] | list[ItemSpec]) -> ItemTable:
    """Aus einer Spec-Liste die Ziel-ItemTable erzeugen (Index ab 1)."""
    if not specs:
        raise WTError("Leere Zieltabelle")
    if len(specs) > 255:
        raise WTError(f"{len(specs)} Items - das Geraet unterstuetzt maximal 255")

    _melde_ungepruefte_funktionen(specs)

    items = [
        NumericItem(index=i, function=s.function, element=s.element, order=s.order)
        for i, s in enumerate(specs, start=1)
    ]
    return ItemTable(number=len(items), items=items)


def _melde_ungepruefte_funktionen(specs: tuple[ItemSpec, ...] | list[ItemSpec]) -> None:
    """Einmal je Tabelle nennen, welche Funktionen unbestaetigt sind.

    'ItemSpec.verify=True' kennzeichnet eine Funktion, die am ORIGINAL-WT3000
    nicht nachgemessen ist - das trifft auf das gesamte Integrations- und
    Oberschwingungsprofil zu. Die Kennzeichnung stand bisher nur im Quelltext:
    sie wurde gesetzt und von niemandem gelesen. Wer eines dieser Profile
    benutzte, erfuhr also nirgends, dass ein Teil der Spalten auf einer
    Annahme beruht - und ein NAN in der CSV sieht aus wie ein Messproblem,
    nicht wie eine offene Frage des Treibers.

    Deshalb eine Zeile ins Protokoll, und zwar EINE je Tabelle statt einer je
    Item: bei 48 Items waeren 40 gleichlautende Warnungen selbst wieder ein
    Grund, das Protokoll nicht zu lesen.
    """
    ungeprueft = sorted({s.function.upper() for s in specs if s.verify})
    if not ungeprueft:
        return
    betroffen = sum(1 for s in specs if s.verify)
    _log.warning(
        "%d von %d Items benutzen Funktionen, die am Original-WT3000 nicht "
        "bestaetigt sind: %s. Sie koennen NAN liefern, ohne dass ein Messfehler "
        "vorliegt.",
        betroffen,
        len(specs),
        ", ".join(ungeprueft),
    )


# ---------------------------------------------------------------------------
# Vergleichsregeln
# ---------------------------------------------------------------------------


def _functions_compatible(requested: str, actual: str) -> bool:
    """Kurzform des Geraets gegen die gesendete Form pruefen.

    VERBose ist aus, das Geraet antwortet in Kurzform ('LAMB' statt 'LAMBDA',
    verifiziert in Stufe 3). SCPI-Regel: die Kurzform ist ein Praefix der
    Langform.

    Die Pruefung laeuft bewusst nur in EINE Richtung - die Antwort muss ein
    Praefix der Anforderung sein. Beidseitiges Praefixmatching wuerde
    'gesendet U, zurueckgelesen UTHD' faelschlich als Treffer werten.
    """
    req, act = requested.upper(), actual.upper()
    return req == act or req.startswith(act)


# Kompatibilitaetsname; die gemeinsame Regel liegt in wt3000_common.
def _canonical_element(element: str | None) -> str:
    """Elementangabe auf ein eindeutiges Token normalisieren.

    Reine Weiterleitung an wt3000_common.canonical_element(). Dort steht auch
    die Begruendung, warum hier KEIN Praefixmatching erlaubt ist:
    'SIGMB'.startswith('SIGM') ist wahr, eine Praefixregel wuerde die
    Wiring-Units SigmaA und SigmaB gleichsetzen.
    """
    return canonical_element(element)


def _elements_compatible(requested: str | None, actual: str | None) -> bool:
    """Elemente nach Normalisierung exakt vergleichen."""
    return _canonical_element(requested) == _canonical_element(actual)


def _orders_compatible(requested: str | None, actual: str | None) -> bool:
    """Fehlenden Order und TOTal/TOT als gleichwertig behandeln.

    Verifiziert in Stufe 3: gesendet 'U,1' -> zurueckgelesen 'U,1,TOT'.
    """
    a = (requested or "TOTAL").upper()
    b = (actual or "TOTAL").upper()
    if a == b:
        return True
    return a in _DEFAULT_ORDERS and b in _DEFAULT_ORDERS


def items_match(requested: NumericItem, actual: NumericItem) -> bool:
    """Pruefen, ob das Geraet das angeforderte Item uebernommen hat."""
    return (
        _functions_compatible(requested.function, actual.function)
        and _elements_compatible(requested.element, actual.element)
        and _orders_compatible(requested.order, actual.order)
    )

# ---------------------------------------------------------------------------
# Backup jenseits von NUMber
# ---------------------------------------------------------------------------


def probe_extra_items(session: WTSession, first_index: int, last_index: int) -> list[NumericItem]:
    """Items oberhalb von NUMber einzeln abfragen und sichern.

    ':NUMeric:NORMal?' gibt nur Items bis NUMber aus. Wenn die Zieltabelle
    laenger ist als die gesicherte, muessen die dahinterliegenden Items
    einzeln gelesen werden, bevor sie ueberschrieben werden.
    """
    if last_index < first_index:
        return []

    _log.info("Sichere Items %d..%d einzeln (jenseits von NUMber)", first_index, last_index)
    tail: list[NumericItem] = []
    for index in range(first_index, last_index + 1):
        response = session.query(f":NUMeric:NORMal:ITEM{index}?")
        tail.append(NumericItem.parse(index, response))
    return tail


# ---------------------------------------------------------------------------
# Backup-Bundle (Tabelle + Tail) auf Platte
# ---------------------------------------------------------------------------


def save_backup_bundle(path: Path, table: ItemTable, tail: list[NumericItem]) -> None:
    """Gesicherte Tabelle inkl. Tail als JSON schreiben."""
    bundle = {
        "table": table.to_dict(),
        "tail": [
            {
                "index": it.index,
                "function": it.function,
                "element": it.element,
                "order": it.order,
                "argument": it.argument,
            }
            for it in tail
        ],
    }
    path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    _log.info(
        "Backup-Bundle gesichert nach %s (%d Items + %d Tail)",
        path,
        len(table.items),
        len(tail),
    )


def load_backup_bundle(path: Path) -> tuple[ItemTable, list[NumericItem]]:
    """Gegenstueck zu save_backup_bundle()."""
    bundle = json.loads(path.read_text(encoding="utf-8"))
    table = ItemTable.from_dict(bundle["table"])
    tail = [
        NumericItem(
            index=int(d["index"]),
            function=d["function"],
            element=d.get("element"),
            order=d.get("order"),
        )
        for d in bundle.get("tail", [])
    ]
    return table, tail


# ---------------------------------------------------------------------------
# Schreiben, pruefen, zuruecksetzen
# ---------------------------------------------------------------------------


def probe_item_write_capability(
    session: WTSession, target: ItemTable, backup: ItemTable
) -> None:
    """Genau EIN Item schreiben und zuruecklesen, bevor die ganze Tabelle geht.

    Faellt der Test durch, ist nur ein einziges Item veraendert - der Restore
    im aufrufenden finally raeumt das auf.
    """
    backup_by_index = {it.index: it for it in backup.items}

    candidate: NumericItem | None = None
    for item in target.items:
        existing = backup_by_index.get(item.index)
        if existing is None or existing.argument != item.argument:
            candidate = item
            break

    if candidate is None:
        _log.info("Zieltabelle entspricht bereits dem Ist-Zustand - Write-Probe uebersprungen")
        return

    command = f":NUMeric:NORMal:ITEM{candidate.index} {candidate.argument}"
    _log.info("Write-Probe: %s", command)
    session.write(command)

    response = session.query(f":NUMeric:NORMal:ITEM{candidate.index}?")
    actual = NumericItem.parse(candidate.index, response)

    if not items_match(candidate, actual):
        errors = session.read_error_queue()
        raise DeviceError(
            f"Write-Probe fehlgeschlagen. Gesendet: {candidate.argument!r}, "
            f"zurueckgelesen: {actual.argument!r}. Fehlerqueue: {errors}. "
            "Moegliche Ursache: Set-Kommandos werden ohne ':COMMunicate:REMote ON' "
            "abgelehnt - dann use_remote=True in WTConfig setzen."
        )

    session.assert_no_error("Write-Probe")
    _log.info("Write-Probe erfolgreich (zurueckgelesen: %s)", actual.argument)


def apply_item_table(session: WTSession, target: ItemTable) -> None:
    """Zieltabelle schreiben. NUMber wird IMMER mitgeschrieben.

    Das Vergessen von NUMber ist der haeufigste Fehler: VALue? liefert dann
    weiterhin nur die alte Anzahl Werte.
    """
    for item in target.items:
        session.write(f":NUMeric:NORMal:ITEM{item.index} {item.argument}")

    session.write(f":NUMeric:NORMal:NUMber {target.number}")
    session.assert_no_error("Schreiben der Item-Tabelle")
    _log.info("Item-Tabelle geschrieben: %d Items, NUMber=%d", len(target.items), target.number)


def verify_item_table(session: WTSession, target: ItemTable) -> list[str]:
    """Ist-Tabelle zurueckliefern und mit der Anforderung vergleichen.

    Rueckgabe: Liste der Abweichungen (leer = alles in Ordnung).
    """
    actual = ItemTable.read_from_device(session)
    problems: list[str] = []

    if actual.number != target.number:
        problems.append(f"NUMber ist {actual.number}, erwartet {target.number}")

    actual_by_index = {it.index: it for it in actual.items}
    for wanted in target.items:
        got = actual_by_index.get(wanted.index)
        if got is None:
            problems.append(f"ITEM{wanted.index} fehlt in der Antwort")
        elif not items_match(wanted, got):
            problems.append(
                f"ITEM{wanted.index}: gesendet {wanted.argument!r}, "
                f"zurueckgelesen {got.argument!r}"
            )

    if not problems:
        _log.info("Verifikation erfolgreich: alle %d Items uebernommen", len(target.items))
    return problems


def restore_item_table(
    session: WTSession,
    backup: ItemTable,
    tail: list[NumericItem],
    force: bool = False,
) -> int:
    """Gesicherten Zustand vollstaendig wiederherstellen.

    Schreibt Items 1..NUMber aus dem Backup, danach den gesicherten Tail,
    danach NUMber. Kein CLEar - es wird nichts geloescht, was nicht vorher
    gesichert wurde.
    """
    written = backup.restore_to_device(session, force=force)

    for item in tail:
        session.write(f":NUMeric:NORMal:ITEM{item.index} {item.argument}")
        written += 1

    if tail:
        # NUMber nach dem Tail nochmals setzen, damit der Ausgabeumfang stimmt.
        session.write(f":NUMeric:NORMal:NUMber {backup.number}")
        written += 1
        session.assert_no_error("Wiederherstellung des Tails")

    return written
