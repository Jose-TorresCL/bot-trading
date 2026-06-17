import yaml
import pytest

from src.config_loader import get_institucional_config


def _write_yaml(path, payload):
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_get_institucional_config_builds_defaults(tmp_path):
    cfg_payload = {
        "version": 1,
        "metadata": {"owner": "QA"},
        "profiles": {
            "tp_sl_by_regime": {
                "base": {
                    "neutral": {"SL_MULT": 1.0, "TP_MULT": 2.0},
                    "trend": {"SL_MULT": 1.5, "TP_MULT": 3.0},
                }
            }
        },
        "defaults": {
            "filters": {
                "exclude_hours": [0, 1, 23],
                "min_atr_pct": 0.2,
                "min_bbw_pct": 0.1,
            },
            "execution": {"fee_bps": 10, "slippage_bps": 5},
            "tp_sl_by_regime_profile": "base",
            "guardrails": {"max_dd_pct": 0.4, "max_fees_pct": 0.2},
        },
        "symbols": {
            "BTCUSDT": {
                "enabled": True,
                "filters": {"min_atr_pct": 0.25},
                "execution": {"fee_bps": 8},
                "tp_sl_by_regime": {"neutral": {"SL_MULT": 1.2, "TP_MULT": 2.4}},
            }
        },
        "portfolio": {"include": ["BTCUSDT"], "weighting": "equal"},
        "sensitivity": {"r_deltas": [0.1, 0.2]},
    }

    cfg_path = tmp_path / "institucional.yaml"
    _write_yaml(cfg_path, cfg_payload)

    cfg = get_institucional_config(str(cfg_path))

    assert cfg.version == 1
    assert cfg.metadata["owner"] == "QA"

    horas_permitidas = cfg.defaults["filters"]["allowed_hours"]
    assert 2 in horas_permitidas
    assert 0 not in horas_permitidas
    assert 23 not in horas_permitidas

    simbolo_cfg = cfg.symbols["BTCUSDT"]
    assert simbolo_cfg.execution["fee_bps"] == 8  # override del símbolo
    assert simbolo_cfg.filters["min_atr_pct"] == 0.25
    assert simbolo_cfg.tp_sl_by_regime["neutral"]["SL_MULT"] == 1.2


def test_get_institucional_config_rejects_missing_keys(tmp_path):
    cfg_payload = {
        "version": 1,
        "defaults": {"filters": {"exclude_hours": [0]}, "execution": {}},
        "profiles": {},
        "portfolio": {"include": ["BTCUSDT"]},
        "sensitivity": {"r_deltas": []},
    }
    cfg_path = tmp_path / "institucional_invalido.yaml"
    _write_yaml(cfg_path, cfg_payload)

    with pytest.raises(ValueError):
        get_institucional_config(str(cfg_path))
