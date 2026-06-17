#!/usr/bin/env python3
"""
Fase 1 Institucional - Bot MCP con persistencia completa y capa de costos
========================================================================

Ejecuta el flujo institucional completo con trazabilidad y auditoría modular.
"""

import os
import sys
import json
import hashlib
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import yaml

# Añadir src al path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Imports del proyecto
from src.core.backtesting import configure_from_institucional, backtesting_legacy
from src.pipeline.carga_un_simbolo_combinado import cargar_y_combinar_datos
from src.core.utilidades import limpiar_ohlcv

# Configuración
MASTER_FILE = "data/historiales/historial_trading_maestro_15m.csv"
INSTITUCIONAL_YAML = "config/institucional.yaml"
METRICS_VERSION = "1.0.0"
MOTOR_VERSION = "Beta A2"

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fase1_institucional")


class Fase1InstitucionalExecutor:
    """Ejecutor de Fase 1 institucional con persistencia completa."""
    
    def __init__(self):
        self.timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path(f"runs/{self.timestamp}")
        self.logs_dir = self.run_dir / "logs"
        self.changelogs_dir = Path("changelogs")
        
        # Setup directorios
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.changelogs_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging a archivo
        log_file = self.logs_dir / f"fase1_{self.timestamp}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)
        
        logger.info(f"🚀 Fase 1 institucional iniciada - Run: {self.timestamp}")
        logger.info(f"📁 Directorio: {self.run_dir}")
        
        self.config_yaml = {}
        self.config_hash = ""
        self.symbols_activos = []
        self.resultados_por_simbolo = {}
        
    def qa_maestro(self) -> bool:
        """Gate QA del archivo maestro."""
        logger.info("🔍 Ejecutando QA maestro...")
        
        if not os.path.exists(MASTER_FILE):
            logger.error(f"❌ Archivo maestro no encontrado: {MASTER_FILE}")
            return False
        
        try:
            df = pd.read_csv(MASTER_FILE)
            logger.info(f"📊 Archivo maestro: {len(df)} filas")
            
            # Verificar columnas requeridas
            required_cols = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                logger.error(f"❌ Columnas faltantes: {missing_cols}")
                return False
            
            # Verificar símbolos
            symbols_available = df["symbol"].unique()
            logger.info(f"🔍 Símbolos disponibles: {list(symbols_available)}")
            
            required_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
            missing_symbols = [s for s in required_symbols if s not in symbols_available]
            if missing_symbols:
                logger.warning(f"⚠️ Símbolos faltantes: {missing_symbols}")
            
            logger.info("✅ QA maestro aprobada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en QA maestro: {e}")
            return False
    
    def cargar_configuracion_institucional(self) -> bool:
        """Carga config/institucional.yaml como fuente única de verdad."""
        logger.info("📋 Cargando configuración institucional...")
        
        try:
            with open(INSTITUCIONAL_YAML, "r", encoding="utf-8") as f:
                self.config_yaml = yaml.safe_load(f)
            
            # Calcular hash SHA-256
            yaml_content = yaml.dump(self.config_yaml, sort_keys=True)
            self.config_hash = hashlib.sha256(yaml_content.encode("utf-8")).hexdigest()
            
            # Identificar símbolos activos
            symbols_config = self.config_yaml.get("symbols", {})
            self.symbols_activos = [
                symbol for symbol, config in symbols_config.items()
                if config.get("enabled", False)
            ]
            
            logger.info(f"🔧 Configuración cargada - Hash: {self.config_hash[:12]}...")
            logger.info(f"📈 Símbolos activos: {self.symbols_activos}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cargando configuración: {e}")
            return False
    
    def congelar_parametros_por_simbolo(self, symbol: str) -> Dict[str, Any]:
        """Congela parámetros por símbolo con persistencia completa."""
        logger.info(f"🧊 Congelando parámetros para {symbol}...")
        
        symbol_dir = self.run_dir / symbol
        symbol_dir.mkdir(exist_ok=True)
        
        # Configurar Beta A2 para el símbolo
        cfg = configure_from_institucional(INSTITUCIONAL_YAML, symbol=symbol, perfil="conservador")
        
        # Extraer parámetros congelados
        params_frozen = {
            "timestamp": self.timestamp,
            "symbol": symbol,
            "motor_version": MOTOR_VERSION,
            "metrics_version": METRICS_VERSION,
            "institucional_hash": self.config_hash,
            "perfil_tp_sl": cfg.perfil_tp_sl,
            "configuracion_beta_a2": {
                "strict_proximity_bars": cfg.strict_proximity_bars,
                "min_mfe_mae_ratio": cfg.min_mfe_mae_ratio,
                "min_atr_pct": cfg.min_atr_pct,
                "min_bbw_pct": cfg.min_bbw_pct,
                "fee_bps": cfg.fee_bps,
                "slippage_bps": cfg.slippage_bps,
                "tp_sl_by_regime": cfg.tp_sl_by_regime,
                "guardrails": cfg.guardrails
            }
        }
        
        # Guardar params_frozen.json
        params_file = symbol_dir / "params_frozen.json"
        with open(params_file, "w", encoding="utf-8") as f:
            json.dump(params_frozen, f, indent=2, ensure_ascii=False)
        
        # Guardar copia del YAML institucional
        yaml_copy = symbol_dir / "institucional.yaml"
        with open(yaml_copy, "w", encoding="utf-8") as f:
            yaml.dump(self.config_yaml, f, default_flow_style=False, allow_unicode=True)
        
        # Guardar hash
        hash_file = symbol_dir / "institucional_hash.txt"
        with open(hash_file, "w", encoding="utf-8") as f:
            f.write(f"{self.config_hash}\n")
            f.write(f"Timestamp: {self.timestamp}\n")
            f.write(f"Symbol: {symbol}\n")
        
        logger.info(f"✅ Parámetros congelados para {symbol}")
        return params_frozen
    
    def ejecutar_backtesting_beta_a2(self, symbol: str, params_frozen: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta motor Beta A2 con configuración congelada."""
        logger.info(f"⚡ Ejecutando backtesting Beta A2 para {symbol}...")
        
        try:
            # Configurar motor
            cfg = configure_from_institucional(INSTITUCIONAL_YAML, symbol=symbol, perfil="conservador")
            
            # Cargar datos (6 meses por defecto)
            df = cargar_y_combinar_datos(MASTER_FILE, symbol=symbol, meses=6)
            df_clean = limpiar_ohlcv(df)
            
            if df_clean.empty:
                logger.warning(f"⚠️ Sin datos para {symbol}")
                return {"error": "Sin datos disponibles"}
            
            logger.info(f"📊 Datos cargados para {symbol}: {len(df_clean)} filas")
            
            # Ejecutar backtesting
            result = backtesting_legacy(df_clean, config_obj=cfg)
            
            if isinstance(result, tuple) and len(result) >= 2:
                resultados, resumen = result[0], result[1]
                trades_enriched = result[2] if len(result) > 2 else []
            else:
                raise ValueError("Resultado de backtesting inesperado")
            
            # Enriquecer trades con capa de costos
            trades_enriquecidos = self.enriquecer_trades(trades_enriched, cfg)
            
            # Calcular métricas
            metricas = self.calcular_metricas_completas(trades_enriquecidos, cfg)
            
            resultado = {
                "symbol": symbol,
                "timestamp": self.timestamp,
                "trades_count": len(trades_enriquecidos),
                "datos_filas": len(df_clean),
                "trades_enriquecidos": trades_enriquecidos,
                "metricas": metricas,
                "resumen_legacy": resumen,
                "configuracion_usada": {
                    "motor_version": MOTOR_VERSION,
                    "metrics_version": METRICS_VERSION,
                    "hash": self.config_hash[:12]
                }
            }
            
            logger.info(f"✅ Backtesting completado para {symbol}: {len(trades_enriquecidos)} trades")
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error en backtesting {symbol}: {e}")
            return {"error": str(e)}
    
    def enriquecer_trades(self, trades_raw: List[Dict], cfg) -> List[Dict[str, Any]]:
        """Enriquece trades con capa de costos completa."""
        trades_enriquecidos = []
        
        for trade in trades_raw:
            # Datos básicos
            entry_price = trade.get("entry_price", 0.0)
            exit_price = trade.get("exit_price", 0.0)
            side = trade.get("side", "long")
            
            # Cálculos de PnL
            if side == "long":
                gross_pnl = exit_price - entry_price
            else:
                gross_pnl = entry_price - exit_price
            
            pnl_pct = (gross_pnl / entry_price * 100) if entry_price > 0 else 0.0
            
            # Costos
            notional = entry_price  # Simplificado: 1 unidad
            commission_entry = notional * (cfg.fee_bps / 10000.0)
            commission_exit = notional * (cfg.fee_bps / 10000.0)
            commission_total = commission_entry + commission_exit
            
            slippage_cost = notional * (cfg.slippage_bps / 10000.0) * 2  # entry + exit
            
            net_pnl = gross_pnl - commission_total - slippage_cost
            
            # Risk metrics
            risk_abs = trade.get("risk_abs", abs(gross_pnl) * 0.5)  # Fallback
            r_multiple = gross_pnl / risk_abs if risk_abs > 0 else 0.0
            
            mfe = trade.get("mfe_abs", max(0, gross_pnl))
            mae = trade.get("mae_abs", max(0, -gross_pnl))
            mfe_r = mfe / risk_abs if risk_abs > 0 else 0.0
            mae_r = mae / risk_abs if risk_abs > 0 else 0.0
            
            trade_enriquecido = {
                "timestamp": trade.get("exit_time", trade.get("entry_time", self.timestamp)),
                "symbol": cfg.symbol,
                "side": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "pnl_pct": pnl_pct,
                "r_multiple": r_multiple,
                "risk_abs": risk_abs,
                "mfe_R": mfe_r,
                "mae_R": mae_r,
                "notional": notional,
                "commission_paid": commission_total,
                "slippage_cost": slippage_cost,
                "regime": trade.get("market_regime", "neutral"),
                "duration_bars": trade.get("exit_index", 0) - trade.get("entry_index", 0)
            }
            
            trades_enriquecidos.append(trade_enriquecido)
        
        return trades_enriquecidos
    
    def calcular_metricas_completas(self, trades: List[Dict], cfg) -> Dict[str, Any]:
        """Calcula métricas brutas y netas completas."""
        if not trades:
            return {"error": "No hay trades para calcular métricas"}
        
        df_trades = pd.DataFrame(trades)
        
        # Métricas básicas
        total_trades = len(trades)
        winning_trades = (df_trades["net_pnl"] > 0).sum()
        losing_trades = (df_trades["net_pnl"] <= 0).sum()
        winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # PnL neto
        total_gross_pnl = df_trades["gross_pnl"].sum()
        total_net_pnl = df_trades["net_pnl"].sum()
        total_commissions = df_trades["commission_paid"].sum()
        total_slippage = df_trades["slippage_cost"].sum()
        
        # Profit Factor
        gross_wins = df_trades[df_trades["gross_pnl"] > 0]["gross_pnl"].sum()
        gross_losses = abs(df_trades[df_trades["gross_pnl"] <= 0]["gross_pnl"].sum())
        profit_factor_gross = gross_wins / gross_losses if gross_losses > 0 else float('inf')
        
        net_wins = df_trades[df_trades["net_pnl"] > 0]["net_pnl"].sum()
        net_losses = abs(df_trades[df_trades["net_pnl"] <= 0]["net_pnl"].sum())
        profit_factor_net = net_wins / net_losses if net_losses > 0 else float('inf')
        
        # Expectancy
        expectancy_gross = df_trades["gross_pnl"].mean()
        expectancy_net = df_trades["net_pnl"].mean()
        
        # Drawdown (simplificado)
        equity_curve = df_trades["net_pnl"].cumsum()
        running_max = equity_curve.cummax()
        drawdown = equity_curve - running_max
        max_drawdown = drawdown.min()
        
        # Fees como porcentaje
        total_notional = df_trades["notional"].sum()
        fees_pct = (total_commissions / total_notional * 100) if total_notional > 0 else 0.0
        
        metricas = {
            "total_trades": total_trades,
            "winning_trades": int(winning_trades),
            "losing_trades": int(losing_trades),
            "winrate_pct": round(winrate, 2),
            "gross_pnl": round(total_gross_pnl, 2),
            "net_pnl": round(total_net_pnl, 2),
            "total_commissions": round(total_commissions, 2),
            "total_slippage": round(total_slippage, 2),
            "profit_factor_gross": round(profit_factor_gross, 3),
            "profit_factor_net": round(profit_factor_net, 3),
            "expectancy_gross": round(expectancy_gross, 4),
            "expectancy_net": round(expectancy_net, 4),
            "max_drawdown": round(max_drawdown, 2),
            "fees_pct": round(fees_pct, 3),
            "avg_trade_duration": round(df_trades["duration_bars"].mean(), 1),
            "r_multiple_avg": round(df_trades["r_multiple"].mean(), 2),
            "mfe_avg": round(df_trades["mfe_R"].mean(), 2),
            "mae_avg": round(df_trades["mae_R"].mean(), 2)
        }
        
        return metricas
    
    def guardar_artefactos_por_simbolo(self, symbol: str, resultado: Dict[str, Any]):
        """Guarda todos los artefactos por símbolo."""
        logger.info(f"💾 Guardando artefactos para {symbol}...")
        
        symbol_dir = self.run_dir / symbol
        
        # trades_enriquecidos.csv
        if "trades_enriquecidos" in resultado and resultado["trades_enriquecidos"]:
            trades_file = symbol_dir / "trades_enriquecidos.csv"
            df_trades = pd.DataFrame(resultado["trades_enriquecidos"])
            df_trades.to_csv(trades_file, index=False)
            logger.info(f"📊 Guardado: {trades_file}")
        
        # session_summary.csv
        if "metricas" in resultado:
            summary_file = symbol_dir / "session_summary.csv"
            metricas = resultado["metricas"]
            df_summary = pd.DataFrame([{
                "symbol": symbol,
                "timestamp": self.timestamp,
                "motor_version": MOTOR_VERSION,
                "metrics_version": METRICS_VERSION,
                **metricas
            }])
            df_summary.to_csv(summary_file, index=False)
            logger.info(f"📈 Guardado: {summary_file}")
        
        # grid_resultados.csv (formato legacy)
        grid_file = symbol_dir / "grid_resultados.csv"
        grid_data = {
            "symbol": symbol,
            "timestamp": self.timestamp,
            "total_trades": resultado.get("trades_count", 0),
            "winrate": resultado.get("metricas", {}).get("winrate_pct", 0),
            "profit_factor": resultado.get("metricas", {}).get("profit_factor_net", 0),
            "net_pnl": resultado.get("metricas", {}).get("net_pnl", 0),
            "max_drawdown": resultado.get("metricas", {}).get("max_drawdown", 0),
            "fees_pct": resultado.get("metricas", {}).get("fees_pct", 0)
        }
        pd.DataFrame([grid_data]).to_csv(grid_file, index=False)
        logger.info(f"🎯 Guardado: {grid_file}")
    
    def generar_changelog_tecnico(self):
        """Genera changelog técnico consolidado."""
        logger.info("📝 Generando changelog técnico...")
        
        changelog_file = self.changelogs_dir / f"{self.timestamp}.md"
        
        # Calcular métricas consolidadas
        total_trades = sum(r.get("trades_count", 0) for r in self.resultados_por_simbolo.values())
        symbols_procesados = len([s for s in self.symbols_activos if s in self.resultados_por_simbolo])
        
        avg_winrate = sum(
            r.get("metricas", {}).get("winrate_pct", 0) 
            for r in self.resultados_por_simbolo.values()
        ) / len(self.resultados_por_simbolo) if self.resultados_por_simbolo else 0
        
        total_net_pnl = sum(
            r.get("metricas", {}).get("net_pnl", 0) 
            for r in self.resultados_por_simbolo.values()
        )
        
        changelog_content = f"""# Changelog Técnico - Fase 1 Institucional
**Timestamp:** {self.timestamp}  
**Etiqueta:** Fase 1 — Persistencia institucional y capa de costos  
**Motor:** {MOTOR_VERSION}  
**METRICS_VERSION:** {METRICS_VERSION}  

## Configuración
- **Hash YAML:** `{self.config_hash}`
- **Fuente:** `{INSTITUCIONAL_YAML}`
- **Símbolos procesados:** {symbols_procesados}/{len(self.symbols_activos)}

## Métricas Consolidadas
- **Total trades:** {total_trades}
- **Winrate promedio:** {avg_winrate:.1f}%
- **PnL neto total:** {total_net_pnl:.2f}

## Resultados por Símbolo
"""
        
        for symbol in self.symbols_activos:
            resultado = self.resultados_por_simbolo.get(symbol, {})
            if "error" in resultado:
                changelog_content += f"- **{symbol}:** ❌ {resultado['error']}\n"
            else:
                metricas = resultado.get("metricas", {})
                changelog_content += f"""- **{symbol}:** ✅ {resultado.get('trades_count', 0)} trades, WR: {metricas.get('winrate_pct', 0):.1f}%, PnL: {metricas.get('net_pnl', 0):.2f}
"""
        
        changelog_content += f"""
## Veredicto Preliminar
Fase 1 completada con persistencia total. Configuración congelada y trazabilidad garantizada.

## Artefactos Generados
- `runs/{self.timestamp}/` - Directorio de ejecución
- `params_frozen.json` por símbolo
- `trades_enriquecidos.csv` con capa de costos
- `session_summary.csv` con métricas completas
- `logs/` técnicos de ejecución

---
**Próximo paso:** Validación longitudinal y aplicación de filtros de producción.
"""
        
        with open(changelog_file, "w", encoding="utf-8") as f:
            f.write(changelog_content)
        
        logger.info(f"📋 Changelog guardado: {changelog_file}")
    
    def ejecutar_fase_1(self) -> bool:
        """Ejecuta la Fase 1 institucional completa."""
        logger.info("🎯 INICIANDO FASE 1 INSTITUCIONAL")
        
        # 1. QA maestro
        if not self.qa_maestro():
            logger.error("❌ QA maestro falló - deteniendo ejecución")
            return False
        
        # 2. Cargar configuración institucional
        if not self.cargar_configuracion_institucional():
            logger.error("❌ Error cargando configuración - deteniendo ejecución")
            return False
        
        # 3. Procesar cada símbolo activo
        for symbol in self.symbols_activos:
            logger.info(f"🔄 Procesando {symbol}...")
            
            # Congelar parámetros
            params_frozen = self.congelar_parametros_por_simbolo(symbol)
            
            # Ejecutar backtesting Beta A2
            resultado = self.ejecutar_backtesting_beta_a2(symbol, params_frozen)
            self.resultados_por_simbolo[symbol] = resultado
            
            # Guardar artefactos
            if "error" not in resultado:
                self.guardar_artefactos_por_simbolo(symbol, resultado)
        
        # 4. Generar changelog técnico
        self.generar_changelog_tecnico()
        
        # 5. Log final
        total_exitosos = len([r for r in self.resultados_por_simbolo.values() if "error" not in r])
        logger.info(f"🎯 FASE 1 COMPLETADA: {total_exitosos}/{len(self.symbols_activos)} símbolos exitosos")
        logger.info(f"📁 Artefactos en: {self.run_dir}")
        
        return total_exitosos > 0


def main():
    """Función principal."""
    print("🚀 Bot MCP - Fase 1 Institucional")
    print("=" * 50)
    
    executor = Fase1InstitucionalExecutor()
    
    try:
        success = executor.ejecutar_fase_1()
        
        if success:
            print("\n✅ FASE 1 INSTITUCIONAL COMPLETADA EXITOSAMENTE")
            print(f"📁 Artefactos guardados en: {executor.run_dir}")
            return 0
        else:
            print("\n❌ FASE 1 FALLÓ")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️ Ejecución interrumpida por usuario")
        return 130
    except Exception as e:
        logger.error(f"❌ Error crítico en Fase 1: {e}")
        print(f"\n❌ Error crítico: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())