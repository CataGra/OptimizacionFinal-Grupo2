"""
Genera datos_ejemplo.xlsx: la plantilla de entrada de la app.
Datos reales de la Cuenca del Salado (MAGyP sep 2026, precios de fertilizantes nov 2026)
sobre un establecimiento típico ficticio (lotes inventados). Fuentes en los comentarios.
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

# costo_usd_ha: labores + semillas + fitosanitarios, SIN fertilizante.
#   Fuente: MAGyP, Márgenes y Resultados Agrícolas (sep 2026), región Cuenca del Salado.
# p_req_kg_ha (kg P2O5/ha): soja = 65,0 USD/ha de fertilizante ÷ 1,65 USD/kg (MAGyP);
#   maíz y trigo = 40 (dosis típica, supuesto); trigo_soja2 = 40 + 18,6 ÷ 1,65 (soja 2ª).
# Pastura (con leguminosa: lotus tenuis, trébol blanco) - SUPUESTOS:
#   costo = (semillas 125 + labores 115,4) ÷ 4 años + 20 de mantenimiento ≈ 80 USD/ha/año
#   p_req = 90 kg/ha de DAP a la siembra (41 kg P2O5) ÷ 4 años ≈ 10
#   ingreso_fijo = alquiler ganadero: 70 kg novillo/ha × 4.110 $/kg (MAG Cañuelas, oct 2026)
#                  ÷ 1.513,88 $/USD (BCRA, sep 2026) ≈ 190 USD/ha/año
cultivos = pd.DataFrame([
    ("soja", "soja", 234.7, 39, 0),
    ("maiz", "gramínea", 390.0, 40, 0),
    ("trigo_soja2", "soja", 427.0, 51, 0),
    ("pastura", "pastura", 80, 10, 190),
], columns=["cultivo", "grupo", "costo_usd_ha", "p_req_kg_ha", "ingreso_fijo_usd_ha"])

# Qué productos (con rendimiento y precio) componen el ingreso de cada cultivo
composicion = pd.DataFrame([
    ("soja", "soja"), ("maiz", "maiz"),
    ("trigo_soja2", "trigo"), ("trigo_soja2", "soja2"),
], columns=["cultivo", "producto"])

# Precios netos (USD/tn) = precio a cosecha − gastos de comercialización y cosecha ÷ rinde.
#   Fuente: MAGyP, Márgenes y Resultados Agrícolas (sep 2026), Cuenca del Salado.
#   El precio de referencia ya es un precio local (retenciones descontadas).
#   soja 360 − 262,2/3,10 | soja2 360 − 165,4/1,84 | maíz 205,5 − 460,6/7,18 | trigo 226 − 280,5/4,21
precios = pd.DataFrame([("soja", 275.4), ("soja2", 270.1), ("maiz", 141.3), ("trigo", 159.4)],
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
# n_req_kg_ha: maíz tras soja (67) y trigo tras soja (77) calibrados con el gasto en fertilizante
#   de MAGyP sep 2026: (153,4 − 40×1,65)/1,30 y (166,6 − 40×1,65)/1,30. El resto, ajustes propuestos:
#   tras pastura con leguminosa ≈ −50% (fijación biológica de N de Lotus tenuis, INTA EEA Cuenca
#   del Salado 2025); trigo tras maíz +15% (inmovilización de N); maíz tras trigo/soja +10%.
# factor: soja tras maíz +5% (literatura ≈ +10% vs. soja/soja; la mitad porque el rinde base ya es
#   un promedio); tras pastura +5/8% (Chacra Exp. Barrow, MDA-INTA); trigo tras maíz −3%.
rotacion = pd.DataFrame([
    ("soja", "maiz", 1.05, 0), ("soja", "pastura", 1.05, 0),
    ("maiz", "soja", 1.00, 67), ("maiz", "trigo_soja2", 0.97, 75), ("maiz", "pastura", 1.08, 35),
    ("trigo_soja2", "maiz", 0.97, 90), ("trigo_soja2", "soja", 1.00, 77),
    ("trigo_soja2", "pastura", 1.05, 40),
    ("pastura", "soja", 1.0, 0), ("pastura", "maiz", 1.0, 0),
    ("pastura", "trigo_soja2", 1.0, 0), ("pastura", "pastura", 1.0, 0),
], columns=["cultivo", "antecesor", "factor", "n_req_kg_ha"])

# Rotación balanceada (≈ 50/50 gramíneas vs. soja, INTA): soja ≤ 35% y gramíneas ≥ 20% del total.
# Pastura ≥ 40%: conservador para la región (solo 29% de la cuenca tiene aptitud agrícola).
# Escenario base sin tope de N ni presupuesto (0 = sin tope); el presupuesto va a sensibilidad.
# Precio N: urea 600 USD/t ÷ 0,46. Precio P: MAP 860 USD/t (CFR) ÷ 0,52. Fuente: Valor Soja / IF, nov 2026.
parametros = pd.DataFrame([
    ("anios", 3, "Horizonte de planificación (años)"),
    ("max_frac_soja", 0.35, "Máx. fracción de la superficie en cultivos del grupo 'soja'"),
    ("min_frac_gramineas", 0.20, "Mín. fracción de la superficie en grupo 'gramínea'"),
    ("min_frac_pastura", 0.40, "Mín. fracción de la superficie en grupo 'pastura'"),
    ("n_max_anual_kg", 0, "Tope de N total por año (kg). Vacío o 0 = sin tope"),
    ("presupuesto_fert_anual_usd", 0, "Presupuesto de fertilizante por año (USD). Vacío o 0 = sin tope"),
    ("precio_n_usd_kg", 1.30, "Precio del N (USD/kg de N)"),
    ("precio_p_usd_kg", 1.65, "Precio del P (USD/kg de P2O5)"),
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
