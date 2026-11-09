"""
App web (Streamlit): optimización de rotaciones - Cuenca del Salado.
Ejecutar:  streamlit run app.py
"""
import io
from pathlib import Path

import pandas as pd
import streamlit as st

import model as M

st.set_page_config(page_title="Rotación óptima - Cuenca del Salado", page_icon="🌾", layout="wide")
EJEMPLO = Path(__file__).parent / "datos_ejemplo.xlsx"
COLORES = ["#f6d6a8", "#f9e79f", "#c8e6c9", "#b3d9f2", "#e1bee7", "#ffccbc", "#d7ccc8"]

st.title("🌾 Rotación óptima de cultivos - Cuenca del Salado")
st.caption("Programación lineal mixta (PuLP). Cargá el cultivo anterior de cada lote y obtené "
           "las mejores rotaciones, ordenadas de la más a la menos conveniente.")

# ----------------------------------------------------------------------------
# Sidebar: origen de datos y opciones
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("1. Datos")
    origen = st.radio("Origen", ["Datos de ejemplo", "Subir mi Excel"])
    archivo = EJEMPLO
    if origen == "Subir mi Excel":
        archivo = st.file_uploader("Archivo .xlsx con el formato de la plantilla", type=["xlsx"])
    if EJEMPLO.exists():
        st.download_button("⬇️ Descargar plantilla Excel", EJEMPLO.read_bytes(),
                           file_name="plantilla_rotacion.xlsx")
    st.header("2. Opciones")
    n_alt = st.slider("Cantidad de alternativas", 1, 10, 5)
    min_diff = st.slider("Diferencia mínima entre alternativas", 1, 10, 3,
                         help="Cantidad mínima de decisiones (lote, año) que deben cambiar "
                              "entre una alternativa y la siguiente.")
    t_lim = st.number_input("Tiempo máximo por resolución (s)", 5, 600, 60)

if archivo is None:
    st.info("Subí un archivo Excel desde la barra lateral para empezar.")
    st.stop()

try:
    hojas = M.read_excel(archivo)
except Exception as e:
    st.error(f"No pude leer el archivo: {e}")
    st.stop()
errores = M.validate(hojas)
if errores:
    st.error("Revisá el archivo:\n\n" + "\n".join(f"- {e}" for e in errores))
    st.stop()

# Partido: determina los rendimientos usados por el modelo
lista_partidos = M.partidos(hojas)
partido = st.sidebar.selectbox("Partido", lista_partidos,
                               help="Los rendimientos de cada cultivo dependen del partido.")

# ----------------------------------------------------------------------------
# Entrada: formulario de lotes (editable) y parámetros
# ----------------------------------------------------------------------------
st.subheader("Lotes y cultivo anterior")
st.caption("Editá la tabla: cambiá el cultivo anterior, la superficie o la clase de suelo, "
           "o agregá y quitá lotes.")
clases = sorted(hojas["aptitud"]["clase"].unique())
lotes_ed = st.data_editor(
    hojas["lotes"].dropna(subset=["lote"]), num_rows="dynamic", width="stretch",
    column_config={
        "ha": st.column_config.NumberColumn("Superficie (ha)", min_value=1.0),
        "clase": st.column_config.SelectboxColumn("Clase de suelo", options=clases, required=True),
        "cultivo_anterior": st.column_config.SelectboxColumn(
            "Cultivo anterior", options=list(hojas["cultivos"]["cultivo"]), required=True),
    }, key="lotes_editor")

with st.expander(f"Rendimientos aplicados en {partido} (tn/ha, por clase de suelo)"):
    re_ = M.rend_efectivo(hojas, partido)
    re_.columns = [f"Clase {c}" for c in re_.columns]
    st.dataframe(re_.style.format("{:.2f}"), width="stretch")
    st.caption("Rendimiento del partido x factor de la clase de suelo (hoja 'factor_clase').")

with st.expander("Parámetros de manejo y precios"):
    par_df = hojas["parametros"].copy()
    par_ed = st.data_editor(par_df, width="stretch", hide_index=True,
                            disabled=[c for c in par_df.columns if c != "valor"],
                            key="par_editor")

if st.button("🚀 Optimizar", type="primary"):
    datos = {k: v.copy() for k, v in hojas.items()}
    datos["lotes"], datos["parametros"] = lotes_ed, par_ed
    errores = M.validate(datos)
    if errores:
        st.error("\n".join(f"- {e}" for e in errores))
    else:
        d = M.prepare(datos, partido)
        with st.spinner("Resolviendo..."):
            sols, msg = M.solve_top_k(d, n_alt, min_diff, t_lim)
        if not sols:
            st.error("El modelo es infactible con estos datos. Probá relajar los mínimos "
                     "(gramíneas, pastura), el tope de soja, el presupuesto o el tope de N, "
                     "o revisá que el cultivo anterior tenga rotaciones permitidas.")
            st.session_state.pop("res", None)
        else:
            st.session_state["res"] = dict(d=d, sols=sols, dets=[M.evaluate(d, s["plan"]) for s in sols])

