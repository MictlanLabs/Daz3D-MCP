// A tiny stand-in for the Daz Studio scripting API, used by the tests.
//
// It implements only what the Daz3D-MCP tool scripts call, so the real .dsa
// files can run under Node.js. The scene lives in a JSON state file whose path
// is in the DAZMCP_FAKE_STATE environment variable; a "scene file" (.duf) is
// the same JSON shape: { "nodes": [ {label, name, class, parent, ...} ] }.
/* eslint-disable no-var */
"use strict";

var fs = require("fs");
var path = require("path");

var STATE_PATH = process.env.DAZMCP_FAKE_STATE;
var state = fs.existsSync(STATE_PATH)
	? JSON.parse(fs.readFileSync(STATE_PATH, "utf8"))
	: { filename: "", modified: false, frame: 0, endFrame: 0, nodes: [], viewportCamera: "Perspective View" };

function saveState() {
	fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2));
}

var INHERITS = {
	DzFigure: ["DzFigure", "DzSkeleton", "DzNode"],
	DzBone: ["DzBone", "DzNode"],
	DzBasicCamera: ["DzBasicCamera", "DzCamera", "DzNode"],
	DzDistantLight: ["DzDistantLight", "DzLight", "DzNode"],
	DzSpotLight: ["DzSpotLight", "DzLight", "DzNode"],
	DzGroupNode: ["DzGroupNode", "DzNode"],
	DzNode: ["DzNode"]
};

function Vec(a) { this.x = a[0]; this.y = a[1]; this.z = a[2]; }
function Prop(v) { this.getValue = function () { return v; }; }

function Node(data) { this.d = data; }
Node.prototype.getName = function () { return this.d.name || this.d.label; };
Node.prototype.getLabel = function () { return this.d.label; };
Node.prototype.setLabel = function (l) { this.d.label = l; state.modified = true; saveState(); };
Node.prototype.className = function () { return this.d.class || "DzNode"; };
Node.prototype.inherits = function (c) { return (INHERITS[this.className()] || ["DzNode"]).indexOf(c) >= 0; };
Node.prototype.getNodeParent = function () { return this.d.parent ? findBy("label", this.d.parent) : null; };
Node.prototype.isVisible = function () { return this.d.visible !== false; };
Node.prototype.isSelected = function () { return !!this.d.selected; };
Node.prototype.getWSPos = function () { return new Vec(this.d.position || [0, 0, 0]); };
Node.prototype.getXRotControl = function () { return new Prop((this.d.rotation || [0, 0, 0])[0]); };
Node.prototype.getYRotControl = function () { return new Prop((this.d.rotation || [0, 0, 0])[1]); };
Node.prototype.getZRotControl = function () { return new Prop((this.d.rotation || [0, 0, 0])[2]); };
Node.prototype.getScaleControl = function () { return new Prop(this.d.scale === undefined ? 1 : this.d.scale); };
Node.prototype.getWSBoundingBox = function () {
	var b = this.d.bbox;
	return {
		isValid: function () { return !!b; },
		min: b ? new Vec(b[0]) : null,
		max: b ? new Vec(b[1]) : null
	};
};
Node.prototype.getFollowTarget = function () { return this.d.fitted_to ? findBy("label", this.d.fitted_to) : null; };
Node.prototype.getNumBones = function () { return this.d.bones || 0; };
Node.prototype.getFocalLength = function () { return this.d.focal_length || 65; };
Node.prototype.getObject = function () { return this.d.geometry ? {} : null; };

function allNodes() { return state.nodes.map(function (d) { return new Node(d); }); }
function findBy(key, value) {
	for (var i = 0; i < state.nodes.length; i++) {
		if (state.nodes[i][key] === value || (key === "name" && state.nodes[i].label === value && !state.nodes[i].name)) {
			return new Node(state.nodes[i]);
		}
	}
	return null;
}

global.DzScene = { OpenNew: 0, MergeFile: 1 };
global.DzApp = { NoInterface: 0 };

global.Scene = {
	getNodeList: allNodes,
	getNumNodes: function () { return state.nodes.length; },
	getFilename: function () { return state.filename; },
	needsSave: function () { return !!state.modified; },
	getTimeStep: function () { return 160; },
	getAnimRange: function () { return { start: 0, end: (state.endFrame || 0) * 160 }; },
	getFrame: function () { return state.frame || 0; },
	setFrame: function (f) { state.frame = f; saveState(); },
	getPrimarySelection: function () {
		var sel = state.nodes.filter(function (n) { return n.selected; });
		return sel.length ? new Node(sel[0]) : null;
	},
	findNodeByLabel: function (l) { return findBy("label", l); },
	findNode: function (n) { return findBy("name", n); },
	findCameraByLabel: function (l) {
		var n = findBy("label", l);
		return n && n.inherits("DzCamera") ? n : null;
	},
	findCamera: function (n) {
		var node = findBy("name", n);
		return node && node.inherits("DzCamera") ? node : null;
	},
	clear: function () { state.nodes = []; state.filename = ""; state.modified = false; saveState(); },
	loadScene: function (file, method) {
		var data;
		try { data = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { return 1; }
		if (method === DzScene.OpenNew) {
			state.nodes = data.nodes;
			state.filename = file;
			state.endFrame = data.endFrame || 0;
			state.modified = false;
		} else {
			state.nodes = state.nodes.concat(data.nodes);
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

global.App = {
	longVersionString: "6.25.2026.14722",
	platform: function () { return 2; },
	getGraphicsMode: function () { return 1; }
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

function fakeImage(w, h) {
	return {
		width: w,
		height: h,
		isNull: function () { return false; },
		pixel: function () {
			var v = process.env.DAZMCP_FAKE_BLACK_FRAME ? 0 : 120;
			return { red: v, green: v, blue: v };
		},
		smoothScale: function (nw, nh) { return fakeImage(nw, nh); },
		save: function (file) { fs.writeFileSync(file, PNG); }
	};
}

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
