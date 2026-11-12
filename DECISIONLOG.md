# DECISION LOG

## Fase

**Fase 1: auditoría y selección de datos.**

## Estado de evidencia

Las decisiones se clasifican como confirmadas, documentadas, inferidas o provisionales y se enlazan con las fuentes e incidencias relevantes.

| decision_id | fecha | decisión | clasificación | fundamento | source_id | issue_id | condición_de_revisión |
|---|---|---|---|---|---|---|---|
| D-001 | 2026-11-03 | Limitar la ejecución a Fase 1 | Confirmado | Instrucción expresa del usuario | SRC-008 |  | Solo mediante nueva autorización |
| D-002 | 2026-11-03 | No entrenar ni ajustar modelos | Confirmado | Prohibición expresa y ausencia de dataset validado | SRC-008 | I-005 | Después de superar las puertas de datos |
| D-003 | 2026-11-03 | Mantener conductividad eléctrica como objetivo provisional | Documentado | Candidata inicial condicionada a cobertura real | SRC-008 | I-005 | Revisar tras auditoría de cobertura |
| D-004 | 2026-11-03 | Mantener propiedades mecánicas en corpus separado | Documentado | Evita mezclar objetivos físicamente distintos | SRC-008 |  | Revisar solo con nuevo alcance científico |
| D-005 | 2026-11-03 | No llamar observable a un campo sin registro accesible | Confirmado metodológicamente | El esquema no demuestra presencia ni cobertura | SRC-008 | I-004 | Revisar al inspeccionar registros |
| D-006 | 2026-11-03 | No seleccionar familia material definitiva | Confirmado | Series y cobertura no verificadas | SRC-008 | I-005 | Revisar al verificar series |
| D-007 | 2026-11-03 | Tratar CNT, grafeno/GNP y negro de carbono como familias candidatas de relleno/geometría | Inferido | Candidatos para orientar la búsqueda, no selección final | SRC-008 | I-005 | Revisar con cobertura observada |
| D-008 | 2026-11-03 | Exigir jerarquía estudio–serie–muestra–medición | Documentado | Evita duplicidad, mezcla y fuga de información | SRC-008 |  | Mantener salvo incompatibilidad de fuente documentada |
| D-009 | 2026-11-03 | Interpretar el 403 como bloqueo del entorno | Confirmado | El cuerpo de respuesta indica `Request blocked by sandbox policy` | SRC-001;SRC-002;SRC-003;SRC-004;SRC-009;SRC-010 | I-001;I-002;I-003 | Revisar si otro entorno devuelve una respuesta distinta |
| D-010 | 2026-11-03 | Posponer conversiones masa–volumen | Confirmado | Requieren densidades y composición exacta | SRC-008 | I-004 | Revisar solo con densidades defendibles |
| D-011 | 2026-11-03 | Adoptar umbrales y rúbrica como hipótesis operativas provisionales | Provisional | Facilitan cribado inicial, pero no están validados por datos ni fuente externa | SRC-008 | I-009 | Someter a sensibilidad tras observar la distribución real de series |
| D-012 | 2026-11-03 | Separar cierre administrativo y cierre científico de Fase 1 | Confirmado metodológicamente | La auditoría está documentada, pero observabilidad y series siguen inconclusas | SRC-008 | I-001;I-004;I-005 | Cerrar científicamente tras resolver las incidencias críticas |
