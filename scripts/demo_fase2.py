#!/usr/bin/env python3
"""
Demo Fase 2 Institucional - Datos sintéticos para demostración
==============================================================

Genera datos sintéticos de trades y demuestra el flujo completo de Fase 2.
"""

import os
import sys
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

# Añadir src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Logger sin emojis para evitar problemas en Windows
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fase2_demo")


class SyntheticTradesGenerator:
    """Generador de trades sintéticos para demostración."""
    
    def __init__(self, symbol: str, seed: int = 42):
        self.symbol = symbol
        np.random.seed(seed)
    
    def generate_trades(self, n_trades: int = 50) -> pd.DataFrame:
        """Genera trades sintéticos con distribución realista."""
        trades = []
        
        for i in range(n_trades):
            # Generar R-multiple con sesgo hacia ganadores pequeños y perdedores
            if np.random.random() < 0.45:  # 45% winners
                r_multiple = np.random.exponential(1.2)  # Winners sesgados hacia valores pequeños
            else:  # 55% losers
                r_multiple = -np.random.exponential(0.8)  # Losers típicamente menores
            
            # Otras métricas derivadas
            risk_abs = np.random.uniform(50, 200)
            notional = risk_abs * np.random.uniform(8, 12)
            pnl_pct = r_multiple * (risk_abs / notional * 100)
            
            # MAE/MFE realistas
            if r_multiple > 0:
                mae_R = -np.random.uniform(0.1, 0.8)
                mfe_R = r_multiple + np.random.uniform(0, 0.5)
            else:
                mae_R = r_multiple - np.random.uniform(0, 0.3)
                mfe_R = np.random.uniform(0, 0.4)
            
            trade = {
                'timestamp': (datetime.now(UTC).timestamp() - i * 3600) * 1000,  # Trades cada hora
                'symbol': self.symbol,
                'r_multiple': r_multiple,
                'pnl_pct': pnl_pct,
                'mae_R': mae_R,
                'mfe_R': mfe_R,
                'risk_abs': risk_abs,
                'notional': notional
            }
            
            trades.append(trade)
        
        df = pd.DataFrame(trades)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        logger.info(f"Trades sintéticos generados para {self.symbol}: {len(df)} trades")
        logger.info(f"Winrate sintético: {(df['r_multiple'] > 0).mean():.1%}")
        
        return df


def crear_demo_run():
    """Crea un run demo con trades sintéticos."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = Path(f"runs/{timestamp}_demo")
    
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    
    for symbol in symbols:
        symbol_dir = run_dir / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        
        # Generar trades sintéticos
        generator = SyntheticTradesGenerator(symbol)
        
        # Diferentes escenarios por símbolo
        if symbol == "BTCUSDT":
            df_trades = generator.generate_trades(60)  # ACCEPT scenario
        elif symbol == "ETHUSDT":
            df_trades = generator.generate_trades(30)  # REVIEW scenario 
            # Degradar métricas
            df_trades['r_multiple'] *= 0.7
            df_trades['pnl_pct'] *= 0.7
        else:  # BNBUSDT
            df_trades = generator.generate_trades(20)  # REJECT scenario
            # Muy degradado
            df_trades['r_multiple'] *= 0.3
            df_trades['pnl_pct'] *= 0.3
        
        # Guardar trades_enriched.csv
        trades_file = symbol_dir / "trades_enriched.csv"
        df_trades.to_csv(trades_file, index=False)
        
        # Params frozen
        params_frozen = {
            'symbol': symbol,
            'timestamp': timestamp,
            'months': 1,
            'institucional_config': 'demo',
            'total_trades': len(df_trades)
        }
        
        params_file = symbol_dir / "params_frozen.json"
        with open(params_file, 'w') as f:
            json.dump(params_frozen, f, indent=2)
        
        # YAML demo
        yaml_content = f"""# Demo {symbol}
symbol: {symbol}
tp_sl_profile: conservador
months: 1
"""
        yaml_file = symbol_dir / "institucional.yaml"
        with open(yaml_file, 'w') as f:
            f.write(yaml_content)
        
        # Hash
        hash_file = symbol_dir / "institucional_hash.txt"
        with open(hash_file, 'w') as f:
            f.write("demo_hash_" + timestamp)
        
        logger.info(f"Demo run creado para {symbol}")
    
    logger.info(f"Demo run completo: {run_dir}")
    return timestamp


def main():
    """Función principal del demo."""
    print("Demo Fase 2 Institucional - Trades Sintéticos")
    print("=" * 50)
    
    try:
        # 1. Crear run demo
        print("1. Creando run demo con trades sintéticos...")
        demo_timestamp = crear_demo_run()
        
        # 2. Ejecutar Fase 2 sobre el run demo
        print("2. Ejecutando Fase 2 sobre datos sintéticos...")
        
        # Importar y usar el ejecutor original
        from fase2_institucional import Fase2InstitucionalExecutor
        
        executor = Fase2InstitucionalExecutor(demo_timestamp + "_demo", simulacion=False)
        success = executor.ejecutar_fase2()
        
        if success:
            print("\nDEMO FASE 2 COMPLETADO EXITOSAMENTE")
            print(f"Run demo: {demo_timestamp}_demo")
            print(f"Artefactos en: runs/{demo_timestamp}_demo/_costed/")
            return 0
        else:
            print("\nDEMO FASE 2 FALLO")
            return 1
            
    except Exception as e:
        print(f"\nERROR EN DEMO: {e}")
        logger.error(f"Error en demo: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())