"""
test_edge_filter.py
-------------------
Valida el filtro de edge neto (costos) introducido en:
  - src/policies/gating.py : passes_edge_filter / should_trade
  - src/core/backtesting.py : _entry_signal (integracion con TP por regimen)

Punto critico verificado: las unidades de atr_pct estan en ESCALA PORCENTUAL
(0.30 == 0.30%), por lo que el filtro normaliza dividiendo por 100 antes de
comparar contra el costo round-trip. Si esa normalizacion faltara, el filtro
nunca bloquearia (bug silencioso).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.policies.gating import passes_edge_filter, should_trade
from src.core.backtesting import BTConfig, _entry_signal


# Parametros de referencia (BNB): fee 8 bps, slippage 5 bps -> costo RT = 0.26%
FEE_BPS = 8.0
SLIP_BPS = 5.0
COST_RT_FRAC = (FEE_BPS + SLIP_BPS) / 10_000.0 * 2.0  # 0.0026
MIN_EDGE = 1.5


# --------------------------------------------------------------------------- #
# passes_edge_filter (funcion pura)
# --------------------------------------------------------------------------- #
def test_buen_edge_pasa():
    # ATR 0.30%, TP 2.5x -> tp_frac = 0.0075 ; umbral = 0.0039 -> pasa
    assert passes_edge_filter(atr_pct=0.30, tp_mult=2.5,
                              fee_bps=FEE_BPS, slippage_bps=SLIP_BPS,
                              min_edge_mult=MIN_EDGE) is True


def test_bajo_edge_bloquea():
    # ATR 0.13%, TP 2.5x -> tp_frac = 0.00325 ; umbral = 0.0039 -> bloquea
    assert passes_edge_filter(atr_pct=0.13, tp_mult=2.5,
                              fee_bps=FEE_BPS, slippage_bps=SLIP_BPS,
                              min_edge_mult=MIN_EDGE) is False


def test_normalizacion_de_unidades():
    # Si NO se normalizara (%/100), tp seria 2.5*0.13 = 0.325 >> umbral y nunca
    # bloquearia. Como SI se normaliza, este caso de bajo ATR bloquea.
    # Verificamos explicitamente el calculo esperado.
    tp_frac = 2.5 * (0.13 / 100.0)
    assert tp_frac < COST_RT_FRAC * MIN_EDGE
    assert passes_edge_filter(atr_pct=0.13, tp_mult=2.5,
                              fee_bps=FEE_BPS, slippage_bps=SLIP_BPS,
                              min_edge_mult=MIN_EDGE) is False


def test_frontera_exacta_pasa():
    # tp_frac == umbral debe pasar (>=). Despejamos atr_pct para igualdad.
    umbral = COST_RT_FRAC * MIN_EDGE          # 0.0039
    atr_pct = (umbral / 2.5) * 100.0          # en escala %
    assert passes_edge_filter(atr_pct=atr_pct, tp_mult=2.5,
                              fee_bps=FEE_BPS, slippage_bps=SLIP_BPS,
                              min_edge_mult=MIN_EDGE) is True


@pytest.mark.parametrize("atr_pct,tp_mult", [
    (None, 2.5),
    (0.30, None),
    (0.0, 2.5),
    (0.30, 0.0),
    ("x", 2.5),
])
def test_fail_open_con_datos_faltantes(atr_pct, tp_mult):
    # Sin datos suficientes o invalidos -> no bloquea (fail-open).
    assert passes_edge_filter(atr_pct=atr_pct, tp_mult=tp_mult,
                              fee_bps=FEE_BPS, slippage_bps=SLIP_BPS,
                              min_edge_mult=MIN_EDGE) is True


def test_edge_mult_mayor_es_mas_estricto():
    # Un edge que pasa con 1.5 debe bloquear con un multiplo mucho mayor.
    assert passes_edge_filter(atr_pct=0.30, tp_mult=2.5, fee_bps=FEE_BPS,
                              slippage_bps=SLIP_BPS, min_edge_mult=1.5) is True
    assert passes_edge_filter(atr_pct=0.30, tp_mult=2.5, fee_bps=FEE_BPS,
                              slippage_bps=SLIP_BPS, min_edge_mult=5.0) is False


# --------------------------------------------------------------------------- #
# should_trade (integracion en el gating de policies)
# --------------------------------------------------------------------------- #
def test_should_trade_bloquea_por_edge():
    ctx = {
        "atr_pct": 0.13, "tp_mult": 2.5,
        "fee_bps": FEE_BPS, "slippage_bps": SLIP_BPS, "min_edge_mult": MIN_EDGE,
    }
    assert should_trade(ctx) is False


def test_should_trade_pasa_con_buen_edge():
    ctx = {
        "atr_pct": 0.30, "tp_mult": 2.5,
        "fee_bps": FEE_BPS, "slippage_bps": SLIP_BPS, "min_edge_mult": MIN_EDGE,
    }
    assert should_trade(ctx) is True


def test_should_trade_sin_edge_keys_mantiene_comportamiento_previo():
    # Sin tp_mult/atr_pct el filtro de edge no aplica (fail-open) y should_trade
    # devuelve True como antes.
    assert should_trade({}) is True


# --------------------------------------------------------------------------- #
# _entry_signal (integracion en backtesting con TP por regimen)
# --------------------------------------------------------------------------- #
def _row(atr_pct: float, regime: str = "neutral") -> pd.Series:
    return pd.Series({
        "timestamp": pd.Timestamp("2025-09-01T10:00:00Z"),
        "close": 100.0,
        "ATR_pct": atr_pct,
        "BBW_pct": 5.0,           # holgado para no bloquear por BBW
        "market_regime": regime,
        "RSI": np.nan,
        "ADX": np.nan,
    })


def test_entry_signal_filtro_desactivado_por_default():
    # min_edge_mult None (default) -> no bloquea por edge aunque el ATR sea bajo.
    cfg = BTConfig(min_atr_pct=0.10, min_bbw_pct=0.10, tp_mult=2.5,
                   fee_bps=FEE_BPS, slippage_bps=SLIP_BPS)
    ok, dbg = _entry_signal(_row(0.13), cfg, side="long")
    assert ok is True
    assert "block_edge" not in dbg


def test_entry_signal_bloquea_por_edge_cuando_activo():
    cfg = BTConfig(min_atr_pct=0.10, min_bbw_pct=0.10, tp_mult=2.5,
                   fee_bps=FEE_BPS, slippage_bps=SLIP_BPS, min_edge_mult=1.5)
    ok, dbg = _entry_signal(_row(0.13), cfg, side="long")
    assert ok is False
    assert dbg.get("block_edge") is True


def test_entry_signal_pasa_buen_edge_cuando_activo():
    cfg = BTConfig(min_atr_pct=0.10, min_bbw_pct=0.10, tp_mult=2.5,
                   fee_bps=FEE_BPS, slippage_bps=SLIP_BPS, min_edge_mult=1.5)
    ok, dbg = _entry_signal(_row(0.30), cfg, side="long")
    assert ok is True
    assert "block_edge" not in dbg


def test_entry_signal_usa_tp_por_regimen():
    # En regimen "range" el TP efectivo es bajo (1.0) -> mismo ATR que pasaria
    # con TP global (2.5) ahora bloquea por usar el TP del regimen.
    profile = {"range": {"tp_mult": 1.0, "sl_mult": 1.0}}
    cfg = BTConfig(min_atr_pct=0.10, min_bbw_pct=0.10, tp_mult=2.5,
                   fee_bps=FEE_BPS, slippage_bps=SLIP_BPS, min_edge_mult=1.5,
                   tp_sl_by_regime=profile)
    # ATR 0.20%: con TP 2.5 pasaria (0.005 > 0.0039), con TP 1.0 del regimen
    # range tp_frac=0.002 < 0.0039 -> bloquea.
    ok, dbg = _entry_signal(_row(0.20, regime="range"), cfg, side="long")
    assert ok is False
    assert dbg.get("tp_eff") == 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
