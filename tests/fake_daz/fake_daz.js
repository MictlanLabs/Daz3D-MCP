// A stand-in for the Daz Studio scripting API, used by the tests.
//
// It implements only what the Daz3D-MCP tool scripts call, so the real .dsa
// files can run under Node.js. It is a model of Daz Studio, not Daz Studio:
// names and behavior follow the public DazScript API reference, and anything
// that passes here still has to be checked on a real Daz Studio.
//
// The scene lives in a JSON state file whose path is in DAZMCP_FAKE_STATE. A
// "scene file" (.duf) is { "nodes": [ {label, name, class, parent, ...} ] }.
// Content files (.duf, plain or gzip) carry a "dazmcp_fake" block that says
// what loading them does (add a figure, fit clothing, apply a pose...).
/* eslint-disable no-var */
"use strict";

var fs = require("fs");
var path = require("path");
var zlib = require("zlib");

var STATE_PATH = process.env.DAZMCP_FAKE_STATE;
var state = fs.existsSync(STATE_PATH)
	? JSON.parse(fs.readFileSync(STATE_PATH, "utf8"))
	: { filename: "", modified: false, frame: 0, endFrame: 0, nodes: [], viewportCamera: "Perspective View" };
state.nextId = state.nextId || 1;
state.renders = state.renders || [];
state.loaded = state.loaded || [];
state.render = state.render || { width: 1920, height: 1080 };
state.renderProps = state.renderProps || defaultRenderProps();

var dirty = false;
function saveState() { dirty = true; }
function changed() { state.modified = true; dirty = true; }
process.on("exit", function () {
	if (dirty) { fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 1)); }
});

// ------------------------------------------------------------- classes ----
var INHERITS = {
	DzFigure: ["DzFigure", "DzSkeleton", "DzNode", "DzElement"],
	DzBone: ["DzBone", "DzNode", "DzElement"],
	DzBasicCamera: ["DzBasicCamera", "DzCamera", "DzNode", "DzElement"],
	DzDistantLight: ["DzDistantLight", "DzLight", "DzCamera", "DzNode", "DzElement"],
	DzSpotLight: ["DzSpotLight", "DzDistantLight", "DzLight", "DzCamera", "DzNode", "DzElement"],
	DzPointLight: ["DzPointLight", "DzLight", "DzCamera", "DzNode", "DzElement"],
	DzGroupNode: ["DzGroupNode", "DzNode", "DzElement"],
	DzNode: ["DzNode", "DzElement"]
};

var PROP_CLASSES = {
	float: ["DzFloatProperty", "DzNumericProperty", "DzProperty"],
	int: ["DzIntProperty", "DzNumericProperty", "DzProperty"],
	color: ["DzColorProperty", "DzIntProperty", "DzNumericProperty", "DzProperty"],
	enum: ["DzEnumProperty", "DzIntProperty", "DzNumericProperty", "DzProperty"],
	bool: ["DzBoolProperty", "DzIntProperty", "DzNumericProperty", "DzProperty"],
	image: ["DzImageProperty", "DzProperty"],
	string: ["DzStringProperty", "DzProperty"]
};

// --------------------------------------------------------- templates ----
// What a Genesis 9 looks like to the scripts: bones, dials and surfaces.
var G9_BONES = [
	["hip", "Hip"], ["pelvis", "Pelvis"], ["spine1", "Abdomen Lower"], ["spine2", "Abdomen Upper"],
	["spine3", "Chest Lower"], ["spine4", "Chest Upper"], ["neck1", "Neck Lower"], ["head", "Head"],
	["l_shoulder", "Left Shoulder"], ["l_upperarm", "Left Upper Arm"], ["l_forearm", "Left Forearm"],
	["l_hand", "Left Hand"], ["r_shoulder", "Right Shoulder"], ["r_upperarm", "Right Upper Arm"],
	["r_forearm", "Right Forearm"], ["r_hand", "Right Hand"], ["l_thigh", "Left Thigh"], ["l_shin", "Left Shin"],
	["l_foot", "Left Foot"], ["r_thigh", "Right Thigh"], ["r_shin", "Right Shin"], ["r_foot", "Right Foot"]
];

