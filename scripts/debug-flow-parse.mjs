import fs from "fs";
import vm from "vm";

for (const f of ["underscore-min.js", "raphael.min.js", "flowchart.min.js"]) {
  vm.runInThisContext(fs.readFileSync(`static/js/vendor/diagram/${f}`, "utf8"), { filename: f });
}

const raw = fs.readFileSync("scripts/sample-flow.txt", "utf8");
const chart = flowchart.parse(raw);
console.log("parse ok", Boolean(chart), "start", chart.start);
console.log("keys", Object.keys(chart.symbols));
