from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "institucional.yaml")


def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _hours_to_allowed(exclude_hours: Optional[List[int]]) -> List[int]:
    cleaned: List[int] = []
    for h in exclude_hours or []:
        try:
            cleaned.append(int(h) % 24)
        except Exception:
            continue
    cleaned = sorted(set(cleaned))
    return [h for h in range(24) if h not in cleaned]


def _validate_schema(raw: Dict[str, Any]) -> None:
    required_top = ["version", "profiles", "defaults", "symbols", "portfolio", "sensitivity"]
    for key in required_top:
        if key not in raw:
            raise ValueError(f"Configuración institucional inválida: falta la clave obligatoria '{key}'")

    defaults = raw.get("defaults", {}) or {}
    filters = defaults.get("filters", {}) or {}
    exclude_hours = filters.get("exclude_hours", [])
    if not isinstance(exclude_hours, list):
        raise TypeError("defaults.filters.exclude_hours debe ser una lista de enteros 0..23")
    for h in exclude_hours:
        if not isinstance(h, (int, float)) or int(h) != h or not (0 <= int(h) <= 23):
            raise ValueError(f"exclude_hours contiene valor inválido: {h}")

    for field_name in ("min_atr_pct", "min_bbw_pct"):
        val = filters.get(field_name)
        if val is None:
            continue
        if not isinstance(val, (int, float)):
            raise TypeError(f"defaults.filters.{field_name} debe ser numérico")
        if not (0.0 <= float(val) <= 1.0):
            raise ValueError(f"defaults.filters.{field_name} debe estar entre 0 y 1")

    execution = defaults.get("execution", {}) or {}
    for field_name in ("fee_bps", "slippage_bps"):
        val = execution.get(field_name)
        if val is None:
            continue
        if not isinstance(val, (int, float)) or int(val) != val:
            raise TypeError(f"defaults.execution.{field_name} debe ser un entero (basis points)")

    guardrails = defaults.get("guardrails", {}) or {}
    for field_name in ("max_dd_pct", "max_fees_pct", "min_pf_net"):
        val = guardrails.get(field_name)
        if val is None:
            continue
        if not isinstance(val, (int, float)):
            raise TypeError(f"defaults.guardrails.{field_name} debe ser numérico")
        if field_name in {"max_dd_pct", "max_fees_pct"} and not (0.0 <= float(val) <= 1.0):
            raise ValueError(f"defaults.guardrails.{field_name} debe estar entre 0 y 1 (fracción)")

    symbols = raw.get("symbols", {}) or {}
    if not isinstance(symbols, dict) or not symbols:
        raise ValueError("Debe definirse al menos un símbolo en symbols")

    portfolio = raw.get("portfolio", {}) or {}
    include = portfolio.get("include", []) or []
    if not isinstance(include, list) or not include:
        raise ValueError("portfolio.include debe ser una lista con al menos un símbolo")
    missing = [sym for sym in include if sym not in symbols]
    if missing:
        raise ValueError(f"portfolio.include contiene símbolos no definidos: {missing}")

    sensitivity = raw.get("sensitivity", {}) or {}
    if not isinstance(sensitivity.get("r_deltas", []), list):
        raise TypeError("sensitivity.r_deltas debe ser una lista")


@dataclass
class SymbolConfig:
    symbol: str
    enabled: bool = True
    winner: Optional[str] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    tp_sl_by_regime: Dict[str, Dict[str, float]] = field(default_factory=dict)
    weight: float = 1.0
    role: Optional[str] = None


@dataclass
class InstitucionalConfig:
    version: int
    raw: Dict[str, Any]
    metadata: Dict[str, Any]
    defaults: Dict[str, Any]
    profiles: Dict[str, Any]
    symbols: Dict[str, SymbolConfig]
    portfolio_include: List[str]
    portfolio_weighting: str
    sensitivity: Dict[str, Any]


