# Rotación óptima de cultivos - Cuenca del Salado

App web (Streamlit) con un modelo de **Programación Lineal Mixta** (PuLP) que recomienda
rotaciones de cultivos a 3 años para un campo de la Cuenca del Salado. El usuario carga el
cultivo anterior de cada lote, elige el partido y obtiene un **ranking de alternativas**,
de la más a la menos conveniente según el margen bruto.

> **Estado de los datos:** el Excel de ejemplo usa **datos reales** de la Cuenca del Salado
> (Ministerio de Agricultura, informe de márgenes de septiembre 2026 y Estimaciones Agrícolas;
> precios de fertilizantes de noviembre 2026) sobre un **establecimiento típico ficticio** (los
> lotes son inventados). Los valores que no tienen una fuente directa están construidos con
> supuestos declarados. Ver la sección [Datos: fuentes, cálculos y supuestos](#5-datos-fuentes-cálculos-y-supuestos).

---

## Contexto: la Cuenca del Salado

### Qué es
El río Salado nace en el sudeste de Santa Fe, atraviesa el centro de la provincia de Buenos Aires
y desemboca en la Bahía de Samborombón, sobre el Río de la Plata. Se habla de "Cuenca del Salado"
en dos sentidos:

- **La cuenca hídrica completa**, que es el área que abarca el *Plan Maestro Integral de la Cuenca
  del Río Salado*: unos **170.000 km²**, más de la mitad de la superficie de la provincia, con más
  de un millón de habitantes y entre el 25% y el 30% de la producción de granos y carnes del país.
- **La Cuenca baja o Depresión del Salado** (también llamada Pampa Deprimida o Pampa inundable),
  que es la zona en la que se enfoca este trabajo: unos **6,5 millones de hectáreas**, alrededor
  del 21% de la provincia.

### Por qué es un caso interesante para optimizar
- Es una llanura muy plana, con suelos hidromórficos (que se anegan) y halomórficos (salinos y
  sódicos), y con ciclos alternados de inundaciones y sequías.
- Por eso solo una parte del territorio, cerca del 29%, tiene aptitud agrícola; en el resto se
  conservan pastizales naturales o pasturas. Es la principal zona de cría vacuna del país, con más
  del 20% del stock bovino nacional.
- En los últimos años la agricultura avanzó sobre las lomas de la región. Eso plantea justamente
  la pregunta que responde este modelo: **cómo combinar cultivos agrícolas y pasturas** en los
  distintos tipos de suelo de un mismo campo, sin caer en el monocultivo.

Esto se refleja en el modelo: los lotes se clasifican en lomas (clase A), medias lomas (clase B) y
bajos alcalinos (clase C, donde solo puede haber pastura), y se exige una superficie mínima de
pastura.

### Partidos incluidos en la app
La cuenca abarca muchos partidos bonaerenses. La app trabaja con **12 partidos** de la región,
para los que hay rendimientos en las Estimaciones Agrícolas del Ministerio de Agricultura:

Ayacucho, Azul, Cañuelas, Castelli, Chascomús, Dolores, General Belgrano, General Juan Madariaga,
Las Flores, Maipú, Rauch y Saladillo.

Para sumar otro partido alcanza con agregar sus rendimientos a `Estimaciones.csv` y volver a
generar el Excel (sección 5.7).

*Fuentes del contexto:* Plan Maestro Integral de la Cuenca del Río Salado (Ministerio de
Infraestructura de la Provincia de Buenos Aires); Jacobo et al. (FAUBA), sobre uso del suelo y
pastizales en la Cuenca baja del Salado; trabajos de INTA y del Ministerio de Agricultura sobre
sistemas ganaderos de la región.

---

## 1. El modelo de optimización

### Idea general
Un campo se divide en lotes. Cada año, cada lote se siembra con **un solo cultivo**. El modelo
decide qué sembrar en cada lote y año para **maximizar el margen bruto total** del horizonte,
respetando la aptitud del suelo, las rotaciones permitidas y límites de manejo.

El **cultivo anterior** de cada lote (año 0) es el dato de partida y es lo que carga el
usuario. A partir de él, el modelo encadena las decisiones año a año.

### Conjuntos y datos
- `i`: lotes, con superficie `A_i` (ha) y clase de suelo (A loma, B media loma, C bajo).
- `j, k`: cultivos (soja, maíz, trigo/soja 2ª, pastura).
- `t = 1..3`: años del horizonte.
- `y_ik`: **dato binario** = 1 si el lote `i` tuvo el cultivo `k` en el año 0.

### Variables de decisión
| Variable | Tipo | Significado |
|---|---|---|
| `z[i,j,t]` | binaria | 1 si el lote `i` siembra el cultivo `j` en el año `t` |
| `v[i,j,k,t]` | continua (0-1) | "cultivo `j` en `t` con antecesor `k` en `t-1`" (vale 0 o 1 por construcción) |
| `N[i,t]`, `P[i,t]` | continuas | kg/ha de nitrógeno y de P₂O₅ aplicados |

### Función objetivo
Maximizar el margen bruto total (USD):

```
max  Σ A_i · ( ingreso(i,j,k) · factor(j,k) - costo_j ) · v[i,j,k,t]
   - Σ A_i · ( precio_N · N[i,t] + precio_P · P[i,t] )
```

donde el ingreso por hectárea es:

```
ingreso = factor_clase × Σ ( rendimiento_partido[producto] × precio[producto] ) + ingreso_fijo
```

### Restricciones
1. **Un cultivo por lote y año:** `Σ_j z[i,j,t] = 1`.
2. **Aptitud del suelo:** si un cultivo no es viable en la clase del lote, no se crea `z` (ej.: en
   clase C solo hay pastura).
3. **Rotación y antecesor (usa la binaria del cultivo anterior):**
   - `Σ_k v[i,j,k,t] = z[i,j,t]`
   - `Σ_j v[i,j,k,t] = antecesor_k`, donde en `t=1` el antecesor es el dato `y_ik` y en `t>1` es `z[i,k,t-1]`.
   - Solo existen `v` para los pares (cultivo, antecesor) permitidos en la hoja `rotacion`;
     el resto está prohibido (ej.: soja tras soja).
4. **Fertilización mínima:** `N` cubre el requerimiento del cultivo según su antecesor
   (crédito de N de la pastura o la soja); `P` cubre el requerimiento del cultivo.
5. **Manejo (por año, sobre toda la superficie):** máximo de soja, mínimo de gramíneas, mínimo de
   pastura, tope de N total y presupuesto de fertilizante.

### Ranking de alternativas
Después de resolver el óptimo, se agrega un **corte "no-good"**: una restricción que obliga a que la
siguiente solución cambie al menos `min_diff` decisiones (lote, año) respecto de la anterior. Se
vuelve a resolver y se repite. Así se obtiene el óptimo y las siguientes mejores alternativas,
ordenadas por margen. Sin esa diferencia mínima, las alternativas serían casi idénticas.

---

## 2. Estructura del proyecto

| Archivo | Para qué sirve |
|---|---|
| `app.py` | Interfaz web (Streamlit): carga de datos, formulario de lotes, ranking y resultados |
| `model.py` | Lectura y validación del Excel, modelo PuLP, ranking top-K y evaluación de planes |
| `make_template.py` | **Genera `datos_ejemplo.xlsx`**: acá se definen costos, precios, factores, etc. |
| `importar_rendimientos.py` | Convierte `Estimaciones.csv` en la tabla de rendimientos por partido |
| `Estimaciones.csv` | Estimaciones agrícolas del Ministerio de Agricultura (fuente de rendimientos) |
| `datos_ejemplo.xlsx` | Excel de entrada que lee la app (se genera con `make_template.py`) |
| `requirements.txt` | Librerías necesarias |

### Hojas del Excel
`lotes`, `aptitud`, `cultivos`, `composicion`, `precios`, `rendimientos_partido`, `factor_clase`,
`rotacion` y `parametros`. La hoja `LEEME` dentro del Excel explica cada una.

---

## 3. Cómo usar la app (Streamlit)

### Instalación (una sola vez)
Requiere **Python 3.9 o más nuevo**. En una terminal, dentro de la carpeta del proyecto:

```
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
En PowerShell, si `activate` da un error de scripts deshabilitados, correr una vez:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
En Mac/Linux: `python3 -m venv venv` y `source venv/bin/activate`.

> Importante: `requirements.txt` fija `pulp==2.9.0`. Las versiones 3.x/4.x cambiaron la API y
> el código no funciona con ellas.

### Ejecutar
Cada vez que quieran usar la app:

```
venv\Scripts\activate
streamlit run app.py
```
Se abre en el navegador en `http://localhost:8501`. Para cerrarla: `Ctrl + C` en la terminal.
Si cambian el código o el Excel, alcanza con apretar *Rerun* arriba a la derecha de la página.

### Uso paso a paso
1. **Barra lateral:** elegir el origen de datos (ejemplo o un Excel propio), el **partido**, la
   cantidad de alternativas y la diferencia mínima entre ellas.
2. **Tabla de lotes:** editar la superficie, la clase de suelo y el **cultivo anterior** de cada
   lote (se pueden agregar o quitar lotes).
3. Opcional: revisar los rendimientos aplicados y los parámetros de manejo.
4. Apretar **Optimizar**.
5. Ver el **ranking** y elegir una alternativa para ver el plan de rotación por lote, la superficie
   por cultivo y año, el plan de fertilización y el margen por año.
6. Descargar los resultados en Excel.

### Regenerar los datos
```
python make_template.py                      # usa Estimaciones.csv de la carpeta
python make_template.py OtroArchivo.csv      # usa otro CSV de rendimientos
```
Tiene que aparecer el mensaje *"Rendimientos reales cargados desde ..."*. Si aparece un aviso de
que no encontró el CSV, se usaron rendimientos ilustrativos. **Cerrar `datos_ejemplo.xlsx` en Excel
antes de correrlo**, o da un error de permisos.

Para actualizar **solo** la hoja de rendimientos sin tocar el resto del Excel:
`python importar_rendimientos.py Estimaciones.csv`.

---

## 4. Trabajo en equipo con Git y GitHub

### Primera vez (cada integrante)
Instalar Git (git-scm.com), configurar nombre y mail, y clonar el repositorio:

```
git config --global user.name "Tu Nombre"
git config --global user.email "tu@mail.com"
git clone https://github.com/CataGra/OptimizacionFinal-Grupo2.git
cd OptimizacionFinal-Grupo2
```
Después crear el entorno virtual e instalar dependencias (sección 3). El dueño del repositorio tiene
que agregar a los demás en *Settings → Collaborators*.

### Ciclo de trabajo diario
```
git pull                         # 1. traer lo último, SIEMPRE antes de empezar
(editar archivos)                # 2. trabajar
git status                       # 3. ver qué cambió
git add .                        # 4. preparar los cambios
git commit -m "Qué se cambió"    # 5. guardar con un mensaje claro
git push                         # 6. subir al repositorio
```

### Reglas para evitar problemas
- Hacer `git pull` **antes** de empezar y `git push` al terminar.
- **No editar `datos_ejemplo.xlsx` a mano:** es un archivo binario y Git no puede combinar cambios
  de dos personas. Los valores se editan en `make_template.py` (texto) y se regenera el Excel.
  Después de regenerar, subir el Excel nuevo con `add`, `commit` y `push`.
- Avisar qué parte toca cada uno (por ejemplo: uno los precios, otro los costos) para no editar las
  mismas líneas.
- Si un `pull` o `push` marca un **conflicto**, abrir el archivo señalado, elegir qué versión
  queda (VS Code muestra los botones *Accept Current / Incoming*), guardar, y repetir `add`,
  `commit` y `push`.
- No subir la carpeta `venv` ni `__pycache__` (ya están en `.gitignore`).

### Publicar la app (opcional)
Con el repositorio en GitHub, en **share.streamlit.io** se conecta la cuenta, se elige el repo y
`app.py`, y se obtiene un link público. Cada `git push` actualiza la app sola. Hay que asegurarse de
haber subido el `datos_ejemplo.xlsx` ya actualizado.

---

## 5. Datos: fuentes, cálculos y supuestos

### 5.1 Cómo se arma el Excel de entrada
1. Los valores están escritos en `make_template.py`, cada uno con un comentario que indica su
   fuente y el cálculo que se hizo.
2. Los rendimientos por partido no se escriben a mano: `importar_rendimientos.py` los calcula a
   partir de `Estimaciones.csv` (descargado del Ministerio de Agricultura).
3. `python make_template.py` junta todo y genera `datos_ejemplo.xlsx`, con 10 hojas: `LEEME`,
   `lotes`, `aptitud`, `cultivos`, `composicion`, `precios`, `rendimientos_partido`,
   `factor_clase`, `rotacion` y `parametros`.
4. La app usa ese Excel como "Datos de ejemplo" y lo ofrece como plantilla descargable. Un usuario
   real completa la misma plantilla con sus propios lotes.

### 5.2 Criterios generales
- **Una sola fuente y una sola fecha** para lo económico: el informe *Resultados Agrícolas.
  Ingresos – Gastos – Márgenes* del Ministerio de Agricultura (septiembre 2026, campaña 2026/27),
  tabla de la **región Cuenca del Salado**. Así precios, costos y márgenes son coherentes entre sí.
- Todo en **USD**. Cuando un dato viene en pesos, se convierte con el dólar BCRA promedio de
  septiembre 2026 (1.513,88 $/USD), el mismo que usa el informe.
- El modelo maximiza **margen bruto en campo propio**: no incluye alquiler de la tierra ni gastos
  de estructura.

### 5.3 Datos tomados de fuentes (con el cálculo aplicado)

| Dato | Hoja | Valor | Cómo se obtuvo |
|---|---|---|---|
| Rendimientos por partido (12 partidos) | `rendimientos_partido` | ej. Chascomús: maíz 7,20; soja 3,13; trigo 3,92; soja 2ª 1,98 tn/ha | Promedio de las campañas 2020/21 a 2025/26 de las Estimaciones Agrícolas, excluyendo campañas sin dato (rendimiento 0) |
| Precio neto (USD/tn) | `precios` | soja 275,4; soja 2ª 270,1; maíz 141,3; trigo 159,4 | Precio a cosecha − (gastos de comercialización y cosecha ÷ rendimiento). Ej. soja: 360 − 262,2/3,10. El precio del informe es local, con retenciones ya descontadas |
| Costo directo sin fertilizante (USD/ha) | `cultivos` | soja 234,7; maíz 390,0; trigo/soja 2ª 427,0 | Labores + semillas + fitosanitarios. Ej. maíz: 136,2 + 117,6 + 136,2 |
| Precio del N | `parametros` | 1,30 USD/kg N | Urea mayorista 595–605 USD/t (Valor Soja / IF Ingeniería en Fertilizantes, 7/11/2026) ÷ 1000 ÷ 0,46 |
| Precio del P | `parametros` | 1,65 USD/kg P₂O₅ | Fosfato monoamónico 850–870 USD/t CFR (misma fuente) ÷ 1000 ÷ 0,52. *Es precio de importación, no mayorista* |
| P requerido soja | `cultivos` | 39 kg P₂O₅/ha | Gasto en fertilizante de la soja según el informe (65,0 USD/ha) ÷ 1,65 |
| N requerido maíz tras soja | `rotacion` | 67 kg N/ha | (Gasto en fertilizante del maíz 153,4 − 40 kg P × 1,65) ÷ 1,30 |
| N requerido trigo tras soja | `rotacion` | 77 kg N/ha | (Gasto en fertilizante del trigo 166,6 − 40 kg P × 1,65) ÷ 1,30 |

### 5.4 Datos construidos con supuestos (y por qué)

| Dato | Valor | Supuesto y justificación |
|---|---|---|
| P requerido maíz y trigo | 40 kg P₂O₅/ha | Dosis típica. El informe da el gasto total en fertilizante, no cómo se reparte entre N y P, así que hay que fijar uno de los dos |
| P requerido trigo/soja 2ª | 51 kg P₂O₅/ha | 40 (trigo) + 18,6 USD/ha de la soja 2ª ÷ 1,65 |
| Pastura: tipo | con leguminosas (lotus tenuis, trébol blanco) | Son las leguminosas adaptadas a los bajos del Salado. Aportan N por fijación biológica (INTA EEA Cuenca del Salado, 2025) |
| Pastura: ingreso | 190 USD/ha/año | No se modela ganado: la pastura se valora por lo que pagaría un ganadero por usarla (**alquiler ganadero**). 70 kg de novillo/ha/año × 4.110 $/kg (novillo MAG Cañuelas, promedio octubre 2026) ÷ 1.513,88 $/USD. Como referencia, el margen de la cría con hacienda propia en la región ronda los 250 USD/ha |
| Pastura: costo | 80 USD/ha/año | El modelo trata la pastura como anual, así que la implantación se reparte en 4 años de vida útil: (semillas 125 + labores 115,4) ÷ 4 ≈ 60, más ≈ 20 de mantenimiento |
| Pastura: P | 10 kg P₂O₅/ha/año | 90 kg/ha de fosfato diamónico a la siembra (dosis de INTA EEA Cuenca del Salado para suelos con < 6 ppm de P) = 41 kg P₂O₅ ÷ 4 años |
| N según antecesor | maíz: 75 tras trigo/soja, 35 tras pastura; trigo: 90 tras maíz, 40 tras pastura | Ajustes sobre los valores calibrados: −50% tras pastura con leguminosa (aporte de N), +15% trigo tras maíz (el rastrojo de maíz inmoviliza N), +10% maíz tras trigo/soja |
| Factor de rendimiento por antecesor | soja tras maíz 1,05; tras pastura 1,05 a 1,08; trigo tras maíz 0,97 | La literatura da ≈ +10% para soja sobre maíz frente a soja sobre soja; se usa la mitad porque el rendimiento base ya es un promedio de lotes con distintos antecesores. Mejora tras pastura: ensayos de la Chacra Experimental Barrow |
| Tope de soja / mínimo de gramíneas | 0,35 / 0,20 de la superficie total | Regla de rotación balanceada (≈ 50% gramíneas y 50% soja en la parte agrícola), relajada para dejar margen de decisión: sobre el 60% agrícola equivale a soja ≤ 58% y gramíneas ≥ 33% |
| Mínimo de pastura | 0,40 | Conservador para la región: solo ≈ 29% de la cuenca tiene aptitud agrícola y se conserva entre 53% y 89% de pastizales |
| Tope de N y presupuesto de fertilizante | 0 (sin tope) | Escenario base sin restricción financiera. El presupuesto se analiza en la sensibilidad |
| Factor por clase de suelo | A 1,0; B 0,8; C 0,6 | Las clases B y C tienen limitaciones de drenaje y sodicidad. Se analiza en la sensibilidad |
| Aptitud | clase C: solo pastura | Bajos alcalinos, no aptos para agricultura |
| Lotes | 10 lotes, 1.600 ha | Establecimiento típico ficticio; 34% de la superficie es clase C, coherente con la región |

### 5.5 Validación contra el Ministerio
Con estos datos, el margen bruto por hectárea que calcula el modelo (lote clase A, Chascomús)
reproduce el del informe para la Cuenca del Salado:

| Cultivo | Modelo (USD/ha) | Ministerio (USD/ha) | Fertilizante modelo / Ministerio |
|---|---|---|---|
| Maíz (tras soja) | 474 | 472 | 153,1 / 153,4 |
| Trigo/soja 2ª (tras soja) | 548 | 555 | 184,2 / 185,3 |
| Soja (tras maíz) | 606 (563 sin efecto antecesor) | 553 | 64,3 / 65,0 |

### 5.6 Observaciones sobre los rendimientos
- En **Dolores** hay pocas campañas con dato (soja 2ª: 2; maíz: 3). Sus resultados son menos
  confiables.
- Cañuelas figura como "Canuelas" porque el CSV no trae la ñ.

### 5.7 Cómo actualizar los datos
1. Editar los valores en `make_template.py`, actualizando también el comentario con la fuente.
2. Correr `python make_template.py` y comprobar que muestre *"Rendimientos reales cargados"*.
3. Abrir la app, verificar que los resultados tengan sentido y subir los cambios con Git.

### 5.8 Fuentes
- Ministerio de Agricultura, Ganadería y Pesca. *Resultados Agrícolas. Ingresos – Gastos –
  Márgenes*, septiembre 2026 (campaña 2026/27), región Cuenca del Salado.
- Ministerio de Agricultura. *Estimaciones Agrícolas* por departamento, campañas 2020/21 a 2025/26
  (`Estimaciones.csv`).
- Valor Soja / Bichos de Campo, en base a IF Ingeniería en Fertilizantes: precios de urea y
  fosfatos, 7 de noviembre de 2026.
- Mercado Agroganadero de Cañuelas: precio promedio del novillo, octubre 2026.
- Antonelli, Bailleres, Taboada y otros (INTA EEA Cuenca del Salado). Fijación biológica de
  nitrógeno de *Lotus tenuis* en la Pampa Deprimida. *Farming System* 3(1), 100122, 2025.
- Borrajo, C. I. (INTA EEA Cuenca del Salado). *Implantación de pastura para sistemas ganaderos
  sustentables*, 2026.
- Chacra Experimental Integrada Barrow (MDA-INTA): efecto de pasturas de alfalfa sobre los
  cultivos siguientes.
- Efecto antecesor maíz sobre soja (≈ +10%): Barraco et al. 2017; Lattanzi 1989 y 2005;
  Alvarez et al. 2017.
- Rotación balanceada: INTA; SEDICI-UNLP. Uso del suelo en la cuenca: Jacobo et al. (FAUBA).

---
## 6. Análisis de sensibilidad

### Qué es y para qué sirve

Muchos valores del modelo son supuestos (topes de manejo, factores de rendimiento, precios, ingreso de la pastura). El análisis de sensibilidad mide **cuánto cambian el margen bruto total y el plan de siembra cuando uno de esos valores resulta distinto de lo previsto**. Permite identificar qué supuestos condicionan realmente la decisión y cuáles casi no influyen.

### Cómo funciona

1. Se resuelve el **escenario base**: la rotación óptima con los datos cargados.
2. Para cada parámetro se recorre una serie de valores alrededor del valor base, **modificando solo ese parámetro** y dejando el resto igual, y se vuelve a optimizar.
3. Cada resultado se compara con el escenario base: variación del margen, decisiones de siembra que cambian y superficie por cultivo.

Los valores base se toman de los datos cargados, por lo que el análisis funciona tanto con el Excel de ejemplo como con un Excel propio. Se aplica a la rotación óptima (no al resto del ranking de alternativas).

### Parámetros analizados

| Grupo | Parámetro | Qué se modifica |
| --- | --- | --- |
| Restricciones de manejo | Presupuesto de fertilizante | Tope anual de gasto, como porcentaje del gasto del plan base |
| | Mínimo de pastura | Superficie mínima con pastura cada año |
| | Tope de soja | Superficie máxima del grupo soja (soja y trigo/soja 2ª) |
| | Mínimo de gramíneas | Superficie mínima del grupo gramíneas (maíz) |
| Suelo y rotación | Rendimiento de la clase de suelo | Factor de rendimiento de las clases con limitaciones (clase B en el ejemplo) |
| | Efecto del antecesor | Escala los factores de rendimiento por cultivo anterior (0 los anula, 1 es el valor base, 2 los duplica) |
| Precios e ingresos | Precio de la soja, del maíz y del trigo | Multiplicador sobre el precio neto de cada producto |
| | Precio de los fertilizantes | Multiplicador sobre el precio del N y del P |
| | Ingreso de la pastura | Ingreso por hectárea (alquiler ganadero) |

El factor de la clase C no se analiza porque en esa clase solo hay pastura, cuyo ingreso es fijo por hectárea y no depende del factor. Si un parámetro no existe en el Excel cargado (por ejemplo, un producto con otro nombre), simplemente se omite.

### Resultados que se obtienen

- **Margen total** y su variación respecto del base (en USD y en %).
- **Plan de siembra:** cuántas decisiones (lote, año) difieren del plan base y en qué tramo de valores el plan base se mantiene sin cambios.
- **Superficie promedio por cultivo** en cada escenario.
- **Gasto en fertilizante** de cada escenario.
- **Escenarios sin solución:** valores para los que el modelo no tiene ninguna rotación posible.
- **Diagnóstico de restricciones:** para el mínimo de pastura, el tope de soja y el mínimo de gramíneas se afloja la restricción un paso y se mide cuánto mejora el margen. La conclusión es *No limita*, *Limita poco* o *Limita*.

### Cómo interpretar los resultados

Hay dos preguntas distintas:

- **¿Cambia el margen?** Indica cuánto está en juego si el supuesto resulta incorrecto.
- **¿Cambia el plan?** Indica si la recomendación es robusta: si el plan se mantiene ante variaciones razonables del parámetro, la decisión no depende de ese supuesto.

Una restricción que no limita (aflojarla no mejora el margen) no condiciona la decisión, porque el plan ya la cumple con holgura. Una restricción que limita tiene un costo concreto en margen, y es la que conviene justificar.

### Cómo usarlo

**Desde la app:** después de apretar **Calcular rotaciones**, abrir la pestaña **Sensibilidad** y apretar **Calcular sensibilidad**. Son unos 70 cálculos y suele tardar menos de un minuto. La pestaña tiene tres secciones:

- **Resumen:** indicadores generales, lectura rápida, gráfico de impacto por parámetro, tabla resumen y diagnóstico de restricciones.
- **Por parámetro:** gráfico del margen, gráfico de superficie por cultivo y tabla de escenarios del parámetro elegido.
- **Tabla completa:** todos los escenarios juntos y descarga en Excel.

El análisis se calcula para el partido elegido, con los lotes y parámetros cargados en ese momento. Si se cambian, hay que volver a calcular las rotaciones y la sensibilidad.

**Desde la terminal** (genera un Excel y un gráfico por parámetro en la carpeta `resultados_sensibilidad/`):

```
python sensibilidad.py
python sensibilidad.py --partido Rauch
```

Los gráficos PNG requieren matplotlib (`pip install matplotlib`), que no está en `requirements.txt` porque la app no lo necesita.

### Alcance

- Se modifica **un parámetro por vez**: no se capturan efectos combinados (por ejemplo, un cambio simultáneo del precio de la soja y del fertilizante).
- Es una sensibilidad por **re-optimización**. No es el análisis clásico de precios sombra y rangos de factibilidad del simplex, que no se aplica de la misma forma a un modelo con variables binarias.
- Los rangos probados son valores representativos alrededor del base y **no son comparables entre parámetros**: no equivale variar un precio ±30 % que un presupuesto de fertilizante.
- Solo se analiza la solución óptima. Si dos planes distintos dan el mismo margen, el análisis puede marcar decisiones distintas aunque se trate de un empate y no de un cambio real de estrategia.
- Los resultados dependen del partido y de los datos cargados.
---

## 7. Análisis de robustez (opcional, por consola)

`robustez.py` complementa a `sensibilidad.py`: en vez de mover un parámetro por vez,
perturba varios a la vez (precios de soja, maíz y trigo, precio de los fertilizantes e
ingreso de la pastura) mediante multiplicadores log-normales de media 1, en N escenarios
aleatorios. En cada escenario evalúa los planes del ranking sin re-optimizar y los compara
con el plan ideal para ese escenario (arrastre o *regret*). Usa `model.py` y
`sensibilidad.py` sin modificarlos; no forma parte de la app de Streamlit.

```bash
python robustez.py                                   # Chascomús, 300 escenarios, semilla 2026
python robustez.py --partido Rauch --n 500 --semilla 7 --sigma 1.5
```

Opciones: `--excel`, `--partido`, `--n` (escenarios), `--semilla`, `--sigma` (escala de la
incertidumbre, 1 = base), `--alt` (alternativas del ranking a comparar) y `--salida`
(carpeta de resultados, por defecto `resultados_robustez/`).

Genera `escenarios.csv` (un renglón por escenario) y `resumen_robustez.csv` (una fila por
plan: margen medio, desvío, 5 % peor, CVaR5, arrastre medio, etc.) y muestra el resumen por pantalla.

---
## 8. Limitaciones y supuestos del modelo
- Un solo cultivo principal por lote y año; no hay ganadería explícita (la pastura se valora con un
  ingreso fijo por hectárea, el alquiler ganadero).
- La pastura se decide año a año, aunque en la realidad dura varios años; por eso su costo de
  implantación se reparte en su vida útil.
- **Fin de horizonte:** el modelo planifica 3 años y no considera qué pasa en el año 4, así que en
  el último año puede elegir un cultivo que deje el lote en peores condiciones.
- El trigo/soja 2ª pertenece al grupo "soja": cuenta para el tope de soja y no para el mínimo de
  gramíneas, aunque incluye trigo (cada cultivo pertenece a un solo grupo).
- Los rendimientos por partido promedian todos los suelos; el modelo los usa como valor de la
  clase de referencia y los ajusta con `factor_clase`.
- La fertilización queda fijada en el mínimo requerido (no hay curva de respuesta del rendimiento
  al fertilizante).
- Precios y costos son de una sola fecha; su variación se estudia en el análisis de sensibilidad.
