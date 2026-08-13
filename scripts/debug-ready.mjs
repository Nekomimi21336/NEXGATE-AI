import fs from "fs";
import vm from "vm";

const diagramJs = fs.readFileSync("static/js/diagram-extension.js", "utf8");
const ctx = { window: {}, document: { readyState: "complete", addEventListener() {} }, console };
vm.createContext(ctx);
vm.runInContext(diagramJs, ctx);

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

console.log("ready raw:", ctx.isDiagramSourceReady("flow", source));
