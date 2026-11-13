"""
Análisis de sensibilidad del modelo de rotación de cultivos (Cuenca del Salado).

Mueve UN parámetro a la vez, re-optimiza con model.py (sin modificarlo) y compara con el
escenario base. Se usa de dos maneras:

  1) Desde la app (pestaña "Sensibilidad"): app.py importa este módulo y llama a analizar().
  2) Por línea de comandos, para generar el Excel y los gráficos del informe:
         python sensibilidad.py
         python sensibilidad.py --partido Rauch
         python sensibilidad.py --excel otro.xlsx --salida otra_carpeta --tlim 120

Cómo leer los resultados:
  - margen_total_usd     : margen bruto de todo el campo en el horizonte (función objetivo).
  - var_margen_pct       : variación respecto del escenario base, en %.
  - decisiones_distintas : cuántas decisiones (lote, año) difieren del plan base. 0 = mismo plan.
  - estado "infactible"  : con ese valor el modelo no tiene solución.
  - Ojo: puede haber planes alternativos con el MISMO margen; si el margen no cambia pero
    decisiones_distintas > 0, es un empate entre planes y no un cambio real de estrategia.
"""
import argparse
import math
import os
import sys

import pandas as pd

import model as M

GRUPOS = {"manejo": "Restricciones de manejo", "suelo": "Suelo y rotación",
          "precios": "Precios e ingresos"}
# Restricciones que se pueden "aflojar" (-1: bajar el valor, +1: subirlo)
DIRECCION = {"min_pastura": -1, "min_gramineas": -1, "max_soja": +1}


# ----------------------------------------------------------------------------
# Formato de valores (decimales con coma, miles con punto)
# ----------------------------------------------------------------------------
def _ar(x, dec=0, trim=True):
    s = f"{x:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if trim and "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def fmt_valor(v, fmt):
    """Texto legible de un valor probado según su tipo (pct, pctbase, mult, dec2, usd)."""
    if fmt == "pct":                       # fracción -> %
        return _ar(100 * v, 1) + " %"
    if fmt == "pctbase":                   # ya viene en %
        return _ar(v, 1) + " %"
    if fmt == "mult":
        return "×" + _ar(v, 2)
    if fmt == "dec2":
        return _ar(v, 2, trim=False)
    if fmt == "usd":
        return _ar(v, 0) + " USD/ha"
    return _ar(v, 2)


# ----------------------------------------------------------------------------
# Modificadores de datos (cada uno trabaja sobre una COPIA de las hojas)
# ----------------------------------------------------------------------------
def set_par(sh, nombre, valor):
    p = sh["parametros"]
    p.loc[p["parametro"] == nombre, "valor"] = float(valor)


def mult_par(sh, nombre, m):
    p = sh["parametros"]
    p.loc[p["parametro"] == nombre, "valor"] = p.loc[p["parametro"] == nombre, "valor"] * m


def mult_precio(productos):
    def f(sh, m):
        pr = sh["precios"]
        mask = pr["producto"].isin(productos)
        pr.loc[mask, "precio_usd_tn"] = pr.loc[mask, "precio_usd_tn"] * m
    return f


def set_factor_clase(clase):
    def f(sh, v):
        fc = sh["factor_clase"]
        fc.loc[fc["clase"] == clase, "factor"] = v
    return f


def set_ingreso_cultivo(cultivo):
    def f(sh, v):
        c = sh["cultivos"]
        c.loc[c["cultivo"] == cultivo, "ingreso_fijo_usd_ha"] = v
    return f


def escala_antecesor(sh, m):
    """Escala el efecto del antecesor: factor = 1 + m * (factor - 1). m=0 lo anula, m=1 es el base."""
    r = sh["rotacion"]
    r["factor"] = 1 + m * (r["factor"] - 1)


def precio_fert(sh, m):
    mult_par(sh, "precio_n_usd_kg", m)
    mult_par(sh, "precio_p_usd_kg", m)


