// Fails when a file is not valid ECMAScript 5.
"use strict";
var fs = require("fs");
var acorn;
try {
	acorn = require("acorn");
} catch (e) {
	console.error("acorn not installed");
	process.exit(3);
}
var file = process.argv[2];
try {
	acorn.parse(fs.readFileSync(file, "utf8"), { ecmaVersion: 5, sourceType: "script" });
} catch (e) {
	console.error(file + ": " + e.message);
	process.exit(1);
}