function skinProps(color) {
	return {
		"Base Color": { type: "color", value: color, mappable: true, map: null },
		"Translucency Weight": { type: "float", value: 0.3, min: 0, max: 1, mappable: true },
		"Glossy Roughness": { type: "float", value: 0.5, min: 0, max: 1, mappable: true },
		"Normal Map": { type: "float", value: 1, min: 0, max: 2, mappable: true, map: null },
		"Cutout Opacity": { type: "float", value: 1, min: 0, max: 1, mappable: true }
	};
}

function clothProps(color) {
	return {
		"Base Color": { type: "color", value: color, mappable: true, map: null },
		"Glossy Roughness": { type: "float", value: 0.7, min: 0, max: 1, mappable: true },
		"Metallic Weight": { type: "float", value: 0, min: 0, max: 1, mappable: true },
		"Cutout Opacity": { type: "float", value: 1, min: 0, max: 1, mappable: true }
	};
}

var TEMPLATES = {
	genesis9: function () {
		var surfaces = ["Head", "Body", "Arms", "Legs", "Eyes", "Mouth"];
		return {
			class: "DzFigure", name: "Genesis9", label: "Genesis 9", geometry: true,
			bbox_local: [[-42, 0, -15], [42, 178, 18]],
			bones: G9_BONES,
			morphs: [
				{ name: "body_bs_BodyTone", label: "Body Tone", group: "/Actor/Full Body/People", value: 0, min: 0, max: 1 },
				{ name: "body_bs_BodyFat", label: "Body Fat", group: "/Actor/Full Body/People", value: 0, min: -1, max: 1 },
				{ name: "body_ctrl_Height", label: "Height", group: "/Actor/Full Body/Proportion", value: 0, min: -1, max: 1 },
				{ name: "head_bs_HeadSize", label: "Head Size", group: "/Actor/Head", value: 0, min: -1, max: 1 },
				{ name: "facs_jnt_JawOpen", label: "Jaw Open", group: "/Pose Controls/Head/Mouth", value: 0, min: 0, max: 1 },
				{ name: "body_cbs_Correct", label: "pJCM Shoulder Down", group: "/Hidden", value: 0, min: 0, max: 1, hidden: true },
				{ name: "Ana9_Body", label: "Ana 9 Body", group: "/Actor/Characters", value: 0, min: 0, max: 1 },
				{ name: "Ana9_Head", label: "Ana 9 Head", group: "/Actor/Characters", value: 0, min: 0, max: 1 },
				{ name: "Leo9_Body", label: "Leo 9 Body", group: "/Actor/Characters", value: 0, min: 0, max: 1 },
				{ name: "Leo9_Head", label: "Leo 9 Head", group: "/Actor/Characters", value: 0, min: 0, max: 1 }
			],
			materials: surfaces.map(function (s) {
				return { name: s, label: s, shader: "Iray Uber", props: skinProps(s === "Eyes" ? [0.3, 0.4, 0.6] : [0.8, 0.62, 0.52]) };
			})
		};
	}
};

function defaultRenderProps() {
	return {
		"Max Samples": { type: "int", value: 5000, min: 1, max: 1000000 },
		"Max Time (secs)": { type: "float", value: 7200, min: 1, max: 1000000 },
		"Rendering Quality Enable": { type: "bool", value: true },
		"Rendering Quality": { type: "float", value: 1, min: 0.01, max: 10000 },
		"Environment Mode": { type: "enum", value: 0, items: ["Dome and Scene", "Dome Only", "Sun-Sky Only", "Scene Only"] },
		"Environment Intensity": { type: "float", value: 1, min: 0, max: 1000 },
		"Environment Map": { type: "image", value: null, mappable: true, map: null },
		"Dome Rotation": { type: "float", value: 0, min: -360, max: 360 },
		"Draw Dome": { type: "bool", value: true }
	};
}

function lightProps(kind) {
	var p = {
		"Color": { type: "color", value: [1, 1, 1] },
		"Illumination": { type: "enum", value: 1, items: ["Off", "On", "On (No Shadow)"] }
	};
	if (kind === "distant") {
		p.Intensity = { type: "float", value: 1, min: 0, max: 1000 };
	} else {
		p["Luminous Flux (Lumen)"] = { type: "float", value: 1500, min: 0, max: 10000000 };
	}
	if (kind === "spot") { p["Spread Angle"] = { type: "float", value: 20, min: 0, max: 180 }; }
	return p;
}

