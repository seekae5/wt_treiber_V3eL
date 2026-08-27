# Oeffentliche Paketoberflaeche des WT3000-Treibers.
#
# Die Module sind azyklisch geschichtet: Transport und Sitzung bilden die
# Basis, darauf liegen SCPI-Fachmodule und Ablaeufe, darueber die Fassade und
# Stufenskripte. Der Import des Pakets benoetigt weder Geraet noch tmctl.dll;
# die DLL wird erst beim Erzeugen eines TmctlTransport geladen.
#
# GRUNDREGEL DIESER DATEI
#
#     Wer nur 'from wt3000_scpi import ...' schreibt, kommt an jede
#     Anwenderfunktion. Ein Import aus 'wt3000_scpi.wt3000_*' ist im
#     Messautomationsskript nie noetig.
#
# Der Massstab ist dabei die Fassade: JEDER Typ, den eine Methode von 'WT3000'
# als Argument verlangt oder als Ergebnis herausgibt, steht hier. Vorher galt
# das nicht - 'wt.applied_ranges(plan)' erwartete einen 'RangePlan', den man nur
# ueber 'from wt3000_scpi.wt3000_ranging import RangePlan' bekam. Der Anwender
# musste also die interne Schichtung kennen, die ihn nichts angeht; die Fassade
# war gebaut, aber der Weg zu ihren Argumenten fuehrte an ihr vorbei. Dasselbe
# galt fuer 'ItemSpec', 'ItemTable', die GROUP_*-Konstanten und die Tabellen der
# zulaessigen Stellwerte.
#
# Gegenprobe in tests/test_package_layout.py.

from __future__ import annotations

# ---------------------------------------------------------------------------
# Layer 0/1 - Verbindung, Sitzung, Fehlerklassen
# ---------------------------------------------------------------------------
from .wt3000_core import (
    ConcurrentAccessError,
    ConfigLocked,
    DeviceError,
    ProtocolError,
    ReadOnlyViolation,
    ReconnectableTransport,
    TmctlError,
    TmctlTransport,
    Transport,
    WTConfig,
    WTError,
    WTSession,
)
from .wt3000_transport import FakeTransport

# Ablageort und Protokolldatei - beides braucht jedes Anwenderskript, und
# beides loeste bisher einen Import aus dem Fachmodul aus.
from .wt3000_common import output_dir, setup_logging

# ---------------------------------------------------------------------------
# Layer 2 - Messwerte, Item-Tabelle, Bereiche, Eingangskonfiguration
# ---------------------------------------------------------------------------
from .wt3000_numeric import ItemTable, NumericItem, NumericValue, ValueStatus
from .wt3000_itemspec import ItemSpec
from .wt3000_rangeio import ChangesNotAllowed, Quantity, RangeAccess, RangeValue
from .wt3000_input import (
    CURRENT_RANGES,
    GROUP_AUTO,
    GROUP_CFACTOR,
    GROUP_FILTER,
    GROUP_MODE,
    GROUP_RANGE,
    GROUP_RATE,
    GROUP_SCALING,
    GROUP_SYNC,
    GROUP_WIRING,
    SENSOR_RANGES,
    UPDATE_RATES_S,
    VOLTAGE_RANGES,
    ElementSettings,
    InputConfig,
    InputLocked,
    InputSnapshot,
    LineFilter,
    MeasMode,
    SyncSource,
    VerificationError,
    Wiring,
    WiringUnit,
    restore_input_snapshot,
)
# Oeffentliche Konfigurations- und Integrationstypen.
from .wt3000_deviceconfig import (
    GROUP_COMPUTATION,
    GROUP_HARMONICS,
    GROUP_INTEGRATE,
    GROUP_RESET,
    GROUP_RUN,
    AveragingSettings,
    AveragingType,
    ComputationConfig,
    ComputationSettings,
    DeviceConfigLocked,
    EfficiencyEquation,
    FrequencyBand,
    HarmonicsConfig,
    HarmonicsSettings,
    IecGrouping,
    IntegrationConfig,
    IntegrationMode,
    IntegrationSettings,
    IntegrationState,
    IntegrationStateError,
    SQFormula,
    SyncMode,
    ThdFormula,
)

# ---------------------------------------------------------------------------
# Layer 3 - Ablaeufe: Bereichsplan, Messung, Ausgabe, Sicherungspunkt
# ---------------------------------------------------------------------------
from .wt3000_ranging import (
    AutoRangeSpec,
    ElementRangeState,
    RangeBackup,
    RangePlan,
    RangeReport,
    RangeSpec,
    applied_ranges,
)
# Messdatensatz, Messsteuerung und Profilfunktionen.
from .wt3000_measure import (
    SIDECAR_VERSION,
    ErrorPolicy,
    LoopStatistics,
    Measurement,
    MeasurementAborted,
    NumericHold,
    RunMetadata,
    SidecarMismatch,
    Sample,
    SampleMark,
    SampleSink,
    build_harmonics_profile,
    build_integration_profile,
    build_standard_profile,
    sidecar_path,
    verify_sidecar,
)
# Ausgabeformate und ihr gemeinsamer Vertrag SampleSink.
from .wt3000_sinks import (
    AppendMismatch,
    CallbackSink,
    CsvSink,
    ExistingFile,
    JsonlSink,
    MultiSink,
    RotatingSink,
    RotationPolicy,
    SinkNotOpen,
    unique_path,
)
# Sitzungs-Backup und Optionsanforderungen gehoeren zur Fassade.
from .wt3000_backup import BACKUP_VERSION, SessionBackup

