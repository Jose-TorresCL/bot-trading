import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
import os

st.title("Dashboard Paper Trading BTCUSDT")

df = pd.read_csv("data/papertrading_BTCUSDT.csv")

# Cargar operaciones desde registro_operaciones.json
def cargar_json_multi(ruta):
    import re
    datos = []
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8") as f:
            contenido = f.read()
            # Divide por objetos JSON usando una expresión regular
            objetos = re.findall(r'\{.*?\}\s*(?=\{|\Z)', contenido, re.DOTALL)
            for obj in objetos:
                try:
                    datos.append(json.loads(obj))
                except Exception:
                    pass
    return datos

operaciones_path = "data/papertrading/registro_operaciones.json"
operaciones = cargar_json_multi(operaciones_path)
df_operaciones = pd.DataFrame(operaciones) if operaciones else pd.DataFrame()

# Mostrar operaciones más recientes arriba
st.subheader("Precios y RSI de las últimas operaciones")
if not df_operaciones.empty:
    df_operaciones["precio"] = df_operaciones["additional_data"].apply(lambda x: x.get("precio") if isinstance(x, dict) else None)
    df_operaciones["RSI"] = df_operaciones["additional_data"].apply(
        lambda x: x.get("indicadores", {}).get("RSI") if isinstance(x, dict) and "indicadores" in x else None
    )
    st.dataframe(df_operaciones[["timestamp", "precio", "RSI"]].iloc[::-1].head(10))
else:
    st.warning("No se encontraron operaciones válidas en registro_operaciones.json.")

# Últimas operaciones del historial (más recientes arriba)
st.subheader("Últimas operaciones")
st.dataframe(df.iloc[::-1].head(20))

# Evolución del saldo virtual
st.subheader("Evolución del saldo virtual")
fig, ax = plt.subplots()
ax.plot(df["timestamp"], df["saldo_virtual"], label="Saldo USDT")
ax.set_xlabel("Fecha")
ax.set_ylabel("Saldo USDT")
plt.xticks(rotation=45)
st.pyplot(fig)

# Cantidad de BTC
st.subheader("Cantidad de BTC")
fig2, ax2 = plt.subplots()
ax2.plot(df["timestamp"], df["cantidad_btc"], color="orange", label="BTC")
ax2.set_xlabel("Fecha")
ax2.set_ylabel("Cantidad BTC")
plt.xticks(rotation=45)
st.pyplot(fig2)

# Métricas rápidas
compras = (df["resultado"].str.startswith("COMPRA")).sum()
ventas = (df["resultado"].str.startswith("VENTA")).sum()
st.metric("Total compras", compras)
st.metric("Total ventas", ventas)
st.metric("Saldo actual", df["saldo_virtual"].iloc[-1])

# Drawdown máximo (cálculo correcto)
saldo = df["saldo_virtual"]
max_saldo = saldo.cummax()
drawdown = (saldo - max_saldo) / max_saldo
drawdown_max = abs(drawdown.min()) * 100  # Valor absoluto en porcentaje
st.metric("Drawdown máximo (%)", f"{drawdown_max:.2f}")

# Winrate y gráficos avanzados solo si hay datos y columnas necesarias
if not df_operaciones.empty and "ganancia" in df_operaciones and "duracion" in df_operaciones:
    winrate = (df_operaciones["ganancia"] > 0).mean() * 100
    st.metric("Winrate (%)", f"{winrate:.2f}")

    st.subheader("Histograma de Ganancias por Operación")
    fig_hist, ax_hist = plt.subplots()
    ax_hist.hist(df_operaciones["ganancia"], bins=30, color="skyblue")
    ax_hist.set_xlabel("Ganancia")
    ax_hist.set_ylabel("Frecuencia")
    st.pyplot(fig_hist)

    st.subheader("Top 5 operaciones más rentables")
    st.dataframe(df_operaciones.nlargest(5, "ganancia"))

    st.subheader("Top 5 operaciones con mayor pérdida")
    st.dataframe(df_operaciones.nsmallest(5, "ganancia"))

    df_operaciones["win"] = df_operaciones["ganancia"] > 0
    df_operaciones["winrate_acum"] = df_operaciones["win"].expanding().mean() * 100
    st.subheader("Winrate acumulado en el tiempo")
    fig_win, ax_win = plt.subplots()
    ax_win.plot(df_operaciones.index, df_operaciones["winrate_acum"])
    ax_win.set_xlabel("Operación #")
    ax_win.set_ylabel("Winrate acumulado (%)")
    st.pyplot(fig_win)

    st.subheader("Ganancia vs Duración en Paper Trading")
    fig3, ax3 = plt.subplots(figsize=(10, 5))
    sns.scatterplot(x="duracion", y="ganancia", data=df_operaciones, ax=ax3)
    st.pyplot(fig3)
else:
    st.warning("No hay suficientes datos o columnas ('ganancia', 'duracion') para mostrar análisis avanzado.")

# Depuración: muestra primeras filas y columnas disponibles
st.write("Primeras filas de operaciones:")
st.write(df_operaciones.head())
st.write("Columnas disponibles:", df_operaciones.columns.tolist())