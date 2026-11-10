// Runs one Daz3D-MCP program under the fake Daz API.
// usage: node run.js <code-file> <entry-function> <args-json-file>
"use strict";
var fs = require("fs");
var vm = require("vm");
require("./fake_daz.js");

var code = fs.readFileSync(process.argv[2], "utf8");
var entry = process.argv[3];
var args = fs.readFileSync(process.argv[4], "utf8");
vm.runInThisContext(code, { filename: "program.dsa" });
process.stdout.write(String(global[entry](args)));
