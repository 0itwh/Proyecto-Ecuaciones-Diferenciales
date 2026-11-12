# ISSUES LOG

## Fase

**Fase 1: auditoría y selección de datos.**

## Estado de evidencia

Las incidencias permanecen abiertas salvo que se indique lo contrario. Cada una incluye criterio de cierre y vínculos de trazabilidad.

| issue_id | fecha_apertura | problema | causa | impacto | alternativa | prioridad | estado | source_id | decision_id | criterio_de_cierre |
|---|---|---|---|---|---|---|---|---|---|---|
| I-001 | 2026-11-03 | No se recuperaron registros | Política del entorno bloqueó HTTP directo | Cobertura real desconocida | Exportación manual o API autorizada | Crítica | Abierto | SRC-001;SRC-002;SRC-003 | D-005;D-006;D-012 | Recuperar una muestra reproducible de registros con identificadores y procedencia |
| I-002 | 2026-11-03 | OpenAPI no descargada | Bloqueo del entorno | Auth, parámetros, respuestas y paginación no validados | JSON/YAML exportado desde Swagger | Alta | Abierto | SRC-004;SRC-010 | D-009 | Conservar especificación OpenAPI versionada y probar rutas no destructivas |
| I-003 | 2026-11-03 | XSD desplegado no recuperado | Bloqueo de `/curate/schema` | Versión canónica desconocida | Descargar XSD vigente y comparar con GitHub | Alta | Abierto | SRC-009;SRC-006 | D-005 | Obtener XSD, fecha y hash del despliegue actual |
| I-004 | 2026-11-03 | Variables efectivamente observables desconocidas | Sin registros individuales | Inventario limitado a requisitos del proyecto | Muestra estratificada XML/JSON | Crítica | Abierto | SRC-008 | D-005;D-010;D-012 | Completar ruta XSD, presencia, unidad y cobertura para cada variable prioritaria |
| I-005 | 2026-11-03 | Series composición–propiedad no verificadas | Sin consulta/exportación de registros | No puede seleccionarse dataset ni familia final | Tabla de candidatos con niveles de composición y condiciones | Crítica | Abierto | SRC-001;SRC-002 | D-002;D-003;D-006;D-007;D-012 | Identificar y auditar series comparables con procedencia completa |
| I-006 | 2026-11-03 | Licencias no verificadas por registro | Metadatos inaccesibles | Riesgo de uso o redistribución incorrectos | Términos oficiales y licencia por registro | Alta | Abierto | SRC-001;SRC-004 |  | Registrar licencia y restricciones antes de redistribuir datos |
| I-007 | 2026-11-03 | Paginación y estabilidad no verificadas | API no ejecutada | Riesgo de descarga incompleta | Pruebas paginadas con conteos reproducibles | Media | Abierto | SRC-004 |  | Documentar límites, cursores, conteos y repetibilidad |
| I-008 | 2026-11-03 | Posibles versiones divergentes del esquema | Varias XSD históricas | Riesgo de parseo inconsistente | Comparar hash y fecha del XSD vigente | Alta | Abierto | SRC-006;SRC-009 | D-009 | Identificar la versión desplegada y registrar diferencias |
| I-009 | 2026-11-03 | Umbrales de cribado no validados | Reglas creadas antes de observar la distribución real | Posible inclusión/exclusión arbitraria | Análisis de sensibilidad de 3/5 niveles y 9/12 puntos | Alta | Abierto | SRC-008 | D-011 | Justificar, modificar o retirar umbrales con evidencia del corpus |