# ----------------------------------------------------------------------------
# Salida
# ----------------------------------------------------------------------------
res = st.session_state.get("res")
if res:
    d, sols, dets = res["d"], res["sols"], res["dets"]
    T = int(d["par"]["anios"])
    best = sols[0]["objetivo"]
    ha_tot = d["lotes"]["ha"].sum()

    st.divider()
    st.subheader(f"Ranking de alternativas - partido de {d['partido']}")
    rank = pd.DataFrame([{
        "Alternativa": f"#{n}" + (" (óptima)" if n == 1 else ""),
        "Margen bruto total (USD)": s["objetivo"],
        "Δ vs óptima (USD)": s["objetivo"] - best,
        "Δ vs óptima (%)": 100 * (s["objetivo"] - best) / best,
        f"Margen USD/ha/año": s["objetivo"] / ha_tot / T,
        "Fertilizante total (USD)": det["fert_total_usd"].sum(),
    } for n, (s, det) in enumerate(zip(sols, dets), start=1)])
    st.dataframe(rank.style.format({
        "Margen bruto total (USD)": "{:,.0f}", "Δ vs óptima (USD)": "{:,.0f}",
        "Δ vs óptima (%)": "{:.2f}%", "Margen USD/ha/año": "{:,.0f}",
        "Fertilizante total (USD)": "{:,.0f}"}), width="stretch", hide_index=True)
    st.bar_chart(rank.set_index("Alternativa")["Margen bruto total (USD)"])

    st.subheader("Detalle de una alternativa")
    sel = st.selectbox("Elegí la alternativa", range(len(sols)),
                       format_func=lambda n: rank.loc[n, "Alternativa"])
    det, plan = dets[sel], sols[sel]["plan"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Margen bruto total", f"USD {sols[sel]['objetivo']:,.0f}")
    c2.metric("Margen promedio", f"USD {sols[sel]['objetivo'] / ha_tot / T:,.0f} /ha/año")
    c3.metric("Gasto en fertilizante", f"USD {det['fert_total_usd'].sum():,.0f}")

    st.markdown("**Plan de rotación por lote**")
    tabla = pd.DataFrame({
        "Superficie (ha)": d["lotes"].set_index("lote")["ha"],
        "Clase": d["lotes"].set_index("lote")["clase"],
        "Año 0 (dato)": d["lotes"].set_index("lote")["cultivo_anterior"],
        **{f"Año {t}": {i: p[t - 1] for i, p in plan.items()} for t in range(1, T + 1)},
    })
    colmap = {c: COLORES[n % len(COLORES)] for n, c in enumerate(d["cultivos"])}
    sty = tabla.style
    aplicar = sty.map if hasattr(sty, "map") else sty.applymap   # compat. pandas < 2.1
    sty = aplicar(
        lambda x: f"background-color: {colmap[x]}" if x in colmap else "",
        subset=["Año 0 (dato)"] + [f"Año {t}" for t in range(1, T + 1)])
    st.dataframe(sty, width="stretch")

    a, b = st.columns(2)
    with a:
        st.markdown("**Superficie por cultivo y año (ha)**")
        sup = det.pivot_table(index="cultivo", columns="año", values="ha", aggfunc="sum", fill_value=0)
        sup.columns = [f"Año {c}" for c in sup.columns]
        st.dataframe(sup.style.format("{:,.0f}"), width="stretch")
    with b:
        st.markdown("**Margen bruto por año (USD)**")
        mar = det.groupby("año")["margen_total_usd"].sum()
        mar.index = [f"Año {t}" for t in mar.index]
        st.bar_chart(mar)

    st.markdown("**Plan de fertilización (kg/ha) y margen por lote y año**")
    st.dataframe(det[["lote", "año", "cultivo", "antecesor", "N_kg_ha", "P2O5_kg_ha",
                      "margen_usd_ha", "margen_total_usd"]].style.format({
        "N_kg_ha": "{:.0f}", "P2O5_kg_ha": "{:.0f}",
        "margen_usd_ha": "{:,.0f}", "margen_total_usd": "{:,.0f}"}),
        width="stretch", hide_index=True)

    # Descarga de resultados
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        rank.to_excel(xw, sheet_name="ranking", index=False)
        for n, x in enumerate(dets, start=1):
            x.to_excel(xw, sheet_name=f"alternativa_{n}", index=False)
    st.download_button("⬇️ Descargar resultados (Excel)", buf.getvalue(), file_name="resultados_rotacion.xlsx")
