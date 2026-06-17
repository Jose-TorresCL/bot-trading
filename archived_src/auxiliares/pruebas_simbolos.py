"""
pruebas_simbolos.py
-------------------
[NO USADO EN EL FLUJO PRINCIPAL]
Script auxiliar para auditar la cantidad de registros por símbolo y el rango temporal
en el archivo de históricos limpio. Úsalo solo para auditorías manuales.
"""

import pandas as pd

df = pd.read_csv("historial_trading_limpio.csv")
print("Conteo de registros por símbolo:")
print(df["symbol"].value_counts())
print("\nRango temporal (timestamp):")
print(df["timestamp"].min(), df["timestamp"].max())