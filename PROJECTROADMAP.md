# PROJECT ROADMAP

## Fase

**Fase 1: auditoría y selección de datos.**

## Objetivo

Distinguir el cierre administrativo de la auditoría del cierre científico necesario para seleccionar un corpus verificable.

## Estado de evidencia

La Fase 1 está **ejecutada administrativamente** y **pendiente de cierre científico** en observabilidad y series por el bloqueo documentado en `I-001`.

## Fase 1A — Auditoría documental y de acceso, ejecutada

- Leer el prompt rector y fijar exclusiones.
- Registrar fuentes oficiales y repositorios primarios.
- Probar el acceso a portales, documentación y endpoints.
- Inventariar variables requeridas o candidatas del proyecto.
- Separar requisitos del proyecto, admisión por XSD, observación en registros y cobertura.
- Definir criterios de serie, inclusión y exclusión.
- Proponer familias candidatas de relleno/geometría sin seleccionar una familia material definitiva.
- Registrar bloqueos, decisiones, hipótesis y cuestiones abiertas.

**Puerta administrativa:** completada.

## Fase 1B — Verificación científica pendiente, no ejecutable con el acceso actual

- Recuperar y versionar el XSD vigente mediante `GET /curate/schema` o un mecanismo oficial equivalente.
- Mapear cada variable candidata a su ruta XSD.
- Inspeccionar una muestra estratificada de XML/JSON accesibles.
- Verificar variables observadas, unidades, cobertura y faltantes.
- Identificar series composición–propiedad y aplicar la rúbrica provisional con análisis de sensibilidad.

**Puerta científica:** pendiente hasta resolver `I-001`, `I-002`, `I-003`, `I-004` e `I-005`.

## Fase 2 — Adquisición y curación exhaustivas, no ejecutada

- Exportar o descargar el corpus seleccionado mediante mecanismos oficiales.
- Construir tablas jerárquicas de estudio, sistema, serie, muestra y medición.
- Normalizar nombres y unidades conservando valores originales.
- Detectar duplicados y cuantificar cobertura y faltantes.

## Fase 3 — Análisis exploratorio y calidad, no ejecutada

- Evaluar rangos físicos, faltantes, distribución por estudio/familia y compatibilidad.
- Analizar sensibilidad a reglas de curación.

## Fase 4 — Modelado estático, no ejecutada

- Baselines estadísticos, percolación dentro de series adecuadas y regresión simbólica físicamente restringida.
- Separación por estudio y serie para evitar fuga de información.

## Fase 5 — Dinámica condicional, no ejecutada

SINDy solo podrá considerarse si existe una variable de evolución físicamente defendible y muestreo temporal suficiente.

## Fase 6 — Validación y comunicación, no ejecutada

Validación externa, incertidumbre, estabilidad, dominio de aplicabilidad y paquete reproducible.
