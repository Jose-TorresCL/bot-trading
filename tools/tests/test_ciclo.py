import sys, os, time
sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from src.core.ciclo_real import ejecutar_ciclo_paper_trading

ciclos = {'n': 0}
_orig_sleep = time.sleep

def sleep_patched(s):
    ciclos['n'] += 1
    print(f'--- Ciclo {ciclos["n"]} completado ---', flush=True)
    if ciclos['n'] >= 3:
        raise KeyboardInterrupt('max ciclos alcanzados')
    _orig_sleep(min(s, 2))

time.sleep = sleep_patched

try:
    ejecutar_ciclo_paper_trading(symbol='BTCUSDT', intervalo=2, capital_inicial=100.0)
except KeyboardInterrupt as e:
    print(f'Test detenido: {e}')
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')