// ------------------------------------------------------------- lookup ----
function byId(id) {
	for (var i = 0; i < state.nodes.length; i++) { if (state.nodes[i].id === id) { return state.nodes[i]; } }
	return null;
}

function wrap(d) { return d ? new Node(d) : null; }

// Gives every node an id and turns label references (old fixtures) into ids.
function normalize(list) {
	var idMap = {};
	list.forEach(function (d) {
		var old = d.id;
		d.id = state.nextId++;
		if (old !== undefined) { idMap[old] = d.id; }
	});
	var resolve = function (ref) {
		if (ref === undefined || ref === null) { return null; }
		if (typeof ref === "number") { return idMap[ref] !== undefined ? idMap[ref] : ref; }
		for (var i = 0; i < list.length; i++) { if (list[i].label === ref) { return list[i].id; } }
		for (i = 0; i < state.nodes.length; i++) { if (state.nodes[i].label === ref) { return state.nodes[i].id; } }
		return null;
	};
	list.forEach(function (d) {
		d.parent = resolve(d.parent);
		d.fitted_to = resolve(d.fitted_to);
	});
	return list;
}

function uniqueLabel(label) {
	var taken = {};
	state.nodes.forEach(function (d) { taken[d.label] = true; });
	if (!taken[label]) { return label; }
	for (var n = 2; ; n++) { if (!taken[label + " (" + n + ")"]) { return label + " (" + n + ")"; } }
}

// --------------------------------------------------------- properties ----
function Vec(a) { this.x = a[0]; this.y = a[1]; this.z = a[2]; }

function Prop(data, label, onChange) {
	this.d = data;
	this.l = label;
	this.onChange = onChange || changed;
}
Prop.prototype.getLabel = function () { return this.l; };
Prop.prototype.getName = function () { return this.d.name || this.l; };
Prop.prototype.className = function () { return PROP_CLASSES[this.d.type || "float"][0]; };
Prop.prototype.inherits = function (c) { return PROP_CLASSES[this.d.type || "float"].indexOf(c) >= 0; };
Prop.prototype.getValue = function () {
	if (this.d.type === "bool") { return this.d.value ? 1 : 0; }
	return this.d.value;
};
Prop.prototype.setValue = function (v) {
	if (this.d.type === "color" || this.d.type === "image") { throw new Error("setValue on " + this.d.type); }
	if (typeof v !== "number" && this.d.type !== "string") { throw new Error("setValue needs a number"); }
	if (this.d.min !== undefined && this.d.type !== "string") { v = Math.max(this.d.min, Math.min(this.d.max, v)); }
	if (this.d.type === "bool") { v = !!v; }
	this.d.value = v;
	this.onChange();
};
Prop.prototype.getDefaultValue = function () { return this.d.def || 0; };
Prop.prototype.getMin = function () { return this.d.min; };
Prop.prototype.getMax = function () { return this.d.max; };
Prop.prototype.isHidden = function () { return !!this.d.hidden; };
Prop.prototype.getPath = function () { return this.d.group || ""; };
Prop.prototype.getColorValue = function () {
	var c = this.d.value || [0, 0, 0];
	return new global.Color(Math.round(c[0] * 255), Math.round(c[1] * 255), Math.round(c[2] * 255));
};
Prop.prototype.setColorValue = function (c) {
	if (!(c instanceof global.Color)) { throw new Error("setColorValue needs a Color"); }
	this.d.value = [c.red / 255, c.green / 255, c.blue / 255];
	this.onChange();
};
Prop.prototype.getStringValue = function () { return this.d.items[this.d.value]; };
Prop.prototype.getNumItems = function () { return this.d.items.length; };
Prop.prototype.getItem = function (i) { return this.d.items[i]; };
Prop.prototype.getBoolValue = function () { return !!this.d.value; };
Prop.prototype.setBoolValue = function (b) { this.d.value = !!b; this.onChange(); };
Prop.prototype.isMappable = function () { return !!this.d.mappable; };
Prop.prototype.getMapValue = function () {
	var m = this.d.map;
	return m ? { getFilename: function () { return m; } } : null;
};
Prop.prototype.setMap = function (tex) {
	if (tex !== null && (!tex || !tex.getFilename)) { throw new Error("setMap needs a DzTexture"); }
	this.d.map = tex ? tex.getFilename() : null;
	this.onChange();
};

