"""
App web (Streamlit): optimización de rotaciones - Cuenca del Salado.
Ejecutar:  streamlit run app.py
La estética (colores y fuentes) está en .streamlit/config.toml.
Foto de portada opcional: guardar una imagen como assets/portada.jpg (si no está, se usa
la ilustración en SVG).
"""
import base64
import io
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import model as M

st.set_page_config(page_title="Rotación de cultivos - Cuenca del Salado",
                   page_icon=":material/grass:", layout="wide")
BASE = Path(__file__).parent
EJEMPLO = BASE / "datos_ejemplo.xlsx"
PORTADA = BASE / "assets" / "portada.jpg"

# ----------------------------------------------------------------------------
# Identidad visual: un color por cultivo, usado igual en toda la app
# ----------------------------------------------------------------------------
TEXTO = "#2E3A2F"
VERDE = "#4F6F43"
COLOR = {"pastura": "#5E7F4F", "maiz": "#D9A93B", "soja": "#A8794A", "trigo_soja2": "#C8B273"}
TINTE = {"pastura": "#D5E0CB", "maiz": "#F3E2AE", "soja": "#E6D3BD", "trigo_soja2": "#EEE6CB"}
NOMBRE = {"pastura": "Pastura", "maiz": "Maíz", "soja": "Soja", "trigo_soja2": "Trigo / soja 2ª",
          "soja2": "Soja 2ª", "trigo": "Trigo"}
EXTRA = ["#7C8C9A", "#B4A07A", "#8E9F7C"]          # por si el usuario agrega otros cultivos

# Parámetros: nombre legible, unidad y factor para mostrarlos (fracciones como %)
PARAM = {
    "anios": ("Horizonte de planificación", "años", 1),
    "max_frac_soja": ("Tope de soja", "% de la superficie", 100),
    "min_frac_gramineas": ("Mínimo de gramíneas", "% de la superficie", 100),
    "min_frac_pastura": ("Mínimo de pastura", "% de la superficie", 100),
    "n_max_anual_kg": ("Tope de nitrógeno por año", "kg (0 = sin tope)", 1),
    "presupuesto_fert_anual_usd": ("Presupuesto de fertilizante por año", "USD (0 = sin tope)", 1),
    "precio_n_usd_kg": ("Precio del nitrógeno", "USD/kg de N", 1),
    "precio_p_usd_kg": ("Precio del fósforo", "USD/kg de P₂O₅", 1),
}


def color(c):
    return COLOR.get(c, EXTRA[hash(c) % len(EXTRA)])


def tinte(c):
    return TINTE.get(c, "#ECECE6")


def nombre(c):
    return NOMBRE.get(c, str(c).replace("_", " ").capitalize())


def num(x, dec=0):
    """Número con formato argentino: 1.437.607 / 12,5."""
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# etiqueta de ejes de Altair con separador de miles argentino
EJE_AR = "replace(format(datum.value, ',.0f'), /,/g, '.')"


def lista(partes):
    partes = [p for p in partes if p]
    return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


# ----------------------------------------------------------------------------
# Estilos generales (ancho de lectura, encabezado, pie)
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 1.5rem; padding-bottom: 2rem;}
header[data-testid="stHeader"] {background: transparent;}
.portada {position: relative; border-radius: 10px; overflow: hidden; min-height: 330px;
          background-size: cover; background-position: center 60%; margin-bottom: 1.6rem;}
.portada::after {content: ""; position: absolute; inset: 0;
          background: linear-gradient(90deg, rgba(28,38,26,.78) 0%, rgba(28,38,26,.45) 45%,
                                      rgba(28,38,26,0) 75%);}
