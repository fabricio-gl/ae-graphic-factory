# Contratos de medios, audio y exportación

## Compatibilidad y migración

El builder produce schema_version 1.1.0; el validador acepta 1.0.0 y 1.1.0. Se mantienen duración obligatoria, 30 fps/1920×1080 por defecto, tipos generales, presets, Track Mattes y separación GRAPHIC_SPEC → JSX AE → integración Premiere. No hay APIs Premiere en el renderer.

exports.mogrt es booleano y por omisión true (comportamiento anterior). Si es true, essential_graphics requiere al menos un control significativo: propiedad existente compatible con su target, nombre no vacío/único, sin duplicaciones. Si es false, se permite una lista vacía y se guarda solo AEP. Los paths legacy TITLE.Source Text y cualquier LABEL.Fill Color siguen admitidos cuando resuelven un elemento real; no se mezclan con property/targets.

Cambios deliberados de seguridad: un spec antiguo con cero controles y exportación implícita, un asset obligatorio usado como capa pero marcado optional, o SVG/JSX como footage ya no es válido. La migración consiste en elegir controles reales o AEP-only, corregir required y suministrar footage admitido. No se sustituyen recursos ni controles silenciosamente. Los fixtures antiguos SVG para footage se reemplazaron por PNG sintéticos, conservando las pruebas de comportamiento y los SVG originales como referencias.

## Medios

Cada capa de medio usa asset_id explícito. El contrato compilado incluye rol, media_type, expected_filename derivado de source, requerimiento de audio y duración mínima. Los assets no utilizados por capas permanecen como referencias y no se importan. No hay búsqueda de «primer asset preserve».

source es relativo, sin '..' ni ruta personal. El selector relocaliza exactamente ese nombre (sin distinguir mayúsculas en Windows), no acepta un reemplazo arbitrario.

Subset conservador nativo para AE 24.x:

| Tipo | Extensiones |
|---|---|
| image | png, jpg, jpeg, bmp, tif, tiff, psd, ai, eps, pdf, exr |
| video | avi, mp4, mov, m4v, mxf |
| audio | wav, aif, aiff, mp3 |

Una extensión permitida no garantiza el codec. Se exige archivo existente/no vacío, canImportAs(FOOTAGE), importación efectiva como FootageItem y comprobación de mainSource, hasVideo/hasAudio, dimensiones y duración. Se desactiva la detección de secuencias numeradas. Errores de importación informan id/rol/nombre y solicitan un archivo decodificable; el plugin no incluye transcodificación ni depende de ffmpeg.

expected puede contener has_video, has_audio, width, height, duration_seconds y min_duration_seconds medidos. Width/height son exactos; las comparaciones temporales admiten 0.0001 s de tolerancia numérica. El renderer actual reproduce desde cero, sin retiming/loop implícito: un medio temporal usado por una capa debe cubrir toda la composición (o una duración mínima explícita mayor). Una imagen fija no exige duración temporal.

El preflight sin mutaciones verifica archivos y contrato antes del undo group. Los metadatos AE requieren importar: esa segunda fase ocurre dentro de la transacción aislada, antes de crear composición/capas. Si falla, se retiran los objetos importados por esa ejecución. Nunca se cambia un proyecto preexistente ni se modifican los medios fuente.

## Audio

Una capa video/audio puede declarar appearance.audio_gain_percent entre 0 y 100. animation.property=audio_gain_percent admite valores escalares en ese rango, interpolation=linear, easing.type=linear, overshoot=false y motion_blur=false. Se exige hasAudio antes de acceder a ADBE Audio Group > ADBE Audio Levels.

El porcentaje representa ganancia de amplitud:

- 100 → [0, 0] dB.
- 50 → aproximadamente [-6.0206, -6.0206] dB.
- 0 → [-192, -192] dB, mínimo/silencio técnico de AE (no -Infinity).
- Para valores positivos: max(-192, 20 × log10(porcentaje / 100)).

Se escribe el mismo valor en ambos canales. La ganancia lineal se muestrea en cada límite de fotograma y cada muestra se convierte a dB; entre muestras AE interpola en dB. No se promete una curva continua exactamente lineal en amplitud entre muestras. Los valores anteriores al primer keyframe mantienen la primera ganancia.

Aceptación: 5 s × 30 fps = 150 frames. Fundido start_frame=135, end_frame=150, 100→0. Son 16 muestras que delimitan 15 intervalos, desde 4.5 hasta 5.0 s. Solo audio puede usar ese último límite; las animaciones visuales terminan en frame 149. Si la duración no es un múltiplo exacto del frame, el límite de audio se acota a duration_seconds.

## Easing y Essential Graphics

No se deduce la dimensión temporal de property.value.length. Se usa una KeyframeEase si isSpatial; para no espaciales PropertyValueType.TwoD y ThreeD usan 2 y 3; los demás (incluido Color) usan 1.

Los controles resuelven property/targets (o legacy source_property). blur corresponde a la cantidad de ADBE Gaussian Blur 2 en un adjustment. Los colores compartidos mantienen su propiedad maestra. Cada addToMotionGraphicsTemplateAs debe retornar true y aumentar motionGraphicsTemplateControllerCount en uno. Antes de exportar se exige al menos un controlador confirmado y el total esperado.

## Estados y recuperación

PREFLIGHT_OK y MEDIA_PREFLIGHT_OK distinguen archivos de metraje. AEP_BUILD_OK indica construcción validada y todavía disponible; AEP_SAVE_OK exige archivo no vacío y app.project.file coincidente. AE_RUNTIME_OK se conserva como compatibilidad para construcción + AEP guardado, no para MOGRT.

MOGRT_EXPORT_OK pasa solo tras retorno true de exportAsMotionGraphicsTemplate y archivo no vacío, siempre después de guardar AEP. Si la API falla o lanza excepción, se marca FAIL y se conserva el AEP, sin rollback. AEP-only usa NOT_APPLICABLE para MOGRT.

Antes de guardar AEP, el fallo retira solo objetos registrados por la ejecución; ROLLBACK_OK informa PASS/FAIL. Si se retira una construcción, AEP_BUILD_OK no queda PASS. No se cierra ni se sale de un proyecto preexistente cuando falla preflight. Salidas existentes se rechazan, no se sobrescriben.

Las fases públicas GENERADO, SINTAXIS_CORRECTA (Node + restricciones ES3), PRUEBA_ESTATICA_OK, PRUEBA_AUTOMATIZADA_OK y VALIDACIÓN_FUNCIONAL_REAL son independientes. El doble de API no es After Effects; sus archivos son virtuales y sus PASS internos solo validan contratos. El JSX deja STATIC_CHECK_OK=NOT_TESTED porque no puede atribuirse la comprobación externa.

## Fuentes y alcance

[Adobe: formatos admitidos](https://helpx.adobe.com/sg/after-effects/desktop/get-started/supported-file-formats/supported-file-formats.html) distingue formato de codec; su documentación actual incluye capacidades posteriores a 24.x. [Adobe: importación SVG](https://helpx.adobe.com/after-effects/desktop/import-files/import-svg-files/import-svg-files.html) corresponde a versiones nuevas, no se retroproyecta a 2024. [Adobe: Essential Graphics](https://helpx.adobe.com/after-effects/desktop/motion-graphics/work-with-motion-graphics-templates/creating-motion-graphics-templates.html) describe propiedades editables.

Los contratos de cardinalidad, volumen y controladores se prueban además con ejecución en el host real cuando está disponible; consulta los registros del caso de aceptación, no deduzcas compatibilidad de un test doble.
