import fs from "fs";
import vm from "vm";

const sample = `それでは、ユーザーがWebサイトにログインする流れのシーケンス図を示します。 \`\`\`sequence
Title: ログイン処理
ユーザー->ブラウザ: ログインページへアクセス
ブラウザ->サーバー: GET /login
サーバー-->>ブラウザ: ログインフォームHTML
ブラウザ->>ユーザー: フォームを表示
ユーザー->ブラウザ: メール & パスワード入力
ブラウザ->サーバー: POST /login {email, pass}
サーバー->DB: 認証照会
DB-->>サーバー: 成功
サーバー->>ブラウザ: セッションCookie + ダッシュボード
ブラウザ->>ユーザー: ダッシュボード表示
\`\`\`

別のテーマでも書けます。`;

const ctx = { window: {}, console, getSelectedModel: () => ({ agent_profile: "deepseek" }) };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("static/js/markdown.js", "utf8"), ctx);
vm.runInContext(fs.readFileSync("static/js/diagram-extension.js", "utf8"), ctx);

for (const streaming of [true, false]) {
  const polished = ctx.polishAssistantMarkdown(sample, { streaming });
  const parts = ctx.splitDiagramMarkdownParts(polished);
  console.log(streaming ? "STREAM" : "FINAL", parts.map((p) => p.kind));
}
