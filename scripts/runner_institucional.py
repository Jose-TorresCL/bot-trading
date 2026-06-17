#!/usr/bin/env python3#!/usr/bin/env python3#!/usr/bin/env python3#!/usr/bin/env python3

"""

Runner Institucional Unificado - Beta A2 Integration# -*- coding: utf-8 -*-

Runner para integracion de Beta A2 con configuracion institucional YAML.

""""""# -*- coding: utf-8 -*-# -*- coding: utf-8 -*-



import osRunner Institucional Unificado - Beta A2 Integration

import sys

import argparse""""""

import logging

import jsonOrquestador completo del flujo institucional:

from typing import List

from pathlib import PathQA -> Backtesting -> Portfolio -> ReportingRunner Institucional Unificado - Beta A2 IntegrationRunner Institucional Unificado - Beta A2 Integration

import pandas as pd

from datetime import datetime



# Anadir src al pathIntegra logica Beta A2 con TP/SL dinamico y guardrails institucionales.========================================================================================================

project_root = Path(__file__).parent.parent

sys.path.insert(0, str(project_root))Compatible con configuracion YAML y testing automatizado.



# Imports del proyecto

try:

    from src.core.backtesting import BTConfig, configure_from_institucional, backtesting_legacyUso:

    from src.pipeline.carga_un_simbolo_combinado import cargar_y_combinar_datos

    from src.core.utilidades import limpiar_ohlcv    python scripts/runner_institucional.py --symbols BTCUSDT,ETHUSDT --months 6Orquestador completo del flujo institucional:Orquestador completo del flujo institucional:

except ImportError as e:

    print(f"Error importing project modules: {e}")    python scripts/runner_institucional.py --qa-only --symbols BTCUSDT

    sys.exit(1)

    python scripts/runner_institucional.py --backtesting-onlyQA → Backtesting → Portfolio → ReportingQA → Fase1/Fase2 → backtesting → portfolio → reporting

# Logger

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')"""

logger = logging.getLogger("runner_institucional")



# Defaults

DEFAULT_OUTPUT_DIR = "data/backtesting/institutional"import os

DEFAULT_CONFIG_PATH = "config/institucional.yaml"

DEFAULT_MASTER_FILE = "data/historiales/historial_trading_maestro_15m.csv"import sysIntegra lógica Beta A2 con TP/SL dinámico y guardrails institucionales.Integra lógica Beta A2 con TP/SL dinámico y guardrails institucionales.



import argparse

def parse_args():

    """Parse argumentos de linea de comandos."""import loggingCompatible con configuración YAML y testing automatizado.Compatible con configuración YAML y testing automatizado.

    parser = argparse.ArgumentParser(

        description="Runner Institucional Unificado con integracion Beta A2"import json

    )

    from typing import Dict, List, Any

    # Configuracion

    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)from pathlib import Path

    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)

    parser.add_argument("--master-file", default=DEFAULT_MASTER_FILE)import pandas as pdUso:Uso:

    

    # Parametrosfrom datetime import datetime

    parser.add_argument("--symbols", required=True)

    parser.add_argument("--months", type=int, default=6)    python scripts/runner_institucional.py --symbols BTCUSDT,ETHUSDT --months 6    python scripts/runner_institucional.py --config config/institucional.yaml --symbols BTCUSDT,ETHUSDT --months 6

    parser.add_argument("--perfil", choices=["conservador", "agresivo"], default="conservador")

    # Añadir src al path

    # Fases

    parser.add_argument("--qa-only", action="store_true")project_root = Path(__file__).parent.parent    python scripts/runner_institucional.py --qa-only --symbols BTCUSDT    python scripts/runner_institucional.py --qa-only --symbols BTCUSDT

    parser.add_argument("--backtesting-only", action="store_true")

    parser.add_argument("--skip-qa", action="store_true")sys.path.insert(0, str(project_root))

    

    # Debug    python scripts/runner_institucional.py --backtesting-only    python scripts/runner_institucional.py --backtesting-only --config config/institucional.yaml

    parser.add_argument("--verbose", "-v", action="store_true")

    # Imports del proyecto

    return parser.parse_args()

try:""""""



def run_qa_phase(symbols: List[str], master_file: str, output_dir: str) -> bool:    from src.core.backtesting import BTConfig, configure_from_institucional, backtesting_legacy

    """Ejecuta fase QA."""

    logger.info("=== FASE QA ===")    from src.pipeline.carga_un_simbolo_combinado import cargar_y_combinar_datos

    logger.info(f"Validando {len(symbols)} simbolos")

        from src.core.utilidades import limpiar_ohlcv

    # Validar archivo maestro

    if not os.path.exists(master_file):except ImportError as e:import osimport os

        logger.error("Archivo maestro no encontrado")

        return False    print(f"Error importing project modules: {e}")

    

    try:    sys.exit(1)import sysimport sys

        df_master = pd.read_csv(master_file)

        logger.info(f"Archivo maestro: {len(df_master)} filas")

    except Exception as e:

        logger.error(f"Error leyendo maestro: {e}")# Loggerimport argparseimport argparse

        return False

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Validar simbolos

    import logging
    logger = logging.getLogger("runner_institucional")
    validated = 0

    for symbol in symbols:

        try:

            df_symbol = cargar_y_combinar_datos(master_file, symbol=symbol)

            df_clean = limpiar_ohlcv(df_symbol)

            

            if df_clean.empty:

                logger.warning(f"Sin datos para {symbol}")

                continue

            

            completeness = len(df_clean) / len(df_symbol) if len(df_symbol) > 0 else 0

            logger.info(f"OK {symbol}: {len(df_clean)} filas ({completeness:.1%})")

            validated += 1

        

        except Exception as e:

            logger.error(f"Error {symbol}: {e}")

    def parse_args() -> argparse.Namespace:import pandas as pdimport pandas as pd

    if validated == 0:

        logger.error("Sin simbolos validados")    """Parse argumentos de linea de comandos."""

        return False

        parser = argparse.ArgumentParser(from datetime import datetimefrom datetime import datetime, timedelta

    logger.info(f"QA APROBADA - {validated}/{len(symbols)} simbolos")

    return True        description="Runner Institucional Unificado con integracion Beta A2"



    )

