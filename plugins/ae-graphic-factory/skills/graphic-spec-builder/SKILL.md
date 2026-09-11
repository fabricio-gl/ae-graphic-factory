---
name: graphic-spec-builder
description: Convierte una idea en lenguaje natural, referencias visuales y una duración exacta en un GRAPHIC_SPEC validable para AE Graphic Factory. Usar para analizar referencias, congelar diseño, geometría, tipografía y movimiento antes de generar JSX. No genera JSX ni permite continuar sin duración.
---

# Graphic Spec Builder

Decide qué debe verse. Produce `GRAPHIC_SPEC.json` como única fuente artística para las fases posteriores; no escribe JSX directamente.

## Input gate

Extrae primero duración, FPS y resolución. La duración exacta es obligatoria. Si falta, detén el flujo y pregunta únicamente: `¿Qué duración exacta debe tener el gráfico?` No escribas `GRAPHIC_SPEC.json`, JSX, AEP ni MOGRT.

Usa `30 fps`, `1920x1080`, After Effects `24.x` y Premiere Pro `2024` cuando el usuario no los sustituya explícitamente. Acepta segundos decimales o frames. Calcula `frame_count` desde duración por FPS. Las animaciones visuales terminan como máximo en `frame_count - 1`; un fundido de audio puede terminar exactamente en el límite final de la composición.

## Resolver el diseño

Mantén esta autoridad: instrucción explícita reciente, duración, referencia adjunta, evidencia verificable, medición, criterio conservador y defaults. Registra en `intent.explicit_constraints` las decisiones concretas sin reinterpretarlas. Resuelve detalles ordinarios de una idea vaga sin preguntar y registra cada inferencia en `assumptions` con confianza.

Acepta imágenes y videos adjuntos directamente. Analízalos con la capacidad visual disponible en la sesión: composición, geometría, jerarquía, color, tipografía, recorte, roles de assets y eventos de movimiento. No pidas al usuario que prepare `reference_analysis.json`. Python no ejecuta visión; la frontera correcta es que esta skill produzca el análisis estructurado y lo entregue al runner.

Asigna a cada archivo un rol inequívoco como `background_video`, `card_content`, `image`, `video`, `logo`, `icon` o `reference`. Cada elemento que use medios debe conservar su `asset_id`; no elijas el primer asset preservado por orden accidental. Preserva como raster el contenido complejo que no necesite edición; reconstruye solo lo que deba animarse, editarse o mejore materialmente la fidelidad.

Cuando texto editable requiera identificar una fuente, usa MyFonts/WhatTheFont, nunca una estimación visual:

1. Para una región nombrada, usa `mcp__codex_apps__myfonts_get_region` y después `mcp__codex_apps__myfonts_detect_font_regions` con su caja; para identificación genérica usa directamente `mcp__codex_apps__myfonts_detect_font_regions`.
2. Usa `mcp__codex_apps__myfonts_predict_font` para la región elegida cuando proceda.
3. Registra únicamente nombres devueltos por MyFonts con confianza `confirmed`, `high`, `medium`, `low` o `unresolved`.
4. Si la llamada falla, deja `font: null`, `confidence: unresolved` y conserva un fallback técnico claramente marcado.

MyFonts es una app conectada descubierta por el registro de capacidades de la sesión, no una ruta privada ni otra skill. No pidas `myfonts-response.json`. Si las herramientas no están disponibles o fallan, entrega `myfonts_response: null` y deja la tipografía `unresolved`. Web es solo verificación complementaria cuando exista CSS, identidad o documentación pública relevante.

## Construir y validar

El builder produce schema 1.1.0 y acepta specs 1.0.0 válidos. Declara `exports.mogrt` (default true): MOGRT requiere al menos un control significativo resuelto a una propiedad del gráfico. Si el usuario solicita solo AEP, usa false; no añadas controles ficticios para superar la validación.

Para footage conserva nombres esperados relativos, rol, `media_type` y, cuando estén medidos, `expected.width/height/duration_seconds/has_video/has_audio`. El orquestador no inventa metadatos de medios. Un recurso visual de referencia no tiene por qué ser footage importable en AE 24.x; por ejemplo, SVG puede analizarse visualmente pero no se importa directamente con este renderer. Consulta el contrato de medios/audio antes de prometer una conversión.

Para volumen usa `appearance.audio_gain_percent` en video/audio y animaciones de `audio_gain_percent`, rango 0–100. Los fundidos son lineales en ganancia muestreada por fotograma; no usan overshoot. El último tramo de 15 frames de una composición de 150 frames es 135→150. No confundas esa indicación con la duración total del pedido.

Lee [el contrato GRAPHIC_SPEC](references/graphic-spec-contract.md). No fuerces una tarjeta: usa un preset explícito solo cuando lo sostengan el pedido o la referencia; para diseños distintos entrega elementos generales o el preset `title_panel`.

En tareas con adjuntos, invoca `../../scripts/run_pipeline.py --orchestrator-stdin --workspace RUTA` y escribe por stdin un envelope interno versión `1.0` con `request`, rutas de `attachments`, `visual_analysis` y `myfonts_response`. El envelope lo crea esta skill y nunca el usuario. `visual_analysis.asset_roles` debe mapear cada nombre de archivo a su rol, y puede incluir `layout`, `colors`, `motion`, `typography`, `text`, `preset` o una lista completa de `elements`. Sin adjuntos puede usarse `--request` directamente.

Para normalizar una respuesta real de MyFonts usa el contrato de `../../scripts/aegf/myfonts_adapter.py`. Valida siempre contra `../../schemas/graphic-spec.schema.json` y las reglas semánticas mediante `../../scripts/validate_graphic_spec.py`.

Tras `GRAPHIC_SPEC_READY`, si el usuario pidió el resultado final, invoca `$ae-graphic-jsx-creator` con el archivo validado, no con el brief original. Para una integración posterior solicita `$premiere-jsx-script-creator`; esa skill solo recibe resultados generados y no reabre decisiones estéticas.
