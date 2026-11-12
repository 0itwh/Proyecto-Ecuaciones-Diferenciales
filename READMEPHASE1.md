# FASE 1 — Auditoría y selección de datos

## Fase

**Fase 1: auditoría y selección de datos.**

## Objetivo

Verificar el acceso a MaterialsMine y NanoMine, sus mecanismos oficiales de consulta y descarga, la documentación de la API, las variables candidatas definidas por el proyecto, su correspondencia con el XSD vigente, las variables efectivamente observables, las familias candidatas y la disponibilidad de series composición–propiedad.

## Estado de evidencia

**Fase 1 ejecutada con limitaciones documentadas.** El acceso HTTP directo quedó bloqueado por la política del entorno. En consecuencia, la comprobación científica de variables observables y series composición–propiedad permanece **inconclusa**, aunque la auditoría de acceso, las reglas de selección y la trazabilidad de incidencias sí quedaron documentadas.

## Alcance ejecutado

Se ejecutó exclusivamente la Fase 1. No se entrenaron modelos, no se ajustaron modelos de percolación, no se ejecutó regresión simbólica y no se ejecutó SINDy.

## Hallazgos clasificados

1. **Confirmado:** las pruebas HTTP directas devolvieron código 403 con el cuerpo `Request blocked by sandbox policy`. Esto confirma una restricción del entorno de ejecución, no una caída demostrada de MaterialsMine o NanoMine.
2. **Documentado:** la interfaz oficial Swagger presenta “MaterialsMine Project API Docs”, versión 1.0.0 y OAS 3.0, con rutas documentadas para esquema, XML y archivos. La operatividad real, autenticación, paginación y formatos de respuesta permanecen no verificados.
3. **Documentado:** el repositorio público `Duke-MatSci/nanomine-schema` contiene versiones históricas del esquema PNC y formularios. No se ha confirmado que alguna de esas versiones coincida con el XSD actualmente desplegado.
4. **Documentado:** se inventariaron 67 variables requeridas o candidatas definidas por el proyecto.
5. **No verificado:** la correspondencia de cada variable con el XSD vigente, su ruta XSD y su presencia en registros accesibles.
6. **Inferido:** CNT–polímero, grafeno/GNP–polímero y negro de carbono–polímero son familias candidatas de relleno y geometría para orientar la búsqueda. No son familias materiales definitivas.
7. **No verificado:** la existencia de series composición–propiedad comparables en los registros actuales.

## Resultado de la Fase 1

No se congela un dataset ni se selecciona una familia material definitiva. La conductividad eléctrica se mantiene como propiedad objetivo provisional, separada de las propiedades mecánicas y condicionada a cobertura real, unidades explícitas y condiciones de medición comparables.

## Criterio de cierre

- **Cierre administrativo:** completado. Se documentaron fuentes, intentos de acceso, variables candidatas, decisiones, incidencias y alternativas.
- **Cierre científico:** pendiente. Requiere recuperar el XSD vigente y una muestra de registros para verificar observabilidad, cobertura y series composición–propiedad.

## Trazabilidad

Los archivos se relacionan mediante `source_id`, `attempt_id`, `issue_id` y `decision_id`. Las reglas numéricas de cribado se identifican expresamente como hipótesis operativas provisionales sujetas a revisión y análisis de sensibilidad.

## Entregables

- `READMEPHASE1.md`
- `DATASETSELECTION.md`
- `PROJECTROADMAP.md`
- `SOURCEREGISTRY.csv`
- `VARIABLEINVENTORY.csv`
- `ACCESSLOG.md`
- `DECISIONLOG.md`
- `ISSUESLOG.md`
