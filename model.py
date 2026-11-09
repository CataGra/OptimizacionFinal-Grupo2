"""
Modelo PLM de rotación de cultivos (PuLP) - Cuenca del Salado.

Variables:
  z[i,j,t]   binaria  : lote i siembra el cultivo j en el año t
  v[i,j,k,t] continua : "j en t con antecesor k en t-1" (0/1 por construcción)
  N[i,t], P[i,t] continuas: kg/ha de N y P2O5

El cultivo anterior del año 0 es un DATO binario (cultivo_anterior de cada lote).
Se resuelve el óptimo y luego se agregan cortes "no-good" para obtener las
siguientes mejores alternativas (ranking de más a menos óptima).
"""
import pandas as pd
import pulp

REQUIRED = {
    "lotes": ["lote", "ha", "clase", "cultivo_anterior"],
    "aptitud": ["clase", "cultivo", "apto"],
    "cultivos": ["cultivo", "grupo", "costo_usd_ha", "p_req_kg_ha", "ingreso_fijo_usd_ha"],
    "composicion": ["cultivo", "producto"],
    "precios": ["producto", "precio_usd_tn"],
    "rendimientos_partido": ["partido", "producto", "rendimiento_tn_ha"],
    "factor_clase": ["clase", "factor"],
    "rotacion": ["cultivo", "antecesor", "factor", "n_req_kg_ha"],
    "parametros": ["parametro", "valor"],
}
PARAMS_REQ = ["anios", "max_frac_soja", "min_frac_gramineas", "min_frac_pastura",
              "n_max_anual_kg", "presupuesto_fert_anual_usd",
              "precio_n_usd_kg", "precio_p_usd_kg"]


# ----------------------------------------------------------------------------
# Lectura y validación de datos
# ----------------------------------------------------------------------------
def read_excel(src):
    """Lee todas las hojas del Excel (ruta o archivo subido)."""
    return pd.read_excel(src, sheet_name=None)


def validate(sheets):
    """Devuelve una lista de errores (vacía si todo está bien)."""
    err = []
    for sh, cols in REQUIRED.items():
        if sh not in sheets:
            err.append(f"Falta la hoja '{sh}'.")
            continue
        miss = [c for c in cols if c not in sheets[sh].columns]
        if miss:
            err.append(f"En la hoja '{sh}' faltan las columnas: {', '.join(miss)}.")
    if err:
        return err

    lotes, cult = sheets["lotes"].dropna(subset=["lote"]), sheets["cultivos"]
    if lotes.empty:
        err.append("No hay lotes cargados.")
        return err
    if lotes["lote"].astype(str).duplicated().any():
        err.append("Hay nombres de lote repetidos.")
    if lotes[["ha", "clase", "cultivo_anterior"]].isna().any().any():
        err.append("Hay lotes con superficie, clase o cultivo anterior vacíos.")
    elif (pd.to_numeric(lotes["ha"], errors="coerce").fillna(0) <= 0).any():
        err.append("Todas las superficies (ha) deben ser mayores que 0.")
    bad = set(lotes["cultivo_anterior"].dropna()) - set(cult["cultivo"])
    if bad:
        err.append(f"Cultivo anterior desconocido: {', '.join(map(str, bad))}.")
    clases = set(sheets["aptitud"]["clase"])
    bad = set(lotes["clase"].dropna()) - clases
    if bad:
        err.append(f"Clase de suelo sin aptitud definida: {', '.join(map(str, bad))}.")
    falt = [p for p in PARAMS_REQ if p not in set(sheets["parametros"]["parametro"])]
    if falt:
        err.append(f"Faltan parámetros: {', '.join(falt)}.")
    prod = set(sheets["composicion"]["producto"])
    f = prod - set(sheets["precios"]["producto"])
    if f:
        err.append(f"Faltan precios en 'precios' para: {', '.join(sorted(f))}.")
    rp = sheets["rendimientos_partido"]
    for p in rp["partido"].dropna().unique():
        f = prod - set(rp.loc[rp["partido"] == p, "producto"])
        if f:
            err.append(f"Partido {p}: faltan rendimientos de {', '.join(sorted(f))}.")
    f = set(sheets["aptitud"]["clase"]) - set(sheets["factor_clase"]["clase"])
    if f:
        err.append(f"Faltan clases en 'factor_clase': {', '.join(sorted(map(str, f)))}.")
    f = set(sheets["composicion"]["cultivo"]) - set(cult["cultivo"])
    if f:
        err.append(f"'composicion' menciona cultivos inexistentes: {', '.join(sorted(f))}.")
    return err


