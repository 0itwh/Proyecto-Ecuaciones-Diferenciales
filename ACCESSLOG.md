# ACCESS LOG

## Fase

**Fase 1: auditoría y selección de datos.**

## Objetivo

Registrar de forma reproducible cada intento de acceso, su resultado, impacto y alternativa.

## Estado de evidencia

Los resultados siguientes están **confirmados** para el entorno de ejecución utilizado. No demuestran por sí solos el estado externo del servicio.

| attempt_id | source_id | fecha_hora | método | recurso | código | tipo_respuesta | autenticación | resultado | impacto | alternativa | issue_id |
|---|---|---|---|---|---:|---|---|---|---|---|---|
| ATT-001 | SRC-001 | 2026-11-03T22:03:00-05:00 | GET directo | https://materialsmine.org/nm | 403 | text/plain | No usada | `Request blocked by sandbox policy` | Registros no inspeccionados | Navegador autorizado | I-001 |
| ATT-002 | SRC-002 | 2026-11-03T22:03:00-05:00 | GET directo | https://materialsmine.org/explorer | 403 | text/plain | No usada | `Request blocked by sandbox policy` | Consultas interactivas no ejecutadas | Explorer manual y exportación | I-001 |
| ATT-003 | SRC-003 | 2026-11-03T22:03:00-05:00 | GET directo | https://materialsmine.org/explorer/tools | 403 | text/plain | No usada | `Request blocked by sandbox policy` | Herramientas no probadas | Revisión manual en navegador | I-001 |
| ATT-004 | SRC-004 | 2026-11-03T22:03:00-05:00 | Lectura web indexada | https://materialsmine.org/api-docs/ | n/a | Swagger/OAS | No determinada | API 1.0.0 y OAS 3.0 documentadas; ejecución no validada | Auth, parámetros y paginación no verificados | Exportar OpenAPI desde Swagger/DevTools | I-002 |
| ATT-005 | SRC-004 | 2026-11-03T22:03:00-05:00 | GET directo | https://materialsmine.org/api-docs/ | 403 | text/plain | No usada | `Request blocked by sandbox policy` | OpenAPI no descargada | Navegador autorizado | I-002 |
| ATT-006 | SRC-009 | 2026-11-03T22:03:00-05:00 | GET directo | https://materialsmine.org/curate/schema | 403 | text/plain | No usada | `Request blocked by sandbox policy` | XSD vigente no recuperado | Swagger “Try it out” o navegador autorizado | I-003 |
| ATT-007 | SRC-010 | 2026-11-03T22:03:00-05:00 | GET directo | https://materialsmine.org/api-docs/swagger.json | 403 | text/plain | No usada | `Request blocked by sandbox policy` | Especificación no descargada | Localizar URL OpenAPI en DevTools | I-002 |
| ATT-008 | SRC-006 | 2026-11-03T22:03:00-05:00 | Búsqueda web | https://github.com/Duke-MatSci/nanomine-schema | n/a | Repositorio Git | No requerida para consulta pública | Versiones históricas XSD y formularios localizados | No confirma XSD desplegado | Comparar hash y fecha con SRC-009 | I-008 |
| ATT-009 | SRC-007 | 2026-11-03T22:03:00-05:00 | Búsqueda web | https://github.com/Duke-MatSci/nanomine | n/a | Repositorio Git | No requerida para consulta pública | Código prototipo/histórico localizado | No usar como verdad de producción | Evidencia auxiliar | I-008 |

## Interpretación

El cuerpo de las respuestas 403 identifica explícitamente la política del entorno. Por ello, se registra el bloqueo como limitación del sandbox y no como caída o denegación propia de MaterialsMine.
