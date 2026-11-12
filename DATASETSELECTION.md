# DATASET SELECTION — Fase 1

## Fase

**Fase 1: auditoría y selección de datos.**

## Objetivo

Definir reglas reproducibles para identificar un corpus estático composición–propiedad sin presentar como confirmada ninguna cobertura todavía no observada.

## Estado de evidencia

Las reglas de inclusión y exclusión están **documentadas** por el proyecto. Los umbrales numéricos de cribado son **hipótesis operativas provisionales**, no resultados científicos, y deberán revisarse cuando se conozca la distribución real de las series.

## Propiedad objetivo provisional

Conductividad eléctrica en S/m, solo si existe cobertura suficiente. La resistividad se conservará con su valor y unidad originales. La transformación `σ = 1/ρ` solo podrá aplicarse después de comprobar unidades, ceros, censura, geometría y condiciones de medición. Las propiedades mecánicas permanecerán en un corpus separado.

## Unidad de análisis

Una muestra experimental vinculada jerárquicamente con estudio, familia, sistema material, serie experimental, lote, medición y réplica.

## Criterios obligatorios de inclusión

1. Matriz polimérica y relleno identificables.
2. Procedencia exacta y un identificador persistente o reproducible.
3. Composición cuantitativa con tipo de fracción y unidad explícitos.
4. Propiedad objetivo y unidad explícitas.
5. Condiciones suficientes para clasificar la comparabilidad: AC/DC; frecuencia si AC; temperatura y dirección cuando estén disponibles.
6. Puntos pertenecientes al mismo sistema material y a un protocolo comparable.
7. Valores originales distinguibles de conversiones, cálculos o digitalización.
8. Réplicas y mediciones repetidas conservadas en su nivel jerárquico.

## Criterios de exclusión

- Puntos aislados sin contexto de serie.
- Mezcla silenciosa de AC/DC, frecuencias, temperaturas o direcciones.
- Composición nominal sin aclarar si corresponde a masa, volumen, phr u otra base.
- Propiedad sin unidad o con transformación irreproducible.
- Duplicados, réplicas o mediciones repetidas tratados como sistemas independientes.
- Curvas digitalizadas sin metadatos mínimos de extracción.
- Conversión masa–volumen sin densidades defendibles.

## Hipótesis operativas de cribado

**H-SEL-001:** considerar inicialmente candidata una agrupación con al menos tres niveles distintos de composición. Este umbral permite detectar una secuencia mínima, pero no garantiza suficiencia, identificabilidad ni ajuste válido.

**H-SEL-002:** dar prioridad exploratoria a agrupaciones con cinco o más niveles distintos de composición. Es una preferencia de auditoría, no una condición científica universal.

**H-SEL-003:** utilizar provisionalmente una rúbrica de 0–12 puntos: procedencia 0–2; composición 0–2; propiedad 0–2; condiciones de medición 0–2; niveles de composición 0–2; procesamiento/microestructura 0–1; incertidumbre/réplicas 0–1. Clasificación provisional: principal ≥9; secundario 6–8; excluir <6.

Las tres hipótesis deberán someterse a análisis de sensibilidad y podrán modificarse tras observar el número, tamaño y calidad de las series. Véase `D-011` e `I-009`.

## Familias candidatas de búsqueda

| Prioridad | Tipo de familia | Candidato | Estado |
|---|---|---|---|
| 1 | Relleno y geometría 1D | CNT–polímero | Inferido; cobertura no verificada |
| 2 | Relleno y geometría 2D | Grafeno/GNP–polímero | Inferido; cobertura no verificada |
| 3 | Relleno y geometría 0D/agregada | Negro de carbono–polímero | Inferido; cobertura no verificada |
| 4 | Relleno híbrido | Sistemas conductores híbridos | Inferido; pospuesto como corpus secundario |

Estas categorías no constituyen familias materiales definitivas. La definición final deberá incorporar matriz, grado, relleno, geometría, tratamiento superficial, mecanismo conductor, procesamiento y protocolo de medición.

## Definición de serie composición–propiedad

Conjunto de muestras que comparte, hasta donde pueda establecerse, matriz y grado, relleno y grado, geometría, tratamiento superficial, fabricación, acondicionamiento y protocolo de medición, y que difiere principalmente en la carga de relleno.

## Decisión

**No se selecciona un dataset definitivo.** No se recuperaron registros ni series reales. La selección permanece pendiente de resolver `I-001`, `I-004` e `I-005`.