def run_backtesting_phase(symbols: List[str], months: int, perfil: str, 

                         config_path: str, master_file: str, output_dir: str) -> bool:    

    """Ejecuta backtesting con Beta A2."""

    logger.info("=== FASE BACKTESTING ===")    # Configuracion# Añadir src al path# Añadir src al path

    logger.info(f"Simbolos: {symbols}, Meses: {months}, Perfil: {perfil}")

        parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Ruta al archivo de configuracion YAML")

    total_trades = 0

    total_pnl = 0.0    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directorio de salida")project_root = Path(__file__).parent.parentproject_root = Path(__file__).parent.parent

    errors = 0

        parser.add_argument("--master-file", default=DEFAULT_MASTER_FILE, help="Archivo maestro de datos")

    for symbol in symbols:

        logger.info(f"Procesando {symbol}...")    sys.path.insert(0, str(project_root))sys.path.insert(0, str(project_root))

        

        try:    # Parametros de ejecucion

            # Configurar Beta A2

            cfg = configure_from_institucional(config_path, symbol=symbol, perfil=perfil)    parser.add_argument("--symbols", required=True, help="Simbolos separados por coma (ej: BTCUSDT,ETHUSDT)")

            

            # Cargar datos    parser.add_argument("--months", type=int, default=6, help="Meses de historia para backtesting")

            df = cargar_y_combinar_datos(master_file, symbol=symbol, meses=months)

            df_clean = limpiar_ohlcv(df)    parser.add_argument("--perfil", choices=["conservador", "agresivo"], default="conservador", help="Perfil TP/SL")# Imports del proyecto# Imports del proyecto

            

            if df_clean.empty:    

                logger.warning(f"Sin datos para {symbol}")

                continue    # Fases de ejecuciontry:try:

            

            # Ejecutar backtesting    parser.add_argument("--qa-only", action="store_true", help="Solo ejecutar fase QA")

            result = backtesting_legacy(df_clean, config_obj=cfg)

                parser.add_argument("--backtesting-only", action="store_true", help="Solo ejecutar fase backtesting")    from src.core.backtesting import BTConfig, configure_from_institucional, backtesting_legacy    from src.core.backtesting import BTConfig, configure_from_institucional, backtesting_legacy

            if isinstance(result, tuple) and len(result) >= 2:

                resultados, resumen = result[0], result[1]    parser.add_argument("--skip-qa", action="store_true", help="Saltar validacion QA")

                trades_enriched = result[2] if len(result) > 2 else []

            else:        from src.pipeline.carga_un_simbolo_combinado import cargar_y_combinar_datos    from src.pipeline.carga_un_simbolo_combinado import cargar_y_combinar_datos

                raise ValueError("Resultado inesperado")

                # Debug

            # Metricas

            trades_count = len(trades_enriched) if trades_enriched else 0    parser.add_argument("--verbose", "-v", action="store_true", help="Logging verboso")    from src.core.utilidades import limpiar_ohlcv    from src.core.utilidades import limpiar_ohlcv

            pnl_net = resumen.get("pnl_net", 0.0) if isinstance(resumen, dict) else 0.0

                

            total_trades += trades_count

            total_pnl += pnl_net    return parser.parse_args()except ImportError as e:    from src.config_loader import load_config, InstitucionalConfig

            

            # Guardar resultados

            symbol_dir = os.path.join(output_dir, symbol)

            os.makedirs(symbol_dir, exist_ok=True)    print(f"Error importing project modules: {e}")except ImportError as e:

            

            if trades_enriched:def run_qa_phase(symbols: List[str], master_file: str, output_dir: str) -> bool:

                trades_file = os.path.join(symbol_dir, f"trades_{symbol}_{perfil}.csv")

                pd.DataFrame(trades_enriched).to_csv(trades_file, index=False)    """Ejecuta fase QA y retorna True si pasa."""    sys.exit(1)    print(f"Error importing project modules: {e}")

            

            resumen_file = os.path.join(symbol_dir, f"resumen_{symbol}_{perfil}.json")    logger.info(f"=== FASE QA ===")

            with open(resumen_file, "w", encoding="utf-8") as f:

                json.dump(resumen, f, indent=2, ensure_ascii=False)    logger.info(f"Validando {len(symbols)} simbolos: {', '.join(symbols)}")    sys.exit(1)

            

            logger.info(f"OK {symbol}: {trades_count} trades, PnL: {pnl_net:.2f}")    

        

        except Exception as e:    qa_results = {# Logger

            logger.error(f"Error {symbol}: {e}")

            errors += 1        "timestamp": datetime.now().isoformat(),

    

    # Guardar consolidado        "symbols_requested": symbols,logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')# Logger

    results = {

        "timestamp": datetime.now().isoformat(),        "symbols_validated": [],

        "symbols": symbols,

        "perfil": perfil,        "symbols_failed": [],logger = logging.getLogger("runner_institucional")logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        "total_trades": total_trades,

        "total_pnl": total_pnl,        "critical_errors": [],

        "errors": errors

    }        "warnings": []logger = logging.getLogger("runner_institucional")

    

    results_file = os.path.join(output_dir, f"backtesting_results_{perfil}.json")    }

    with open(results_file, "w", encoding="utf-8") as f:

        json.dump(results, f, indent=2, ensure_ascii=False)    # Defaults

    

    success = errors == 0 and total_trades > 0    # Validar archivo maestro

    

    if success:    if not os.path.exists(master_file):DEFAULT_OUTPUT_DIR = "data/backtesting/institutional"# Archivos de salida por defecto

        logger.info(f"BACKTESTING COMPLETADO - {total_trades} trades, PnL: {total_pnl:.2f}")

    else:        qa_results["critical_errors"].append(f"Archivo maestro no encontrado: {master_file}")

        logger.error("BACKTESTING CON ERRORES")

            logger.error("ERROR: Archivo maestro no encontrado")DEFAULT_CONFIG_PATH = "config/institucional.yaml"DEFAULT_OUTPUT_DIR = "data/backtesting/institutional"

    return success

        return False



