---
name: ae-graphic-jsx-creator
description: Traduce un GRAPHIC_SPEC ya congelado y validado a un JSX completo para Adobe After Effects 24.x, con AEP, Essential Graphics y exportación MOGRT. Usar después de graphic-spec-builder o para validar JSX AE; no rediseña el gráfico ni usa APIs de Premiere.
---

# AE Graphic JSX Creator

Decide cómo construir en After Effects un diseño ya cerrado. Rechaza un `GRAPHIC_SPEC` inválido y nunca usa el brief original para cambiar estética, timing o jerarquía.

## Construcción

Lee [el contrato de generación JSX](references/after-effects-jsx-contract.md). Prioriza Shape Layers, propiedades por `matchName`, texto editable, Gaussian Blur nativo, Track Matte, `KeyframeEase`, Motion Blur y propiedades compatibles con Essential Graphics. No introduzcas plugins de terceros.

Usa nombres funcionales breves como `BG`, `BLUR`, `CARD`, `CARD_MATTE`, `CARD_SHADOW`, `HL_01`, `TITLE` y `SUBTITLE`. Expón controles humanos como `Título`, `Color de subrayado` o `Posición de tarjeta`; nunca IDs internos.

Renderiza los tipos generales del spec. Para `paragraph` usa `addBoxText([width, height])`; conserva `addText()` para point text y aplica `sourceRectAtTime()` solo cuando el spec solicite ajuste de anclaje. `shape_size` debe animar Rectangle Path > Size y, para un origen lateral/superior/inferior, compensar Rectangle Path > Position. Los elementos con `matte_id` usan `setTrackMatte(..., TrackMatteType.ALPHA)` y verifican `trackMatteLayer`.

Los controles Essential Graphics se resuelven por `targets` y `property`, no por nombres hard-coded. Un color compartido crea un `ADBE Color Control` maestro en `CONTROLS` y vincula todos sus targets mediante expresiones.

El JSX mantiene: configuración, estado/log, preflight de archivos sin mutaciones, importación controlada y validación de metraje, construcción, relaciones/Track Mattes, animación, Essential Graphics, validación, guardado AEP y exportación MOGRT si se solicita. La importación es necesaria para leer metadatos AE; no se crean capas hasta verificar todos los medios. Comprueba rol/nombre/extensión y existencia antes de importar, y FootageItem/hasVideo/hasAudio/dimensiones/duración antes de acceder a propiedades de capa. No aceptes JSX, SVG ni un archivo arbitrario como footage.

Easing: `property.isSpatial` exige exactamente una KeyframeEase. Las propiedades no espaciales TwoD/ThreeD usan 2/3, las restantes 1; la longitud del array de valor no es una regla válida. Para audio usa `ADBE Audio Levels`, 20·log10(ganancia/100) en ambos canales y -192 dB para 0; valida hasAudio antes de resolver esa propiedad.

MOGRT solicitado exige controles significativos en el spec y `motionGraphicsTemplateControllerCount` creciente tras cada publicación. Nunca inventes un control de relleno. `blur` publica la cantidad nativa de Gaussian Blur. El éxito conjunto exige retorno true de exportación y archivo no vacío. AEP-only anuncia solo AEP. Un fallo MOGRT conserva el AEP verificado; rollback retira únicamente objetos propios de una construcción no guardada y registra si falla.

No codifiques rutas personales. Resuelve recursos desde `AEGF_INPUT_DIR`, `input` junto a output o el directorio del JSX. El selector solo relocaliza el nombre esperado y siempre se valida; no admite sustituciones silenciosas. Permite `AEGF_OUTPUT_DIR` y rechaza sobrescribir un AEP/MOGRT existente.

## Generar y comprobar

Ejecuta `../../scripts/generate_ae_jsx.py GRAPHIC_SPEC.json crear_grafico.jsx` y luego `../../scripts/validate_ae_jsx.py crear_grafico.jsx --strict`. Corrige todo error antes de reportar `STATIC_CHECK_OK`.

Marca `AE_RUNTIME_OK` solo si el JSX se ejecutó realmente en After Effects 24.x y se verificaron composición, capas y AEP. Marca `MOGRT_EXPORT_OK` solo si la exportación real produjo el archivo. La prueba estática no equivale a ninguno de esos estados.

Si se solicita integración Premiere, entrega el AEP/MOGRT, composición, duración, FPS, pista, intervalo y una sola política a `$premiere-jsx-script-creator`. No generes operaciones Premiere dentro del JSX de After Effects.
