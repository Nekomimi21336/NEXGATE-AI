# NEXGATE AI

AI チャット・タスク・プロジェクト管理・画像生成などを備えた Web アプリケーション。
Flask（Python）製バックエンドと、Vite + TypeScript への移行途中のフロントエンドで構成されています。

## 構成

- `app.py` — Flask アプリ本体（3 モードを `NEXGATE_APP_MODE` で切り替え）
- `run_servers.py` — 3 つのサーバーを一括起動
  - Frontend: `http://127.0.0.1:5000`（`frontend_server.py`）
  - API Portal: `http://127.0.0.1:5001`（`api_portal_server.py`）
  - API: `http://127.0.0.1:5002`（`api_server.py`）
- `data/` — 実行時データ（JSON ストア、git 管理外）
- `static/` — レガシー JS/CSS
- `frontend_src/` — TypeScript 移行用ソース（進行中）
- `scanner/` — PDF/画像スキャン・OCR
- `sites/nexgate.space/` — 公開サイト

## セットアップ

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # 実際の値を設定
python run_servers.py
```

フロントエンドの開発時（任意）:

```bash
npm install
npm run dev
```

## 環境変数

シークレット類（API キー、OAuth client secret、PayPal 等）は必ず `.env` で管理してください。
`data/system_config.json` には保存されません（管理画面から保存しようとしても、env が設定されている場合は無視されます）。
全キーの一覧は [.env.example](.env.example) を参照。

### 重要なフラグ

- `NEXGATE_VITE_ENABLED` — TypeScript バンドル（`static/dist`）を有効化するフラグ。
  移行が未完了のため、**デフォルトでは無効**です。`static/dist/js/app.js` が存在しても
  このフラグが `1` でなければレガシー JS が使われます。
- `NEXGATE_OCR_AUTO_INSTALL` — 起動時に OCR 依存を自動インストールするか（既定: 無効）。
- `REQUEST_DETAILS_RETENTION_DAYS` — `data/request_details` の保持日数（既定: 30 日）。

## テスト

```bash
python -m unittest discover -s tests -v
```

テストは stdlib のみで動作します。リポジトリ内のシークレット混入スキャンも含まれます。

## データのクリーンアップ

```bash
python data_cleanup.py --dry-run   # 削除対象の確認
python data_cleanup.py             # request_details の古いログを削除
```

`run_servers.py` の起動時にも自動実行されます。

## デプロイ

`deploy.py` と `.deploy.env`（`.deploy.env.example` をコピー）を使用します。

```bash
python deploy.py
```
