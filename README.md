# Bot de Trading Algorítmico

Este proyecto es un bot de trading algorítmico desarrollado en Python. Permite analizar datos, probar estrategias y operar de forma automatizada.

## Estructura del proyecto

- `src/` - Código fuente del bot y estrategias.
- `data/` - Datos históricos y de prueba.
- `notebooks/` - Jupyter Notebooks para análisis y experimentos.
- `resultados/` - Reportes y resultados de simulaciones.
- `bd/` - Archivos de bases de datos (si aplica).

- `scripts/auditar_sesgo_operativo.py`: Audita el sesgo operativo sin ejecutar trades usando el maestro 15m; genera `auditoria_sesgo_operativo.md` con bloqueos por filtro/régimen/horas.
1. Clona el repositorio:
   ```
   git clone <URL-del-repositorio>
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Instala las dependencias:
   ```
   pip install -r requirements.txt
   ```

## Uso

1. Ejecuta los notebooks para análisis.
2. Corre el bot desde la carpeta `src/`:
   ```
   python src/main.py
   ```

   ### Nota institucional

   - Consulta el documento "auditoría_técnica_y_organizativa.md" en la raíz para el diagnóstico completo, propuesta de reorganización y el runner institucional sugerido (flujo datos → backtest → TP/SL por régimen → portfolio → veredicto/launch).

---

## Guía de Backtesting y Análisis de Resultados

### Flujo del Notebook de Backtesting

1. **Carga de datos y parámetros:**  
   Se cargan los resultados y parámetros desde archivos generados por el bot.

2. **Resumen estadístico por símbolo y periodo:**  
   Se agrupan y analizan las operaciones por par y periodo, mostrando métricas como ganancia media, máxima, desviación estándar, duración y cantidad de operaciones.

3. **Gráficos comparativos:**  
   Visualización de la dispersión de ganancias y duración por símbolo y periodo.

4. **Selección y exportación de operaciones robustas:**  
   Filtrado y exportación de operaciones con alta ganancia y baja duración.

5. **Exportar la mejor operación por símbolo y periodo:**  
   Identificación y guardado de las mejores operaciones para cada grupo.

6. **Guardar la mejor combinación de parámetros:**  
   Selección y guardado de los parámetros óptimos según el backtesting.

7. **Análisis avanzado de operaciones registradas:**  
   Revisión de las decisiones del bot y exportación de un resumen.

### ¿Cómo interpretar los resultados?

- Revisa el resumen estadístico para identificar patrones y oportunidades de mejora.
- Analiza los gráficos para detectar outliers y tendencias.
- Usa los archivos exportados para ajustar tu bot y replicar condiciones exitosas.

### Recomendaciones prácticas

- Ajusta la estrategia en los pares menos rentables.
- Analiza las operaciones con ganancia máxima para detectar si son replicables.
- Compara la rentabilidad entre diferentes periodos para cada símbolo.
- Evalúa si la duración de las operaciones influye en la ganancia y ajusta los límites si es necesario.
- Utiliza los parámetros óptimos guardados para futuros backtesting o trading real.
- Documenta los cambios y resultados para facilitar el seguimiento y la mejora continua.

### Compartir y retomar el análisis

- Guarda los archivos generados (`.csv`, `.json`) en la carpeta correspondiente.
- Copia los fragmentos relevantes del notebook o los resultados en este README para referencia rápida.
- Cuando quieras avanzar o consultar, comparte el README y los archivos de resultados.

---

## Contribución

- Usa ramas para nuevas funciones o correcciones.
- Haz commits claros y descriptivos.
- Abre un Pull Request para revisión.

## Licencia
- Proyecto pensado y realizado por Jose Torres apoyado con inteligencia artificial.