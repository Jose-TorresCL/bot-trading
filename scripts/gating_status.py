import os
import json
from datetime import datetime
import argparse
from typing import Dict, Any

"""Genera gating_status.json integrando:
- sanity_flags.json
- drop_tests_flags.json
- walk_forward_flags_refined.json (refinado)

Heurística de consolidación por símbolo:
- pf_net_ok: viene de sanity (pf_net_ok True) y símbolo con pf_net individual >0 (drop tests individual).
- fragilizador: True si en drop tests flags.fragile True OR (remover símbolo reduce max_dd_net) y no empeora pf significativamente.
- stable_pf: derivado global: si TODAS las ventanas refined son estables => True (aplica a portfolio, se replica por símbolo). Si no, False.
- recomendacion (prioridad):
    1. Si min_trades_ok False y pf_net_ok False => 'ampliar muestra antes de promoción'
    2. Si fragilizador True => 'mantener en observación con throttling'
    3. Si pf_net_ok True y min_trades_ok False => 'edge preliminar, recolectar más trades'
    4. Si pf_net_ok True y stable_pf True => 'candidato a promoción (paper)'
    5. default => 'monitorizar'

Campos adicionales:
- value_add (del drop tests flags)
- few_trades
- pnl_share_pct
- raw: subestructura con métricas clave usadas para transparencia.
"""


def load_json(path: str) -> Any:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description='Construir gating_status.json')
    parser.add_argument('--run-id', required=True, help='ID de run (carpeta ANALISIS)')
    parser.add_argument('--analysis-root', default=os.path.join('data','backtesting','ANALISIS'))
    args = parser.parse_args()

    run_dir = os.path.join(args.analysis_root, args.run_id, 'modelo_costos')

    sanity_path = os.path.join(run_dir, 'sanity_flags.json')
    drop_path = os.path.join(run_dir, 'drop_tests', 'drop_tests_flags.json')
    wf_refined_path = os.path.join(run_dir, 'walk_forward_flags_refined.json')

    sanity = load_json(sanity_path)
    drop = load_json(drop_path)
    wf_refined = load_json(wf_refined_path)

    # global stability: todas ventanas estables en refined
    windows = wf_refined.get('windows', {})
    global_stable_pf = all(w.get('estable') for w in windows.values()) and len(windows) > 0

    gating: Dict[str, Any] = {}

    for symbol, sflags in sanity.items():
        d = drop['symbols'].get(symbol, {})
        indiv = d.get('individual', {})
        dflags = d.get('flags', {})
        pnl_share = indiv.get('pnl_share_pct')

        pf_net_ok = bool(sflags.get('pf_net_ok', False) and indiv.get('pf_net', 0) > 0)
        fragilizador = bool(dflags.get('fragile'))
        few_trades = bool(dflags.get('few_trades')) or not sflags.get('min_trades_ok', False)
        value_add = bool(dflags.get('value_add'))

        # recomendacion por prioridad
        if (not sflags.get('min_trades_ok')) and (not pf_net_ok):
            recomendacion = 'ampliar muestra antes de promoción'
        elif fragilizador:
            recomendacion = 'mantener en observación con throttling'
        elif pf_net_ok and (not sflags.get('min_trades_ok')):
            recomendacion = 'edge preliminar, recolectar más trades'
        elif pf_net_ok and global_stable_pf:
            recomendacion = 'candidato a promoción (paper)'
        else:
            recomendacion = 'monitorizar'

        gating[symbol] = {
            'pf_net_ok': pf_net_ok,
            'fragilizador': fragilizador,
            'stable_pf': global_stable_pf,
            'recomendacion': recomendacion,
            'value_add': value_add,
            'few_trades': few_trades,
            'pnl_share_pct': pnl_share,
            'raw': {
                'sanity': sflags,
                'drop_flags': dflags,
                'pf_net_individual': indiv.get('pf_net'),
                'expectancy_individual': indiv.get('expectancy_net'),
                'max_dd_individual': indiv.get('max_dd_net'),
                'trades_individual': indiv.get('trades')
            }
        }

    out_path = os.path.join(run_dir, 'gating_status.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'run_id': args.run_id,
            'generated_utc': datetime.utcnow().isoformat() + 'Z',
            'global_stable_pf': global_stable_pf,
            'symbols': gating
        }, f, ensure_ascii=False, indent=2)

    print(f'Generado {out_path}')


if __name__ == '__main__':
    main()