# ----------------------------------------------------------------------------
# Definición de los barridos
# ----------------------------------------------------------------------------
def _con_base(candidatos, base):
    return sorted({round(float(x), 4) for x in candidatos} | {round(float(base), 4)})


def piso_pastura(d):
    """Fracción del campo en lotes donde, por el suelo, solo puede haber pastura."""
    ha = dict(zip(d["lotes"]["lote"], d["lotes"]["ha"]))
    clase = dict(zip(d["lotes"]["lote"], d["lotes"]["clase"]))
    solo = sum(ha[i] for i in ha
               if all(d["grupo"][j] == "pastura" for j in d["cultivos"] if (clase[i], j) in d["apto"]))
    return solo / sum(ha.values())


def clases_variables(sheets, d):
    """Clases de suelo cuyo factor de rendimiento tiene sentido variar: se usan, admiten algún
    cultivo que no sea pastura y no son la clase de referencia (la de mayor factor)."""
    fc = sheets["factor_clase"].set_index("clase")["factor"]
    ref, en_uso, out = fc.max(), set(d["lotes"]["clase"]), []
    for c in fc.index:
        if c not in en_uso or abs(fc[c] - ref) < 1e-9:
            continue
        if any(d["grupo"][j] != "pastura" and (c, j) in d["apto"] for j in d["cultivos"]):
            out.append(c)
    return out