def get_institucional_config(path: Optional[str] = None) -> InstitucionalConfig:
    cfg_path = path or CONFIG_PATH
    if not os.path.exists(cfg_path):
        raise FileNotFoundError(f"Institucional config not found at {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    _validate_schema(raw)

    version = int(raw.get("version", 1))
    metadata = raw.get("metadata", {}) or {}
    profiles = raw.get("profiles", {})
    defaults = raw.get("defaults", {})

    # Prepare defaults
    d_filters = defaults.get("filters", {})
    exclude_hours = d_filters.get("exclude_hours", [])
    allowed_hours = _hours_to_allowed(exclude_hours)
    d_filters = _deep_merge(d_filters, {"allowed_hours": allowed_hours})

    # TP/SL profile resolution
    profile_name = defaults.get("tp_sl_by_regime_profile")
    profile_map = profiles.get("tp_sl_by_regime", {})
    tp_sl_profile = profile_map.get(profile_name, {}) if profile_name else {}

    defaults_resolved = {
        "filters": d_filters,
        "execution": defaults.get("execution", {}),
        "tp_sl_by_regime": tp_sl_profile,
        "guardrails": defaults.get("guardrails", {}),
    }

    symbols_cfg: Dict[str, SymbolConfig] = {}
    for sym, scfg in (raw.get("symbols", {}) or {}).items():
        # Merge recursive: defaults+symbol overrides
        merged_filters = _deep_merge(d_filters, scfg.get("filters", {}) or {})
        merged_execution = _deep_merge(defaults.get("execution", {}), scfg.get("execution", {}))

        # symbol tp/sl: explicit dict wins, else inherit profile
        tp_sl_over = scfg.get("tp_sl_by_regime")
        merged_tp_sl = tp_sl_profile if not tp_sl_over else _deep_merge(tp_sl_profile, tp_sl_over)

        symbols_cfg[sym] = SymbolConfig(
            symbol=sym,
            enabled=bool(scfg.get("enabled", True)),
            winner=scfg.get("winner"),
            filters=merged_filters,
            execution=merged_execution,
            tp_sl_by_regime=merged_tp_sl,
            weight=float(scfg.get("weight", 1.0)),
            role=scfg.get("role"),
        )

    portfolio = raw.get("portfolio", {})
    sensitivity = raw.get("sensitivity", {})

    return InstitucionalConfig(
        version=version,
        raw=raw,
        metadata=metadata,
        defaults=defaults_resolved,
        profiles=profiles,
        symbols=symbols_cfg,
        portfolio_include=portfolio.get("include", list(symbols_cfg.keys())),
        portfolio_weighting=portfolio.get("weighting", "equal"),
        sensitivity=sensitivity,
    )


def freeze_params(out_dir: str, cfg: InstitucionalConfig, extra: Optional[Dict[str, Any]] = None) -> str:
    os.makedirs(out_dir, exist_ok=True)
    frozen = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": cfg.version,
        "metadata": cfg.metadata,
        "defaults": cfg.defaults,
        "symbols": {s: vars(sc) for s, sc in cfg.symbols.items()},
    }
    if extra:
        frozen["extra"] = extra
    # Also copy source YAML for traceability if available
    yaml_hash = None
    try:
        src_yaml = CONFIG_PATH
        if os.path.exists(src_yaml):
            with open(src_yaml, "r", encoding="utf-8") as fy:
                yaml_text = fy.read()
            yaml_hash = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
            meta_dir = os.path.join(out_dir, "metadata")
            os.makedirs(meta_dir, exist_ok=True)
            with open(os.path.join(meta_dir, "institucional.yaml"), "w", encoding="utf-8") as fo:
                fo.write(yaml_text)
    except Exception:
        yaml_hash = None
    if yaml_hash:
        frozen["yaml_sha256"] = yaml_hash
    out_path = os.path.join(out_dir, "params_frozen.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(frozen, f, ensure_ascii=False, indent=2)
    return out_path
