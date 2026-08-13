import fs from "fs";
import vm from "vm";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><html><body><div id='c'></div></body></html>");
const { window } = dom;
global.window = window;
global.document = window.document;

for (const f of [
  "underscore-min.js",
  "raphael.min.js",
  "flowchart.min.js",
  "snap.svg-min.js",
  "sequence-diagram-min.js",
]) {
  vm.runInThisContext(fs.readFileSync(`static/js/vendor/diagram/${f}`, "utf8"));
}

const diagramJs = fs.readFileSync("static/js/diagram-extension.js", "utf8");
vm.runInThisContext(
  diagramJs.replace(
    /if \(document\.readyState[\s\S]*bindSequenceDiagramResize\(\);\s*\}/,
    ""
  )
);

const source = `Title: ユーザー登録処理
st=>start: 開始
e=>end: 終了
input=>inputoutput: ユーザー情報を入力
cond1=>condition: 必須項目は
全て入力済み？
op1=>operation: エラーメッセージ表示
cond2=>condition: メールアドレス
形式は正しい？
op2=>operation: 登録処理を実行
cond3=>condition: 登録成功？
op3=>operation: 完了画面を表示
op4=>operation: エラー処理
st->input->cond1
cond1(no)->op1->input
cond1(yes)->cond2
cond2(no)->op1->input
cond2(yes)->op2->cond3
cond3(yes)->op3->e
cond3(no)->op4->input`;

console.log("ready:", window.isDiagramSourceReady("flow", source));

const inner = document.createElement("div");
inner.className = "md-diagram-inner";
const wrap = document.createElement("div");
wrap.className = "md-diagram md-diagram-flow";
wrap.appendChild(inner);
document.body.appendChild(wrap);

const ok = window.renderDiagramInto(inner, "flow", source);
console.log("render:", ok, "svg:", !!inner.querySelector("svg"), "fallback:", !!inner.querySelector(".md-diagram-fallback"));
if (inner.querySelector(".md-diagram-fallback")) console.log(inner.textContent.slice(0, 300));