# ---------------------------------------------------------------------------
# Layer 4 - die Fassade
# ---------------------------------------------------------------------------
from .wt3000_device import (
    INPUT_GROUPS,
    OPTION_REQUIREMENTS,
    DeviceInfo,
    ItemAccess,
    MeasureControl,
    WT3000,
)

__all__ = [
    "__version__",
    "MODULES",
    # -- Fassade ------------------------------------------------------------
    "WT3000",
    "DeviceInfo",
    "ItemAccess",
    "MeasureControl",
    "OPTION_REQUIREMENTS",
    # -- Verbindung ---------------------------------------------------------
    "WTConfig",
    "WTSession",
    "Transport",
    "TmctlTransport",
    "FakeTransport",
    # -- Fehlerklassen ------------------------------------------------------
    "WTError",
    "TmctlError",
    "ProtocolError",
    "DeviceError",
    "ReadOnlyViolation",
    "ReconnectableTransport",
    "ConcurrentAccessError",
    # 'ConfigLocked' ist die gemeinsame Basis der drei Sperren darunter - wer
    # nicht unterscheiden muss, faengt sie und nur sie.
    "ConfigLocked",
    "InputLocked",
    "DeviceConfigLocked",
    "ChangesNotAllowed",
    "VerificationError",
    # -- Aufzaehlungen und Werttypen ----------------------------------------
    "Quantity",
    "Wiring",
    "WiringUnit",
    "SyncSource",
    "LineFilter",
    "MeasMode",
    "ValueStatus",
    "NumericValue",
    # -- Eingangskonfiguration ----------------------------------------------
    "InputConfig",
    "InputSnapshot",
    "ElementSettings",
    "restore_input_snapshot",
    # Gruppen fuer 'wt.input.unlocked(...)'. INPUT_GROUPS ist die vollstaendige
    # Liste, wie sie 'WT3000.restore_backup()' benutzt.
    "INPUT_GROUPS",
    "GROUP_WIRING",
    "GROUP_RANGE",
    "GROUP_AUTO",
    "GROUP_CFACTOR",
    "GROUP_FILTER",
    "GROUP_SCALING",
    "GROUP_SYNC",
    "GROUP_MODE",
    "GROUP_RATE",
    # Zulaessige Stellwerte - damit ein Skript sie nachschlagen kann, statt
    # sie zu raten und am Geraet aufzulaufen.
    "VOLTAGE_RANGES",
    "CURRENT_RANGES",
    "SENSOR_RANGES",
    "UPDATE_RATES_S",
    # -- Messbereiche -------------------------------------------------------
    "RangeAccess",
    "RangeValue",
    "RangeSpec",
    "AutoRangeSpec",
    "RangePlan",
    "RangeBackup",
    "RangeReport",
    "ElementRangeState",
    # Der uebliche Weg ist die Fassadenmethode 'wt.applied_ranges(plan)'; diese
    # Funktion ist dieselbe Klammer fuer ein RangeAccess ohne Fassade.
    "applied_ranges",
    # -- Item-Tabelle: WAS gemessen wird ------------------------------------
    "ItemSpec",
    "ItemTable",
    "NumericItem",
    "build_standard_profile",
    "build_integration_profile",
    "build_harmonics_profile",
    # -- Sicherungspunkt ----------------------------------------------------
    "SessionBackup",
    "BACKUP_VERSION",
    # -- Rechenfunktionen ---------------------------------------------------
    "ComputationConfig",
    "ComputationSettings",
    "AveragingSettings",
    "AveragingType",
    "EfficiencyEquation",
    "SQFormula",
    "SyncMode",
    "GROUP_COMPUTATION",
    # -- Oberschwingungen ---------------------------------------------------
    "HarmonicsConfig",
    "HarmonicsSettings",
    "FrequencyBand",
    "ThdFormula",
    "IecGrouping",
    "GROUP_HARMONICS",
    # -- Integration --------------------------------------------------------
    "IntegrationConfig",
    "IntegrationMode",
    "IntegrationSettings",
    "IntegrationState",
    "IntegrationStateError",
    "GROUP_INTEGRATE",
    "GROUP_RUN",
    "GROUP_RESET",
    # -- Steuerbare Messung -------------------------------------------------
    "Measurement",
    "LoopStatistics",
    "NumericHold",
    # -- Fehlerstrategie bei Kommunikationsabbruechen -----------------------
    "ErrorPolicy",
    "MeasurementAborted",
    # -- Verbindliche Metadaten (M4-3) --------------------------------------
    "RunMetadata",
    "SidecarMismatch",
    "verify_sidecar",
    "sidecar_path",
    "SIDECAR_VERSION",
    # -- Datensatz ----------------------------------------------------------
    "Sample",
    "SampleMark",
    # -- Ausgabeformate -----------------------------------------------------
    "SampleSink",
    "CsvSink",
    "JsonlSink",
    "CallbackSink",
    "MultiSink",
    "SinkNotOpen",
    "ExistingFile",
    # -- Rotation und sicheres Fortsetzen (M4-4) ----------------------------
    "RotatingSink",
    "RotationPolicy",
    "AppendMismatch",
    "unique_path",
    # -- Ablage und Protokoll -----------------------------------------------
    "output_dir",
    "setup_logging",
]

__version__ = "0.3.0"

# Die Fachmodule des Pakets, in Schichtreihenfolge. Dient der Dokumentation und
# dem Importtest in tests/test_package_layout.py.
MODULES: tuple[str, ...] = (
    "wt3000_transport",
    "wt3000_core",
    "wt3000_common",
    "wt3000_numeric",
    "wt3000_rangeio",
    "wt3000_input",
    "wt3000_deviceconfig",
    "wt3000_itemspec",
    "wt3000_backup",
    "wt3000_ranging",
    "wt3000_measure",
    "wt3000_sinks",
    "wt3000_device",
)
