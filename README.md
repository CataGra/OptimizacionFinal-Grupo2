# Rotación óptima de cultivos - Cuenca del Salado

App web (Streamlit) con un modelo de Programación Lineal Mixta (PuLP).
El usuario carga el cultivo anterior de cada lote y obtiene un ranking de rotaciones a 3 años,
de la más a la menos conveniente (margen bruto), con plan de siembra y fertilización.

## Ejecutar local
    pip install -r requirements.txt
    python make_template.py        # genera datos_ejemplo.xlsx (ya incluido)
    streamlit run app.py

## Deploy (Streamlit Community Cloud)
1. Subir esta carpeta a un repo de GitHub (app.py, model.py, datos_ejemplo.xlsx, requirements.txt).
2. En share.streamlit.io: New app -> elegir repo y archivo principal `app.py`.

## Archivos
- `app.py`: interfaz (carga de datos, formulario de lotes, ranking y resultados).
- `model.py`: lectura/validación del Excel, modelo PuLP, ranking top-K y evaluación.
- `make_template.py`: genera la plantilla Excel de ejemplo (datos ilustrativos).
- `datos_ejemplo.xlsx`: plantilla con las hojas lotes, aptitud, cultivos, rendimientos, rotacion, parametros.

## Modelo
- z[i,j,t] binaria: lote i siembra j en el año t. El cultivo anterior (año 0) es dato binario.
- v[i,j,k,t]: linealiza "j con antecesor k" (efecto en rendimiento y N requerido).
- Objetivo: max margen bruto = ingresos - costos directos - fertilizantes.
- Restricciones: un cultivo por lote y año, aptitud por clase de suelo, rotaciones permitidas,
  máx. soja, mín. gramíneas, mín. pastura, tope de N, presupuesto de fertilizante.
- Ranking: tras cada solución se agrega un corte no-good que exige cambiar al menos
  `min_diff` decisiones (lote, año) para obtener la siguiente alternativa.
