# Contrato GRAPHIC_SPEC

`GRAPHIC_SPEC` es la frontera entre diseño y construcción. Debe superar el schema `schemas/graphic-spec.schema.json` y las reglas semánticas del validador antes de generar JSX.

## Autoridad

1. Restricción explícita más reciente.
2. Duración exacta.
3. Referencias adjuntas.
4. Evidencia externa verificable.
5. Medición de imagen o video.
6. Inferencia profesional conservadora.
7. Defaults.

Cada restricción explícita conserva `source_text`, `path` y `value`. Cada dato no comprobable se registra en `assumptions` con razón y confianza. La tipografía identificada conserva proveedor y confianza; un fallo no se convierte en un nombre inventado.

## Tiempo

`frame_count` se deriva de duración por FPS, salvo una duración expresada directamente en frames. Las animaciones visuales cumplen `0 <= start_frame <= end_frame < frame_count`. Para audio, `start_frame < end_frame <= frame_count`; el último keyframe puede ubicarse en el límite de la composición, nunca después de duration_seconds. La composición conserva duration_seconds como hard constraint.

## Medios, audio y migración 1.1

Lee [el contrato de runtime y migración](../../../references/runtime-contracts.md) para formatos, metadatos esperados, ganancia de audio y exportación condicional. Los specs 1.0.0 con controles reales siguen siendo válidos. Un antiguo spec que solicitaba implícitamente MOGRT sin controles ahora se rechaza: declara un control real o pide explícitamente AEP-only.

## Referencias y frontera de orquestación

La skill recibe imágenes/videos, ejecuta la capacidad visual de la sesión y pasa al runner un envelope interno por stdin. El usuario no entrega JSON. El núcleo Python valida y normaliza ese handoff, pero no simula visión.

El análisis puede aportar `layout`, `colors`, `motion`, `typography`, `asset_roles`, `preset` y, para reconstrucciones libres, `elements`, `animation` y `essential_graphics`. Solo completa campos que el usuario no haya fijado. Los assets complejos usan `preserve_or_reconstruct: preserve`; elementos editables o animables usan `reconstruct`. Cada elemento de medio declara `asset_id` y las esquinas redondeadas de raster declaran `matte_id`.

## Modelo general

Los elementos base son `text`, `shape`, `image`, `video`, `icon`, `matte`, `line`, `panel`, `group` y `adjustment`. `editorial_card` y `title_panel` son presets opcionales. Un `GRAPHIC_SPEC` custom puede combinar esos tipos sin introducir `CARD`, `TITLE` o `HL_*` salvo que el diseño realmente los necesite.

El texto puede ser `point` o `paragraph`; el segundo declara `text_box.width` y `text_box.height`. `shape_size` anima Rectangle Path > Size y declara `origin` para estabilizar el borde. Los controles de Essential Graphics nuevos declaran `property` y `targets`; cuando comparten varios targets usan `master: true`.

## MyFonts

La app conectada devuelve candidatos. El adaptador acepta un resultado normalizado con `selected_font` o `candidates`. Solo un nombre presente en esa respuesta puede pasar a `typography[].font`; si no hay candidato válido, el estado es `unresolved`.