// A transform dial bound to an [x, y, z] array of the node.
function TransformProp(d, key, index, fallback) {
	this.getValue = function () { return (d[key] || fallback)[index]; };
	this.setValue = function (v) {
		if (typeof v !== "number" || isNaN(v)) { throw new Error("setValue needs a number"); }
		if (!d[key]) { d[key] = fallback.slice(); }
		d[key][index] = v;
		changed();
	};
	this.getDefaultValue = function () { return fallback[index]; };
}

function propertyHost(props) {
	var labels = Object.keys(props || {});
	return {
		findPropertyByLabel: function (l) { return props && props[l] ? new Prop(props[l], l) : null; },
		findProperty: function (n) {
			for (var i = 0; i < labels.length; i++) { if (props[labels[i]].name === n) { return new Prop(props[labels[i]], labels[i]); } }
			return null;
		},
		getNumProperties: function () { return labels.length; },
		getProperty: function (i) { return new Prop(props[labels[i]], labels[i]); }
	};
}

// --------------------------------------------------------------- nodes ----
function Node(d) {
	this.d = d;
	var host = propertyHost(d.props);
	this.findPropertyByLabel = host.findPropertyByLabel;
	this.findProperty = host.findProperty;
	this.getNumProperties = host.getNumProperties;
	this.getProperty = host.getProperty;
	if (this.inherits("DzSkeleton")) {
		this.setFollowTarget = function (target) {
			d.fitted_to = target ? target.d.id : null;
			if (!target) { d.parent = null; }
			changed();
		};
	}
}
Node.prototype.getElementID = function () { return this.d.id; };
Node.prototype.getName = function () { return this.d.name || this.d.label; };
Node.prototype.getLabel = function () { return this.d.label; };
Node.prototype.setLabel = function (l) { this.d.label = l; changed(); };
Node.prototype.className = function () { return this.d.class || "DzNode"; };
Node.prototype.inherits = function (c) { return (INHERITS[this.className()] || ["DzNode"]).indexOf(c) >= 0; };
Node.prototype.getNodeParent = function () { return wrap(byId(this.d.parent)); };
Node.prototype.getNodeChildren = function (recurse) {
	var id = this.d.id;
	var out = [];
	state.nodes.forEach(function (n) {
		if (n.parent === id) {
			out.push(wrap(n));
			if (recurse) { out = out.concat(wrap(n).getNodeChildren(true)); }
		}
	});
	return out;
};
Node.prototype.addNodeChild = function (child) { child.d.parent = this.d.id; changed(); };
Node.prototype.isVisible = function () { return this.d.visible !== false; };
Node.prototype.setVisible = function (v) { this.d.visible = !!v; changed(); };
Node.prototype.isSelected = function () { return !!this.d.selected; };
Node.prototype.select = function (on) {
	this.d.selected = !!on;
	if (on) { state.primary = this.d.id; } else if (state.primary === this.d.id) { state.primary = null; }
	saveState();
};
// World position and scale (rotation of parents is ignored: good enough here).
Node.prototype.getWSScale = function () {
	var s = this.d.scale === undefined ? 1 : this.d.scale;
	var parent = byId(this.d.parent);
	return parent ? s * wrap(parent).getWSScale() : s;
};
Node.prototype.getWSPos = function () {
	var p = (this.d.position || [0, 0, 0]).slice();
	var parent = byId(this.d.parent);
	if (parent) {
		var pp = wrap(parent).getWSPos();
		var ps = wrap(parent).getWSScale();
		p = [pp.x + p[0] * ps, pp.y + p[1] * ps, pp.z + p[2] * ps];
	}
	return new Vec(p);
};
Node.prototype.getXPosControl = function () { return new TransformProp(this.d, "position", 0, [0, 0, 0]); };
Node.prototype.getYPosControl = function () { return new TransformProp(this.d, "position", 1, [0, 0, 0]); };
Node.prototype.getZPosControl = function () { return new TransformProp(this.d, "position", 2, [0, 0, 0]); };
Node.prototype.getXRotControl = function () { return new TransformProp(this.d, "rotation", 0, [0, 0, 0]); };
Node.prototype.getYRotControl = function () { return new TransformProp(this.d, "rotation", 1, [0, 0, 0]); };
Node.prototype.getZRotControl = function () { return new TransformProp(this.d, "rotation", 2, [0, 0, 0]); };
Node.prototype.getScaleControl = function () {
	var d = this.d;
	return {
		getValue: function () { return d.scale === undefined ? 1 : d.scale; },
		setValue: function (v) { d.scale = v; changed(); },
		getDefaultValue: function () { return 1; }
	};
};
Node.prototype.getWSBoundingBox = function () {
	var b = this.d.bbox;
	if (this.d.bbox_local) {
		var p = this.getWSPos();
		var s = this.getWSScale();
		var l = this.d.bbox_local;
		b = [[p.x + l[0][0] * s, p.y + l[0][1] * s, p.z + l[0][2] * s], [p.x + l[1][0] * s, p.y + l[1][1] * s, p.z + l[1][2] * s]];
	}
	return {
		isValid: function () { return !!b; },
		min: b ? new Vec(b[0]) : null,
		max: b ? new Vec(b[1]) : null
	};
};
Node.prototype.getFollowTarget = function () { return wrap(byId(this.d.fitted_to)); };
Node.prototype.getSkeleton = function () { return this.className() === "DzBone" ? wrap(byId(this.d.parent)) : null; };
Node.prototype.boneNodes = function () {
	var id = this.d.id;
	return state.nodes.filter(function (n) { return n.parent === id && n.class === "DzBone"; }).map(wrap);
};
Node.prototype.getNumBones = function () {
	return typeof this.d.bones === "number" ? this.d.bones : this.boneNodes().length;
};
Node.prototype.getBone = function (i) { return this.boneNodes()[i] || null; };
Node.prototype.findBone = function (name) {
	return this.boneNodes().filter(function (b) { return b.getName() === name; })[0] || null;
};
Node.prototype.findBoneByLabel = function (label) {
	return this.boneNodes().filter(function (b) { return b.getLabel() === label; })[0] || null;
};
Node.prototype.getFocalLength = function () {
	var p = this.d.props && this.d.props["Focal Length"];
	return p ? p.value : (this.d.focal_length || 65);
};
Node.prototype.getObject = function () {
	var d = this.d;
	if (!d.geometry && !d.morphs && !d.materials) { return null; }
	var morphs = d.morphs || [];
	var mats = d.materials || [];
	return {
		getNumModifiers: function () { return morphs.length; },
		getModifier: function (i) {
			var m = morphs[i];
			return {
				getName: function () { return m.name; },
				getLabel: function () { return m.label; },
				inherits: function (c) { return c === "DzMorph" || c === "DzModifier"; },
				className: function () { return "DzMorph"; },
				getValueControl: function () { return new Prop(m, m.label); }
			};
		},
		getCurrentShape: function () {
			return {
				getNumMaterials: function () { return mats.length; },
				getMaterial: function (i) { return material(mats[i]); }
			};
		}
	};
};

