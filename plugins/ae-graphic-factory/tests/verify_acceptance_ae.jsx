#target aftereffects
// Read-only verification of a generated acceptance AEP in a NEW AE instance.
(function () {
    var root = $.getenv("AEGF_ACCEPTANCE_DIR");
    var logFile;
    var owned = false;
    var comp = null;
    var i;
    var video;
    var blur;
    var levels;
    var position;
    var report = [];
    function check(condition, message) {
        if (!condition) {
            throw new Error(message);
        }
        report.push("PASS | " + message);
    }
    try {
        if (!root || (app.project && app.project.numItems > 0)) {
            throw new Error("Se requiere AEGF_ACCEPTANCE_DIR y una instancia con proyecto vacío.");
        }
        logFile = new File(root + "/output/real_ae_verification.log");
        var projectFile = new File(root + "/output/grafico.aep");
        check(projectFile.exists, "AEP existe");
        app.open(projectFile);
        owned = true;
        check(app.project && app.project.file && app.project.file.fsName === projectFile.fsName, "AEP reabierto");
        for (i = 1; i <= app.project.numItems; i += 1) {
            if (app.project.item(i) instanceof CompItem && app.project.item(i).name === "AEGF_MASTER") {
                comp = app.project.item(i);
            }
        }
        check(comp && comp.width === 1920 && comp.height === 1080 && comp.duration === 5 && comp.frameRate === 30, "Composición 5 s 1920x1080 30 fps");
        check(comp.numLayers === 3, "Tres capas esperadas");
        video = comp.layer("VIDEO");
        blur = comp.layer("BLUR");
        check(video && video.hasVideo && video.hasAudio, "VIDEO conserva video y audio");
        check(video.source.width === 108 && video.source.height === 192 && video.source.duration === 5, "Metraje vertical de 5 segundos");
        check(blur.property("ADBE Effect Parade").property("BACKGROUND_BLUR").property(1).value === 80, "Gaussian Blur guardado en 80");
        check(comp.motionGraphicsTemplateControllerCount === 1, "Un controlador real Essential Graphics");
        check(comp.getMotionGraphicsTemplateControllerName(1) === "Desenfoque", "Controlador humano Desenfoque");
        levels = video.property("ADBE Audio Group").property("ADBE Audio Levels");
        check(levels.numKeys === 16, "16 muestras delimitan 15 intervalos del fundido");
        check(Math.abs(levels.keyTime(1) - 4.5) < 0.0001 && Math.abs(levels.keyTime(16) - 5) < 0.0001, "Fundido exactamente 4.5 a 5.0 s");
        check(levels.keyValue(1)[0] === 0 && levels.keyValue(1)[1] === 0, "100 por ciento es 0 dB en ambos canales");
        check(levels.keyValue(16)[0] === -192 && levels.keyValue(16)[1] === -192, "0 por ciento es -192 dB en ambos canales");
        check(Math.abs(levels.keyValue(6)[0] - 20 * Math.log(2 / 3) / Math.LN10) < 0.0001, "Conversión logarítmica intermedia");
        position = video.property("ADBE Transform Group").property("ADBE Position");
        check(position.isSpatial && position.numKeys === 4, "Entrada y salida de Posición espacial guardadas");
        check(position.keyInTemporalEase(1).length === 1 && position.keyOutTemporalEase(1).length === 1, "AE confirma una sola KeyframeEase espacial");
        check(video.property("ADBE Transform Group").property("ADBE Opacity").keyInTemporalEase(1).length === 1, "AE confirma una sola KeyframeEase escalar");
        check(new File(root + "/output/grafico.mogrt").length > 0, "MOGRT real no vacío");
        report.push("VALIDACIÓN_FUNCIONAL_REAL=PASS");
    } catch (error) {
        report.push("VALIDACIÓN_FUNCIONAL_REAL=FAIL | " + error.toString() + " | line=" + error.line);
    }
    report.push("After Effects=" + app.version);
    if (logFile && logFile.open("w")) {
        logFile.encoding = "UTF-8";
        logFile.write(report.join("\n"));
        logFile.close();
    }
    $.writeln(report.join("\n"));
    if (owned) {
        app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
        app.quit();
    }
}());
