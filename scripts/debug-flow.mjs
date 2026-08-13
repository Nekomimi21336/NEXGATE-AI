import fs from "fs";
import vm from "vm";
import { JSDOM } from "jsdom";

const markdownJs = fs.readFileSync("static/js/markdown.js", "utf8");
const diagramJs = fs.readFileSync("static/js/diagram-extension.js", "utf8");

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
const { window } = dom;
const context = {
  window: Object.assign(window, { __USER__: { expression_extension_enabled: true } }),
  document: window.document,
  console,
  getComputedStyle: window.getComputedStyle.bind(window),
  ResizeObserver: class { observe() {} disconnect() {} },
};
vm.createContext(context);
vm.runInContext(markdownJs, context);
vm.runInContext(diagramJs, context);

const sample = `フローチャートのサンプルを作成します。 以下は「ユーザー登録処理」の流れです。 \`\`\`flow
Title: ユーザー登録処理
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
cond3(no)->op4->input
\`\`\`

このフローチャートの流れ：

1. **開始** → ユーザー情報を入力`;

const polished = context.polishAssistantMarkdown(sample);
console.log("=== polished fence ===");
const m = polished.match(/```flow[\s\S]*?```/);
console.log(m ? m[0] : "NO FENCE");

const parts = context.splitDiagramMarkdownParts(polished);
const flow = parts.find((p) => p.kind === "flow");
console.log("\nflow part:", Boolean(flow));
if (!flow) process.exit(1);

const ready = context.isDiagramSourceReady("flow", flow.source);
console.log("isDiagramSourceReady:", ready);

const sanitized = flow.source
  .split("\n")
  .map((l) => l.trim())
  .filter(Boolean);
console.log("\n=== sanitized via manual ===");
console.log(flow.source);

const inner = window.document.createElement("div");
inner.className = "md-diagram-inner";
const wrap = window.document.createElement("div");
wrap.className = "md-diagram md-diagram-flow";
wrap.dataset.diagramKind = "flow";
wrap.appendChild(inner);
window.document.body.appendChild(wrap);

try {
  const ok = context.renderDiagramInto(inner, "flow", flow.source);
  console.log("\nrenderDiagramInto:", ok);
  console.log("svg:", Boolean(inner.querySelector("svg")));
  console.log("fallback:", Boolean(inner.querySelector(".md-diagram-fallback")));
  if (inner.querySelector(".md-diagram-fallback")) {
    console.log(inner.textContent.slice(0, 200));
  }
} catch (err) {
  console.error("render error", err);
}
