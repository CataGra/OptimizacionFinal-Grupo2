"""
Análisis de robustez por simulación (Monte Carlo) del modelo de rotación de cultivos.

Complementa sensibilidad.py: allí se mueve UN parámetro por vez; acá se perturban VARIOS a la vez
(precios de soja, maíz y trigo, precio de los fertilizantes e ingreso de la pastura), que es lo
que pasa en la realidad. Usa model.py y sensibilidad.py sin modificarlos.

Qué hace:
  1. Resuelve el escenario base y el ranking de las N_ALT mejores alternativas.
  2. Sortea ESCENARIOS con multiplicadores log-normales de media 1 (el valor esperado no cambia).
  3. En cada escenario evalúa (sin re-optimizar) cada plan del ranking y re-optimiza
     (el "plan ideal" si se hubiera conocido el escenario).
  4. Arrastre (regret) = margen del plan ideal - margen del plan evaluado.

Uso (desde la carpeta del proyecto):
    python robustez.py
    python robustez.py --partido Rauch --n 500 --semilla 7 --sigma 1.5
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M
import sensibilidad as S

# desvío (de log) de cada multiplicador; --sigma los escala a todos juntos
SIGMA = {"precio_soja": 0.15, "precio_maiz": 0.15, "precio_trigo": 0.15,
         "precio_fert": 0.20, "ingreso_pastura": 0.15}


def aplicar(sheets, mult, nombre_pastura):
    sh = S.clonar(sheets)
    S.mult_precio(["soja", "soja2"])(sh, mult["precio_soja"])
    S.mult_precio(["maiz"])(sh, mult["precio_maiz"])
    S.mult_precio(["trigo"])(sh, mult["precio_trigo"])
    S.precio_fert(sh, mult["precio_fert"])
    if nombre_pastura is not None:
        c = sh["cultivos"]
        c["ingreso_fijo_usd_ha"] = c["ingreso_fijo_usd_ha"].astype(float)
        c.loc[c["cultivo"] == nombre_pastura, "ingreso_fijo_usd_ha"] *= mult["ingreso_pastura"]
    return sh


def main():
    ap = argparse.ArgumentParser(description="Robustez por simulación del plan de rotación.")
    ap.add_argument("--excel", default="datos_ejemplo.xlsx")
    ap.add_argument("--partido", default="Chascomús")
    ap.add_argument("--n", type=int, default=300, help="cantidad de escenarios")
    ap.add_argument("--semilla", type=int, default=2026)
    ap.add_argument("--sigma", type=float, default=1.0, help="escala de la incertidumbre (1 = base)")
    ap.add_argument("--alt", type=int, default=5, help="alternativas del ranking a comparar")
    ap.add_argument("--salida", default="resultados_robustez")
    a = ap.parse_args()

    sheets = M.read_excel(a.excel)
    d0 = M.prepare(sheets, a.partido)
    top, _ = M.solve_top_k(d0, n_alt=a.alt, min_diff=3)
    planes = [s["plan"] for s in top]
    pj = next((j for j in d0["cultivos"] if d0["grupo"][j] == "pastura"), None)

    rng = np.random.default_rng(a.semilla)
    filas, valores = [], []
    for e in range(a.n):
        mult = {k: float(np.exp(a.sigma * s * rng.standard_normal() - (a.sigma * s) ** 2 / 2))
                for k, s in SIGMA.items()}
        sh = aplicar(sheets, mult, pj)
        d = M.prepare(sh, a.partido)
        ideal, _ = M.solve_top_k(d, n_alt=1, min_diff=1)
        v_ideal = ideal[0]["objetivo"]
        vals = [M.evaluate(d, p)["margen_total_usd"].sum() for p in planes]
        filas.append(dict(escenario=e, **mult, ideal=v_ideal,
                          difiere_del_base=S.dif_planes(ideal[0]["plan"], planes[0]),
                          **{f"plan{r + 1}": v for r, v in enumerate(vals)}))
        valores.append(vals)

    df = pd.DataFrame(filas)
    resumen = []
    for r in range(len(planes)):
        v = df[f"plan{r + 1}"]
        reg = df["ideal"] - v
        p5 = v.quantile(0.05)
        resumen.append(dict(
            plan=f"{r + 1}" + (" (óptimo)" if r == 0 else ""),
            margen_base=top[r]["objetivo"], margen_medio=v.mean(), desvio=v.std(),
            p5=p5, cvar5=v[v <= p5].mean(),
            arrastre_medio=reg.mean(), arrastre_medio_pct=100 * (reg / df["ideal"]).mean(),
            arrastre_p95_pct=100 * (reg / df["ideal"]).quantile(0.95),
            arrastre_max_pct=100 * (reg / df["ideal"]).max(),
            pct_escenarios_dentro_1pct=100 * ((reg / df["ideal"]) < 0.01).mean()))
    res = pd.DataFrame(resumen)

    os.makedirs(a.salida, exist_ok=True)
    df.to_csv(os.path.join(a.salida, "escenarios.csv"), index=False)
    res.to_csv(os.path.join(a.salida, "resumen_robustez.csv"), index=False)
    print(f"\nPartido: {a.partido} | {a.n} escenarios | semilla {a.semilla} | sigma x{a.sigma}")
    print(res.round(2).to_string(index=False))
    print(f"\nDecisiones (lote, año) que cambian entre el plan ideal de cada escenario y el base: "
          f"media {df['difiere_del_base'].mean():.1f} de {len(d0['lotes']) * int(d0['par']['anios'])}")
    print(f"Resultados en '{a.salida}'.")


if __name__ == "__main__":
    main()