def partidos(sheets):
    """Lista de partidos disponibles en la hoja rendimientos_partido."""
    return sorted(sheets["rendimientos_partido"]["partido"].dropna().unique())


def rend_efectivo(sheets, partido):
    """Rendimiento (tn/ha) por producto y clase de suelo para un partido."""
    rp = sheets["rendimientos_partido"]
    base = rp[rp["partido"] == partido].set_index("producto")["rendimiento_tn_ha"]
    fc = sheets["factor_clase"].set_index("clase")["factor"]
    return pd.DataFrame({c: base * f for c, f in fc.items()})


def prepare(sheets, partido):
    """Convierte las hojas en las estructuras que usa el modelo, para un partido.

    ingreso(clase, cultivo) = factor_clase * sum(rend_partido[producto] * precio[producto])
                              + ingreso_fijo (ej. valor del forraje de la pastura)
    """
    lotes = sheets["lotes"].dropna(subset=["lote"]).copy()
    lotes["lote"] = lotes["lote"].astype(str)
    lotes["ha"] = lotes["ha"].astype(float)
    cult = sheets["cultivos"].set_index("cultivo")
    par = dict(zip(sheets["parametros"]["parametro"], sheets["parametros"]["valor"]))
    rot = sheets["rotacion"]
    precio = dict(zip(sheets["precios"]["producto"], sheets["precios"]["precio_usd_tn"]))
    rp = sheets["rendimientos_partido"]
    rend = dict(zip(rp.loc[rp["partido"] == partido, "producto"],
                    rp.loc[rp["partido"] == partido, "rendimiento_tn_ha"]))
    fc = dict(zip(sheets["factor_clase"]["clase"], sheets["factor_clase"]["factor"]))
    comp = sheets["composicion"].groupby("cultivo")["producto"].apply(list).to_dict()
    fijo = cult["ingreso_fijo_usd_ha"].fillna(0).to_dict()
    ingreso = {(c, j): fc[c] * sum(rend[p] * precio[p] for p in comp.get(j, [])) + fijo[j]
               for c in fc for j in cult.index}
    return dict(
        lotes=lotes,
        partido=partido,
        cultivos=list(cult.index),
        grupo=cult["grupo"].to_dict(),
        costo=cult["costo_usd_ha"].to_dict(),
        preq=cult["p_req_kg_ha"].to_dict(),
        apto={(r.clase, r.cultivo) for r in sheets["aptitud"].itertuples() if int(r.apto) == 1},
        ingreso=ingreso,
        factor={(r.cultivo, r.antecesor): float(r.factor) for r in rot.itertuples()},
        nreq={(r.cultivo, r.antecesor): float(r.n_req_kg_ha) for r in rot.itertuples()},
        par=par,
    )


def _limit(par, key):
    """Parámetro opcional: vacío o <= 0 significa 'sin restricción'."""
    v = par.get(key)
    return None if v is None or pd.isna(v) or float(v) <= 0 else float(v)


