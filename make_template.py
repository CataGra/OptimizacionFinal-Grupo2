"""
Genera datos_ejemplo.xlsx: la plantilla de entrada de la app.
Los valores son ILUSTRATIVOS (reemplazar con datos de INTA / Bolsa de Cereales / AACREA).
Uso:  python make_template.py [Estimaciones.csv]
"""
import os
import sys

import pandas as pd

from importar_rendimientos import rendimientos_desde_csv

lotes = pd.DataFrame([
    ("L1", 120, "A", "soja"), ("L2", 90, "A", "maiz"), ("L3", 150, "A", "trigo_soja2"),
    ("L4", 200, "B", "soja"), ("L5", 180, "B", "pastura"), ("L6", 100, "B", "maiz"),
    ("L7", 130, "B", "pastura"), ("L8", 250, "C", "pastura"), ("L9", 300, "C", "pastura"),
    ("L10", 80, "A", "soja"),
], columns=["lote", "ha", "clase", "cultivo_anterior"])

# ingreso_fijo_usd_ha: ingreso que no depende del rendimiento (valor del forraje de la pastura)
cultivos = pd.DataFrame([
    ("soja", "soja", 230, 30, 0),
    ("maiz", "gramínea", 420, 40, 0),
    ("trigo_soja2", "soja", 520, 55, 0),
    ("pastura", "pastura", 40, 25, 130),
], columns=["cultivo", "grupo", "costo_usd_ha", "p_req_kg_ha", "ingreso_fijo_usd_ha"])

# Qué productos (con rendimiento y precio) componen el ingreso de cada cultivo
composicion = pd.DataFrame([
    ("soja", "soja"), ("maiz", "maiz"),
    ("trigo_soja2", "trigo"), ("trigo_soja2", "soja2"),
], columns=["cultivo", "producto"])

# Precios netos de flete y retenciones (USD/tn) - ILUSTRATIVOS
precios = pd.DataFrame([("soja", 270), ("soja2", 270), ("maiz", 140), ("trigo", 160)],
                       columns=["producto", "precio_usd_tn"])

# Rendimiento por partido (tn/ha): promedio real de las Estimaciones Agrícolas (CSV).
# Si el CSV no está en la carpeta, usa valores ILUSTRATIVOS y avisa.
CSV_RENDIMIENTOS = sys.argv[1] if len(sys.argv) > 1 else "Estimaciones.csv"
if os.path.exists(CSV_RENDIMIENTOS):
    rendimientos_partido = rendimientos_desde_csv(CSV_RENDIMIENTOS)
    print(f"Rendimientos reales cargados desde {CSV_RENDIMIENTOS}")
else:
    print(f"AVISO: no encontré {CSV_RENDIMIENTOS}; uso rendimientos ILUSTRATIVOS.")
    base = dict(soja=3.3, maiz=8.5, trigo=4.0, soja2=1.9)
    mult = {"Chascomús": 1.00, "Dolores": 0.95, "Rauch": 0.92, "Castelli": 0.88,
            "Las Flores": 0.97, "Ayacucho": 0.93}
    rendimientos_partido = pd.DataFrame(
        [(p, prod, round(r * m, 2), "ilustrativo")
         for p, m in mult.items() for prod, r in base.items()],
        columns=["partido", "producto", "rendimiento_tn_ha", "fuente"])

# Ajuste del rendimiento según clase de suelo (A = referencia)
factor_clase = pd.DataFrame([("A", 1.00), ("B", 0.80), ("C", 0.60)],
                            columns=["clase", "factor"])

aptitud = pd.DataFrame(
    [(c, j, int(not (c == "C" and j != "pastura")))
     for c in ["A", "B", "C"] for j in cultivos["cultivo"]],
    columns=["clase", "cultivo", "apto"])

# Pares (cultivo, antecesor) PERMITIDOS. Lo que no está acá queda prohibido.
rotacion = pd.DataFrame([
    ("soja", "maiz", 1.05, 0), ("soja", "pastura", 1.03, 0),
    ("maiz", "soja", 1.00, 100), ("maiz", "trigo_soja2", 0.97, 110), ("maiz", "pastura", 1.08, 60),
    ("trigo_soja2", "maiz", 1.04, 90), ("trigo_soja2", "soja", 0.97, 70),
    ("trigo_soja2", "pastura", 1.05, 50),
    ("pastura", "soja", 1.0, 0), ("pastura", "maiz", 1.0, 0),
    ("pastura", "trigo_soja2", 1.0, 0), ("pastura", "pastura", 1.0, 0),
], columns=["cultivo", "antecesor", "factor", "n_req_kg_ha"])

parametros = pd.DataFrame([
    ("anios", 3, "Horizonte de planificación (años)"),
    ("max_frac_soja", 0.55, "Máx. fracción de la superficie en cultivos del grupo 'soja'"),
    ("min_frac_gramineas", 0.15, "Mín. fracción de la superficie en grupo 'gramínea'"),
    ("min_frac_pastura", 0.40, "Mín. fracción de la superficie en grupo 'pastura'"),
    ("n_max_anual_kg", 45000, "Tope de N total por año (kg). Vacío o 0 = sin tope"),
    ("presupuesto_fert_anual_usd", 90000, "Presupuesto de fertilizante por año (USD). Vacío o 0 = sin tope"),
    ("precio_n_usd_kg", 1.3, "Precio del N (USD/kg de N)"),
    ("precio_p_usd_kg", 1.4, "Precio del P (USD/kg de P2O5)"),
], columns=["parametro", "valor", "descripcion"])

leeme = pd.DataFrame({"instrucciones": [
    "Hoja 'lotes': un renglón por lote. 'cultivo_anterior' es el cultivo de la campaña previa (dato binario del modelo).",
    "Hoja 'aptitud': 1 si el cultivo es viable en esa clase de suelo, 0 si no.",
    "Hoja 'cultivos': costo directo sin fertilizante, requerimiento de P y grupo (soja / gramínea / pastura).",
    "Hoja 'rendimientos_partido': rendimiento (tn/ha) de cada producto por partido, para el suelo de referencia (clase A).",
    "Hoja 'factor_clase': multiplica el rendimiento según la clase de suelo (A = 1.0).",
    "Hojas 'composicion' y 'precios': qué productos componen el ingreso de cada cultivo y su precio neto (USD/tn).",
    "Ingreso (USD/ha) = factor_clase x sum(rendimiento_partido x precio) + ingreso_fijo del cultivo (ej. forraje de pastura).",
    "Hoja 'rotacion': pares (cultivo, antecesor) permitidos, con factor de rendimiento y N requerido. Lo ausente está prohibido.",
    "Hoja 'parametros': horizonte, restricciones de manejo y precios de fertilizantes.",
]})

with pd.ExcelWriter("datos_ejemplo.xlsx") as xw:
    for name, df in [("LEEME", leeme), ("lotes", lotes), ("aptitud", aptitud),
                     ("cultivos", cultivos), ("composicion", composicion), ("precios", precios),
                     ("rendimientos_partido", rendimientos_partido), ("factor_clase", factor_clase),
                     ("rotacion", rotacion), ("parametros", parametros)]:
        df.to_excel(xw, sheet_name=name, index=False)
print("datos_ejemplo.xlsx generado")