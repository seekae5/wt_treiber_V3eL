# Macht 'wt_treiber_lib' aus dem Quellbaum importierbar, ohne dass das Paket
# installiert sein muss - damit ein Beispiel sofort laeuft, statt zuerst an
# einem ImportError zu scheitern.
#
# Nach 'pip install -e .' ist diese Datei ueberfluessig; dann kann die Zeile
#     import _pfad
# aus den Beispielen verschwinden. In einem EIGENEN Messskript hat sie nichts
# zu suchen - dort ist das Paket installiert.

from __future__ import annotations

import sys
from pathlib import Path

_QUELLEN = Path(__file__).resolve().parents[1] / "src"
if _QUELLEN.is_dir() and str(_QUELLEN) not in sys.path:
    sys.path.insert(0, str(_QUELLEN))
