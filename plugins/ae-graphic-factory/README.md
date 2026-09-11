# AE Graphic Factory

AE Graphic Factory convierte una idea natural, referencias visuales y una duración exacta en un `GRAPHIC_SPEC` validado y un JSX autosuficiente para After Effects 24.x. La creación real de AEP/MOGRT queda para una fase posterior en After Effects; la integración con Premiere Pro 2024 se delega a la skill externa `premiere-jsx-script-creator`.

## Entrada y defaults

La duración exacta es obligatoria. Sin ella, el flujo pregunta `¿Qué duración exacta debe tener el gráfico?` y no genera `GRAPHIC_SPEC` ni JSX.

Si el pedido no indica otros valores, se aplican:

- 30 fps;
- 1920×1080;
- After Effects 24.x;
- Premiere Pro 2024.

No es necesario escribir JSON, YAML, keyframes ni propiedades de After Effects. Las instrucciones concretas se conservan como restricciones; los vacíos de una idea vaga se resuelven y quedan registrados en `assumptions`.

## Referencias visuales y tipografía

En Codex, adjunta imágenes o videos al pedido. `graphic-spec-builder` usa la capacidad visual de la sesión y entrega al núcleo Python un envelope interno versionado. Python valida y normaliza ese handoff, pero no simula visión. El usuario no prepara `reference_analysis.json`.

Cada asset recibe un rol explícito, por ejemplo `background_video`, `card_content`, `image`, `logo`, `icon` o `reference`, y cada elemento de metraje declara su `asset_id`.

Cuando identificar una fuente editable sea material, la skill usa MyFonts/WhatTheFont solo si sus herramientas están presentes en el registro de capacidades de la sesión. El adaptador conserva únicamente nombres devueltos por el proveedor; si la capacidad no está disponible o falla, produce `font: null` y `confidence: unresolved`. Los mocks de éxito y fallo viven en `tests/fixtures/`.

## Probar completamente offline

Desde la raíz extraída del plugin:

```powershell
python -X utf8 -B -m unittest discover -s tests -v
python -X utf8 -B scripts/run_offline_e2e.py --workspace AE_Graphic_Lab_offline
python -X utf8 -B scripts/run_release_checks.py
```

`run_offline_e2e.py` genera dos casos separados:

- editorial de 6 s con video de fondo, captura, blur, Track Matte redondeado, dos reveals y entrada/salida;
- no editorial `custom` de 5 s con panel, icono, cifra y texto secundario animados por separado, sin `CARD`, `TITLE` ni `HL_*`.

La suite usa medios sintéticos, validación de schema, validación estática y un doble estricto de la API AE ejecutado con Node. El doble no es After Effects y nunca convierte sus resultados en validación runtime Adobe.

## Cargar y probar después en Codex

El CLI comprobado en esta versión de Codex instala plugins desde un marketplace configurado; el ZIP no contiene ni modifica un marketplace. Extrae la carpeta `ae-graphic-factory` en la ubicación que ya use tu marketplace local y confirma que su entrada apunte a esa copia. Después ejecuta:

```powershell
codex plugin add ae-graphic-factory@<marketplace>
```

Abre una tarea nueva para cargar la versión actualizada. Invoca `$graphic-spec-builder` con idea, referencias y duración; tras validar el spec, usa `$ae-graphic-jsx-creator`. La integración posterior usa `$premiere-jsx-script-creator` con exactamente una política: `STRICT_EMPTY`, `REUSE` o `REPLACE_RANGE`.

No se afirma un nombre de marketplace concreto: depende de la configuración local y no forma parte de este paquete.

## Prueba manual posterior en After Effects

Esta fase no forma parte de las pruebas offline. En una instancia separada de After Effects 24.x y con un proyecto vacío:

1. coloca los medios requeridos en `input/` junto al workspace del JSX;
2. ejecuta `output/crear_grafico.jsx` mediante `Archivo > Secuencias de comandos > Ejecutar archivo de secuencia de comandos`;
3. selecciona una carpeta de salida nueva, o define `AEGF_OUTPUT_DIR`;
4. verifica composición, capas, controles, `grafico.aep`, `grafico.mogrt` y `ae_graphic_factory.log`;
5. marca estados runtime solo a partir de esa ejecución real.

La skill de Premiere no fabrica AEP/MOGRT ni reinterpreta el diseño. Solo integra resultados downstream mediante Dynamic Link/importación, timeline, validación y guardado.

## Estados de validación

- `PASS`: la fase indicada se ejecutó y se verificó.
- `FAIL`: la fase se ejecutó y no cumplió el contrato.
- `NOT_TESTED`: la fase no se ejecutó; es el estado obligatorio para AE/MOGRT/Premiere durante validación offline.
- `NOT_APPLICABLE`: una fase no corresponde al flujo, por ejemplo MOGRT en una ejecución real solicitada como AEP-only.

`GRAPHIC_SPEC_READY`, `JSX_GENERATED` y `STATIC_CHECK_OK` pueden quedar en `PASS` offline. `AE_RUNTIME_OK`, `MOGRT_EXPORT_OK`, `PREMIERE_IMPORT_OK` y `PREMIERE_TIMELINE_OK` exigen ejecutar realmente las aplicaciones correspondientes.

Consulta [contratos de runtime](references/runtime-contracts.md) para medios, audio, easing, Essential Graphics, guardado, exportación y recuperación, y [la frontera Premiere](references/premiere-integration.md) para la integración downstream.
