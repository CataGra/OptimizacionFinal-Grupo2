# Rotación óptima de cultivos - Cuenca del Salado

App web (Streamlit) con un modelo de **Programación Lineal Mixta** (PuLP) que recomienda
rotaciones de cultivos a 3 años para un campo de la Cuenca del Salado. El usuario carga el
cultivo anterior de cada lote, elige el partido y obtiene un **ranking de alternativas**,
de la más a la menos conveniente según el margen bruto.

> **Estado de los datos:** los rendimientos por partido son **reales** (Estimaciones Agrícolas
> del Ministerio de Agricultura). Los demás valores (precios, costos, factores de suelo y de
> antecesor, etc.) son **ilustrativos** y están pendientes de reemplazo. Ver la sección
> [Datos pendientes](#datos-pendientes).

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

## 5. Datos pendientes

| Dato | Hoja / lugar | Estado | Dónde conseguirlo |
|---|---|---|---|
| Rendimientos por partido (tn/ha) | `rendimientos_partido` | **Real** (promedio 2020/21-2025/26, excluye campañas sin dato) | Estimaciones Agrícolas, Min. de Agricultura |
| **Precios** (USD/tn, netos de retenciones y flete) | `precios` en `make_template.py` | **Pendiente** (ilustrativo) | Mercado de Rosario / BCR, Matba-Rofex, Bolsa de Cereales |
| **Costos directos** (USD/ha, sin fertilizante) | `cultivos` | **Pendiente** (ilustrativo) | Márgenes brutos de INTA, AACREA, Min. Desarrollo Agrario bonaerense |
| Precio de fertilizantes (USD/kg de N y P₂O₅) | `parametros` | **Pendiente** (ilustrativo) | Publicaciones de costos e insumos |
| Valor del forraje de la pastura (USD/ha) | `cultivos` (`ingreso_fijo_usd_ha`) | **Pendiente** (ilustrativo) | INTA Cuenca del Salado (margen de cría / alquiler ganadero) |
| Factores de antecesor y N requerido | `rotacion` | **Pendiente** (ilustrativo) | Trabajos de INTA (EEA Cuenca del Salado, EEA Balcarce) |
| Factor de rendimiento por clase de suelo | `factor_clase` | **Supuesto** (A=1,0; B=0,8; C=0,6) | Bibliografía INTA; aclarar como supuesto |
| Aptitud de cada clase | `aptitud` | **Supuesto** | Cartas de suelos INTA (Visor GeoINTA) |
| Partidos Rauch y Castelli | `rendimientos_partido` | **Faltan** (no estaban en el CSV) | Volver a descargar el CSV incluyendo esos departamentos |
| Soja de 2ª en Dolores | `rendimientos_partido` | Solo 2 campañas con dato | Aclararlo en el informe o descartar el partido |

### Si no se encuentran los precios
- Tomar **valores de referencia** de una campaña y fuente concretas (por ejemplo, precio de pizarra
  o futuros de la Bolsa de Cereales), restar retenciones y flete con porcentajes explícitos, y
  **documentarlos como supuesto** en el informe.
- Hacer un **análisis de sensibilidad**: correr el modelo con precios ±10 % y mostrar si la
  rotación óptima cambia. Es un buen argumento aunque los precios no sean exactos.
- Dejar siempre registrado el año de cada precio, para no mezclar campañas.

### Cómo cargar los datos reales
1. Editar los valores en `make_template.py` (precios, costos, parámetros, factores).
2. Correr `python make_template.py` y comprobar que muestre *"Rendimientos reales cargados"*.
3. Abrir la app, verificar que los resultados tengan sentido y subir los cambios con Git.

---

## 6. Limitaciones y supuestos
- Un solo cultivo principal por lote y año; no hay ganadería explícita (la pastura se valora con un
  ingreso fijo por hectárea).
- Los rendimientos por partido promedian todos los suelos; el modelo los usa como valor de la
  clase de referencia y los ajusta con `factor_clase`.
- La fertilización queda fijada en el mínimo requerido (no hay curva de respuesta del rendimiento
  al fertilizante).
- Los factores de antecesor y las demandas de N son aproximaciones que deben respaldarse con
  bibliografía.