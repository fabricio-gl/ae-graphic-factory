# Contrato JSX de After Effects

Objetivo: After Effects 24.x y sintaxis ExtendScript compatible. El archivo se genera exclusivamente desde un `GRAPHIC_SPEC` válido.

## Invariantes estáticos

- `#target aftereffects` y una IIFE autosuficiente.
- `CONFIG`, `STATE`, log, preflight y errores accionables.
- Composición con duración, FPS, anchura y altura del spec.
- Propiedades por `matchName`, capas con nombres funcionales y animación dentro de frames.
- Point text y paragraph text diferenciados; este último conserva caja y medición de anclaje.
- `shape_size` conectado a Rectangle Path > Size con compensación de origen.
- Track Matte real mediante `setTrackMatte()` para contenido raster redondeado.
- Easing `ease_in`, `ease_out` y `ease_in_out` traducido a influencias temporales distintas; overshoot con keyframe intermedio.
- Controles compartidos resueltos mediante una propiedad maestra y expresiones.
- Essential Graphics mediante `addToMotionGraphicsTemplateAs`.
- Ninguna ruta absoluta personal ni placeholder.
- `app.project.save(aepFile)` ocurre antes de `exportAsMotionGraphicsTemplate()`.
- El retorno de exportación se guarda y se comprueba explícitamente.
- El éxito conjunto ocurre únicamente después de esa comprobación. AEP-only tiene su propio mensaje.
- Posición espacial usa una sola KeyframeEase; TwoD/ThreeD no espaciales usan 2/3, COLOR y escalares 1.
- Preflight de nombres/formatos antes de importar; metadatos y hasAudio antes de crear capas.
- MOGRT requiere controladores reales contados; Gaussian Blur publica su cantidad, no un control ficticio.
- El AEP guardado no se retira si falla MOGRT. El rollback no toca un proyecto preexistente.

## Ejecución

El script exige un proyecto vacío para no alterar trabajo abierto. Usa `AEGF_OUTPUT_DIR` si existe; en caso contrario solicita una carpeta. Resuelve assets relativos a `AEGF_INPUT_DIR`, al directorio `input` junto al JSX o mediante selección. Guarda `grafico.aep`, exporta `grafico.mogrt` y escribe `ae_graphic_factory.log`.

La existencia de un JSX válido permite `JSX_GENERATED` y `STATIC_CHECK_OK`, no `AE_RUNTIME_OK` ni `MOGRT_EXPORT_OK`.

Lee [runtime y migración](../../../references/runtime-contracts.md) al generar o auditar medios, audio, controles o estados. El JSX no se atribuye una prueba estática que no ejecutó: ese resultado lo emite el validador externo.
