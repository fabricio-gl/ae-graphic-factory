"""Generate an After Effects 24.x ExtendScript from a frozen GRAPHIC_SPEC."""

from __future__ import annotations

import json
from typing import Any, Dict

from .graphic_spec import validate_graphic_spec
from .schema_validation import validate_graphic_spec_schema
from .media_contract import MEDIA_EXTENSIONS, media_requirements


def generate_jsx(spec: Dict[str, Any]) -> str:
    errors = validate_graphic_spec_schema(spec) + validate_graphic_spec(spec)
    if errors:
        raise ValueError("GRAPHIC_SPEC inválido: " + "; ".join(errors))

    config = {
        "spec": spec,
        "comp_name": "AEGF_MASTER",
        "template_name": "grafico",
        "export_mogrt": spec.get("exports", {}).get("mogrt", True),
        "media_assets": media_requirements(spec),
        "media_extensions": MEDIA_EXTENSIONS,
        "output": {
            "aep_filename": "grafico.aep",
            "mogrt_filename": "grafico.mogrt",
            "log_filename": "ae_graphic_factory.log",
        },
    }
    config_json = json.dumps(config, ensure_ascii=True, separators=(",", ":"))

    return """#target aftereffects
(function aeGraphicFactory() {
    var CONFIG = %s;
    var STATE = {
        outputFolder: null,
        inputFolder: null,
        assetFiles: {},
        footage: {},
        layers: {},
        comp: null,
        phase: "PREFLIGHT_OK",
        ownsBuild: false,
        undoOpen: false,
        aepSaved: false,
        controllersAdded: 0,
        createdItems: [],
        log: [],
        states: {
            GRAPHIC_SPEC_READY: "PASS",
            JSX_GENERATED: "PASS",
            STATIC_CHECK_OK: "NOT_TESTED",
            PREFLIGHT_OK: "NOT_TESTED",
            MEDIA_PREFLIGHT_OK: "NOT_TESTED",
            AEP_BUILD_OK: "NOT_TESTED",
            AEP_SAVE_OK: "NOT_TESTED",
            ROLLBACK_OK: "NOT_APPLICABLE",
            AE_RUNTIME_OK: "NOT_TESTED",
            MOGRT_EXPORT_OK: "NOT_TESTED",
            PREMIERE_IMPORT_OK: "NOT_TESTED",
            PREMIERE_TIMELINE_OK: "NOT_TESTED"
        }
    };

    function log(message) {
        STATE.log.push((new Date()).toUTCString() + " | " + message);
        $.writeln("AEGF | " + message);
    }

    function fail(message) {
        throw new Error("AE Graphic Factory: " + message);
    }

    function headless() {
        return $.getenv("AEGF_HEADLESS") === "1";
    }

    function joinPath(folder, name) {
        return folder.fsName + "/" + name;
    }

    function hexToRgb(value) {
        var clean = String(value || "#000000").replace("#", "");
        if (clean.length !== 6) {
            fail("Color hexadecimal inválido: " + value);
        }
        return [
            parseInt(clean.substr(0, 2), 16) / 255,
            parseInt(clean.substr(2, 2), 16) / 255,
            parseInt(clean.substr(4, 2), 16) / 255
        ];
    }

    function byId(collection, id) {
        var i;
        for (i = 0; i < collection.length; i += 1) {
            if (collection[i].id === id) {
                return collection[i];
            }
        }
        return null;
    }

    function typographyFor(elementId) {
        var typography = CONFIG.spec.typography;
        var i;
        for (i = 0; i < typography.length; i += 1) {
            if (typography[i].element === elementId) {
                return typography[i];
            }
        }
        return {
            font: null,
            fallback: "ArialMT",
            size: 64,
            leading: 72,
            tracking: 0,
            alignment: "left"
        };
    }

    function chooseOutputFolder() {
        var fromEnv = $.getenv("AEGF_OUTPUT_DIR");
        if (fromEnv) {
            return new Folder(fromEnv);
        }
        return Folder.selectDialog("AE Graphic Factory: elige la carpeta de salida");
    }

    function chooseInputFolder() {
        var fromEnv = $.getenv("AEGF_INPUT_DIR");
        var scriptFile;
        var sibling;
        if (fromEnv) {
            return new Folder(fromEnv);
        }
        scriptFile = new File($.fileName);
        sibling = new Folder(scriptFile.parent.parent.fsName + "/input");
        if (sibling.exists) {
            return sibling;
        }
        return scriptFile.parent;
    }

    function resolveAssetFile(asset) {
        var direct;
        var relative;
        relative = new File(joinPath(STATE.inputFolder, asset.source));
        if (relative.exists) {
            validateAssetFile(asset, relative);
            return relative;
        }
        if (asset.required && !headless()) {
            direct = File.openDialog(
                "Rol " + asset.role + ": localiza exactamente " + asset.expected_filename,
                "Medio esperado:" + asset.expected_filename,
                false
            );
            if (direct && direct.exists) {
                validateAssetFile(asset, direct);
                return direct;
            }
        }
        if (asset.required) {
            fail("No se encontró el recurso obligatorio " + asset.source + ". Copia el archivo a input o define AEGF_INPUT_DIR.");
        }
        return null;
    }

    function assetError(asset, detail) {
        fail("Asset " + asset.id + " (rol " + asset.role + "; esperado " + asset.expected_filename + "): " + detail);
    }

    function validateAssetFile(asset, file) {
        var name = File.decode(file.name);
        var dot = name.lastIndexOf(".");
        var extension = dot < 0 ? "" : name.substr(dot).toLowerCase();
        var allowed = CONFIG.media_extensions[asset.media_type] || [];
        var accepted = false;
        var i;
        if (!file.exists || file.length <= 0) {
            assetError(asset, "archivo inexistente o vacío. Copia el medio a input.");
        }
        for (i = 0; i < allowed.length; i += 1) {
            if (extension === allowed[i]) {
                accepted = true;
            }
        }
        if (!accepted) {
            assetError(asset, "formato " + extension + " no compatible. Permitidos: " + allowed.join(", ") +
                ". No hay transcodificación automática; entrega un medio compatible con AE 24.x.");
        }
        if (name.toLowerCase() !== asset.expected_filename.toLowerCase()) {
            assetError(asset, "se seleccionó " + name + ". Selecciona el nombre esperado o corrige GRAPHIC_SPEC.");
        }
    }

    function rememberItem(item) {
        if (!item) {
            fail("After Effects no devolvió el objeto creado.");
        }
        STATE.createdItems.push(item);
        return item;
    }

    function validateFootage(asset, footage) {
        var expected = asset.expected || {};
        var visual = asset.media_type !== "audio";
        var minimum = Math.max(asset.minimum_duration, expected.min_duration_seconds || 0);
        if (!(footage instanceof FootageItem) || !footage.mainSource) {
            assetError(asset, "la importación no produjo un FootageItem válido.");
        }
        if (visual && (!footage.hasVideo || !(footage.width > 0 && footage.height > 0))) {
            assetError(asset, "se requiere hasVideo y dimensiones positivas; no es metraje visual.");
        }
        if (asset.require_audio && !footage.hasAudio) {
            assetError(asset, "se requiere hasAudio=true para el audio/fundido declarado.");
        }
        if (asset.media_type === "image" && !footage.mainSource.isStill) {
            assetError(asset, "se esperaba una imagen fija.");
        }
        if (asset.media_type !== "image" && (footage.mainSource.isStill || !(footage.duration > 0))) {
            assetError(asset, "se esperaba un medio temporal con duración positiva.");
        }
        if (expected.has_video !== undefined && footage.hasVideo !== expected.has_video) {
            assetError(asset, "hasVideo no coincide con expected.has_video.");
        }
        if (expected.has_audio !== undefined && footage.hasAudio !== expected.has_audio) {
            assetError(asset, "hasAudio no coincide con expected.has_audio.");
        }
        if ((expected.width !== undefined && footage.width !== expected.width) ||
            (expected.height !== undefined && footage.height !== expected.height)) {
            assetError(asset, "dimensiones " + footage.width + "x" + footage.height + " distintas de las esperadas.");
        }
        if (asset.media_type !== "image" && footage.duration + 0.0001 < minimum) {
            assetError(asset, "duración " + footage.duration + " s insuficiente; se requieren " + minimum +
                " s. No se aplica loop, congelado ni retiming implícito.");
        }
        if (expected.duration_seconds !== undefined && Math.abs(footage.duration - expected.duration_seconds) > 0.0001) {
            assetError(asset, "duración distinta de expected.duration_seconds.");
        }
        log("Medio verificado: " + asset.id + " | hasVideo=" + footage.hasVideo + " | hasAudio=" +
            footage.hasAudio + " | " + footage.width + "x" + footage.height + " | duration=" + footage.duration);
    }

    function preflight() {
        var spec = CONFIG.spec;
        var comp = spec.composition;
        var majorVersion = parseInt(String(app.version).split(".")[0], 10);
        var i;
        if (isNaN(majorVersion) || majorVersion < 24) {
            fail("Se requiere After Effects 24.x o superior; versión detectada: " + app.version);
        }
        if (!(comp.duration_seconds > 0 && comp.frame_count > 0 && comp.fps > 0 && comp.width >= 16 && comp.height >= 16)) {
            fail("La composición de GRAPHIC_SPEC no es válida.");
        }
        if (app.project && app.project.numItems > 0) {
            fail("Ejecuta el JSX en un proyecto vacío para no alterar trabajo existente.");
        }
        STATE.outputFolder = chooseOutputFolder();
        if (!STATE.outputFolder) {
            fail("No se eligió una carpeta de salida.");
        }
        STATE.inputFolder = chooseInputFolder();
        if (CONFIG.export_mogrt && spec.essential_graphics.length < 1) {
            fail("La exportación MOGRT requiere al menos un controlador significativo en GRAPHIC_SPEC.");
        }
        if (new File(joinPath(STATE.outputFolder, CONFIG.output.aep_filename)).exists ||
            (CONFIG.export_mogrt && new File(joinPath(STATE.outputFolder, CONFIG.output.mogrt_filename)).exists)) {
            fail("La salida ya contiene AEP/MOGRT. Elige una carpeta nueva para no sobrescribir resultados.");
        }
        for (i = 0; i < CONFIG.media_assets.length; i += 1) {
            STATE.assetFiles[CONFIG.media_assets[i].id] = resolveAssetFile(CONFIG.media_assets[i]);
        }
        STATE.states.PREFLIGHT_OK = "PASS";
        log("Preflight OK para After Effects " + app.version);
    }

    function ensureProjectAndFolders() {
        if (!STATE.outputFolder.exists && !STATE.outputFolder.create()) {
            fail("No se pudo crear la carpeta de salida: " + STATE.outputFolder.fsName);
        }
        if (!app.project) {
            app.newProject();
        }
        if (!app.project) {
            fail("After Effects no creó el proyecto.");
        }
    }

    function importAssets() {
        var assets = CONFIG.media_assets;
        var i;
        var options;
        for (i = 0; i < assets.length; i += 1) {
            if (STATE.assetFiles[assets[i].id]) {
                validateAssetFile(assets[i], STATE.assetFiles[assets[i].id]);
                try {
                    options = new ImportOptions(STATE.assetFiles[assets[i].id]);
                    if (!options.canImportAs(ImportAsType.FOOTAGE)) {
                        assetError(assets[i], "AE no permite importarlo como footage. Comprueba formato/codec.");
                    }
                    options.importAs = ImportAsType.FOOTAGE;
                    options.sequence = false;
                    STATE.footage[assets[i].id] = rememberItem(app.project.importFile(options));
                } catch (importError) {
                    assetError(assets[i], "falló la importación. Entrega un archivo decodificable por AE 24.x. " + importError.toString());
                }
                validateFootage(assets[i], STATE.footage[assets[i].id]);
            }
        }
        STATE.states.MEDIA_PREFLIGHT_OK = "PASS";
    }

    function setTransform(layer, geometry, appearance) {
        var transform = layer.property("ADBE Transform Group");
        if (geometry.position) {
            transform.property("ADBE Position").setValue(geometry.position);
        }
        if (appearance && appearance.opacity !== undefined) {
            transform.property("ADBE Opacity").setValue(appearance.opacity);
        }
    }

    function createShapeLayer(definition) {
        var layer = STATE.comp.layers.addShape();
        var root = layer.property("ADBE Root Vectors Group");
        var group = root.addProperty("ADBE Vector Group");
        var vectors = group.property("ADBE Vectors Group");
        var path;
        var fill;
        group.name = "RECT";
        if (definition.geometry.shape === "ellipse") {
            path = vectors.addProperty("ADBE Vector Shape - Ellipse");
            path.name = "ELLIPSE_PATH";
            path.property("ADBE Vector Ellipse Size").setValue(definition.geometry.size);
            path.property("ADBE Vector Ellipse Position").setValue(definition.geometry.path_position || [0, 0]);
        } else {
            path = vectors.addProperty("ADBE Vector Shape - Rect");
            path.name = "RECT_PATH";
            path.property("ADBE Vector Rect Size").setValue(definition.geometry.size);
            path.property("ADBE Vector Rect Position").setValue(definition.geometry.path_position || [0, 0]);
            path.property("ADBE Vector Rect Roundness").setValue(definition.geometry.roundness || 0);
        }
        fill = vectors.addProperty("ADBE Vector Graphic - Fill");
        fill.name = "FILL";
        fill.property("ADBE Vector Fill Color").setValue(hexToRgb(definition.appearance.color || "#FFFFFF"));
        fill.property("ADBE Vector Fill Opacity").setValue(
            definition.appearance.opacity === undefined ? 100 : definition.appearance.opacity
        );
        layer.name = definition.label;
        setTransform(layer, definition.geometry, definition.appearance);
        return layer;
    }

    function createSolidLayer(definition) {
        var comp = CONFIG.spec.composition;
        var color = hexToRgb(definition.appearance.color);
        var layer = STATE.comp.layers.addSolid(color, definition.label, comp.width, comp.height, 1, comp.duration_seconds);
        if (!layer) {
            fail("No se creó el sólido " + definition.label);
        }
        rememberItem(layer.source);
        layer.name = definition.label;
        setTransform(layer, definition.geometry, definition.appearance);
        return layer;
    }

    function createAdjustmentLayer(definition) {
        var layer = createSolidLayer({
            label: definition.label,
            geometry: definition.geometry,
            appearance: {
                color: "#FFFFFF",
                opacity: definition.appearance.opacity === undefined ? 100 : definition.appearance.opacity
            }
        });
        var blur = layer.property("ADBE Effect Parade").addProperty("ADBE Gaussian Blur 2");
        layer.adjustmentLayer = true;
        blur.name = "BACKGROUND_BLUR";
        blur.property(1).setValue(definition.appearance.blurriness || 0);
        if (blur.numProperties >= 3) {
            blur.property(3).setValue(true);
        }
        return layer;
    }

    function createTextLayer(definition) {
        var box = definition.text_box;
        var layer;
        var source;
        var doc;
        var type = typographyFor(definition.id);
        var rect;
        if (definition.text_mode === "paragraph" && box) {
            layer = STATE.comp.layers.addBoxText([box.width, box.height]);
        } else {
            layer = STATE.comp.layers.addText(definition.appearance.text || "");
        }
        source = layer.property("ADBE Text Properties").property("ADBE Text Document");
        doc = source.value;
        doc.text = definition.appearance.text || "";
        doc.fillColor = hexToRgb(definition.appearance.color);
        doc.applyFill = true;
        doc.fontSize = type.size;
        doc.autoLeading = false;
        doc.leading = type.leading;
        doc.tracking = type.tracking;
        try {
            doc.font = type.font || type.fallback;
        } catch (fontError) {
            log("Aviso: no se pudo aplicar la fuente; se conserva el fallback de After Effects. " + fontError.toString());
        }
        if (type.alignment === "center") {
            doc.justification = ParagraphJustification.CENTER_JUSTIFY;
        } else if (type.alignment === "right") {
            doc.justification = ParagraphJustification.RIGHT_JUSTIFY;
        } else {
            doc.justification = ParagraphJustification.LEFT_JUSTIFY;
        }
        source.setValue(doc);
        layer.name = definition.label;
        if (definition.anchor_strategy === "source_rect_center") {
            rect = layer.sourceRectAtTime(0, false);
            layer.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([
                rect.left + rect.width / 2,
                rect.top + rect.height / 2
            ]);
        }
        setTransform(layer, definition.geometry, definition.appearance);
        return layer;
    }

    function createFootageLayer(definition) {
        var assetId = definition.asset_id || definition.appearance.asset_id;
        var footage = STATE.footage[assetId];
        var layer;
        var sx;
        var sy;
        if (!footage) {
            fail("No existe footage importado para " + assetId);
        }
        layer = STATE.comp.layers.add(footage);
        if (!layer) {
            fail("No se creó la capa de footage " + definition.label);
        }
        layer.name = definition.label;
        layer.outPoint = CONFIG.spec.composition.duration_seconds;
        if (definition.appearance.audio_gain_percent !== undefined) {
            audioLevelsProperty(layer).setValue(audioGainValue(definition.appearance.audio_gain_percent));
        }
        if (definition.type === "audio") {
            return layer;
        }
        setTransform(layer, definition.geometry, definition.appearance);
        sx = definition.geometry.size[0] / footage.width * 100;
        sy = definition.geometry.size[1] / footage.height * 100;
        if (definition.appearance.fit === "cover") {
            layer.property("ADBE Transform Group").property("ADBE Scale").setValue([Math.max(sx, sy), Math.max(sx, sy)]);
        } else {
            layer.property("ADBE Transform Group").property("ADBE Scale").setValue([Math.min(sx, sy), Math.min(sx, sy)]);
        }
        return layer;
    }

    function createGroupLayer(definition) {
        var layer = STATE.comp.layers.addNull(CONFIG.spec.composition.duration_seconds);
        if (!layer) {
            fail("No se creó el grupo " + definition.label);
        }
        rememberItem(layer.source);
        layer.name = definition.label;
        setTransform(layer, definition.geometry, definition.appearance);
        return layer;
    }

    function createElement(definition) {
        var layer;
        if (definition.type === "solid") {
            layer = createSolidLayer(definition);
        } else if (definition.type === "adjustment") {
            layer = createAdjustmentLayer(definition);
        } else if (
            definition.type === "shape" || definition.type === "shadow" ||
            definition.type === "panel" || definition.type === "matte" ||
            definition.type === "line" || (definition.type === "icon" && !definition.asset_id)
        ) {
            layer = createShapeLayer(definition);
        } else if (definition.type === "text") {
            layer = createTextLayer(definition);
        } else if (
            definition.type === "raster" || definition.type === "image" ||
            definition.type === "video" || definition.type === "audio" || (definition.type === "icon" && definition.asset_id)
        ) {
            layer = createFootageLayer(definition);
        } else if (definition.type === "group") {
            layer = createGroupLayer(definition);
        } else {
            fail("Tipo de elemento no soportado: " + definition.type);
        }
        layer.motionBlur = false;
        STATE.layers[definition.id] = layer;
    }

    function applyRelationships(elements) {
        var i;
        var definition;
        var layer;
        var parentLayer;
        var matteLayer;
        for (i = 0; i < elements.length; i += 1) {
            definition = elements[i];
            layer = STATE.layers[definition.id];
            if (definition.parent_id) {
                parentLayer = STATE.layers[definition.parent_id];
                if (!parentLayer) {
                    fail("No existe el parent " + definition.parent_id + " para " + definition.id);
                }
                layer.parent = parentLayer;
                if (layer.parent !== parentLayer) {
                    fail("After Effects no confirmó el parent de " + definition.id);
                }
            }
            if (definition.matte_id) {
                matteLayer = STATE.layers[definition.matte_id];
                if (!matteLayer || typeof layer.setTrackMatte !== "function") {
                    fail("Track Matte no disponible para " + definition.id);
                }
                layer.setTrackMatte(matteLayer, TrackMatteType.ALPHA);
                if (layer.trackMatteLayer !== matteLayer) {
                    fail("After Effects no confirmó el Track Matte de " + definition.id);
                }
            }
        }
    }

    function buildComposition() {
        var comp = CONFIG.spec.composition;
        var elements = CONFIG.spec.elements.slice(0);
        var i;
        elements.sort(function (a, b) { return a.layer_order - b.layer_order; });
        STATE.comp = rememberItem(app.project.items.addComp(CONFIG.comp_name, comp.width, comp.height, 1, comp.duration_seconds, comp.fps));
        STATE.comp.motionGraphicsTemplateName = CONFIG.template_name;
        STATE.comp.motionBlur = true;
        for (i = 0; i < elements.length; i += 1) {
            createElement(elements[i]);
        }
        applyRelationships(elements);
    }

    function vectorProperty(elementId, matchName) {
        var layer = STATE.layers[elementId];
        var root = layer ? layer.property("ADBE Root Vectors Group") : null;
        var i;
        var j;
        var vectors;
        var property;
        if (!root) {
            return null;
        }
        for (i = 1; i <= root.numProperties; i += 1) {
            vectors = root.property(i).property("ADBE Vectors Group");
            if (!vectors) {
                continue;
            }
            for (j = 1; j <= vectors.numProperties; j += 1) {
                property = vectors.property(j);
                if (property.matchName === matchName) {
                    return property;
                }
            }
        }
        return null;
    }

    function rectanglePathProperty(elementId, propertyMatchName) {
        var path = vectorProperty(elementId, "ADBE Vector Shape - Rect");
        return path ? path.property(propertyMatchName) : null;
    }

    function fillColorProperty(elementId) {
        var fill = vectorProperty(elementId, "ADBE Vector Graphic - Fill");
        return fill ? fill.property("ADBE Vector Fill Color") : null;
    }

    function animationProperty(animation) {
        var layer = STATE.layers[animation.element];
        var transform;
        var effect;
        if (!layer) {
            fail("No existe la capa para animar: " + animation.element);
        }
        transform = layer.property("ADBE Transform Group");
        if (animation.property === "position") {
            return transform.property("ADBE Position");
        }
        if (animation.property === "scale") {
            return transform.property("ADBE Scale");
        }
        if (animation.property === "opacity") {
            return transform.property("ADBE Opacity");
        }
        if (animation.property === "rotation") {
            return transform.property("ADBE Rotate Z");
        }
        if (animation.property === "blur") {
            effect = layer.property("ADBE Effect Parade").property("BACKGROUND_BLUR");
            return effect ? effect.property(1) : null;
        }
        if (animation.property === "audio_gain_percent") {
            return audioLevelsProperty(layer);
        }
        if (animation.property === "color") {
            return fillColorProperty(animation.element);
        }
        if (animation.property === "shape_size") {
            return rectanglePathProperty(animation.element, "ADBE Vector Rect Size");
        }
        return null;
    }

    function easeArray(property, influence) {
        var dimensions = 1;
        var result = [];
        var i;
        if (!property.isSpatial) {
            if (property.propertyValueType === PropertyValueType.TwoD) {
                dimensions = 2;
            } else if (property.propertyValueType === PropertyValueType.ThreeD) {
                dimensions = 3;
            }
        }
        for (i = 0; i < dimensions; i += 1) {
            result.push(new KeyframeEase(0, influence));
        }
        return result;
    }

    function audioLevelsProperty(layer) {
        var audio;
        var levels;
        if (!layer || !layer.hasAudio) {
            fail("audio_gain_percent requiere una capa con hasAudio=true.");
        }
        audio = layer.property("ADBE Audio Group");
        levels = audio ? audio.property("ADBE Audio Levels") : null;
        if (!levels) {
            fail("ADBE Audio Levels no está disponible en " + layer.name);
        }
        layer.audioEnabled = true;
        return levels;
    }

    function audioGainValue(percent) {
        var db;
        if (typeof percent !== "number" || !isFinite(percent) || percent < 0 || percent > 100) {
            fail("audio_gain_percent debe estar entre 0 y 100.");
        }
        db = percent === 0 ? -192 : Math.max(-192, 20 * Math.log(percent / 100) / Math.LN10);
        return [db, db];
    }

    function applyAudioGainAnimation(property, animation) {
        var frame;
        var ratio;
        var gain;
        var time;
        var key;
        for (frame = animation.start_frame; frame <= animation.end_frame; frame += 1) {
            ratio = (frame - animation.start_frame) / (animation.end_frame - animation.start_frame);
            gain = animation.start_value + (animation.end_value - animation.start_value) * ratio;
            time = Math.min(frame / CONFIG.spec.composition.fps, CONFIG.spec.composition.duration_seconds);
            property.setValueAtTime(time, audioGainValue(gain));
            key = property.nearestKeyIndex(time);
            setKeyInterpolation(property, key, "linear");
        }
    }

    function setKeyInterpolation(property, keyIndex, interpolation) {
        var kind = KeyframeInterpolationType.BEZIER;
        if (interpolation === "hold") {
            kind = KeyframeInterpolationType.HOLD;
        } else if (interpolation === "linear") {
            kind = KeyframeInterpolationType.LINEAR;
        }
        property.setInterpolationTypeAtKey(keyIndex, kind, kind);
    }

    function applyTemporalEasing(property, firstKey, lastKey, easing) {
        var neutral = easeArray(property, 16.667);
        var strong = easeArray(property, easing.influence);
        var firstIn = neutral;
        var firstOut = neutral;
        var lastIn = neutral;
        var lastOut = neutral;
        if (easing.type === "ease_in") {
            firstOut = strong;
        } else if (easing.type === "ease_out") {
            lastIn = strong;
        } else if (easing.type === "ease_in_out") {
            firstOut = strong;
            lastIn = strong;
        } else if (easing.type !== "linear") {
            fail("Tipo de easing no soportado: " + easing.type);
        }
        property.setTemporalEaseAtKey(firstKey, firstIn, firstOut);
        property.setTemporalEaseAtKey(lastKey, lastIn, lastOut);
    }

    function overshootValue(startValue, endValue, amount) {
        var result;
        var i;
        if (startValue instanceof Array && endValue instanceof Array) {
            result = [];
            for (i = 0; i < endValue.length; i += 1) {
                result.push(endValue[i] + (endValue[i] - startValue[i]) * amount);
            }
            return result;
        }
        if (typeof startValue === "number" && typeof endValue === "number") {
            return endValue + (endValue - startValue) * amount;
        }
        fail("Overshoot requiere valores numéricos.");
        return endValue;
    }

    function normalizedAnimationValue(animation, value) {
        if (animation.property === "color" && typeof value === "string") {
            return hexToRgb(value);
        }
        return value;
    }

    function applyValuesAndEasing(property, animation, startTime, endTime) {
        var firstKey;
        var lastKey;
        var middleKey;
        var overshootTime;
        var overshootAmount;
        var startValue = normalizedAnimationValue(animation, animation.start_value);
        var endValue = normalizedAnimationValue(animation, animation.end_value);
        property.setValueAtTime(startTime, startValue);
        if (animation.easing.overshoot) {
            overshootAmount = animation.easing.overshoot_amount || 0.08;
            overshootTime = startTime + (endTime - startTime) * 0.78;
            property.setValueAtTime(overshootTime, overshootValue(startValue, endValue, overshootAmount));
        }
        property.setValueAtTime(endTime, endValue);
        firstKey = property.nearestKeyIndex(startTime);
        lastKey = property.nearestKeyIndex(endTime);
        setKeyInterpolation(property, firstKey, animation.interpolation);
        setKeyInterpolation(property, lastKey, animation.interpolation);
        if (animation.easing.overshoot) {
            middleKey = property.nearestKeyIndex(overshootTime);
            setKeyInterpolation(property, middleKey, animation.interpolation);
        }
        if (animation.interpolation === "bezier") {
            applyTemporalEasing(property, firstKey, lastKey, animation.easing);
        }
    }

    function originPathPosition(sizeValue, finalSize, origin, basePosition) {
        var result = [basePosition[0], basePosition[1]];
        if (origin === "left") {
            result[0] += (sizeValue[0] - finalSize[0]) / 2;
        } else if (origin === "right") {
            result[0] += (finalSize[0] - sizeValue[0]) / 2;
        } else if (origin === "top") {
            result[1] += (sizeValue[1] - finalSize[1]) / 2;
        } else if (origin === "bottom") {
            result[1] += (finalSize[1] - sizeValue[1]) / 2;
        }
        return result;
    }

    function applyShapeSizeAnimation(animation, property, startTime, endTime) {
        var positionProperty = rectanglePathProperty(animation.element, "ADBE Vector Rect Position");
        var definition = byId(CONFIG.spec.elements, animation.element);
        var basePosition = definition.geometry.path_position || [0, 0];
        var positionAnimation;
        if (!positionProperty) {
            fail("shape_size requiere Rectangle Path > Position.");
        }
        applyValuesAndEasing(property, animation, startTime, endTime);
        positionAnimation = {
            property: "shape_position",
            start_value: originPathPosition(animation.start_value, animation.end_value, animation.origin, basePosition),
            end_value: originPathPosition(animation.end_value, animation.end_value, animation.origin, basePosition),
            interpolation: animation.interpolation,
            easing: {
                type: animation.easing.type,
                influence: animation.easing.influence,
                overshoot: false
            }
        };
        applyValuesAndEasing(positionProperty, positionAnimation, startTime, endTime);
    }

    function applyAnimation(animation) {
        var property = animationProperty(animation);
        var fps = CONFIG.spec.composition.fps;
        var startTime = animation.start_frame / fps;
        var endTime = animation.end_frame / fps;
        if (!property) {
            fail("Propiedad de animación no soportada: " + animation.property + " en " + animation.element);
        }
        if (animation.property === "audio_gain_percent") {
            applyAudioGainAnimation(property, animation);
        } else if (animation.property === "shape_size") {
            applyShapeSizeAnimation(animation, property, startTime, endTime);
        } else {
            applyValuesAndEasing(property, animation, startTime, endTime);
        }
        if (animation.motion_blur) {
            STATE.layers[animation.element].motionBlur = true;
        }
    }

    function animate() {
        var animations = CONFIG.spec.animation;
        var i;
        for (i = 0; i < animations.length; i += 1) {
            applyAnimation(animations[i]);
        }
    }

    function elementProperty(elementId, propertyName) {
        var layer = STATE.layers[elementId];
        var transform;
        if (!layer) {
            return null;
        }
        transform = layer.property("ADBE Transform Group");
        if (propertyName === "source_text") {
            return layer.property("ADBE Text Properties").property("ADBE Text Document");
        }
        if (propertyName === "fill_color") {
            return fillColorProperty(elementId);
        }
        if (propertyName === "opacity") {
            return transform.property("ADBE Opacity");
        }
        if (propertyName === "position") {
            return transform.property("ADBE Position");
        }
        if (propertyName === "scale") {
            return transform.property("ADBE Scale");
        }
        if (propertyName === "rotation") {
            return transform.property("ADBE Rotate Z");
        }
        if (propertyName === "blur") {
            return animationProperty({element: elementId, property: "blur"});
        }
        return null;
    }

    function legacySourceProperty(path) {
        var parts = path.split(".");
        var label = parts[0];
        var propertyName = parts.slice(1).join(".");
        var element = null;
        var i;
        for (i = 0; i < CONFIG.spec.elements.length; i += 1) {
            if (CONFIG.spec.elements[i].label === label) {
                element = CONFIG.spec.elements[i].id;
                break;
            }
        }
        if (propertyName === "Source Text") {
            return elementProperty(element, "source_text");
        }
        if (propertyName === "Fill Color") {
            return elementProperty(element, "fill_color");
        }
        return null;
    }

    function controlsLayer() {
        var layer = STATE.layers.__controls__;
        if (!layer) {
            layer = STATE.comp.layers.addNull(CONFIG.spec.composition.duration_seconds);
            if (!layer) {
                fail("No se creó la capa de controles maestros.");
            }
            rememberItem(layer.source);
            layer.name = "CONTROLS";
            layer.shy = true;
            STATE.layers.__controls__ = layer;
        }
        return layer;
    }

    function expressionString(value) {
        return String(value).split(String.fromCharCode(92)).join("/").split(String.fromCharCode(34)).join("'");
    }

    function createMasterProperty(control) {
        var targets = control.targets;
        var masterLayer = controlsLayer();
        var effects = masterLayer.property("ADBE Effect Parade");
        var effect;
        var property;
        var targetProperty;
        var i;
        if (control.property !== "fill_color") {
            fail("El control maestro aún no admite: " + control.property);
        }
        effect = effects.addProperty("ADBE Color Control");
        effect.name = control.label;
        property = effect.property(1);
        targetProperty = elementProperty(targets[0], control.property);
        if (!targetProperty) {
            fail("No se pudo resolver el primer target de " + control.label);
        }
        property.setValue(targetProperty.value);
        for (i = 0; i < targets.length; i += 1) {
            targetProperty = elementProperty(targets[i], control.property);
            if (!targetProperty || !targetProperty.canSetExpression) {
                fail("No se puede vincular el target " + targets[i] + " al control maestro.");
            }
            targetProperty.expression =
                'thisComp.layer("CONTROLS").effect("' + expressionString(control.label) + '")(1)';
        }
        return property;
    }

    function propertyForControl(control) {
        if (control.source_property) {
            return legacySourceProperty(control.source_property);
        }
        if (control.master || control.targets.length > 1) {
            return createMasterProperty(control);
        }
        return elementProperty(control.targets[0], control.property);
    }

    function configureEssentialGraphics() {
        var controls = CONFIG.spec.essential_graphics;
        var i;
        var property;
        var added;
        var before;
        if (CONFIG.export_mogrt && controls.length < 1) {
            fail("MOGRT solicitado sin controles Essential Graphics.");
        }
        for (i = 0; i < controls.length; i += 1) {
            property = propertyForControl(controls[i]);
            if (!property) {
                fail("No se pudo resolver Essential Graphics: " + controls[i].label);
            }
            if (!property.canAddToMotionGraphicsTemplate || !property.canAddToMotionGraphicsTemplate(STATE.comp)) {
                fail("La propiedad no es compatible con Essential Graphics: " + controls[i].label);
            }
            before = STATE.comp.motionGraphicsTemplateControllerCount;
            added = property.addToMotionGraphicsTemplateAs(STATE.comp, controls[i].label);
            if (added !== true) {
                fail("No se pudo añadir el control Essential Graphics: " + controls[i].label);
            }
            if (STATE.comp.motionGraphicsTemplateControllerCount !== before + 1) {
                fail("AE no confirmó el nuevo controlador Essential Graphics: " + controls[i].label);
            }
            STATE.controllersAdded += 1;
        }
    }

    function findLayerByName(name) {
        var i;
        for (i = 1; i <= STATE.comp.numLayers; i += 1) {
            if (STATE.comp.layer(i).name === name) {
                return STATE.comp.layer(i);
            }
        }
        return null;
    }

    function validateAfterBuild() {
        var comp = CONFIG.spec.composition;
        var elements = CONFIG.spec.elements;
        var i;
        if (STATE.comp.width !== comp.width || STATE.comp.height !== comp.height) {
            fail("La resolución creada no coincide con GRAPHIC_SPEC.");
        }
        if (Math.abs(STATE.comp.duration - comp.duration_seconds) > 0.0001 || Math.abs(STATE.comp.frameRate - comp.fps) > 0.0001) {
            fail("Duración o FPS creados no coinciden con GRAPHIC_SPEC.");
        }
        for (i = 0; i < elements.length; i += 1) {
            if (!findLayerByName(elements[i].label)) {
                fail("Falta la capa esperada " + elements[i].label);
            }
            if (elements[i].matte_id && STATE.layers[elements[i].id].trackMatteLayer !== STATE.layers[elements[i].matte_id]) {
                fail("El Track Matte no quedó aplicado a " + elements[i].label);
            }
        }
        log("Validación de composición y capas OK");
    }

    function writeLogFile() {
        var file;
        var key;
        if (!STATE.outputFolder) {
            return;
        }
        file = new File(joinPath(STATE.outputFolder, CONFIG.output.log_filename));
        if (file.open("w")) {
            file.encoding = "UTF-8";
            for (key in STATE.states) {
                if (STATE.states.hasOwnProperty(key)) {
                    file.writeln(key + "=" + STATE.states[key]);
                }
            }
            file.writeln("---");
            file.write(STATE.log.join("\\n"));
            file.close();
        } else {
            $.writeln("AEGF | No se pudo escribir el log: " + file.fsName + " | " + file.error);
        }
    }

    function saveAepAndExportMogrt() {
        var aepFile = new File(joinPath(STATE.outputFolder, CONFIG.output.aep_filename));
        var mogrtFile = new File(joinPath(STATE.outputFolder, CONFIG.output.mogrt_filename));
        var exportOk;
        STATE.phase = "AEP_SAVE_OK";
        app.project.save(aepFile);
        if (!aepFile.exists || aepFile.length <= 0 || !app.project.file || app.project.file.fsName !== aepFile.fsName) {
            fail("After Effects no confirmó el guardado del AEP.");
        }
        STATE.aepSaved = true;
        STATE.states.AEP_SAVE_OK = "PASS";
        STATE.states.AE_RUNTIME_OK = "PASS";
        log("AEP guardado: " + aepFile.fsName);
        if (!CONFIG.export_mogrt) {
            STATE.states.MOGRT_EXPORT_OK = "NOT_APPLICABLE";
            return;
        }
        STATE.phase = "MOGRT_EXPORT_OK";
        if (STATE.controllersAdded < 1 ||
            STATE.comp.motionGraphicsTemplateControllerCount !== STATE.controllersAdded) {
            fail("No se exporta MOGRT: falta confirmar al menos un controlador significativo.");
        }
        exportOk = STATE.comp.exportAsMotionGraphicsTemplate(true, STATE.outputFolder.fsName);
        if (exportOk !== true) {
            STATE.states.MOGRT_EXPORT_OK = "FAIL";
            fail("exportAsMotionGraphicsTemplate() devolvió un resultado no exitoso.");
        }
        if (!mogrtFile.exists || mogrtFile.length <= 0) {
            STATE.states.MOGRT_EXPORT_OK = "FAIL";
            fail("La API devolvió éxito pero no existe " + mogrtFile.fsName);
        }
        STATE.states.MOGRT_EXPORT_OK = "PASS";
        log("MOGRT exportado: " + mogrtFile.fsName);
    }

    function rollbackUnsavedBuild() {
        var i;
        var failed = false;
        if (!STATE.ownsBuild || STATE.aepSaved) {
            return;
        }
        for (i = STATE.createdItems.length - 1; i >= 0; i -= 1) {
            try {
                STATE.createdItems[i].remove();
            } catch (removeError) {
                failed = true;
                log("Rollback falló al retirar un objeto propio: " + removeError.toString());
            }
        }
        STATE.states.ROLLBACK_OK = failed ? "FAIL" : "PASS";
        if (STATE.states.AEP_BUILD_OK === "PASS") {
            STATE.states.AEP_BUILD_OK = "FAIL";
        }
        log(failed ? "Construcción parcial: revisión manual necesaria." : "Construcción no guardada retirada del proyecto.");
    }

    function run() {
        var successMessage;
        var failureMessage;
        if (!CONFIG.export_mogrt) {
            STATE.states.MOGRT_EXPORT_OK = "NOT_APPLICABLE";
        }
        try {
            preflight();
            STATE.ownsBuild = true;
            app.beginUndoGroup("AE Graphic Factory");
            STATE.undoOpen = true;
            log("Inicio de creación de proyecto");
            ensureProjectAndFolders();
            STATE.phase = "MEDIA_PREFLIGHT_OK";
            log("Importación de assets");
            importAssets();
            STATE.phase = "AEP_BUILD_OK";
            log("Construcción de composición");
            buildComposition();
            log("Aplicación de animación");
            animate();
            log("Configuración de Essential Graphics");
            configureEssentialGraphics();
            log("Validación posterior");
            validateAfterBuild();
            STATE.states.AEP_BUILD_OK = "PASS";
            log("Guardado AEP y exportación MOGRT");
            saveAepAndExportMogrt();
            successMessage = CONFIG.export_mogrt ?
                "AE Graphic Factory: AEP y MOGRT generados correctamente en " + STATE.outputFolder.fsName :
                "AE Graphic Factory: AEP guardado correctamente; MOGRT no solicitado. " + STATE.outputFolder.fsName;
            log(successMessage);
            writeLogFile();
            if (!headless()) {
                alert(successMessage);
            }
        } catch (error) {
            STATE.states[STATE.phase] = "FAIL";
            log("ERROR | " + error.toString() + " | line=" + error.line + " | file=" + error.fileName);
            if (STATE.states.AE_RUNTIME_OK === "NOT_TESTED") {
                STATE.states.AE_RUNTIME_OK = "FAIL";
            }
            rollbackUnsavedBuild();
            failureMessage = STATE.aepSaved ?
                "AEP guardado y conservado. Exportación MOGRT fallida; no se retiró la construcción. " :
                (STATE.ownsBuild ? "Construcción no guardada; consulta el estado ROLLBACK_OK. " :
                    "Preflight fallido; no se modificó el proyecto. ");
            log(failureMessage);
            writeLogFile();
            if (!headless()) {
                alert(failureMessage + error.toString());
            }
        } finally {
            if (STATE.undoOpen) {
                try {
                    app.endUndoGroup();
                } catch (undoError) {
                    log("No se pudo cerrar el grupo de deshacer: " + undoError.toString());
                }
            }
            if ($.getenv("AEGF_QUIT_AFTER_RUN") === "1" && STATE.ownsBuild && STATE.states.ROLLBACK_OK !== "FAIL") {
                try {
                    if (app.project) {
                        app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
                    }
                    app.quit();
                } catch (quitError) {
                    $.writeln(quitError.toString());
                }
            }
        }
    }

    run();
}());
""" % config_json