def main():    DEFAULT_MASTER_FILE = "data/historiales/historial_trading_maestro_15m.csv"DEFAULT_CONFIG_PATH = "config/institucional.yaml"

    """Funcion principal."""

    args = parse_args()    try:

    

    if args.verbose:        df_master = pd.read_csv(master_file)DEFAULT_MASTER_FILE = "data/historiales/historial_trading_maestro_15m.csv"

        logging.getLogger().setLevel(logging.DEBUG)

            logger.info(f"Archivo maestro cargado: {len(df_master)} filas")

    # Parse simbolos

    symbols = [s.strip().upper() for s in args.symbols.split(",")]    except Exception as e:

    logger.info(f"Runner iniciado para {len(symbols)} simbolos: {symbols}")

            qa_results["critical_errors"].append(f"Error leyendo archivo maestro: {e}")

    # Crear directorio

    os.makedirs(args.output_dir, exist_ok=True)        logger.error(f"ERROR: Error leyendo archivo maestro: {e}")def parse_args() -> argparse.Namespace:

    

    success = True        return False

    

    try:        """Parse argumentos de línea de comandos."""class InstitucionalRunner:

        # Fase QA

        if not args.skip_qa and not args.backtesting_only:    # Validar datos por simbolo

            qa_success = run_qa_phase(symbols, args.master_file, args.output_dir)

            if not qa_success:    for symbol in symbols:    parser = argparse.ArgumentParser(    """Runner institucional con integración Beta A2 completa."""

                if args.qa_only:

                    return 1        try:

                else:

                    logger.error("QA fallo - deteniendo")            df_symbol = cargar_y_combinar_datos(master_file, symbol=symbol)        description="Runner Institucional Unificado con integración Beta A2",    

                    return 1

            else:            df_clean = limpiar_ohlcv(df_symbol)

                logger.info("QA aprobada")

                            formatter_class=argparse.RawDescriptionHelpFormatter    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH, output_dir: str = DEFAULT_OUTPUT_DIR):

        if args.qa_only:

            return 0            if df_clean.empty:

        

        # Fase Backtesting                qa_results["symbols_failed"].append(symbol)    )        self.config_path = config_path

        bt_success = run_backtesting_phase(

            symbols, args.months, args.perfil,                 qa_results["warnings"].append(f"Sin datos para {symbol}")

            args.config, args.master_file, args.output_dir

        )                logger.warning(f"ADVERTENCIA: Sin datos para {symbol}")            self.output_dir = output_dir

        

        if not bt_success:                continue

            success = False

                        # Configuración        self.config_data = {}

        # Reporte final

        final_report = {            completeness = len(df_clean) / len(df_symbol) if len(df_symbol) > 0 else 0

            "timestamp": datetime.now().isoformat(),

            "symbols": symbols,            if completeness < 0.9:    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Ruta al archivo de configuración YAML")        self.results = {}

            "months": args.months,

            "perfil": args.perfil,                qa_results["warnings"].append(f"Baja calidad de datos para {symbol}: {completeness:.1%}")

            "success": success

        }                logger.warning(f"ADVERTENCIA: Baja calidad para {symbol}: {completeness:.1%}")    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directorio de salida")        self.qa_results = {}

        

        report_file = os.path.join(args.output_dir, "final_report.json")            

        with open(report_file, "w", encoding="utf-8") as f:

            json.dump(final_report, f, indent=2, ensure_ascii=False)            qa_results["symbols_validated"].append(symbol)    parser.add_argument("--master-file", default=DEFAULT_MASTER_FILE, help="Archivo maestro de datos")        

        

        logger.info(f"COMPLETADO - Reporte: {report_file}")            logger.info(f"OK {symbol}: {len(df_clean)} filas limpias ({completeness:.1%})")

        

        return 0 if success else 1                    # Crear directorios de salida

    

    except Exception as e:        except Exception as e:

        logger.error(f"Error critico: {e}")

        return 1            qa_results["symbols_failed"].append(symbol)    # Parámetros de ejecución        os.makedirs(output_dir, exist_ok=True)



            qa_results["critical_errors"].append(f"Error procesando {symbol}: {e}")

