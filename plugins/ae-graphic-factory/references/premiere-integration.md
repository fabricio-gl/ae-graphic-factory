# Integración Premiere downstream

AE Graphic Factory reutiliza la skill externa `$premiere-jsx-script-creator`; no incorpora una copia ni le asigna fabricación de AEP/MOGRT.

Entrada: AEP o MOGRT realmente generado, composición, duración, FPS, pista, intervalo y exactamente una política. Políticas preservadas: `STRICT_EMPTY`, `REUSE`, `REPLACE_RANGE`.

Autoridad dentro del flujo: instrucción explícita reciente, GRAPHIC_SPEC congelado, artefacto generado, duración/FPS, pista/intervalo, timeline real e inferencias técnicas. Premiere no cambia tipografía, color, timing interno, composición ni referencia visual.

Solo la ejecución real permite `PREMIERE_IMPORT_OK`; además debe verificarse el TrackItem en timeline para `PREMIERE_TIMELINE_OK`.