function material(m) {
	var host = propertyHost(m.props);
	host.getName = function () { return m.name; };
	host.getLabel = function () { return m.label || m.name; };
	host.getMaterialName = function () { return m.shader || "Iray Uber"; };
	host.className = function () { return "DzUberIrayMaterial"; };
	return host;
}

// ------------------------------------------------------------ globals ----
global.Color = function (r, g, b) { this.red = r; this.green = g; this.blue = b; };
global.DzVec3 = function (x, y, z) { this.x = x; this.y = y; this.z = z; };
global.Size = function (w, h) { this.width = w; this.height = h; };

function newNode(cls, label, props) {
	return new Node({ class: cls, label: label, name: label, props: props, position: [0, 0, 0], rotation: [0, 0, 0] });
}
global.DzBasicCamera = function () {
	return newNode("DzBasicCamera", "Camera", { "Focal Length": { type: "float", value: 65, min: 1, max: 10000 } });
};
global.DzSpotLight = function () { return newNode("DzSpotLight", "Spotlight", lightProps("spot")); };
global.DzPointLight = function () { return newNode("DzPointLight", "Point Light", lightProps("point")); };
global.DzDistantLight = function () { return newNode("DzDistantLight", "Distant Light", lightProps("distant")); };

global.DzScene = { OpenNew: 0, MergeFile: 1 };
global.DzApp = { NoInterface: 0 };
global.DzRenderOptions = { DirectToFile: 1, ActiveWindow: 0, NewWindow: 2 };