.portada .texto {position: relative; z-index: 1; padding: 54px 48px; max-width: 700px; color: #fff;}
.portada h1 {font-family: "Newsreader", serif; font-weight: 600; font-size: 2.9rem;
          line-height: 1.08; margin: 0 0 14px; color: #fff; padding: 0;}
.portada p {font-size: 1.08rem; line-height: 1.55; margin: 0 0 22px; color: #F1F3EC;}
.portada .datos {display: flex; gap: 36px; flex-wrap: wrap; max-width: 640px;}
.portada .datos div {font-size: .9rem; color: #E4E8DD; line-height: 1.3;}
.portada .datos b {display: block; font-size: 1.35rem; color: #fff; font-weight: 600;}
.paso {color: #6B776A; font-size: .95rem; margin: -0.4rem 0 0.8rem;}
.resumen {background: #fff; border: 1px solid #DDE3D6; border-left: 4px solid #4F6F43;
          border-radius: 8px; padding: 18px 22px; line-height: 1.65; max-width: 860px;}
.resumen p {margin: 0 0 6px;}
.vacio {border: 1px dashed #C9D2C0; border-radius: 8px; padding: 22px 24px; color: #5B665A;
        max-width: 860px; line-height: 1.6;}
.pie {margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid #DDE3D6; color: #6B776A;
      font-size: .85rem; line-height: 1.6;}
@media (max-width: 700px) {.portada .texto {padding: 32px 22px;} .portada h1 {font-size: 2rem;}}
</style>""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Portada: paisaje del Salado en SVG (atardecer, lotes en perspectiva, montes)
# con un movimiento suave de los cultivos del frente y del sol
# ----------------------------------------------------------------------------
def paisaje_svg():
    W, H, hz, vx = 1200, 360, 176, 760          # ancho, alto, horizonte, punto de fuga
    lotes = [("#D9A93B", -400), ("#5E7F4F", -60), ("#C8B273", 260), ("#A8794A", 560),
             ("#5E7F4F", 860), ("#D9A93B", 1150), ("#C8B273", 1500)]
    capas = []
    # lotes en perspectiva: franjas que convergen al punto de fuga
    for (col, x0), (_, x1) in zip(lotes, lotes[1:] + [(None, 1900)]):
        capas.append(f'<polygon points="{vx},{hz} {x0},{H} {x1},{H}" fill="{col}"/>')
    # surcos
    for i in range(-40, 120):
        xb = -500 + i * 22
        capas.append(f'<line x1="{vx}" y1="{hz}" x2="{xb}" y2="{H}" stroke="#1F2A1D" '
                     f'stroke-opacity="0.13" stroke-width="1.4"/>')
    # espigas en primer plano (se mecen)
    espigas = []
    for i in range(70):
        x = i * 18 + (i % 3) * 5
        h = 40 + (i * 37) % 30
        espigas.append(f'<path d="M{x},{H} q4,-{h / 2} 2,-{h}" stroke="#B8962F" stroke-width="2.2" '
                       f'fill="none"/><ellipse cx="{x + 2}" cy="{H - h}" rx="3.2" ry="9" fill="#D9B55A"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">
<defs>
  <linearGradient id="cielo" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#8FAAB8"/><stop offset=".55" stop-color="#E7C99A"/>
    <stop offset="1" stop-color="#F4D9A0"/></linearGradient>
  <radialGradient id="halo"><stop offset="0" stop-color="#FFF4D6" stop-opacity=".95"/>
    <stop offset="1" stop-color="#FFE7B0" stop-opacity="0"/></radialGradient>
  <linearGradient id="bruma" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#F4D9A0" stop-opacity=".75"/>
    <stop offset="1" stop-color="#F4D9A0" stop-opacity="0"/></linearGradient>
  <style>
    .mecer {{transform-origin: 50% 100%; animation: mecer 7s ease-in-out infinite;}}
    .sol {{animation: brillo 9s ease-in-out infinite;}}
    @keyframes mecer {{0%,100% {{transform: skewX(0deg);}} 50% {{transform: skewX(-3deg);}}}}
    @keyframes brillo {{0%,100% {{opacity: .85;}} 50% {{opacity: 1;}}}}
    @media (prefers-reduced-motion: reduce) {{.mecer, .sol {{animation: none;}}}}
  </style>
</defs>
<rect width="{W}" height="{hz + 2}" fill="url(#cielo)"/>
<g class="sol"><circle cx="{vx + 120}" cy="{hz - 14}" r="120" fill="url(#halo)"/>
  <circle cx="{vx + 120}" cy="{hz - 14}" r="22" fill="#FFF1CF"/></g>
<path d="M0,{hz} L0,{hz - 8} q30,-14 60,-6 q20,-18 48,-4 q26,-10 40,2 L260,{hz - 4} q40,-20 80,-8
  q18,-10 34,0 L520,{hz - 2} q30,-16 70,-6 q24,-12 44,2 L1000,{hz - 4} q36,-22 80,-10 q30,-8 50,4
  L{W},{hz - 6} L{W},{hz} Z" fill="#40553A"/>
{"".join(capas)}
<rect y="{hz}" width="{W}" height="40" fill="url(#bruma)"/>
<g class="mecer">{"".join(espigas)}</g>
</svg>'''


def portada():
    if PORTADA.exists():
        fondo = f"data:image/jpeg;base64,{base64.b64encode(PORTADA.read_bytes()).decode()}"
    else:
        fondo = f"data:image/svg+xml;base64,{base64.b64encode(paisaje_svg().encode()).decode()}"
    st.markdown(f"""
<div class="portada" style="background-image:url('{fondo}')" role="img"
     aria-label="Campo de cultivos en la Cuenca del Salado">
  <div class="texto">
    <h1>Rotación de cultivos en la Cuenca del Salado</h1>
    <p>Planificá qué sembrar en cada lote durante los próximos tres años para obtener el mayor
       margen bruto, sin repetir cultivos y respetando la aptitud de cada suelo.</p>
    <div class="datos">
      <div><b>12</b>partidos con rendimientos reales</div>
      <div><b>4</b>cultivos en rotación</div>
      <div><b>Sep 2026</b>precios y costos del Ministerio</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)


def leyenda(cultivos):
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:18px">'
        f'<span style="width:14px;height:14px;border-radius:3px;background:{color(c)}"></span>'
        f'{nombre(c)}</span>' for c in cultivos)
    st.html(f'<div style="font-size:0.9rem;color:{TEXTO};margin:4px 0 10px">{chips}</div>')


def resumen(d, plan, det, sols, sel, ha_tot, T):
    """Texto accionable con lo que dice la alternativa elegida."""
    obj = sols[sel]["objetivo"]
    sup = det.groupby(["año", "cultivo"])["ha"].sum()
    orden = [c for c in COLOR if c != "pastura"] + [c for c in sup.index.get_level_values(1).unique()
                                                    if c not in COLOR]
    lineas = []
    for t in range(1, T + 1):
        s = sup.loc[t]
        agri = [f"{num(s[c])} ha de {nombre(c).lower()}" for c in orden if c in s and s[c] > 0]
        pas = s.get("pastura", 0)
        lineas.append(f"<p><b>Año {t}:</b> {lista(agri)}"
                      + (f"; {num(pas)} ha quedan con pastura." if pas else "."))
    titulo = "La rotación óptima" if sel == 0 else f"La alternativa #{sel + 1}"
    txt = (f"<p>{titulo} deja un margen bruto de <b>USD {num(obj)}</b> en {T} años "
           f"(USD {num(obj / ha_tot / T)} por hectárea y por año).</p>" + "".join(lineas))
    # ¿hay una alternativa casi igual que gaste menos fertilizante?
    if sel == 0 and len(sols) > 1:
        f0 = det["fert_total_usd"].sum()
        mejores = [(n, sols[n]["objetivo"], res_dets[n]["fert_total_usd"].sum())
                   for n in range(1, len(sols))]
        mejores = [m for m in mejores if m[2] < f0 and (obj - m[1]) / obj < 0.01]
        if mejores:
            n, o, f = max(mejores, key=lambda m: f0 - m[2])
            txt += (f"<p style='margin-top:10px'>Para gastar menos en fertilizante, la "
                    f"alternativa #{n + 1} deja casi lo mismo (USD {num(obj - o)} menos) y ahorra "
                    f"USD {num(f0 - f)} en fertilizante.</p>")
    st.markdown(f'<div class="resumen">{txt}</div>', unsafe_allow_html=True)


portada()

# ----------------------------------------------------------------------------
# Barra lateral
# ----------------------------------------------------------------------------
with st.sidebar:
    st.header("Datos", anchor=False)
    origen = st.radio("Origen", ["Datos de ejemplo", "Subir mi Excel"],
                      help="Los datos de ejemplo son un establecimiento típico de la zona con "
                           "precios, costos y rendimientos reales.")
    archivo = EJEMPLO
    if origen == "Subir mi Excel":
        archivo = st.file_uploader("Archivo .xlsx con el formato de la plantilla", type=["xlsx"])
    lugar_partido = st.container()
    if EJEMPLO.exists():
        st.download_button("Descargar plantilla Excel", EJEMPLO.read_bytes(),
                           file_name="plantilla_rotacion.xlsx", icon=":material/download:")
    st.header("Opciones", anchor=False)
    n_alt = st.slider("Cantidad de alternativas", 1, 10, 5,
                      help="Además de la óptima, la app busca las siguientes mejores rotaciones.")
    with st.expander("Opciones avanzadas"):
        min_diff = st.slider("Diferencia mínima entre alternativas", 1, 10, 3,
                             help="Cantidad mínima de decisiones (lote, año) que deben cambiar "
                                  "entre una alternativa y la siguiente.")
        t_lim = st.number_input("Tiempo máximo por cálculo (s)", 5, 600, 60)

if archivo is None:
    st.info("Subí un archivo Excel desde la barra lateral para empezar.")
    st.stop()

try:
    hojas = M.read_excel(archivo)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()
errores = M.validate(hojas)
if errores:
    st.error("Revisá el archivo:\n\n" + "\n".join(f"- {e}" for e in errores))
    st.stop()

lista_partidos = M.partidos(hojas)
with lugar_partido:
    partido = st.selectbox("Partido", lista_partidos,
                           index=lista_partidos.index("Chascomús") if "Chascomús" in lista_partidos else 0,
                           help="Los rendimientos de cada cultivo dependen del partido.")

# ----------------------------------------------------------------------------
# Entrada: lotes y parámetros
# ----------------------------------------------------------------------------
st.subheader("Lotes y cultivo anterior", anchor=False)
st.markdown('<p class="paso">Editá la tabla: cambiá el cultivo anterior, la superficie o la clase '
            'de suelo, o agregá y quitá lotes.</p>', unsafe_allow_html=True)
clases = sorted(hojas["aptitud"]["clase"].unique())
lotes_ed = st.data_editor(
    hojas["lotes"].dropna(subset=["lote"]), num_rows="dynamic", width="stretch",
    column_config={
        "lote": st.column_config.TextColumn("Lote"),
        "ha": st.column_config.NumberColumn("Superficie (ha)", min_value=1.0, format="%d"),
        "clase": st.column_config.SelectboxColumn("Clase de suelo", options=clases, required=True),
        "cultivo_anterior": st.column_config.SelectboxColumn(
            "Cultivo anterior", options=list(hojas["cultivos"]["cultivo"]), required=True,
            format_func=nombre),
    }, key="lotes_editor")

# parámetros en formato legible (las fracciones se muestran como %)
par_df = hojas["parametros"].copy()
vista = pd.DataFrame({
    "Parámetro": [PARAM.get(p, (p,))[0] for p in par_df["parametro"]],
    "Valor": [float(v) * PARAM.get(p, (p, "", 1))[2] for p, v in zip(par_df["parametro"], par_df["valor"])],
    "Unidad": [PARAM.get(p, (p, ""))[1] for p in par_df["parametro"]],
})

c_izq, c_der = st.columns(2)
with c_izq.expander(f"Rendimientos en {partido} (tn/ha)"):
    re_ = M.rend_efectivo(hojas, partido)
    re_.columns = [f"Clase {c}" for c in re_.columns]
    re_.index = [nombre(i) for i in re_.index]
    st.dataframe(re_.style.format(lambda v: num(v, 2)), width="stretch")
    st.caption("Rendimiento del partido multiplicado por el factor de la clase de suelo.")
with c_der.expander("Parámetros de manejo y precios"):
    vista_ed = st.data_editor(vista, width="stretch", hide_index=True,
                              disabled=["Parámetro", "Unidad"],
                              column_config={"Valor": st.column_config.NumberColumn(format="localized")},
                              key="par_editor")
    st.caption("Los topes y mínimos son porcentajes de la superficie total del campo.")
par_ed = par_df.copy()
par_ed["valor"] = [v / PARAM.get(p, (p, "", 1))[2] for p, v in zip(par_df["parametro"], vista_ed["Valor"])]

if st.button("Calcular rotaciones", type="primary", icon=":material/calculate:"):
    datos = {k: v.copy() for k, v in hojas.items()}
    datos["lotes"], datos["parametros"] = lotes_ed, par_ed
    errores = M.validate(datos)
    if errores:
        st.error("\n".join(f"- {e}" for e in errores))
    else:
        d = M.prepare(datos, partido)
        with st.spinner("Buscando las mejores rotaciones..."):
            sols, msg = M.solve_top_k(d, n_alt, min_diff, t_lim)
        if not sols:
            st.error("No hay ninguna rotación posible con estos datos. Probá relajar los mínimos "
                     "de gramíneas o pastura, el tope de soja, el presupuesto o el tope de N, "
                     "o revisá que el cultivo anterior de cada lote tenga rotaciones permitidas.")
            st.session_state.pop("res", None)
        else:
            st.session_state["res"] = dict(d=d, sols=sols, dets=[M.evaluate(d, s["plan"]) for s in sols])

# ----------------------------------------------------------------------------
# Resultados
# ----------------------------------------------------------------------------
res = st.session_state.get("res")
if not res:
    st.markdown('<div class="vacio">Cuando calcules, acá vas a ver el plan de siembra de cada lote '
                'para los próximos tres años, el margen bruto esperado, el plan de fertilización y '
                'un ranking de alternativas parecidas para comparar.</div>', unsafe_allow_html=True)
else:
    d, sols, dets = res["d"], res["sols"], res["dets"]
    res_dets = dets
    T = int(d["par"]["anios"])
    best = sols[0]["objetivo"]
    ha_tot = d["lotes"]["ha"].sum()

    st.divider()
    st.header(f"Resultados para {d['partido']}", anchor=False)

    rank = pd.DataFrame([{
        "Alternativa": f"#{n}" + (" (óptima)" if n == 1 else ""),
        "Margen bruto total (USD)": s["objetivo"],
        "Diferencia con la óptima (USD)": s["objetivo"] - best,
        "Diferencia (%)": 100 * (s["objetivo"] - best) / best,
        "Margen (USD/ha/año)": s["objetivo"] / ha_tot / T,
        "Fertilizante total (USD)": det["fert_total_usd"].sum(),
    } for n, (s, det) in enumerate(zip(sols, dets), start=1)])

    sel = st.selectbox("Alternativa a analizar", range(len(sols)),
                       format_func=lambda n: rank.loc[n, "Alternativa"])
    det, plan = dets[sel], sols[sel]["plan"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"Margen bruto en {T} años (USD)", num(sols[sel]["objetivo"]), border=True)
    m2.metric("Margen promedio (USD/ha/año)", num(sols[sel]["objetivo"] / ha_tot / T), border=True)
    m3.metric("Gasto en fertilizante (USD)", num(det["fert_total_usd"].sum()), border=True)
    m4.metric(f"Superficie ({len(d['lotes'])} lotes)", f"{num(ha_tot)} ha", border=True)

    resumen(d, plan, det, sols, sel, ha_tot, T)
    st.write("")

    t_plan, t_rank, t_sup, t_fert = st.tabs(["Plan de rotación", "Ranking de alternativas",
                                              "Superficie y márgenes", "Fertilización"])

    with t_plan:
        anos = [f"Año {t}" for t in range(1, T + 1)]
        L = d["lotes"].set_index("lote")
        tabla = pd.DataFrame({
            "Superficie (ha)": L["ha"],
            "Clase": L["clase"],
            "Año 0 (dato)": L["cultivo_anterior"].map(nombre),
            **{f"Año {t}": {i: nombre(p[t - 1]) for i, p in plan.items()} for t in range(1, T + 1)},
        })
        cols_cult = ["Año 0 (dato)"] + anos
        clave = {nombre(c): c for c in set(L["cultivo_anterior"]) | {c for p in plan.values() for c in p}}
        leyenda(sorted(clave.values(), key=lambda c: list(COLOR).index(c) if c in COLOR else 99))
        sty = tabla.style
        aplicar = sty.map if hasattr(sty, "map") else sty.applymap   # compat. pandas < 2.1
        sty = aplicar(lambda x: f"background-color: {tinte(clave.get(x, x))}; color: {TEXTO}",
                      subset=cols_cult)
        sty = sty.format({"Superficie (ha)": num})
        st.dataframe(sty, width="stretch")
        st.caption("El año 0 es el cultivo de la campaña anterior, que se carga como dato.")

    with t_rank:
        st.dataframe(rank.style.format({
            "Margen bruto total (USD)": num, "Diferencia con la óptima (USD)": num,
            "Diferencia (%)": lambda v: num(v, 2) + " %", "Margen (USD/ha/año)": num,
            "Fertilizante total (USD)": num}), width="stretch", hide_index=True)
        graf = alt.Chart(rank).mark_bar(color=VERDE, cornerRadiusEnd=2).encode(
            y=alt.Y("Alternativa:N", sort=None, title=None),
            x=alt.X("Diferencia con la óptima (USD):Q", title="Diferencia con la óptima (USD)",
                    axis=alt.Axis(labelExpr=EJE_AR)),
            tooltip=[alt.Tooltip("Alternativa:N"),
                     alt.Tooltip("Diferencia con la óptima (USD):Q", format=",.0f")],
        ).properties(height=40 * len(rank) + 30)
        st.altair_chart(graf, width="stretch")
        st.caption("Las alternativas suelen quedar muy cerca de la óptima: elegir otra puede convenir "
                   "si, por ejemplo, usa menos fertilizante.")

    with t_sup:
        a, b = st.columns(2)
        sup = det.groupby(["año", "cultivo"], as_index=False)["ha"].sum()
        sup["Año"] = "Año " + sup["año"].astype(str)
        sup["Cultivo"] = sup["cultivo"].map(nombre)
        dominio = [nombre(c) for c in COLOR] + [nombre(c) for c in sup["cultivo"].unique() if c not in COLOR]
        rango = list(COLOR.values()) + [color(c) for c in sup["cultivo"].unique() if c not in COLOR]
        with a:
            st.markdown("**Superficie por cultivo (ha)**")
            st.altair_chart(alt.Chart(sup).mark_bar().encode(
                x=alt.X("Año:N", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("ha:Q", title="Hectáreas", stack="zero", axis=alt.Axis(labelExpr=EJE_AR)),
                color=alt.Color("Cultivo:N", scale=alt.Scale(domain=dominio, range=rango),
                                legend=alt.Legend(orient="bottom", title=None)),
                tooltip=["Año", "Cultivo", alt.Tooltip("ha:Q", format=",.0f")],
            ).properties(height=300), width="stretch")
        with b:
            st.markdown("**Margen bruto por año (USD)**")
            mar = det.groupby("año", as_index=False)["margen_total_usd"].sum()
            mar["Año"] = "Año " + mar["año"].astype(str)
            st.altair_chart(alt.Chart(mar).mark_bar(color=VERDE).encode(
                x=alt.X("Año:N", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("margen_total_usd:Q", title="USD", axis=alt.Axis(labelExpr=EJE_AR)),
                tooltip=["Año", alt.Tooltip("margen_total_usd:Q", title="Margen", format=",.0f")],
            ).properties(height=300), width="stretch")

    with t_fert:
        fert = det[["lote", "año", "cultivo", "antecesor", "N_kg_ha", "P2O5_kg_ha",
                    "margen_usd_ha", "margen_total_usd"]].copy()
        fert["cultivo"] = fert["cultivo"].map(nombre)
        fert["antecesor"] = fert["antecesor"].map(nombre)
        fert = fert.rename(columns={
            "lote": "Lote", "año": "Año", "cultivo": "Cultivo", "antecesor": "Antecesor",
            "N_kg_ha": "N (kg/ha)", "P2O5_kg_ha": "P₂O₅ (kg/ha)",
            "margen_usd_ha": "Margen (USD/ha)", "margen_total_usd": "Margen del lote (USD)"})
        st.dataframe(fert.style.format({
            "N (kg/ha)": num, "P₂O₅ (kg/ha)": num,
            "Margen (USD/ha)": num, "Margen del lote (USD)": num}),
            width="stretch", hide_index=True)
        st.caption("Dosis mínimas para cubrir el requerimiento de cada cultivo según su antecesor.")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        rank.to_excel(xw, sheet_name="ranking", index=False)
        for n, x in enumerate(dets, start=1):
            x.to_excel(xw, sheet_name=f"alternativa_{n}", index=False)
    st.download_button("Descargar resultados (Excel)", buf.getvalue(),
                       file_name="resultados_rotacion.xlsx", icon=":material/download:")

# ----------------------------------------------------------------------------
# Pie de página
# ----------------------------------------------------------------------------
st.markdown("""
<div class="pie">
  <b>Fuentes de datos.</b> Precios, costos y márgenes: Ministerio de Agricultura, Ganadería y Pesca,
  <i>Resultados Agrícolas</i>, septiembre 2026, región Cuenca del Salado. Rendimientos: Estimaciones
  Agrícolas por departamento, campañas 2020/21 a 2025/26. Fertilizantes: Valor Soja e IF Ingeniería
  en Fertilizantes, noviembre 2026. Hacienda: Mercado Agroganadero de Cañuelas. Pasturas y
  leguminosas: INTA EEA Cuenca del Salado.<br>
  Trabajo de Aplicación Final de Optimización, Grupo 2. Modelo de programación lineal entera
  mixta resuelto con PuLP y CBC.
</div>""", unsafe_allow_html=True)