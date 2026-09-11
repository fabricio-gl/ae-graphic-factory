/* Executable contract double, NOT Adobe and NOT evidence of Adobe compatibility.
 * Unknown API/property access fails. Options inject import/save/export failures.
 * Run: node tests/ae_host_double.js < {source: "...JSX...", options: {...}}
 */
"use strict";
var fs = require("fs"), vm = require("vm"), path = require("path").posix;
var input = JSON.parse(fs.readFileSync(0, "utf8"));
var opts = input.options || {};
var trace = {events: [], logs: [], properties: [], files: {}, removed: [], alerts: []};
var vfiles = {};
Object.keys(opts.files || {}).forEach(function (name) {
    vfiles[name] = Object.assign({length: 100, data: ""}, opts.files[name]);
});
function event(name, value) { trace.events.push({name: name, value: value}); }
function AEFile(name) {
    this.fsName = String(name).replace(/\\/g, "/");
    this.name = path.basename(this.fsName);
    this.parent = new AEFolder(path.dirname(this.fsName));
}
Object.defineProperty(AEFile.prototype, "exists", {get: function () { return !!vfiles[this.fsName]; }});
Object.defineProperty(AEFile.prototype, "length", {get: function () { return vfiles[this.fsName] ? vfiles[this.fsName].length : 0; }});
AEFile.decode = decodeURIComponent;
AEFile.openDialog = function (message, filter) {
    event("dialog", {message: message, filter: filter});
    return opts.selection ? new AEFile(opts.selection) : null;
};
AEFile.prototype.open = function () { vfiles[this.fsName] = {length: 0, data: ""}; return true; };
AEFile.prototype.write = function (s) { vfiles[this.fsName].data += s; vfiles[this.fsName].length += s.length; };
AEFile.prototype.writeln = function (s) { this.write(s + "\n"); };
AEFile.prototype.close = function () {};
function AEFolder(name) { this.fsName = name; this.exists = true; }
Object.defineProperty(AEFolder.prototype, "parent", {get: function () { return new AEFolder(path.dirname(this.fsName)); }});
AEFolder.prototype.create = function () { return true; };
AEFolder.selectDialog = function () { return new AEFolder("/output"); };
var PVT = {OneD: 1, TwoD: 2, ThreeD: 3, TwoD_SPATIAL: 4, ThreeD_SPATIAL: 5, COLOR: 6, TEXT_DOCUMENT: 7};
function Prop(name, value, type, spatial) {
    this.matchName = name; this.name = name; this.value = value; this.propertyValueType = type || PVT.OneD;
    this.isSpatial = !!spatial; this.keys = []; this.eases = []; this.canSetExpression = true;
    trace.properties.push(this);
}
Prop.prototype.setValue = function (v) { this.value = v; };
Prop.prototype.setValueAtTime = function (t, v) {
    var key = this.keys.find(function (k) { return Math.abs(k.time - t) < 1e-8; });
    if (!key) { key = {time: t}; this.keys.push(key); this.keys.sort(function (a, b) { return a.time - b.time; }); }
    key.value = v; this.value = v;
};
Prop.prototype.nearestKeyIndex = function (t) {
    var nearest = 0;
    this.keys.forEach(function (k, i, arr) { if (Math.abs(k.time - t) < Math.abs(arr[nearest].time - t)) nearest = i; });
    return nearest + 1;
};
Prop.prototype.setInterpolationTypeAtKey = function (k, a, b) { this.keys[k - 1].interpolation = [a, b]; };
Prop.prototype.setTemporalEaseAtKey = function (k, a, b) {
    // Host contract independent of generated easeArray implementation.
    var n = this.isSpatial ? 1 : (this.propertyValueType === PVT.TwoD ? 2 : this.propertyValueType === PVT.ThreeD ? 3 : 1);
    if (a.length !== n || b.length !== n) throw Error("AE_TEMPORAL_EASE_LENGTH: " + this.matchName + " expected " + n);
    this.eases.push({key: k, incoming: a, outgoing: b});
};
Prop.prototype.canAddToMotionGraphicsTemplate = function () { return !opts.controllerUnsupported; };
Prop.prototype.addToMotionGraphicsTemplateAs = function (comp, label) {
    event("addController", label);
    if (opts.controllerReject) return false;
    if (!opts.controllerLie) comp.motionGraphicsTemplateControllerCount += 1;
    return true;
};
function Group(name, children) { this.name = name; this.matchName = name; this.children = children || []; }
Object.defineProperty(Group.prototype, "numProperties", {get: function () { return this.children.length; }});
Group.prototype.property = function (name) {
    return typeof name === "number" ? this.children[name - 1] :
        this.children.find(function (p) { return p.name === name || p.matchName === name; }) || null;
};
Group.prototype.addProperty = function (name) {
    var child;
    if (name === "ADBE Vector Group") child = new Group(name, [new Group("ADBE Vectors Group")]);
    else if (name === "ADBE Vector Shape - Rect") child = new Group(name, [
        new Prop("ADBE Vector Rect Size", [100, 100], PVT.TwoD),
        new Prop("ADBE Vector Rect Position", [0, 0], PVT.TwoD), new Prop("ADBE Vector Rect Roundness", 0)]);
    else if (name === "ADBE Vector Shape - Ellipse") child = new Group(name, [
        new Prop("ADBE Vector Ellipse Size", [100, 100], PVT.TwoD), new Prop("ADBE Vector Ellipse Position", [0, 0], PVT.TwoD)]);
    else if (name === "ADBE Vector Graphic - Fill") child = new Group(name, [
        new Prop("ADBE Vector Fill Color", [1, 1, 1], PVT.COLOR), new Prop("ADBE Vector Fill Opacity", 100)]);
    else if (name === "ADBE Gaussian Blur 2") child = new Group(name, [
        new Prop("ADBE Gaussian Blur 2-0001", 0), new Prop("ADBE Gaussian Blur 2-0002", 1), new Prop("ADBE Gaussian Blur 2-0003", false)]);
    else if (name === "ADBE Color Control") child = new Group(name, [new Prop("ADBE Color Control-0001", [1, 1, 1], PVT.COLOR)]);
    else throw Error("UNMODELED addProperty: " + name);
    this.children.push(child); return child;
};
var items = [];
function addItem(item) {
    item.remove = function () {
        var i = items.indexOf(item);
        if (i < 0 || opts.rollbackThrow) throw Error("REMOVE_FAILED");
        items.splice(i, 1); trace.removed.push(item.name);
    };
    items.push(item); return item;
}
function Footage(meta) {
    Object.assign(this, {name: "footage", width: 108, height: 192, duration: 5,
        hasVideo: true, hasAudio: true, mainSource: {isStill: false}}, meta || {});
}
function Layer(kind, source) {
    this.name = kind; this.source = source; this.hasAudio = !!(source && source.hasAudio);
    this.groups = [new Group("ADBE Transform Group", [
        new Prop("ADBE Position", [0, 0], PVT.TwoD_SPATIAL, true), new Prop("ADBE Scale", [100, 100], PVT.TwoD),
        new Prop("ADBE Opacity", 100), new Prop("ADBE Rotate Z", 0), new Prop("ADBE Anchor Point", [0, 0], PVT.TwoD_SPATIAL, true)
    ]), new Group("ADBE Effect Parade")];
    if (kind === "shape") this.groups.push(new Group("ADBE Root Vectors Group"));
    if (kind === "text") this.groups.push(new Group("ADBE Text Properties", [new Prop("ADBE Text Document", {}, PVT.TEXT_DOCUMENT)]));
    if (this.hasAudio) this.groups.push(new Group("ADBE Audio Group", [new Prop("ADBE Audio Levels", [0, 0], PVT.TwoD)]));
}
Layer.prototype.property = function (name) { return this.groups.find(function (g) { return g.name === name; }) || null; };
Layer.prototype.sourceRectAtTime = function () { return {left: 0, top: 0, width: 600, height: 80}; };
Layer.prototype.setTrackMatte = function (matte, type) { this.trackMatteLayer = matte; event("trackMatte", type); };
function Comp(name, width, height, duration, fps) {
    this.name = name; this.width = width; this.height = height; this.duration = duration; this.frameRate = fps;
    this.motionGraphicsTemplateControllerCount = 0; this.layerList = [];
    var comp = this;
    function layer(kind, source) { var l = new Layer(kind, source); comp.layerList.unshift(l); event("layer", kind); return l; }
    this.layers = {
        add: function (f) { return layer("footage", f); },
        addShape: function () { return layer("shape"); },
        addText: function () { event("addText"); return layer("text"); },
        addBoxText: function () { event("addBoxText"); return layer("text"); },
        addSolid: function () { return layer("solid", addItem(new Footage({name: "solid", hasAudio: false, mainSource: {isStill: true}}))); },
        addNull: function () { return layer("null", addItem(new Footage({name: "null", hasAudio: false, mainSource: {isStill: true}}))); }
    };
}
Object.defineProperty(Comp.prototype, "numLayers", {get: function () { return this.layerList.length; }});
Comp.prototype.layer = function (i) { return this.layerList[i - 1]; };
Comp.prototype.exportAsMotionGraphicsTemplate = function () {
    event("export", this.motionGraphicsTemplateControllerCount);
    if (!this.motionGraphicsTemplateControllerCount) throw Error("AE_NO_CONTROLLERS");
    if (opts.exportThrow) throw Error("EXPORT_EXCEPTION");
    if (opts.exportReject) return false;
    if (!opts.exportMissing) vfiles["/output/grafico.mogrt"] = {length: 256, data: "mock, not MOGRT"};
    return true;
};
var project = {
    items: {addComp: function (n, w, h, par, d, fps) { event("comp"); return addItem(new Comp(n, w, h, d, fps)); }},
    importFile: function (options) {
        event("import", options.file.fsName);
        if (opts.importThrow) throw Error("CODEC_ERROR");
        if (opts.importNull) return null;
        return addItem(new Footage((opts.metadata || {})[options.file.fsName]));
    },
    save: function (file) {
        event("save");
        if (opts.saveThrow) throw Error("SAVE_FAILED");
        if (!opts.saveMissing) { this.file = file; vfiles[file.fsName] = {length: 256, data: "mock, not AEP"}; }
    },
    close: function () { event("close"); }
};
Object.defineProperty(project, "numItems", {get: function () { return items.length + (opts.existingProject ? 1 : 0); }});
Object.assign(global, {
    File: AEFile, Folder: AEFolder, FootageItem: Footage, PropertyValueType: PVT,
    ImportOptions: function (file) { this.file = file; this.canImportAs = function () { return !opts.cannotImport; }; },
    ImportAsType: {FOOTAGE: "FOOTAGE"}, TrackMatteType: {ALPHA: "ALPHA"}, CloseOptions: {DO_NOT_SAVE_CHANGES: 0},
    KeyframeEase: function (speed, influence) { this.speed = speed; this.influence = influence; },
    KeyframeInterpolationType: {BEZIER: "BEZIER", LINEAR: "LINEAR", HOLD: "HOLD"},
    ParagraphJustification: {CENTER_JUSTIFY: 1, RIGHT_JUSTIFY: 2, LEFT_JUSTIFY: 3},
    alert: function (s) { trace.alerts.push(s); },
    app: {version: "24.6", project: project, beginUndoGroup: function () { event("begin"); },
        endUndoGroup: function () { event("end"); }, quit: function () { event("quit"); }},
    $: {fileName: "/output/crear_grafico.jsx",
        getenv: function (key) { return Object.assign({AEGF_OUTPUT_DIR: "/output", AEGF_INPUT_DIR: "/input", AEGF_HEADLESS: "1"}, opts.env || {})[key] || ""; },
        writeln: function (s) { trace.logs.push(s); }}
});
var source = input.source.replace(/^\s*#target aftereffects\s*$/m, "");
try { vm.runInThisContext(source, {timeout: 5000}); } catch (error) { trace.uncaught = error.toString(); }
trace.files = vfiles;
trace.remainingItems = items.length;
process.stdout.write(JSON.stringify(trace));