# ----------------------------------------------------------------------------
# Modelo
# ----------------------------------------------------------------------------
def solve_top_k(d, n_alt=5, min_diff=3, time_limit=60):
    """Resuelve el óptimo y las siguientes n_alt-1 mejores alternativas.

    min_diff: mínimo de decisiones (lote, año) que deben diferir entre alternativas.
    Devuelve (lista de soluciones, mensaje de estado).
    """
    par = d["par"]
    T = list(range(1, int(par["anios"]) + 1))
    L = list(d["lotes"]["lote"])
    C = d["cultivos"]
    ha = dict(zip(d["lotes"]["lote"], d["lotes"]["ha"]))
    clase = dict(zip(d["lotes"]["lote"], d["lotes"]["clase"]))
    ant0 = dict(zip(d["lotes"]["lote"], d["lotes"]["cultivo_anterior"]))
    area_total = sum(ha.values())
    cN, cP = float(par["precio_n_usd_kg"]), float(par["precio_p_usd_kg"])

    viables = {i: [j for j in C if (clase[i], j) in d["apto"]] for i in L}
    idx = {i: n for n, i in enumerate(L)}
    cid = {j: n for n, j in enumerate(C)}

    m = pulp.LpProblem("Rotacion", pulp.LpMaximize)
    z = {(i, j, t): pulp.LpVariable(f"z_{idx[i]}_{cid[j]}_{t}", cat="Binary")
         for i in L for j in viables[i] for t in T}
    v = {(i, j, k, t): pulp.LpVariable(f"v_{idx[i]}_{cid[j]}_{cid[k]}_{t}", 0, 1)
         for i in L for j in viables[i] for k in C if (j, k) in d["factor"] for t in T}
    Nv = {(i, t): pulp.LpVariable(f"N_{idx[i]}_{t}", 0) for i in L for t in T}
    Pv = {(i, t): pulp.LpVariable(f"P_{idx[i]}_{t}", 0) for i in L for t in T}

    def previo(i, k, t):
        if t == 1:                                   # dato binario del cultivo anterior
            return 1 if ant0[i] == k else 0
        return z[(i, k, t - 1)] if k in viables[i] else 0

    m += (pulp.lpSum(ha[i] * (d["ingreso"][(clase[i], j)] * d["factor"][(j, k)]
                              - d["costo"][j]) * var for (i, j, k, t), var in v.items())
          - pulp.lpSum(ha[i] * (cN * Nv[(i, t)] + cP * Pv[(i, t)]) for i in L for t in T))

    for i in L:
        for t in T:
            m += pulp.lpSum(z[(i, j, t)] for j in viables[i]) == 1
            for j in viables[i]:
                m += pulp.lpSum(v[(i, j, k, t)] for k in C if (i, j, k, t) in v) == z[(i, j, t)]
            for k in C:
                m += (pulp.lpSum(v[(i, j, k, t)] for j in viables[i] if (i, j, k, t) in v)
                      == previo(i, k, t))
            m += Nv[(i, t)] >= pulp.lpSum(d["nreq"].get((j, k), 0) * v[(i, j, k, t)]
                                          for j in viables[i] for k in C if (i, j, k, t) in v)
            m += Pv[(i, t)] >= pulp.lpSum(d["preq"][j] * z[(i, j, t)] for j in viables[i])

    def area_grupo(g, t):
        return pulp.lpSum(ha[i] * z[(i, j, t)] for i in L for j in viables[i] if d["grupo"][j] == g)

    for t in T:
        m += area_grupo("soja", t) <= float(par["max_frac_soja"]) * area_total
        m += area_grupo("gramínea", t) >= float(par["min_frac_gramineas"]) * area_total
        m += area_grupo("pastura", t) >= float(par["min_frac_pastura"]) * area_total
        if (nmax := _limit(par, "n_max_anual_kg")):
            m += pulp.lpSum(ha[i] * Nv[(i, t)] for i in L) <= nmax
        if (bud := _limit(par, "presupuesto_fert_anual_usd")):
            m += pulp.lpSum(ha[i] * (cN * Nv[(i, t)] + cP * Pv[(i, t)]) for i in L) <= bud

    sols, msg = [], "ok"
    md = min(max(1, int(min_diff)), len(L) * len(T))
    for r in range(int(n_alt)):
        m.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
        if pulp.LpStatus[m.status] != "Optimal":
            msg = "infactible" if r == 0 else "ok"
            break
        plan = {i: [next(j for j in viables[i] if z[(i, j, t)].value() > 0.5) for t in T]
                for i in L}
        sols.append(dict(plan=plan, objetivo=pulp.value(m.objective)))
        chosen = [z[(i, plan[i][t - 1], t)] for i in L for t in T]
        m += pulp.lpSum(chosen) <= len(L) * len(T) - md, f"corte_{r}"     # corte no-good
    return sols, msg


# ----------------------------------------------------------------------------
# Evaluación de un plan (detalle accionable)
# ----------------------------------------------------------------------------
def evaluate(d, plan):
    """Detalle lote x año: cultivo, antecesor, ingresos, costos, fertilización, margen."""
    par = d["par"]
    cN, cP = float(par["precio_n_usd_kg"]), float(par["precio_p_usd_kg"])
    rows = []
    for r in d["lotes"].itertuples():
        prev = r.cultivo_anterior
        for t, j in enumerate(plan[r.lote], start=1):
            ing = d["ingreso"][(r.clase, j)] * d["factor"][(j, prev)]
            n, p = d["nreq"].get((j, prev), 0.0), d["preq"][j]
            fert = cN * n + cP * p
            rows.append(dict(lote=r.lote, clase=r.clase, ha=r.ha, año=t, cultivo=j,
                             antecesor=prev, ingreso_usd_ha=ing, costo_usd_ha=d["costo"][j],
                             N_kg_ha=n, P2O5_kg_ha=p, fert_usd_ha=fert,
                             margen_usd_ha=ing - d["costo"][j] - fert,
                             margen_total_usd=r.ha * (ing - d["costo"][j] - fert),
                             fert_total_usd=r.ha * fert))
            prev = j
    return pd.DataFrame(rows)