if __name__ == "__main__":

    sys.exit(main())            logger.error(f"ERROR {symbol}: {e}")    parser.add_argument("--symbols", required=True, help="Símbolos separados por coma (ej: BTCUSDT,ETHUSDT)")        os.makedirs("logs", exist_ok=True)

    

    # Guardar reporte QA    parser.add_argument("--months", type=int, default=6, help="Meses de historia para backtesting")        

    os.makedirs(output_dir, exist_ok=True)

    qa_file = os.path.join(output_dir, "qa_report.json")    parser.add_argument("--perfil", choices=["conservador", "agresivo"], default="conservador", help="Perfil TP/SL")        # Setup logging

    with open(qa_file, "w", encoding="utf-8") as f:

        json.dump(qa_results, f, indent=2, ensure_ascii=False)            log_file = os.path.join("logs", f"runner_institucional_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    

    # Decision    # Fases de ejecución        file_handler = logging.FileHandler(log_file, encoding="utf-8")

    has_errors = len(qa_results["critical_errors"]) > 0

    validated_symbols = len(qa_results["symbols_validated"])    parser.add_argument("--qa-only", action="store_true", help="Solo ejecutar fase QA")        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    

    if has_errors:    parser.add_argument("--backtesting-only", action="store_true", help="Solo ejecutar fase backtesting")        logger.addHandler(file_handler)

        logger.error(f"ERROR: QA FALLIDA - Errores criticos")

        return False    parser.add_argument("--skip-qa", action="store_true", help="Saltar validación QA")        

    

    if validated_symbols == 0:            logger.info(f"Runner institucional iniciado - config: {config_path}, output: {output_dir}")

        logger.error("ERROR: QA FALLIDA - Sin simbolos validados")

        return False    # Debug    

    

    logger.info(f"OK: QA APROBADA - {validated_symbols}/{len(symbols)} simbolos validados")    parser.add_argument("--verbose", "-v", action="store_true", help="Logging verboso")    def load_institutional_config(self) -> bool:

    return True

            """Carga configuración institucional YAML."""



def run_backtesting_phase(symbols: List[str], months: int, perfil: str, config_path: str, master_file: str, output_dir: str) -> bool:    return parser.parse_args()        try:

    """Ejecuta fase backtesting con Beta A2."""

    logger.info(f"=== FASE BACKTESTING ===")            from src.core.backtesting import load_institucional_config

    logger.info(f"Simbolos: {symbols}, Meses: {months}, Perfil: {perfil}")

                self.config_data = load_institucional_config(self.config_path)

    results = {

        "timestamp": datetime.now().isoformat(),def run_qa_phase(symbols: List[str], master_file: str, output_dir: str) -> bool:            

        "symbols": symbols,

        "perfil_tp_sl": perfil,    """Ejecuta fase QA y retorna True si pasa."""            if not self.config_data:

        "results_by_symbol": {},

        "errors": []    logger.info(f"=== FASE QA ===")                logger.error(f"Configuración vacía en {self.config_path}")

    }

        logger.info(f"Validando {len(symbols)} símbolos: {', '.join(symbols)}")                return False

    total_trades = 0

    total_pnl = 0.0                

    

    for symbol in symbols:    qa_results = {            logger.info(f"Configuración institucional cargada: {len(self.config_data)} secciones")

        logger.info(f"Procesando {symbol}...")

                "timestamp": datetime.now().isoformat(),            return True

        try:

            # Configurar BTConfig con Beta A2        "symbols_requested": symbols,        

            cfg = configure_from_institucional(config_path, symbol=symbol, perfil=perfil)

                    "symbols_validated": [],        except Exception as e:

            # Cargar datos

            df = cargar_y_combinar_datos(master_file, symbol=symbol, meses=months)        "symbols_failed": [],            logger.error(f"Error cargando configuración institucional: {e}")

            df_clean = limpiar_ohlcv(df)

                    "critical_errors": [],            return False

            if df_clean.empty:

                results["errors"].append(f"Sin datos para {symbol}")        "warnings": []    

                continue

                }    def run_qa_phase(self, symbols: List[str], master_file: str = DEFAULT_MASTER_FILE) -> bool:

            # Ejecutar backtesting

            logger.info(f"Backtesting {symbol} ({len(df_clean)} filas)")            """

            result = backtesting_legacy(df_clean, config_obj=cfg)

                # Validar archivo maestro        Fase QA: Validación de datos y configuración.

            if isinstance(result, tuple) and len(result) >= 2:

                resultados, resumen = result[0], result[1]    if not os.path.exists(master_file):        

                trades_enriched = result[2] if len(result) > 2 else []

            else:        qa_results["critical_errors"].append(f"Archivo maestro no encontrado: {master_file}")        Args:

                raise ValueError(f"Resultado inesperado: {type(result)}")

                    logger.error("❌ Archivo maestro no encontrado")            symbols: Lista de símbolos a validar

            # Metricas

            trades_count = len(trades_enriched) if trades_enriched else 0        return False            master_file: Archivo maestro de datos

            pnl_net = resumen.get("pnl_net", 0.0) if isinstance(resumen, dict) else 0.0

                        

            results["results_by_symbol"][symbol] = {

                "trades_count": trades_count,    try:        Returns:

                "pnl_net": pnl_net,

                "win_rate": resumen.get("win_rate", 0.0) if isinstance(resumen, dict) else 0.0,        df_master = pd.read_csv(master_file)            True si QA pasa, False si hay problemas críticos

                "profit_factor": resumen.get("profit_factor", 0.0) if isinstance(resumen, dict) else 0.0

            }        logger.info(f"Archivo maestro cargado: {len(df_master)} filas")        """

            

            total_trades += trades_count    except Exception as e:        logger.info(f"=== FASE QA ===")

            total_pnl += pnl_net

                    qa_results["critical_errors"].append(f"Error leyendo archivo maestro: {e}")        logger.info(f"Validando {len(symbols)} símbolos: {', '.join(symbols)}")

            # Guardar por simbolo

            symbol_dir = os.path.join(output_dir, symbol)        logger.error(f"❌ Error leyendo archivo maestro: {e}")        

            os.makedirs(symbol_dir, exist_ok=True)

                    return False        qa_results = {

            if trades_enriched:

                trades_file = os.path.join(symbol_dir, f"trades_{symbol}_{perfil}.csv")                "timestamp": datetime.now().isoformat(),

                pd.DataFrame(trades_enriched).to_csv(trades_file, index=False)

                # Validar datos por símbolo            "symbols_requested": symbols,

            resumen_file = os.path.join(symbol_dir, f"resumen_{symbol}_{perfil}.json")

            with open(resumen_file, "w", encoding="utf-8") as f:    for symbol in symbols:            "symbols_validated": [],

                json.dump(resumen, f, indent=2, ensure_ascii=False)

                    try:            "symbols_failed": [],

            logger.info(f"OK {symbol}: {trades_count} trades, PnL: {pnl_net:.2f}")

                    df_symbol = cargar_y_combinar_datos(master_file, symbol=symbol)            "data_quality": {},

        except Exception as e:

            results["errors"].append(f"Error en {symbol}: {e}")            df_clean = limpiar_ohlcv(df_symbol)            "config_validation": {},

            logger.error(f"ERROR {symbol}: {e}")

                            "critical_errors": [],

    # Guardar resultados consolidados

    results["consolidated"] = {            if df_clean.empty:            "warnings": []

        "total_trades": total_trades,

        "total_pnl": total_pnl                qa_results["symbols_failed"].append(symbol)        }

    }

                    qa_results["warnings"].append(f"Sin datos para {symbol}")        

    results_file = os.path.join(output_dir, f"backtesting_results_{perfil}.json")

    with open(results_file, "w", encoding="utf-8") as f:                logger.warning(f"⚠️ Sin datos para {symbol}")        # 1. Validar archivo maestro

        json.dump(results, f, indent=2, ensure_ascii=False)

                    continue        if not os.path.exists(master_file):

    success = len(results["errors"]) == 0 and total_trades > 0

                            qa_results["critical_errors"].append(f"Archivo maestro no encontrado: {master_file}")

    if success:

        logger.info(f"OK: BACKTESTING COMPLETADO - {total_trades} trades, PnL: {total_pnl:.2f}")            completeness = len(df_clean) / len(df_symbol) if len(df_symbol) > 0 else 0            self.qa_results = qa_results

    else:

        logger.error(f"ERROR: BACKTESTING CON ERRORES")            if completeness < 0.9:            return False

    

    return success                qa_results["warnings"].append(f"Baja calidad de datos para {symbol}: {completeness:.1%}")        



                logger.warning(f"⚠️ Baja calidad para {symbol}: {completeness:.1%}")        try:

def main():

    """Funcion principal del runner institucional."""                        df_master = pd.read_csv(master_file)

    args = parse_args()

                qa_results["symbols_validated"].append(symbol)            logger.info(f"Archivo maestro cargado: {len(df_master)} filas")

    if args.verbose:

        logging.getLogger().setLevel(logging.DEBUG)            logger.info(f"✓ {symbol}: {len(df_clean)} filas limpias ({completeness:.1%})")            

    

    # Parse simbolos                    # Validar columnas requeridas

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    logger.info(f"Runner institucional iniciado para {len(symbols)} simbolos: {symbols}")        except Exception as e:            required_cols = ["symbol", "timestamp", "open", "high", "low", "close", "volume"]

    

    # Crear directorio de salida            qa_results["symbols_failed"].append(symbol)            missing_cols = [col for col in required_cols if col not in df_master.columns]

    os.makedirs(args.output_dir, exist_ok=True)

                qa_results["critical_errors"].append(f"Error procesando {symbol}: {e}")            if missing_cols:

    success = True

                logger.error(f"✗ {symbol}: {e}")                qa_results["critical_errors"].append(f"Columnas faltantes en master: {missing_cols}")

    try:

        # Fase QA            

        if not args.skip_qa and not args.backtesting_only:

            qa_success = run_qa_phase(symbols, args.master_file, args.output_dir)    # Guardar reporte QA        except Exception as e:

            if not qa_success:

                if args.qa_only:    os.makedirs(output_dir, exist_ok=True)            qa_results["critical_errors"].append(f"Error leyendo archivo maestro: {e}")

                    logger.error("ERROR: QA fallo")

                    return 1    qa_file = os.path.join(output_dir, "qa_report.json")            self.qa_results = qa_results

                else:

                    logger.error("ERROR: QA fallo - deteniendo ejecucion")    with open(qa_file, "w", encoding="utf-8") as f:            return False

                    return 1

            else:        json.dump(qa_results, f, indent=2, ensure_ascii=False)        

                logger.info("OK: QA aprobada")

                    # 2. Validar datos por símbolo

        if args.qa_only:

            logger.info("OK: Modo QA-only completado")    # Decisión        for symbol in symbols:

            return 0

            has_errors = len(qa_results["critical_errors"]) > 0            try:

        # Fase Backtesting

        bt_success = run_backtesting_phase(    validated_symbols = len(qa_results["symbols_validated"])                df_symbol = cargar_y_combinar_datos(master_file, symbol=symbol)

            symbols, args.months, args.perfil, 

            args.config, args.master_file, args.output_dir                    df_clean = limpiar_ohlcv(df_symbol)

        )

            if has_errors:                

        if not bt_success:

            logger.warning("ADVERTENCIA: Backtesting completado con errores")        logger.error(f"❌ QA FALLIDA - Errores críticos")                if df_clean.empty:

            success = False

        else:        return False                    qa_results["symbols_failed"].append(symbol)

            logger.info("OK: Backtesting completado exitosamente")

                                qa_results["warnings"].append(f"Sin datos para {symbol}")

        # Reporte final

        final_report = {    if validated_symbols == 0:                    continue

            "timestamp": datetime.now().isoformat(),

            "symbols": symbols,        logger.error("❌ QA FALLIDA - Sin símbolos validados")                

            "months": args.months,

            "perfil": args.perfil,        return False                # Métricas de calidad

            "success": success

        }                    data_quality = {

        

        report_file = os.path.join(args.output_dir, "final_report.json")    logger.info(f"✅ QA APROBADA - {validated_symbols}/{len(symbols)} símbolos validados")                    "rows_total": len(df_symbol),

        with open(report_file, "w", encoding="utf-8") as f:

            json.dump(final_report, f, indent=2, ensure_ascii=False)    return True                    "rows_clean": len(df_clean),

        

        logger.info(f"COMPLETADO - Reporte: {report_file}")                    "data_completeness": len(df_clean) / len(df_symbol) if len(df_symbol) > 0 else 0,

        

        return 0 if success else 1                    "date_range": {

    

    except KeyboardInterrupt:def run_backtesting_phase(symbols: List[str], months: int, perfil: str, config_path: str, master_file: str, output_dir: str) -> bool:                        "start": df_clean["timestamp"].min().isoformat() if "timestamp" in df_clean.columns else None,

        logger.info("INTERRUPCION: Ejecucion interrumpida por usuario")

        return 130    """Ejecuta fase backtesting con Beta A2."""                        "end": df_clean["timestamp"].max().isoformat() if "timestamp" in df_clean.columns else None

    

    except Exception as e:    logger.info(f"=== FASE BACKTESTING ===")                    },

        logger.error(f"ERROR CRITICO en runner institucional: {e}")

        return 1    logger.info(f"Símbolos: {symbols}, Meses: {months}, Perfil: {perfil}")                    "missing_data_pct": (len(df_symbol) - len(df_clean)) / len(df_symbol) * 100 if len(df_symbol) > 0 else 0



                    }

if __name__ == "__main__":

    sys.exit(main())    results = {                

        "timestamp": datetime.now().isoformat(),                qa_results["data_quality"][symbol] = data_quality

        "symbols": symbols,                

        "perfil_tp_sl": perfil,                # Validar calidad mínima

        "results_by_symbol": {},                if data_quality["data_completeness"] < 0.9:  # < 90% completeness

        "errors": []                    qa_results["warnings"].append(f"Baja calidad de datos para {symbol}: {data_quality['data_completeness']:.1%}")

    }                

                    qa_results["symbols_validated"].append(symbol)

    total_trades = 0                logger.info(f"✓ {symbol}: {len(df_clean)} filas limpias ({data_quality['data_completeness']:.1%})")

    total_pnl = 0.0            

                except Exception as e:

    for symbol in symbols:                qa_results["symbols_failed"].append(symbol)

        logger.info(f"Procesando {symbol}...")                qa_results["critical_errors"].append(f"Error procesando {symbol}: {e}")

                        logger.error(f"✗ {symbol}: {e}")

        try:        

            # Configurar BTConfig con Beta A2        # 3. Validar configuración institucional

            cfg = configure_from_institucional(config_path, symbol=symbol, perfil=perfil)        try:

                        config_validation = {

            # Cargar datos                "profiles_available": list(self.config_data.get("tp_sl_profiles", {}).keys()),

            df = cargar_y_combinar_datos(master_file, symbol=symbol, meses=months)                "symbols_configured": list(self.config_data.get("symbols", {}).keys()),

            df_clean = limpiar_ohlcv(df)                "guardrails_active": bool(self.config_data.get("guardrails", {})),

                            "defaults_present": bool(self.config_data.get("defaults", {}))

            if df_clean.empty:            }

                results["errors"].append(f"Sin datos para {symbol}")            qa_results["config_validation"] = config_validation

                continue            logger.info(f"Configuración validada: {len(config_validation['profiles_available'])} perfiles TP/SL")

                    

            # Ejecutar backtesting        except Exception as e:

            logger.info(f"Backtesting {symbol} ({len(df_clean)} filas)")            qa_results["warnings"].append(f"Error validando configuración: {e}")

            result = backtesting_legacy(df_clean, config_obj=cfg)        

                    self.qa_results = qa_results

            if isinstance(result, tuple) and len(result) >= 2:        

                resultados, resumen = result[0], result[1]        # Guardar reporte QA

                trades_enriched = result[2] if len(result) > 2 else []        qa_file = os.path.join(self.output_dir, "qa_report.json")

            else:        with open(qa_file, "w", encoding="utf-8") as f:

                raise ValueError(f"Resultado inesperado: {type(result)}")            json.dump(qa_results, f, indent=2, ensure_ascii=False)

                    

            # Métricas        # Decisión crítica

            trades_count = len(trades_enriched) if trades_enriched else 0        has_critical_errors = len(qa_results["critical_errors"]) > 0

            pnl_net = resumen.get("pnl_net", 0.0) if isinstance(resumen, dict) else 0.0        validated_symbols = len(qa_results["symbols_validated"])

                    

            results["results_by_symbol"][symbol] = {        if has_critical_errors:

                "trades_count": trades_count,            logger.error(f"❌ QA FALLIDA - Errores críticos: {qa_results['critical_errors']}")

                "pnl_net": pnl_net,            return False

                "win_rate": resumen.get("win_rate", 0.0) if isinstance(resumen, dict) else 0.0,        

                "profit_factor": resumen.get("profit_factor", 0.0) if isinstance(resumen, dict) else 0.0        if validated_symbols == 0:

            }            logger.error("❌ QA FALLIDA - Sin símbolos validados")

                        return False

            total_trades += trades_count        

            total_pnl += pnl_net        logger.info(f"✅ QA APROBADA - {validated_symbols}/{len(symbols)} símbolos validados")

                    return True

            # Guardar por símbolo    parser.add_argument("--skip-qa", action="store_true", help="Saltar validación QA del maestro")

            symbol_dir = os.path.join(output_dir, symbol)    parser.add_argument("--force", action="store_true", help="Continuar aunque la QA falle")

            os.makedirs(symbol_dir, exist_ok=True)    parser.add_argument("--strict-proximity", type=int, default=None, help="Override opcional para strict_proximity_bars")

                parser.add_argument("--min-mfe-mae-ratio", type=float, default=None, help="Override opcional para min_mfe_mae_ratio")

            if trades_enriched:    return parser.parse_args(args=args)

                trades_file = os.path.join(symbol_dir, f"trades_{symbol}_{perfil}.csv")

                pd.DataFrame(trades_enriched).to_csv(trades_file, index=False)

            def _ejecutar_qa(master_path: Path, qa_dir: Path) -> Dict[str, Any]:

            resumen_file = os.path.join(symbol_dir, f"resumen_{symbol}_{perfil}.json")    qa_dir.mkdir(parents=True, exist_ok=True)

            with open(resumen_file, "w", encoding="utf-8") as f:    df = qa.leer(master_path)

                json.dump(resumen, f, indent=2, ensure_ascii=False)    conteo_rows, gmin, gmax = qa.conteo_y_cobertura(df)

                dup_counts, grid_ok = qa.verificar_timestamps(df)

            logger.info(f"✓ {symbol}: {trades_count} trades, PnL: {pnl_net:.2f}")    gaps_info, gaps_critical = qa.detectar_gaps(df)

            calidad_stats = qa.calidad_ohlcv(df)

        except Exception as e:    checks, overall = qa.resumen_final(conteo_rows, dup_counts, grid_ok, gaps_info, gaps_critical, calidad_stats)

            results["errors"].append(f"Error en {symbol}: {e}")    report_path = qa_dir / "qa_maestro.md"

            logger.error(f"✗ {symbol}: {e}")    qa.generar_markdown(report_path, conteo_rows, gmin, gmax, dup_counts, grid_ok, gaps_info, gaps_critical, calidad_stats, checks, overall)

        return {

    # Guardar resultados consolidados        "overall": overall,

    results["consolidated"] = {        "checks": checks,

        "total_trades": total_trades,        "report": str(report_path),

        "total_pnl": total_pnl    }

    }

    

    results_file = os.path.join(output_dir, f"backtesting_results_{perfil}.json")def _filtrar_meses(df: pd.DataFrame, months: int) -> pd.DataFrame:

    with open(results_file, "w", encoding="utf-8") as f:    if months <= 0 or "timestamp" not in df.columns:

        json.dump(results, f, indent=2, ensure_ascii=False)        return df.copy()

        end = pd.to_datetime(df["timestamp"].max(), utc=True)

    success = len(results["errors"]) == 0 and total_trades > 0    cutoff = end - pd.DateOffset(months=months)

        return df.loc[pd.to_datetime(df["timestamp"], utc=True) >= cutoff].copy()

    if success:

        logger.info(f"✅ BACKTESTING COMPLETADO - {total_trades} trades, PnL: {total_pnl:.2f}")

    else:def _ejecutar_backtesting_simbolo(

        logger.error(f"❌ BACKTESTING CON ERRORES")    df_symbol: pd.DataFrame,

        cfg_symbol,

    return success    out_dir: Path,

    months: int,

) -> Dict[str, Any]:

def main():    out_dir.mkdir(parents=True, exist_ok=True)

    """Función principal del runner institucional."""    df_filtered = _filtrar_meses(df_symbol, months)

    args = parse_args()    if df_filtered.empty:

            LOGGER.warning("%s sin datos tras filtrado; se omite backtesting", cfg_symbol.symbol)

    if args.verbose:        resumen_vacio = {"trades": 0, "profit_factor": 0.0, "winrate": 0.0, "expectancy": 0.0, "max_drawdown": 0.0}

        logging.getLogger().setLevel(logging.DEBUG)        return {"resumen": resumen_vacio, "trades": pd.DataFrame(), "resultados": []}

    

    # Parse símbolos    resultados, resumen, trades_enriched = backtesting_legacy(df_filtered, config_obj=cfg_symbol)

    symbols = [s.strip().upper() for s in args.symbols.split(",")]    trades_df = pd.DataFrame(trades_enriched)

    logger.info(f"Runner institucional iniciado para {len(symbols)} símbolos: {symbols}")    trades_path = out_dir / f"trades_{cfg_symbol.symbol}.csv"

        resumen_path = out_dir / f"resumen_{cfg_symbol.symbol}.json"

    # Crear directorio de salida    trades_df.to_csv(trades_path, index=False)

    os.makedirs(args.output_dir, exist_ok=True)    resumen_path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

        return {"resumen": resumen, "trades": trades_df, "resultados": resultados}

    success = True

    

    try:def _consolidar_portafolio(trades_por_simbolo: Dict[str, pd.DataFrame]) -> Dict[str, Any]:

        # Fase QA    if not trades_por_simbolo:

        if not args.skip_qa and not args.backtesting_only:        return {"trades": 0, "net_pnl": 0.0, "profit_factor": 0.0, "winrate": 0.0, "expectancy": 0.0, "max_drawdown": 0.0}

            qa_success = run_qa_phase(symbols, args.master_file, args.output_dir)

            if not qa_success:    pnl_series = []

                if args.qa_only:    for df in trades_por_simbolo.values():

                    logger.error("❌ QA falló")        if df.empty:

                    return 1            continue

                else:        pnl = pd.to_numeric(df.get("net_pnl", pd.Series(dtype=float)), errors="coerce").fillna(0.0)

                    logger.error("❌ QA falló - deteniendo ejecución")        exit_times = pd.to_datetime(df.get("exit_time", pd.Series(pd.NaT)), utc=True, errors="coerce")

                    return 1        pnl_series.append(pd.DataFrame({"timestamp": exit_times, "pnl": pnl}))

            else:    if not pnl_series:

                logger.info("✅ QA aprobada")        return {"trades": 0, "net_pnl": 0.0, "profit_factor": 0.0, "winrate": 0.0, "expectancy": 0.0, "max_drawdown": 0.0}

        

        if args.qa_only:    merged = pd.concat(pnl_series, ignore_index=True)

            logger.info("✅ Modo QA-only completado")    merged = merged.sort_values("timestamp").reset_index(drop=True)

            return 0    pnl_values = merged["pnl"].fillna(0.0)

            total_trades = len(pnl_values)

        # Fase Backtesting    total_wins = (pnl_values > 0).sum()

        bt_success = run_backtesting_phase(    total_winrate = (total_wins / total_trades * 100.0) if total_trades else 0.0

            symbols, args.months, args.perfil,     total_pnl = float(pnl_values.sum())

            args.config, args.master_file, args.output_dir    gains = float(pnl_values[pnl_values > 0].sum())

        )    losses = float(-pnl_values[pnl_values < 0].sum())

            if losses > 0:

        if not bt_success:        profit_factor = gains / losses

            logger.warning("⚠️ Backtesting completado con errores")    else:

            success = False        profit_factor = float("inf") if gains > 0 else 0.0

        else:    expectancy = float(pnl_values.mean()) if total_trades else 0.0

            logger.info("✅ Backtesting completado exitosamente")    equity = pnl_values.cumsum()

            dd = equity - equity.cummax()

        # Reporte final    max_dd = float(dd.min()) if not dd.empty else 0.0

        final_report = {

            "timestamp": datetime.now().isoformat(),    return {

            "symbols": symbols,        "trades": int(total_trades),

            "months": args.months,        "net_pnl": total_pnl,

            "perfil": args.perfil,        "profit_factor": float(profit_factor),

            "success": success        "winrate": float(total_winrate),

        }        "expectancy": expectancy,

                "max_drawdown": max_dd,

        report_file = os.path.join(args.output_dir, "final_report.json")    }

        with open(report_file, "w", encoding="utf-8") as f:

            json.dump(final_report, f, indent=2, ensure_ascii=False)

        def _guardar_portafolio(resumen: Dict[str, Any], out_dir: Path) -> Path:

        logger.info(f"🎯 EJECUCIÓN COMPLETADA - Reporte: {report_file}")    out_dir.mkdir(parents=True, exist_ok=True)

            portfolio_path = out_dir / "portfolio_resumen.json"


        portfolio_path.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if success else 1
        return portfolio_path

    except KeyboardInterrupt:

        logger.info("❌ Ejecución interrumpida por usuario")

        return 130def run(args: Optional[List[str]] = None) -> int:

        ns = _parse_args(args)

    except Exception as e:

        logger.error(f"❌ Error crítico en runner institucional: {e}")    master_path = Path(ns.master).resolve()

        return 1    if not master_path.exists():

        raise FileNotFoundError(f"No se encontró el maestro en {master_path}")



if __name__ == "__main__":    config_path = Path(ns.config).resolve() if ns.config else None

    sys.exit(main())    instit_cfg = get_institucional_config(str(config_path) if config_path else None)

    symbols_cfg = {s: sc for s, sc in instit_cfg.symbols.items() if sc.enabled}
    if ns.symbols:
        requested = [s.strip().upper() for s in ns.symbols.split(",") if s.strip()]
        symbols = [s for s in requested if s in symbols_cfg]
    else:
        symbols = [s for s in instit_cfg.portfolio_include if s in symbols_cfg]
    if not symbols:
        raise ValueError("No hay símbolos habilitados para procesar")

    run_root = Path(ns.out_root).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = run_root / timestamp
    qa_dir = run_dir / "qa"
    bt_dir = run_dir / "backtesting"
    trades_dir = bt_dir / "trades"
    portfolio_dir = run_dir / "portfolio"

    trades_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(run_dir)
    LOGGER.info("Runner institucional iniciado. Símbolos: %s", ",".join(symbols))

    qa_result = None
    if ns.skip_qa:
        LOGGER.info("QA maestro omitida por bandera --skip-qa")
    else:
        qa_result = _ejecutar_qa(master_path, qa_dir)
        LOGGER.info("QA maestro completada. overall=%s", qa_result["overall"])
        if not qa_result["overall"] and not ns.force:
            raise SystemExit("QA maestro falló; reintentar con --force para continuar de todas maneras")

    df_master = pd.read_csv(master_path)
    if "timestamp" in df_master.columns:
        df_master["timestamp"] = pd.to_datetime(df_master["timestamp"], utc=True, errors="coerce")
    if "symbol" not in df_master.columns:
        raise ValueError("El maestro no contiene columna 'symbol'")

    overrides: Dict[str, Any] = {}
    if ns.strict_proximity is not None:
        overrides["strict_proximity_bars"] = int(ns.strict_proximity)
    if ns.min_mfe_mae_ratio is not None:
        overrides["min_mfe_mae_ratio"] = float(ns.min_mfe_mae_ratio)

    simbolo_resumenes: Dict[str, Dict[str, Any]] = {}
    trades_por_simbolo: Dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        cfg_symbol = bt_config_from_symbol(instit_cfg, symbol, overrides=overrides if overrides else None)
        LOGGER.info("Procesando %s (strict=%s, min_mfe_ratio=%s)", symbol, cfg_symbol.strict_proximity_bars, cfg_symbol.min_mfe_mae_ratio)
        df_symbol = df_master.loc[df_master["symbol"] == symbol].copy()
        resultado_bt = _ejecutar_backtesting_simbolo(df_symbol, cfg_symbol, trades_dir, ns.months)
        simbolo_resumenes[symbol] = resultado_bt["resumen"]
        trades_por_simbolo[symbol] = resultado_bt["trades"]
        LOGGER.info(
            "Resumen %s: trades=%s pf=%.3f guardrails=%s",
            symbol,
            resultado_bt["resumen"].get("trades"),
            resultado_bt["resumen"].get("profit_factor"),
            resultado_bt["resumen"].get("guardrails_passed"),
        )

    portfolio_resumen = _consolidar_portafolio(trades_por_simbolo)
    _guardar_portafolio(portfolio_resumen, portfolio_dir)

    extras = {
        "symbols": symbols,
        "months": ns.months,
        "dry_run": ns.dry_run,
        "qa": qa_result,
        "portfolio": portfolio_resumen,
        "resumenes": simbolo_resumenes,
        "runner_args": vars(ns),
    }
    freeze_params(str(run_dir), instit_cfg, extra=extras)
    (run_dir / "runner_args.json").write_text(json.dumps(vars(ns), ensure_ascii=False, indent=2), encoding="utf-8")

    LOGGER.info("Runner institucional finalizado. Carpeta: %s", run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
