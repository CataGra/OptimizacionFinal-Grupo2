#extraer_estimacion_agricolas

"""
Convierte el CSV de Estimaciones Agrícolas (Min. de Agricultura) en la hoja
'rendimientos_partido' de datos_ejemplo.xlsx (promedio de las campañas disponibles).

Uso:  python importar_rendimientos.py Estimaciones.csv [datos_ejemplo.xlsx]
"""
import sys
import pandas as pd

csv = sys.argv[1]
xlsx = sys.argv[2] if len(sys.argv) > 2 else "datos_ejemplo.xlsx"

df = pd.read_csv(csv, encoding="latin-1", sep=";")
PRODUCTO = {"Maíz": "maiz", "Soja 1ra": "soja", "Trigo total": "trigo", "Soja 2da": "soja2"}
NOMBRE = {"CHASCOMUS": "Chascomús", "MAIPU": "Maipú"}      # tildes

# Rendimiento 0 = campaña sin siembra / sin dato: se excluye del promedio
df = df[df["Cultivo"].isin(PRODUCTO) & (df["Rendimiento"] > 0)].copy()
df["producto"] = df["Cultivo"].map(PRODUCTO)
df["partido"] = df["Departamento"].map(lambda x: NOMBRE.get(x, x.title()))
df["tn_ha"] = df["Rendimiento"] / 1000                      # kg/ha -> tn/ha

g = (df.groupby(["partido", "producto"])
       .agg(rendimiento_tn_ha=("tn_ha", "mean"), n=("tn_ha", "size"),
            desde=("Campaña", "min"), hasta=("Campaña", "max")).reset_index())
g["rendimiento_tn_ha"] = g["rendimiento_tn_ha"].round(2)
g["fuente"] = ("Min. Agricultura, Estimaciones Agrícolas, promedio " + g["desde"] + " a "
               + g["hasta"] + " (" + g["n"].astype(str) + " campañas)")
out = g[["partido", "producto", "rendimiento_tn_ha", "fuente"]]

hojas = pd.read_excel(xlsx, sheet_name=None)
hojas["rendimientos_partido"] = out
with pd.ExcelWriter(xlsx) as xw:
    for nombre, h in hojas.items():
        h.to_excel(xw, sheet_name=nombre, index=False)
print(out.pivot(index="partido", columns="producto", values="rendimiento_tn_ha"))
print(g.groupby("partido")["n"].min().rename("mín. campañas con dato").to_string())