// Pretends to be the Daz Studio executable for no-plugin mode tests:
// "DAZStudio script.dsa" runs the script in the (fake) running instance.
"use strict";
var fs = require("fs");
var vm = require("vm");
require("./fake_daz.js");
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"), { filename: process.argv[2] });
