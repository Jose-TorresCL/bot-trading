#!/usr/bin/env python3
"""
Fase 2 Institucional - Modelo de costos trade-a-trade y veredictos operativos
===========================================================================

Aplica modelo de costos, revalida performance neta y emite veredictos por símbolo.
Requiere completar Fase 1 con artefactos en runs/<timestamp>/.
"""

import os
import sys
import json
import hashlib
import logging
import argparse
from pathlib import Path
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

# Añadir src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configuración
INSTITUCIONAL_YAML = "config/institucional.yaml"
COSTO_TRADES_YAML = "config/costo_trades.yaml"
METRICS_VERSION = "1.0.0"

# Logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("fase2_institucional")


class CostoTradesConfig:
    """Configuración del modelo de costos trade-a-trade."""
    
    def __init__(self, config_path: str = COSTO_TRADES_YAML):
        self.fee_pct = 0.0008  # 0.08% por defecto
        self.slippage_pct = 0.0005  # 0.05% por defecto
        self.notional_base = 1000.0  # Base para derivar notional
        self.min_pf_net = 1.0  # PF neto mínimo para ACCEPT
        self.review_pf_threshold = 1.5  # PF < 1.5 marca REVIEW
        self.max_dd_threshold = 0.25  # 25% max drawdown
        
        if os.path.exists(config_path):
            self._load_from_yaml(config_path)
        else:
            logger.warning(f"Config {config_path} no encontrado, usando defaults")
            self._create_default_config(config_path)
    
    def _load_from_yaml(self, config_path: str):
        """Carga configuración desde YAML."""
        try:
            import yaml
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            costs = config.get('costs', {})
            self.fee_pct = costs.get('fee_pct', self.fee_pct)
            self.slippage_pct = costs.get('slippage_pct', self.slippage_pct)
            self.notional_base = costs.get('notional_base', self.notional_base)
            
            thresholds = config.get('thresholds', {})
            self.min_pf_net = thresholds.get('min_pf_net', self.min_pf_net)
            self.review_pf_threshold = thresholds.get('review_pf_threshold', self.review_pf_threshold)
            self.max_dd_threshold = thresholds.get('max_dd_threshold', self.max_dd_threshold)
            
            logger.info(f"Configuración costos cargada: fee={self.fee_pct:.4f}, slippage={self.slippage_pct:.4f}")
        
        except Exception as e:
            logger.error(f"Error cargando {config_path}: {e}")
    
    def _create_default_config(self, config_path: str):
        """Crea configuración por defecto."""
        default_config = {
            'version': 1,
            'costs': {
                'fee_pct': self.fee_pct,
                'slippage_pct': self.slippage_pct,
                'notional_base': self.notional_base,
                'description': 'Modelo de costos trade-a-trade'
            },
            'thresholds': {
                'min_pf_net': self.min_pf_net,
                'review_pf_threshold': self.review_pf_threshold,
                'max_dd_threshold': self.max_dd_threshold,
                'description': 'Umbrales para veredictos operativos'
            }
        }
        
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            import yaml
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, indent=2, allow_unicode=True)
            logger.info(f"Configuración por defecto creada en {config_path}")
        except Exception as e:
            logger.warning(f"No se pudo crear {config_path}: {e}")