function findBy(key, value) {
	for (var i = 0; i < state.nodes.length; i++) {
		if (state.nodes[i][key] === value || (key === "name" && state.nodes[i].label === value && !state.nodes[i].name)) {
			return wrap(state.nodes[i]);
		}
	}
	return null;
}

function primary() {
	var p = state.primary ? byId(state.primary) : null;
	if (p && p.selected) { return wrap(p); }
	var sel = state.nodes.filter(function (n) { return n.selected; });
	return sel.length ? wrap(sel[0]) : null;
}

global.Scene = {
	getNodeList: function () { return state.nodes.map(wrap); },
	getNumNodes: function () { return state.nodes.length; },
	getFilename: function () { return state.filename; },
	needsSave: function () { return !!state.modified; },
	getTimeStep: function () { return 160; },
	getAnimRange: function () { return { start: 0, end: (state.endFrame || 0) * 160 }; },
	getFrame: function () { return state.frame || 0; },
	setFrame: function (f) { state.frame = f; saveState(); },
	getPrimarySelection: primary,
	setPrimarySelection: function (n) { n.select(true); },
	selectAllNodes: function (on) { state.nodes.forEach(function (n) { n.selected = !!on; }); state.primary = null; saveState(); },
	findNodeByLabel: function (l) { return findBy("label", l); },
	findNode: function (n) { return findBy("name", n); },
	findCameraByLabel: function (l) {
		var n = findBy("label", l);
		return n && n.inherits("DzCamera") && !n.inherits("DzLight") ? n : null;
	},
	findCamera: function (n) {
		var node = findBy("name", n);
		return node && node.inherits("DzCamera") && !node.inherits("DzLight") ? node : null;
	},
	addNode: function (node) {
		if (byId(node.d.id)) { return true; }
		node.d.id = state.nextId++;
		state.nodes.push(node.d);
		changed();
		return true;
	},
	removeNode: function (node) {
		var gone = {};
		gone[node.d.id] = true;
		state.nodes.forEach(function (n) { if (n.parent === node.d.id && n.class === "DzBone") { gone[n.id] = true; } });
		if (!byId(node.d.id)) { return false; }
		state.nodes = state.nodes.filter(function (n) { return !gone[n.id]; });
		state.nodes.forEach(function (n) {
			if (gone[n.parent]) { n.parent = null; }
			if (gone[n.fitted_to]) { n.fitted_to = null; }
		});
		changed();
		return true;
	},
	clear: function () { state.nodes = []; state.filename = ""; state.modified = false; saveState(); },
	loadScene: function (file, method) {
		var data;
		try { data = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { return 1; }
		if (method === DzScene.OpenNew) {
			state.nodes = [];
			state.nodes = normalize(data.nodes);
			state.filename = file;
			state.endFrame = data.endFrame || 0;
			state.modified = false;
		} else {
			state.nodes = state.nodes.concat(normalize(data.nodes));
			state.modified = true;
		}
		saveState();
		return 0;
	},
	saveScene: function (file) {
		fs.writeFileSync(file, JSON.stringify({ nodes: state.nodes, endFrame: state.endFrame }));
		state.filename = file;
		state.modified = false;
		saveState();
		return 0;
	},
	saveThumbnailImage: function (file) { fs.writeFileSync(file, PNG); }
};

// ------------------------------------------------------------ content ----
function contentDirs() {
	var env = process.env.DAZMCP_FAKE_CONTENT_DIRS;
	return env ? env.split(path.delimiter).filter(Boolean) : (state.contentDirs || []);
}

function readContent(file) {
	var buf = fs.readFileSync(file);
	if (buf[0] === 0x1f && buf[1] === 0x8b) { buf = zlib.gunzipSync(buf); }
	return JSON.parse(buf.toString("utf8"));
}

function generationOf(name) {
	var m = /^Genesis(\d+)/.exec(name || "");
	return m ? "Genesis " + m[1] : null;
}

function addFromTemplate(spec, target) {
	var base = spec.template ? TEMPLATES[spec.template]() : {};
	var key;
	for (key in spec) { if (spec.hasOwnProperty(key) && key !== "template") { base[key] = spec[key]; } }
	var bones = base.bones;
	delete base.bones;
	base.class = base.class || (base.follows ? "DzFigure" : "DzNode");
	base.label = uniqueLabel(base.label);
	base.position = base.position || [0, 0, 0];
	base.rotation = base.rotation || [0, 0, 0];
	if (base.follows) {
		if (target && target.inherits("DzFigure") && !target.d.fitted_to &&
				(!base.generation || generationOf(target.d.name) === base.generation)) {
			base.fitted_to = target.d.id;
			base.parent = target.d.id;
		}
	}
	delete base.follows;
	delete base.generation;
	var node = new Node(base);
	Scene.addNode(node);
	(bones || []).forEach(function (b) {
		Scene.addNode(new Node({ class: "DzBone", name: b[0], label: b[1], parent: node.d.id, position: [0, 0, 0], rotation: [0, 0, 0] }));
	});
	return node;
}

function applyMaterials(node, spec) {
	(node.d.materials || []).forEach(function (m) {
		var values = spec[m.name] || spec["*"];
		if (!values) { return; }
		Object.keys(values).forEach(function (label) {
			if (m.props[label]) { m.props[label].value = values[label]; }
		});
	});
}

function openContent(file) {
	var data;
	try { data = readContent(file); } catch (e) { return false; }
	var fake = data.dazmcp_fake || {};
	var target = primary();
	var figure = target && target.inherits("DzFigure") ? target : null;
	var added = null;
	state.loaded.push({ file: path.basename(file), target: target ? target.getLabel() : null });
	(fake.add || []).forEach(function (spec) { added = addFromTemplate(spec, target); });
	if (fake.pose && figure) {
		Object.keys(fake.pose).forEach(function (bone) {
			var b = figure.findBone(bone);
			if (b) { b.d.rotation = fake.pose[bone].slice(); }
		});
	}
	if (fake.morphs && target) {
		(target.d.morphs || []).forEach(function (m) {
			if (fake.morphs.hasOwnProperty(m.label)) { m.value = fake.morphs[m.label]; }
		});
	}
	if (fake.materials && target) { applyMaterials(target, fake.materials); }
	if (added) { Scene.selectAllNodes(false); added.select(true); }
	changed();
	return true;
}

// ------------------------------------------------------------- render ----
function renderOptions() {
	return {
		getImageSize: function () { return new global.Size(state.render.width, state.render.height); },
		setImageSize: function (s) { state.render.width = s.width; state.render.height = s.height; saveState(); },
		setAspectConstrained: function () {},
		setRenderImgToId: function (id) { state.render.toId = id; },
		setRenderImgFilename: function (f) { state.render.filename = f; },
		setIsCurrentFrameRender: function () {}
	};
}

// Camera-space test of a point: is it inside the picture?
function inFrame(cam, p) {
	var deg = Math.PI / 180;
	var c = cam.getWSPos();
	var r = cam.d.rotation || [0, 0, 0];
	var x = p[0] - c.x, y = p[1] - c.y, z = p[2] - c.z;
	var a = -r[1] * deg; // undo Y
	var x1 = x * Math.cos(a) + z * Math.sin(a);
	var z1 = -x * Math.sin(a) + z * Math.cos(a);
	var b = -r[0] * deg; // undo X
	var y2 = y * Math.cos(b) - z1 * Math.sin(b);
	var z2 = y * Math.sin(b) + z1 * Math.cos(b);
	if (z2 >= 0) { return false; }
	var f = cam.getFocalLength();
	var aspect = state.render.width / state.render.height;
	return Math.abs(x1 / -z2) <= 18 / f + 1e-6 && Math.abs(y2 / -z2) <= 18 / (aspect * f) + 1e-6;
}

function renderSummary(cam) {
	var figures = state.nodes.filter(function (n) { return n.class === "DzFigure" && !n.fitted_to; });
	return figures.map(function (d) {
		var n = wrap(d);
		var wearing = state.nodes.filter(function (o) { return o.fitted_to === d.id; }).map(function (o) { return o.label; });
		var posed = n.boneNodes().filter(function (b) { return (b.d.rotation || [0, 0, 0]).some(function (v) { return v; }); }).length;
		var box = n.getWSBoundingBox();
		var corners = 0;
		if (box.isValid() && cam) {
			[box.min.x, box.max.x].forEach(function (x) {
				[box.min.y, box.max.y].forEach(function (y) {
					[box.min.z, box.max.z].forEach(function (z) { if (inFrame(cam, [x, y, z])) { corners++; } });
				});
			});
		}
		return {
			label: d.label, wearing: wearing, posed_bones: posed,
			morphs_in_use: (d.morphs || []).filter(function (m) { return m.value; }).length,
			corners_in_frame: corners
		};
	});
}

var renderMgr = {
	getRenderOptions: renderOptions,
	getActiveRenderer: function () { return { getName: function () { return "NVIDIA Iray"; } }; },
	getRenderElementObjects: function () { return [propertyHost(state.renderProps)]; },
	doRender: function () {
		if (state.render.toId !== DzRenderOptions.DirectToFile || !state.render.filename) { return false; }
		var cam = viewport3d.getCamera();
		fs.writeFileSync(state.render.filename, PNG);
		state.renders.push({
			file: state.render.filename,
			camera: cam ? cam.getLabel() : null,
			width: state.render.width,
			height: state.render.height,
			max_samples: state.renderProps["Max Samples"].value,
			max_time: state.renderProps["Max Time (secs)"].value,
			lights: state.nodes.filter(function (n) { return /Light$/.test(n.class); }).length,
			environment_mode: state.renderProps["Environment Mode"].items[state.renderProps["Environment Mode"].value],
			figures: renderSummary(cam && cam.inherits("DzCamera") && byId(cam.d.id) ? cam : null)
		});
		saveState();
		return true;
	}
};

global.App = {
	longVersionString: "6.25.2026.14722",
	platform: function () { return 2; },
	getGraphicsMode: function () { return 1; },
	getContentMgr: function () {
		return {
			getNumContentDirectories: function () { return contentDirs().length; },
			getContentDirectoryPath: function (i) { return contentDirs()[i]; },
			getNumPoserDirectories: function () { return 0; },
			openFile: openContent
		};
	},
	getImageMgr: function () {
		return { getImage: function (p) { return { getFilename: function () { return p; } }; } };
	},
	getRenderMgr: function () { return renderMgr; }
};

// 1x1 transparent PNG.
var PNG = Buffer.from(
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
	"base64");

var viewport3d = {
	getCamera: function () {
		return findBy("label", state.viewportCamera) || new Node({ label: state.viewportCamera, class: "DzBasicCamera" });
	},
	setCamera: function (cam) { state.viewportCamera = cam.getLabel(); saveState(); },
	captureImage: function () {
		if (process.env.DAZMCP_FAKE_NO_CAPTURE) { return { isNull: function () { return true; }, width: 0, height: 0 }; }
		return fakeImage(1920, 1080);
	}
};

function fakeImage(w, h, source) {
	return {
		width: w,
		height: h,
		isNull: function () { return false; },
		pixel: function () {
			var v = process.env.DAZMCP_FAKE_BLACK_FRAME ? 0 : 120;
			return { red: v, green: v, blue: v };
		},
		smoothScale: function (nw, nh) { return fakeImage(nw, nh, source); },
		save: function (file) { fs.writeFileSync(file, source ? fs.readFileSync(source) : PNG); }
	};
}

// Image(path) loads a picture from disk (here: as big as the last render).
global.Image = function (file) {
	if (!fs.existsSync(file)) { throw new Error("no image " + file); }
	return fakeImage(state.render.width, state.render.height, file);
};

global.MainWindow = {
	getViewportMgr: function () {
		return { getActiveViewport: function () { return { get3DViewport: function () { return viewport3d; } }; } };
	}
};

global.DzFileInfo = function (p) {
	this.exists = function () { return fs.existsSync(p); };
	this.path = function () { return path.dirname(p); };
};
global.DzDir = function (p) { this.exists = function () { return fs.existsSync(p); }; };
global.getErrorMessage = function (code) { return "error " + code; };

global.DzFile = function (p) {
	var buf = "";
	this.open = function () { buf = ""; return true; };
	this.write = function (s) { buf += s; return s.length; };
	this.close = function () { fs.writeFileSync(p, buf); };
	this.rename = function (n) { fs.renameSync(p, n); p = n; return true; };
};
global.DzFile.WriteOnly = 2;

// Old state files and fixtures have no ids yet.
if (state.nodes.some(function (n) { return n.id === undefined; })) {
	var fresh = state.nodes;
	state.nodes = [];
	state.nodes = normalize(fresh);
	saveState();
}
