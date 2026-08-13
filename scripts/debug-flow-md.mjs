import fs from "fs";
import vm from "vm";

const markdownJs = fs.readFileSync("static/js/markdown.js", "utf8");
const context = {
  window: { __USER__: { expression_extension_enabled: true } },
  console,
};
vm.createContext(context);
vm.runInContext(markdownJs, context);

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
const parts = context.splitDiagramMarkdownParts(polished);
const flow = parts.find((p) => p.kind === "flow");
console.log("flow part:", Boolean(flow));
console.log("source lines:", flow?.source?.split("\n").length);
console.log("has cond3(no):", flow?.source?.includes("cond3(no)"));
console.log("markdown parts:", parts.map((p) => ({ kind: p.kind, len: (p.text || p.source || "").length })));