def escenarios(sheets, d, ref_fert):
    """Lista de análisis. 'base' es el valor del escenario base (se marca en gráficos y tablas).
    Los valores base se toman de los datos cargados, así que funciona con cualquier Excel."""
    par, prods, esc = d["par"], set(sheets["precios"]["producto"]), []
    piso = piso_pastura(d)

    if ref_fert > 0:
        esc.append(dict(
            key="presupuesto_fert", grupo="manejo", titulo="Presupuesto de fertilizante",
            eje="% del gasto anual de fertilizante del plan base", fmt="pctbase", base=100,
            valores=[100, 95, 90, 85, 80, 75, 70, 60, 50],
            desc="Tope de gasto anual en fertilizante, como porcentaje del gasto anual más alto del "
                 "plan base. Con 100 % el plan base sigue siendo posible; por debajo, el modelo "
                 "tiene que cambiar de cultivos para gastar menos.",
            f=lambda sh, v: set_par(sh, "presupuesto_fert_anual_usd", ref_fert * v / 100 + 1)))

    b = float(par["min_frac_pastura"])
    piso_v = math.floor(piso * 1e4) / 1e4          # truncado: queda justo por debajo del piso real
    cand = [0.30, 0.50, 0.60, 0.70, 0.80] + ([piso_v] if piso_v > 0 else [])
    esc.append(dict(
        key="min_pastura", grupo="manejo", titulo="Mínimo de pastura",
        eje="fracción mínima de la superficie", fmt="pct", base=b, valores=_con_base(cand, b),
        desc="Superficie mínima que debe quedar con pastura cada año."
             + (f" El {fmt_valor(piso, 'pct')} del campo ya queda en pastura por aptitud del suelo: "
                "ese es el piso real, y todo lo que se exige por encima tiene un costo." if piso > 0 else ""),
        f=lambda sh, v: set_par(sh, "min_frac_pastura", v)))

    b = float(par["max_frac_soja"])
    esc.append(dict(
        key="max_soja", grupo="manejo", titulo="Tope de soja", eje="fracción máxima de la superficie",
        fmt="pct", base=b, valores=_con_base([0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50], b),
        desc="Máxima superficie que puede ocupar el grupo soja (soja y trigo/soja 2ª) cada año.",
        f=lambda sh, v: set_par(sh, "max_frac_soja", v)))

    b = float(par["min_frac_gramineas"])
    esc.append(dict(
        key="min_gramineas", grupo="manejo", titulo="Mínimo de gramíneas",
        eje="fracción mínima de la superficie", fmt="pct", base=b,
        valores=_con_base([0.0, 0.10, 0.20, 0.30, 0.40, 0.50], b),
        desc="Mínima superficie que debe ocupar el grupo gramíneas (maíz) cada año.",
        f=lambda sh, v: set_par(sh, "min_frac_gramineas", v)))

    fc = sheets["factor_clase"].set_index("clase")["factor"]
    for c in clases_variables(sheets, d):
        b = float(fc[c])
        vals = [min(1.5, max(0.1, b + dx)) for dx in (-0.2, -0.1, 0.1, 0.2)]
        esc.append(dict(
            key=f"factor_clase_{c}", grupo="suelo", titulo=f"Rendimiento de la clase {c}",
            eje="factor sobre el rendimiento de la clase de referencia", fmt="dec2", base=b,
            valores=_con_base(vals, b),
            desc=f"Rendimiento de los lotes de clase {c} respecto de la clase de referencia. "
                 "Es un supuesto del modelo, no un dato medido.",
            f=set_factor_clase(c)))

    esc.append(dict(
        key="efecto_antecesor", grupo="suelo", titulo="Efecto del antecesor",
        eje="escala del efecto (0 = sin efecto, 1 = base)", fmt="mult", base=1.0,
        valores=[0.0, 0.5, 1.0, 1.5, 2.0],
        desc="Escala cuánto influye el cultivo anterior en el rendimiento. Con 0 el rendimiento no "
             "depende del antecesor, con 1 es el valor base y con 2 el efecto se duplica.",
        f=escala_antecesor))

    for key, titulo, productos, texto in [
            ("precio_soja", "Precio de la soja", ["soja", "soja2"], "de la soja y la soja de segunda"),
            ("precio_maiz", "Precio del maíz", ["maiz"], "del maíz"),
            ("precio_trigo", "Precio del trigo", ["trigo"], "del trigo")]:
        presentes = [p for p in productos if p in prods]
        if presentes:
            esc.append(dict(
                key=key, grupo="precios", titulo=titulo, eje="multiplicador del precio base",
                fmt="mult", base=1.0, valores=[0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
                desc=f"Precio neto {texto if len(presentes) == len(productos) else 'de la soja'}"
                     ", multiplicado por el factor indicado.",
                f=mult_precio(presentes)))

    esc.append(dict(
        key="precio_fert", grupo="precios", titulo="Precio de los fertilizantes",
        eje="multiplicador del precio base", fmt="mult", base=1.0,
        valores=[0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
        desc="Precio del nitrógeno y del fósforo, multiplicado por el factor indicado.",
        f=precio_fert))

    pj = next((j for j in d["cultivos"] if d["grupo"][j] == "pastura"), None)
    if pj is not None:
        b = float(sheets["cultivos"].set_index("cultivo")["ingreso_fijo_usd_ha"].fillna(0)[pj])
        if b > 0:
            vals = [int(round(b * m / 10.0)) * 10 for m in (0.5, 0.8, 1.3, 1.6, 2.1, 2.65)]
            esc.append(dict(
                key="ingreso_pastura", grupo="precios", titulo="Ingreso de la pastura",
                eje="USD por hectárea y por año", fmt="usd", base=b, valores=_con_base(vals, b),
                desc="Ingreso por hectárea de la pastura (alquiler ganadero). No se modela ganado: "
                     "es un valor fijo por hectárea.",
                f=set_ingreso_cultivo(pj)))
    return esc


# ----------------------------------------------------------------------------
# Resolución y métricas
# ----------------------------------------------------------------------------
def clonar(sheets):
    sh = {k: v.copy() for k, v in sheets.items()}
    sh["parametros"]["valor"] = sh["parametros"]["valor"].astype(float)
    return sh


def resolver(sheets, partido, tlim):
    """Resuelve solo el óptimo. Devuelve (solución o None, datos preparados, estado)."""
    d = M.prepare(sheets, partido)
    sols, msg = M.solve_top_k(d, n_alt=1, min_diff=1, time_limit=tlim)
    return (sols[0] if sols else None), d, msg


def metricas(d, sol):
    ev = M.evaluate(d, sol["plan"])
    area = d["lotes"]["ha"].sum()
    n_anios = ev["año"].nunique()
    share = ev.groupby("cultivo")["ha"].sum() / (area * n_anios)
    fert_anual = ev.groupby("año")["fert_total_usd"].sum()
    fila = dict(margen_total_usd=sol["objetivo"],
                fert_total_usd=ev["fert_total_usd"].sum(),
                fert_max_anual_usd=fert_anual.max())
    for c in d["cultivos"]:
        fila[f"pct_{c}"] = 100 * share.get(c, 0.0)
    return fila, ev


def dif_planes(p1, p2):
    return sum(a != b for i in p1 for a, b in zip(p1[i], p2[i]))


def texto_plan(fila):
    if fila["estado"] != "ok":
        return "Sin solución"
    if fila["es_base"]:
        return "Valor base"
    n = fila["decisiones_distintas"]
    return "Mismo plan que el base" if n == 0 else f"{n} decisión distinta" if n == 1 \
        else f"{n} decisiones distintas"


def correr(sheets, partido, tlim, esc, base_sol, base_obj, avance=None, verbose=False):
    filas = []
    for v in esc["valores"]:
        sh = clonar(sheets)
        esc["f"](sh, v)
        sol, d, msg = resolver(sh, partido, tlim)
        fila = dict(parametro=esc["key"], valor=v, etiqueta=fmt_valor(v, esc["fmt"]),
                    es_base=abs(v - esc["base"]) < 1e-9)
        if sol is None:
            fila.update(estado=msg)
        else:
            m, _ = metricas(d, sol)
            fila.update(estado="ok", **m,
                        var_margen_usd=sol["objetivo"] - base_obj,
                        var_margen_pct=100 * (sol["objetivo"] - base_obj) / base_obj,
                        decisiones_distintas=dif_planes(sol["plan"], base_sol["plan"]))
        fila["plan"] = texto_plan(fila)
        filas.append(fila)
        if verbose:
            print(f"   {esc['key']:<18} {fila['etiqueta']:>12}  ->  "
                  + (f"margen {fila['margen_total_usd']:>12,.0f} USD ({fila['var_margen_pct']:+.1f}%), "
                     f"{fila['plan']}" if sol else "SIN SOLUCIÓN"))
        if avance:
            avance()
    return pd.DataFrame(filas)


def rango_estable(df, base):
    """Valores extremos, contiguos al base, para los que el plan es idéntico al base."""
    df = df.sort_values("valor").reset_index(drop=True)
    ib = df.index[(df["valor"] - base).abs() < 1e-9]
    if len(ib) == 0:
        return None
    lo = hi = ib[0]
    igual = lambda i: df.loc[i, "estado"] == "ok" and df.loc[i, "decisiones_distintas"] == 0
    while lo - 1 >= 0 and igual(lo - 1):
        lo -= 1
    while hi + 1 < len(df) and igual(hi + 1):
        hi += 1
    return df.loc[lo, "valor"], df.loc[hi, "valor"]


def armar_resumen(escs, resultados):
    filas = []
    for e in escs:
        df = resultados[e["key"]]
        ok = df[df["estado"] == "ok"]
        f = lambda x: fmt_valor(x, e["fmt"])
        est = rango_estable(df, e["base"])
        plan_estable = ("—" if est is None else "Solo con el valor base" if est[0] == est[1]
                        else f"{f(est[0])} a {f(est[1])}")
        filas.append(dict(
            parametro=e["key"], titulo=e["titulo"], grupo=e["grupo"], grupo_nombre=GRUPOS[e["grupo"]],
            valor_base=f(e["base"]), rango_probado=f"{f(df['valor'].min())} a {f(df['valor'].max())}",
            var_min_pct=ok["var_margen_pct"].min(), var_max_pct=ok["var_margen_pct"].max(),
            rango_pct=ok["var_margen_pct"].max() - ok["var_margen_pct"].min(),
            plan_estable=plan_estable,
            escenarios_infactibles=int((df["estado"] != "ok").sum()),
            escenarios_plan_distinto=int((ok["decisiones_distintas"] > 0).sum()),
            total_escenarios=len(df)))
    return pd.DataFrame(filas)


def diagnostico_restricciones(escs, resultados, umbral_pct=0.05):
    """¿Cada restricción de manejo realmente limita? Se afloja un paso y se mide cuánto mejora."""
    filas = []
    for e in escs:
        if e["key"] not in DIRECCION:
            continue
        ok = resultados[e["key"]].query("estado == 'ok'")
        sentido = DIRECCION[e["key"]]
        vec = ok[ok["valor"] < e["base"] - 1e-9] if sentido < 0 else ok[ok["valor"] > e["base"] + 1e-9]
        if vec.empty:
            continue
        fila = vec.loc[vec["valor"].idxmax() if sentido < 0 else vec["valor"].idxmin()]
        mej = fila["var_margen_pct"]
        concl = "No limita" if mej <= umbral_pct else "Limita poco" if mej <= 1 else "Limita"
        filas.append(dict(
            parametro=e["key"], restriccion=e["titulo"], valor_actual=fmt_valor(e["base"], e["fmt"]),
            se_afloja_a=fmt_valor(fila["valor"], e["fmt"]), mejora_usd=fila["var_margen_usd"],
            mejora_pct=mej, conclusion=concl))
    return pd.DataFrame(filas, columns=["parametro", "restriccion", "valor_actual", "se_afloja_a",
                                        "mejora_usd", "mejora_pct", "conclusion"])


def plan_base_df(d, sol):
    plan = pd.DataFrame({i: p for i, p in sol["plan"].items()}).T
    plan.columns = [f"año {t}" for t in range(1, plan.shape[1] + 1)]
    lotes = d["lotes"].set_index("lote")
    plan.insert(0, "clase", lotes["clase"])
    plan.insert(1, "ha", lotes["ha"])
    return plan


def analizar(sheets, partido, tlim=60, avance=None, verbose=False):
    """Corre todo el análisis para un partido. 'avance(i, n, texto)' informa el progreso.
    Devuelve un diccionario con el escenario base, los barridos y los resúmenes."""
    sheets = clonar(sheets)
    base_sol, d0, msg = resolver(sheets, partido, tlim)
    if base_sol is None:
        raise ValueError("Con los datos cargados no hay ninguna rotación posible, así que no se "
                         "puede analizar la sensibilidad.")
    base_m, base_ev = metricas(d0, base_sol)
    base_obj = base_sol["objetivo"]
    escs = escenarios(sheets, d0, base_m["fert_max_anual_usd"])
    total, hecho, resultados = sum(len(e["valores"]) for e in escs), [0], {}
    for e in escs:
        def tick(titulo=e["titulo"]):
            hecho[0] += 1
            if avance:
                avance(hecho[0], total, titulo)
        if verbose:
            print(f"> {e['titulo']}")
        resultados[e["key"]] = correr(sheets, partido, tlim, e, base_sol, base_obj, tick, verbose)
    return dict(partido=partido, d=d0, base_sol=base_sol, base_obj=base_obj, base_m=base_m,
                base_ev=base_ev, plan_base=plan_base_df(d0, base_sol), escs=escs,
                resultados=resultados, resumen=armar_resumen(escs, resultados),
                restricciones=diagnostico_restricciones(escs, resultados))


# ----------------------------------------------------------------------------
# Salidas
# ----------------------------------------------------------------------------
def exportar_excel(destino, sens):
    """Escribe el análisis completo en un Excel (ruta o buffer)."""
    with pd.ExcelWriter(destino, engine="openpyxl") as xw:
        sens["resumen"].to_excel(xw, sheet_name="resumen", index=False)
        sens["restricciones"].to_excel(xw, sheet_name="restricciones", index=False)
        sens["plan_base"].reset_index(names="lote").to_excel(xw, sheet_name="plan_base", index=False)
        sens["base_ev"].to_excel(xw, sheet_name="detalle_base", index=False)
        for k, df in sens["resultados"].items():
            df.to_excel(xw, sheet_name=k[:31], index=False)


def graficos(sens, carpeta):
    """Un PNG por parámetro y uno resumen (requiere matplotlib; es opcional)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(matplotlib no está instalado: se omiten los gráficos. "
              "Para generarlos: pip install matplotlib)")
        return
    for esc in sens["escs"]:
        df = sens["resultados"][esc["key"]]
        ok = df[df["estado"] == "ok"]
        fig, ax = plt.subplots(figsize=(6.2, 4))
        ax.plot(ok["valor"], ok["margen_total_usd"] / 1e3, marker="o", color="#2f6b3a")
        ax.axvline(esc["base"], ls="--", color="gray", lw=1)
        ax.set_xlabel(esc["eje"])
        ax.set_ylabel("Margen bruto total (miles de USD)")
        ax.set_title(esc["titulo"], fontsize=11)
        ax.grid(alpha=0.3)
        inf = df[df["estado"] != "ok"]["etiqueta"].tolist()
        if inf:
            fig.text(0.01, 0.01, f"Sin solución con: {inf}", fontsize=8, color="firebrick")
        fig.tight_layout()
        fig.savefig(os.path.join(carpeta, f"sens_{esc['key']}.png"), dpi=150)
        plt.close(fig)

    r = sens["resumen"].sort_values("rango_pct")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.barh(r["titulo"], r["var_max_pct"] - r["var_min_pct"], left=r["var_min_pct"], color="#2f6b3a")
    ax.axvline(0, color="gray", lw=1)
    ax.set_xlabel("Variación del margen total vs. base (%) en el rango probado")
    ax.set_title("Resumen: impacto de cada parámetro\n(los rangos probados no son comparables entre sí)",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(carpeta, "sens_resumen.png"), dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Análisis de sensibilidad del modelo de rotación.")
    ap.add_argument("--excel", default="datos_ejemplo.xlsx")
    ap.add_argument("--partido", default="Chascomús")
    ap.add_argument("--salida", default="resultados_sensibilidad")
    ap.add_argument("--tlim", type=int, default=60, help="límite de tiempo por optimización (s)")
    a = ap.parse_args()

    sheets = M.read_excel(a.excel)
    err = M.validate(sheets)
    if err:
        sys.exit("Errores en el Excel:\n- " + "\n- ".join(err))
    if a.partido not in M.partidos(sheets):
        sys.exit(f"Partido '{a.partido}' no encontrado. Disponibles: {', '.join(M.partidos(sheets))}")
    os.makedirs(a.salida, exist_ok=True)

    print(f"\nPartido: {a.partido}")
    sens = analizar(sheets, a.partido, a.tlim, verbose=True)
    print(f"\nEscenario base: margen total {sens['base_obj']:,.0f} USD | fertilizante máx. anual "
          f"{sens['base_m']['fert_max_anual_usd']:,.0f} USD")
    print("Plan base (cultivo por lote y año):")
    print(sens["plan_base"].to_string(), "\n")
    print("RESUMEN\n" + sens["resumen"].drop(columns=["parametro", "grupo"]).round(2).to_string(index=False))
    print("\nRESTRICCIONES DE MANEJO\n" + sens["restricciones"].round(2).to_string(index=False))

    exportar_excel(os.path.join(a.salida, "sensibilidad.xlsx"), sens)
    graficos(sens, a.salida)
    print(f"\nListo. Resultados en la carpeta '{a.salida}'.")


if __name__ == "__main__":
    main()