class Fase2InstitucionalExecutor:
    """Ejecutor de Fase 2 institucional con modelo de costos y veredictos."""
    
    def __init__(self, run_timestamp: str, simulacion: bool = False):
        self.run_timestamp = run_timestamp
        self.simulacion = simulacion
        self.run_dir = Path(f"runs/{run_timestamp}")
        self.costed_dir = self.run_dir / "_costed"
        self.logs_dir = self.run_dir / "logs"
        self.changelogs_dir = Path("changelogs")
        
        # Validar que existe el run
        if not self.run_dir.exists():
            raise FileNotFoundError(f"Run {run_timestamp} no encontrado en {self.run_dir}")
        
        # Crear directorios si no existe
        if not self.simulacion:
            self.costed_dir.mkdir(exist_ok=True)
            self.logs_dir.mkdir(exist_ok=True)
            self.changelogs_dir.mkdir(exist_ok=True)
        
        # Setup logging
        if not self.simulacion:
            log_file = self.logs_dir / f"fase2_{datetime.now(UTC).strftime('%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)
        
        # Cargar configuración de costos
        self.costo_config = CostoTradesConfig()
        
        # Estado
        self.symbols = []
        self.resultados_por_simbolo = {}
        self.veredictos = {}
        
        logger.info(f"🔄 Fase 2 institucional iniciada - Run: {run_timestamp}")
        logger.info(f"📁 Directorio costed: {self.costed_dir}")
        logger.info(f"🎯 Modo simulación: {self.simulacion}")
    
    def detectar_simbolos_disponibles(self) -> List[str]:
        """Detecta símbolos con artefactos de Fase 1."""
        symbols = []
        for item in self.run_dir.iterdir():
            if item.is_dir() and item.name not in ['_costed', 'logs']:
                params_file = item / "params_frozen.json"
                if params_file.exists():
                    symbols.append(item.name)
        
        logger.info(f"📊 Símbolos detectados: {symbols}")
        return symbols
    
    def cargar_run_base(self, symbol: str) -> Tuple[Dict[str, Any], Optional[pd.DataFrame]]:
        """Carga params_frozen.json y trades_enriched.csv por símbolo."""
        symbol_dir = self.run_dir / symbol
        
        # Cargar params_frozen.json
        params_file = symbol_dir / "params_frozen.json"
        with open(params_file, 'r', encoding='utf-8') as f:
            params_frozen = json.load(f)
        
        # Buscar trades_enriched.csv (puede estar en diferentes formatos)
        trades_file = None
        possible_files = [
            symbol_dir / "trades_enriched.csv",
            symbol_dir / "trades_enriquecidos.csv",
            symbol_dir / "session_summary.csv",  # Fallback
            symbol_dir / "grid_resultados.csv"   # Fallback
        ]
        
        df_trades = None
        for file_path in possible_files:
            if file_path.exists():
                try:
                    df_trades = pd.read_csv(file_path)
                    trades_file = file_path
                    logger.info(f"✅ Trades cargados desde {file_path.name}: {len(df_trades)} filas")
                    break
                except Exception as e:
                    logger.warning(f"Error cargando {file_path}: {e}")
        
        if df_trades is None:
            logger.warning(f"⚠️ No se encontraron trades para {symbol}")
        
        return params_frozen, df_trades
    
    def validar_columnas_minimas(self, df_trades: pd.DataFrame, symbol: str) -> Tuple[bool, List[str]]:
        """Valida columnas mínimas requeridas."""
        required_cols = [
            'timestamp', 'symbol', 'r_multiple', 'pnl_pct', 
            'mae_R', 'mfe_R', 'risk_abs'
        ]
        
        missing_cols = []
        for col in required_cols:
            if col not in df_trades.columns:
                missing_cols.append(col)
        
        # Columnas opcionales que podemos derivar
        optional_cols = ['notional', 'commission_paid', 'slippage_cost', 'net_pnl']
        derivable_cols = []
        for col in optional_cols:
            if col not in df_trades.columns:
                derivable_cols.append(col)
        
        valid = len(missing_cols) == 0
        
        if not valid:
            logger.error(f"❌ {symbol}: faltan columnas requeridas: {missing_cols}")
        else:
            logger.info(f"✅ {symbol}: columnas básicas validadas")
        
        if derivable_cols:
            logger.info(f"📋 {symbol}: columnas a derivar: {derivable_cols}")
        
        return valid, derivable_cols
    
    def derivar_columnas_faltantes(self, df_trades: pd.DataFrame, symbol: str, params_frozen: Dict) -> pd.DataFrame:
        """Deriva columnas faltantes usando modelo de costos."""
        df = df_trades.copy()
        
        # 1. Derivar notional si no existe
        if 'notional' not in df.columns:
            # Usar risk_abs * factor o base configurable
            if 'risk_abs' in df.columns:
                df['notional'] = df['risk_abs'] * 10  # Asumir 10:1 ratio
                logger.info(f"📊 {symbol}: notional derivado desde risk_abs")
            else:
                df['notional'] = self.costo_config.notional_base
                logger.warning(f"⚠️ {symbol}: notional fijado a {self.costo_config.notional_base}")
        
        # 2. Calcular commission_paid si no existe
        if 'commission_paid' not in df.columns:
            df['commission_paid'] = df['notional'] * self.costo_config.fee_pct
            logger.info(f"💰 {symbol}: commission_paid calculado ({self.costo_config.fee_pct:.4f})")
        
        # 3. Calcular slippage_cost si no existe
        if 'slippage_cost' not in df.columns:
            df['slippage_cost'] = df['notional'] * self.costo_config.slippage_pct
            logger.info(f"📉 {symbol}: slippage_cost calculado ({self.costo_config.slippage_pct:.4f})")
        
        # 4. Calcular gross_pnl si no existe
        if 'gross_pnl' not in df.columns:
            if 'pnl_pct' in df.columns and 'notional' in df.columns:
                df['gross_pnl'] = df['pnl_pct'] * df['notional'] / 100
                logger.info(f"📈 {symbol}: gross_pnl derivado desde pnl_pct")
            else:
                df['gross_pnl'] = 0.0
                logger.warning(f"⚠️ {symbol}: gross_pnl fijado a 0")
        
        # 5. Recalcular net_pnl
        df['net_pnl'] = df['gross_pnl'] - df['commission_paid'] - df['slippage_cost']
        logger.info(f"✅ {symbol}: net_pnl recalculado")
        
        return df
    
    def compute_core_metrics(self, df_trades: pd.DataFrame, symbol: str) -> Dict[str, float]:
        """Calcula métricas core netas y brutas."""
        if df_trades.empty:
            return self._empty_metrics()
        
        # Métricas básicas
        total_trades = len(df_trades)
        
        # Gross metrics
        gross_wins = (df_trades['gross_pnl'] > 0).sum()
        gross_losses = (df_trades['gross_pnl'] <= 0).sum()
        gross_winrate = (gross_wins / total_trades * 100) if total_trades > 0 else 0
        
        gross_profit = df_trades[df_trades['gross_pnl'] > 0]['gross_pnl'].sum()
        gross_loss = abs(df_trades[df_trades['gross_pnl'] <= 0]['gross_pnl'].sum())
        pf_gross = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        expectancy_gross = df_trades['gross_pnl'].mean()
        
        # Net metrics
        net_wins = (df_trades['net_pnl'] > 0).sum()
        net_losses = (df_trades['net_pnl'] <= 0).sum()
        net_winrate = (net_wins / total_trades * 100) if total_trades > 0 else 0
        
        net_profit = df_trades[df_trades['net_pnl'] > 0]['net_pnl'].sum()
        net_loss = abs(df_trades[df_trades['net_pnl'] <= 0]['net_pnl'].sum())
        pf_net = net_profit / net_loss if net_loss > 0 else float('inf')
        
        expectancy_net = df_trades['net_pnl'].mean()
        
        # Max Drawdown (sobre equity neta)
        equity_curve = df_trades['net_pnl'].cumsum()
        running_max = equity_curve.cummax()
        drawdown = equity_curve - running_max
        max_dd_net = abs(drawdown.min()) if not drawdown.empty else 0.0
        
        # Fees como porcentaje
        total_fees = df_trades['commission_paid'].sum() + df_trades['slippage_cost'].sum()
        total_notional = df_trades['notional'].sum()
        fees_pct = (total_fees / total_notional * 100) if total_notional > 0 else 0.0
        
        metrics = {
            'total_trades': total_trades,
            'gross_winrate': gross_winrate,
            'net_winrate': net_winrate,
            'pf_gross': pf_gross,
            'pf_net': pf_net,
            'expectancy_gross': expectancy_gross,
            'expectancy_net': expectancy_net,
            'max_dd_net': max_dd_net,
            'fees_pct': fees_pct,
            'total_gross_pnl': df_trades['gross_pnl'].sum(),
            'total_net_pnl': df_trades['net_pnl'].sum(),
            'total_fees': total_fees
        }
        
        logger.info(f"📊 {symbol} métricas: PF_net={pf_net:.2f}, Exp_net={expectancy_net:.2f}, WR_net={net_winrate:.1f}%")
        
        return metrics
    
    def _empty_metrics(self) -> Dict[str, float]:
        """Métricas vacías para símbolos sin trades."""
        return {
            'total_trades': 0,
            'gross_winrate': 0.0,
            'net_winrate': 0.0,
            'pf_gross': 0.0,
            'pf_net': 0.0,
            'expectancy_gross': 0.0,
            'expectancy_net': 0.0,
            'max_dd_net': 0.0,
            'fees_pct': 0.0,
            'total_gross_pnl': 0.0,
            'total_net_pnl': 0.0,
            'total_fees': 0.0
        }
    
    def aplicar_filtros_robustez(self, metrics: Dict[str, float], symbol: str) -> Tuple[str, str]:
        """Aplica filtros de robustez y retorna veredicto y razón."""
        pf_net = metrics['pf_net']
        expectancy_net = metrics['expectancy_net']
        max_dd_net = metrics['max_dd_net']
        
        # 1. REJECT: PF neto < 1.0 o expectancy <= 0
        if pf_net < self.costo_config.min_pf_net:
            return "REJECT", f"PF_net={pf_net:.2f} < {self.costo_config.min_pf_net}"
        
        if expectancy_net <= 0:
            return "REJECT", f"Expectancy_net={expectancy_net:.2f} <= 0"
        
        # 2. REVIEW: 1.0 <= PF < 1.5 o max_dd > umbral
        if pf_net < self.costo_config.review_pf_threshold:
            return "REVIEW", f"PF_net={pf_net:.2f} < {self.costo_config.review_pf_threshold}"
        
        if max_dd_net > self.costo_config.max_dd_threshold:
            return "REVIEW", f"Max_DD={max_dd_net:.2f} > {self.costo_config.max_dd_threshold}"
        
        # 3. ACCEPT: Todas las validaciones pasaron
        return "ACCEPT", f"PF_net={pf_net:.2f}, Exp_net={expectancy_net:.2f}"
    
    def persistir_artefactos_costed(self, symbol: str, df_trades_costed: pd.DataFrame, 
                                  metrics: Dict[str, float], veredicto: Dict[str, Any]):
        """Persiste artefactos procesados en _costed/<symbol>/."""
        if self.simulacion:
            logger.info(f"🎭 SIMULACION: persistir artefactos para {symbol}")
            return
        
        symbol_costed_dir = self.costed_dir / symbol
        symbol_costed_dir.mkdir(exist_ok=True)
        
        # 1. trades_enriched_costed.csv
        trades_file = symbol_costed_dir / "trades_enriched_costed.csv"
        df_trades_costed.to_csv(trades_file, index=False)
        
        # 2. session_summary_net.csv
        summary_data = {
            'symbol': [symbol],
            'timestamp': [datetime.now(UTC).isoformat()],
            **{k: [v] for k, v in metrics.items()}
        }
        summary_df = pd.DataFrame(summary_data)
        summary_file = symbol_costed_dir / "session_summary_net.csv"
        summary_df.to_csv(summary_file, index=False)
        
        # 3. grid_resultados_net.csv (formato grid)
        grid_data = [{
            'symbol': symbol,
            'timestamp': datetime.now(UTC).isoformat(),
            'pf_net': metrics['pf_net'],
            'expectancy_net': metrics['expectancy_net'],
            'winrate_net': metrics['net_winrate'],
            'max_dd_net': metrics['max_dd_net'],
            'fees_pct': metrics['fees_pct'],
            'total_trades': metrics['total_trades'],
            'verdict': veredicto['verdict']
        }]
        grid_df = pd.DataFrame(grid_data)
        grid_file = symbol_costed_dir / "grid_resultados_net.csv"
        grid_df.to_csv(grid_file, index=False)
        
        # 4. veredicto.json
        veredicto_file = symbol_costed_dir / "veredicto.json"
        with open(veredicto_file, 'w', encoding='utf-8') as f:
            json.dump(veredicto, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 {symbol}: artefactos costed persistidos")
    
    def generar_changelog_costed(self):
        """Genera changelog técnico costed_changelog_<timestamp>.md."""
        if self.simulacion:
            logger.info("🎭 SIMULACION: generar changelog costed")
            return
        
        changelog_file = self.changelogs_dir / f"costed_changelog_{self.run_timestamp}.md"
        
        # Leer hash del YAML original
        yaml_hash = "unknown"
        try:
            hash_file = self.run_dir / list(self.symbols)[0] / "institucional_hash.txt"
            if hash_file.exists():
                yaml_hash = hash_file.read_text().strip()
        except:
            pass
        
        changelog_content = f"""# Changelog Técnico - Fase 2 Costed
## Run: {self.run_timestamp}
## Generado: {datetime.now(UTC).isoformat()}

### Hash del YAML institucional
```
{yaml_hash}
```

### Versiones
- METRICS_VERSION: {METRICS_VERSION}
- Motor: Beta A2 con modelo de costos trade-a-trade

### Parámetros de costo aplicados
- Fee: {self.costo_config.fee_pct:.4f} ({self.costo_config.fee_pct*100:.2f}%)
- Slippage: {self.costo_config.slippage_pct:.4f} ({self.costo_config.slippage_pct*100:.2f}%)
- Notional base: {self.costo_config.notional_base:.2f}

### Umbrales de robustez
- Min PF net: {self.costo_config.min_pf_net}
- PF review threshold: {self.costo_config.review_pf_threshold}
- Max DD threshold: {self.costo_config.max_dd_threshold}

### Resumen por símbolo

"""
        
        for symbol in self.symbols:
            if symbol in self.veredictos:
                v = self.veredictos[symbol]
                changelog_content += f"""#### {symbol}
- **Veredicto**: {v['verdict']}
- **Razón**: {v['reason']}
- **PF Net**: {v['pf_net']:.2f}
- **Expectancy Net**: {v['expectancy_net']:.4f}
- **Winrate Net**: {v['winrate_net']:.1f}%
- **Max DD Net**: {v['max_dd_net']:.4f}

"""
        
        # Resumen consolidado
        accept_count = sum(1 for v in self.veredictos.values() if v['verdict'] == 'ACCEPT')
        review_count = sum(1 for v in self.veredictos.values() if v['verdict'] == 'REVIEW')
        reject_count = sum(1 for v in self.veredictos.values() if v['verdict'] == 'REJECT')
        
        changelog_content += f"""### Resumen consolidado
- **Total símbolos**: {len(self.symbols)}
- **ACCEPT**: {accept_count}
- **REVIEW**: {review_count}
- **REJECT**: {reject_count}

### Artefactos generados
```
runs/{self.run_timestamp}/_costed/
├── <SYMBOL>/
│   ├── trades_enriched_costed.csv
│   ├── session_summary_net.csv
│   ├── grid_resultados_net.csv
│   └── veredicto.json
└── run_metadata_update.json
```

### Logs estructurados
- COST_MODEL_APPLIED: {len(self.symbols)} símbolos procesados
- METRICS_NET_COMPUTED: Métricas netas calculadas por símbolo
- VERDICT_ISSUED: {accept_count} ACCEPT, {review_count} REVIEW, {reject_count} REJECT

---
**Etiqueta**: Fase 2 — Capa de costos y veredictos operativos
"""
        
        with open(changelog_file, 'w', encoding='utf-8') as f:
            f.write(changelog_content)
        
        logger.info(f"📋 Changelog costed generado: {changelog_file}")
    
    def actualizar_run_metadata(self):
        """Actualiza run_metadata con modelo de costos aplicado."""
        if self.simulacion:
            logger.info("🎭 SIMULACION: actualizar run_metadata")
            return
        
        metadata_update = {
            'timestamp_fase2': datetime.now(UTC).isoformat(),
            'model_costos_aplicado': True,
            'fee_pct': self.costo_config.fee_pct,
            'slippage_pct': self.costo_config.slippage_pct,
            'script_hash': self._get_script_hash(),
            'veredictos_summary': {
                'accept': sum(1 for v in self.veredictos.values() if v['verdict'] == 'ACCEPT'),
                'review': sum(1 for v in self.veredictos.values() if v['verdict'] == 'REVIEW'),
                'reject': sum(1 for v in self.veredictos.values() if v['verdict'] == 'REJECT')
            }
        }
        
        metadata_file = self.costed_dir / "run_metadata_update.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata_update, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📊 Run metadata actualizado")
    
    def _get_script_hash(self) -> str:
        """Calcula hash SHA-256 de este script."""
        try:
            with open(__file__, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except:
            return "unknown"
    
    def notificar_veredictos(self):
        """Emite notificación si hay REJECT o REVIEW."""
        rejects = [s for s, v in self.veredictos.items() if v['verdict'] == 'REJECT']
        reviews = [s for s, v in self.veredictos.items() if v['verdict'] == 'REVIEW']
        
        if rejects or reviews:
            message = f"🚨 FASE 2 ALERT - Run {self.run_timestamp}\n"
            if rejects:
                message += f"❌ REJECT: {', '.join(rejects)}\n"
            if reviews:
                message += f"⚠️ REVIEW: {', '.join(reviews)}\n"
            
            logger.warning(message)
            # TODO: Integrar con Slack/Email si está configurado
    
    def ejecutar_fase2(self) -> bool:
        """Ejecuta Fase 2 completa."""
        logger.info("🔄 === INICIANDO FASE 2 INSTITUCIONAL ===")
        
        try:
            # 1. Detectar símbolos
            self.symbols = self.detectar_simbolos_disponibles()
            if not self.symbols:
                logger.error("❌ No se encontraron símbolos con artefactos Fase 1")
                return False
            
            # 2. Procesar cada símbolo
            for symbol in self.symbols:
                logger.info(f"🔧 Procesando {symbol}...")
                
                # Cargar run base
                params_frozen, df_trades = self.cargar_run_base(symbol)
                if df_trades is None:
                    logger.warning(f"⚠️ Saltando {symbol}: sin datos de trades")
                    continue
                
                # Validar columnas mínimas
                valid, derivable = self.validar_columnas_minimas(df_trades, symbol)
                if not valid:
                    logger.error(f"❌ Saltando {symbol}: validación de columnas falló")
                    continue
                
                # Derivar columnas faltantes
                df_trades_costed = self.derivar_columnas_faltantes(df_trades, symbol, params_frozen)
                
                # Calcular métricas core
                metrics = self.compute_core_metrics(df_trades_costed, symbol)
                
                # Aplicar filtros de robustez
                verdict, reason = self.aplicar_filtros_robustez(metrics, symbol)
                
                # Crear veredicto
                veredicto = {
                    'symbol': symbol,
                    'pf_net': metrics['pf_net'],
                    'expectancy_net': metrics['expectancy_net'],
                    'winrate_net': metrics['net_winrate'],
                    'max_dd_net': metrics['max_dd_net'],
                    'verdict': verdict,
                    'reason': reason,
                    'timestamp': datetime.now(UTC).isoformat()
                }
                
                self.veredictos[symbol] = veredicto
                self.resultados_por_simbolo[symbol] = {
                    'trades_costed': df_trades_costed,
                    'metrics': metrics,
                    'veredicto': veredicto
                }
                
                # Persistir artefactos
                self.persistir_artefactos_costed(symbol, df_trades_costed, metrics, veredicto)
                
                # Log estructurado
                logger.info(f"✅ COST_MODEL_APPLIED: {symbol}")
                logger.info(f"📊 METRICS_NET_COMPUTED: {symbol}")
                logger.info(f"⚖️ VERDICT_ISSUED: {symbol} = {verdict}")
            
            # 3. Generar changelog costed
            self.generar_changelog_costed()
            
            # 4. Actualizar run metadata
            self.actualizar_run_metadata()
            
            # 5. Notificar veredictos
            self.notificar_veredictos()
            
            # Resumen final
            logger.info("🎯 === FASE 2 COMPLETADA ===")
            logger.info(f"📊 Símbolos procesados: {len(self.symbols)}")
            for verdict_type in ['ACCEPT', 'REVIEW', 'REJECT']:
                count = sum(1 for v in self.veredictos.values() if v['verdict'] == verdict_type)
                logger.info(f"⚖️ {verdict_type}: {count}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en Fase 2: {e}")
            return False


def parse_args():
    """Parse argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Fase 2 Institucional - Modelo de costos y veredictos operativos"
    )
    
    parser.add_argument("--run", required=True, help="Timestamp del run de Fase 1")
    parser.add_argument("--simulacion", action="store_true", help="Modo simulación (sin persistencia)")
    parser.add_argument("--force", action="store_true", help="Sobreescribir artefactos existentes")
    
    return parser.parse_args()


def main():
    """Función principal."""
    args = parse_args()
    
    print("🔄 Bot MCP - Fase 2 Institucional")
    print("=" * 50)
    print(f"Run: {args.run}")
    print(f"Modo simulación: {args.simulacion}")
    print("=" * 50)
    
    try:
        executor = Fase2InstitucionalExecutor(args.run, simulacion=args.simulacion)
        success = executor.ejecutar_fase2()
        
        if success:
            print("\n✅ FASE 2 COMPLETADA EXITOSAMENTE")
            return 0
        else:
            print("\n❌ FASE 2 FALLÓ")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ INTERRUPCIÓN: Ejecución cancelada por usuario")
        return 130
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")
        logger.error(f"Error crítico: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())