#!/usr/bin/env python3
"""Test de integración Beta A2 con guardrails institucionales."""

import pytest
import sys
from pathlib import Path

# Añadir src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.backtesting import configure_from_institucional, backtesting_legacy
from src.pipeline.carga_un_simbolo_combinado import cargar_y_combinar_datos
from src.core.utilidades import limpiar_ohlcv


def test_beta_a2_configuracion():
    """Test configuración Beta A2 desde YAML institucional."""
    # Test perfil conservador
    cfg_cons = configure_from_institucional(
        'config/institucional.yaml', 
        'BTCUSDT', 
        'conservador'
    )
    
    assert cfg_cons.strict_proximity_bars >= 0
    assert cfg_cons.min_atr_pct > 0
    assert cfg_cons.min_bbw_pct > 0
    assert cfg_cons.symbol == 'BTCUSDT'
    
    # Test perfil agresivo
    cfg_agre = configure_from_institucional(
        'config/institucional.yaml', 
        'BTCUSDT', 
        'agresivo'
    )
    
    assert cfg_agre.strict_proximity_bars >= 0
    print(f"✅ Configuración Beta A2 OK - conservador: {cfg_cons.strict_proximity_bars}, agresivo: {cfg_agre.strict_proximity_bars}")


def test_beta_a2_backtesting_smoke():
    """Test de humo del backtesting con guardrails Beta A2."""
    # Configurar
    cfg = configure_from_institucional(
        'config/institucional.yaml', 
        'BTCUSDT', 
        'conservador'
    )
    
    # Cargar datos de prueba (pequeño dataset)
    df = cargar_y_combinar_datos(
        'data/historiales/historial_trading_maestro_15m.csv', 
        symbol='BTCUSDT', 
        meses=1
    )
    df_clean = limpiar_ohlcv(df)
    
    assert not df_clean.empty, "Dataset de prueba no puede estar vacío"
    
    # Ejecutar backtesting con muestra pequeña (primeras 200 filas)
    df_test = df_clean.head(200)
    result = backtesting_legacy(df_test, config_obj=cfg)
    
    # Verificar resultado
    assert isinstance(result, tuple)
    assert len(result) >= 2
    
    resultados, resumen = result[0], result[1]
    trades_enriched = result[2] if len(result) > 2 else []
    
    # Verificar estructura
    assert isinstance(resultados, list)
    assert isinstance(resumen, dict)
    
    # Verificar que los guardrails fueron aplicados (puede haber stats)
    if hasattr(cfg, '_guardrail_stats'):
        stats = getattr(cfg, '_guardrail_stats', {})
        print(f"📊 Estadísticas guardrails: {stats}")
    
    print(f"✅ Backtesting Beta A2 smoke test OK - {len(trades_enriched)} trades generados")


def test_beta_a2_tp_sl_dinamico():
    """Test TP/SL dinámico por régimen."""
    from src.core.backtesting import _resolve_tp_sl, BTConfig
    
    # Mock de configuración TP/SL
    cfg = BTConfig()
    cfg.tp_sl_by_regime = {
        "bull": {"sl_mult": 1.0, "tp_mult": 2.5},
        "bear": {"sl_mult": 1.2, "tp_mult": 2.0},
        "neutral": {"sl_mult": 1.1, "tp_mult": 2.2}
    }
    cfg.sl_mult = 1.5  # fallback
    cfg.tp_mult = 3.0  # fallback
    
    # Test resolución por régimen
    sl_bull, tp_bull = _resolve_tp_sl(cfg, "bull")
    assert sl_bull == 1.0
    assert tp_bull == 2.5
    
    sl_bear, tp_bear = _resolve_tp_sl(cfg, "bear")
    assert sl_bear == 1.2
    assert tp_bear == 2.0
    
    # Test fallback para régimen desconocido
    sl_unknown, tp_unknown = _resolve_tp_sl(cfg, "unknown")
    assert sl_unknown == 1.5  # fallback
    assert tp_unknown == 3.0  # fallback
    
    print("✅ TP/SL dinámico por régimen OK")


def test_beta_a2_guardrails():
    """Test funciones auxiliares de guardrails Beta A2."""
    from src.core.backtesting import (
        _check_strict_proximity_guardrail,
        _check_mfe_mae_ratio_guardrail,
        BTConfig
    )
    
    # Test strict proximity
    cfg = BTConfig()
    cfg.strict_proximity_bars = 5
    
    last_signals = {"bull": 10}
    
    # Señal muy cerca (debe rechazarse)
    assert not _check_strict_proximity_guardrail(cfg, last_signals, 12, "bull")
    
    # Señal suficientemente lejos (debe aceptarse)
    assert _check_strict_proximity_guardrail(cfg, last_signals, 16, "bull")
    
    # Test MFE/MAE ratio
    cfg.min_mfe_mae_ratio = 1.5
    
    # Trade con buen ratio
    good_trade = {"mfe": 30.0, "mae": 15.0}  # ratio = 2.0
    assert _check_mfe_mae_ratio_guardrail(cfg, good_trade)
    
    # Trade con mal ratio
    bad_trade = {"mfe": 10.0, "mae": 15.0}  # ratio = 0.67
    assert not _check_mfe_mae_ratio_guardrail(cfg, bad_trade)
    
    print("✅ Guardrails Beta A2 funcionando correctamente")


if __name__ == "__main__":
    print("🧪 Ejecutando tests de integración Beta A2...")
    
    try:
        test_beta_a2_configuracion()
        test_beta_a2_backtesting_smoke()
        test_beta_a2_tp_sl_dinamico()
        test_beta_a2_guardrails()
        
        print("\n🎯 ¡TODOS LOS TESTS BETA A2 PASARON!")
        print("✅ Integración Beta A2 verificada correctamente")
        
    except Exception as e:
        print(f"\n❌ TEST FALLÓ: {e}")
        raise