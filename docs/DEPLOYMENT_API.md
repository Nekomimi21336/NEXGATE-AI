# 3サーバー構成のデプロイ

## 構成

| サービス | 既定ポート | 起動 |
|----------|------------|------|
| メインフロント | 5000 | `frontend_server.py` |
| API管理フロント | 5001 | `api_portal_server.py` |
| APIサーバー | 5002 | `api_server.py` |

開発時は `python run_servers.py` で3プロセスを一括起動できます。

## 必須環境変数

- `FLASK_SECRET_KEY` — 3サービスで同一値（セッション共有）
- `NEXGATE_INTERNAL_API_KEY` — メインフロント → APIサーバー用共通キー
- `API_INTERNAL_URL` — フロント/ポータルから見た API の内部 URL
- `FRONTEND_BASE_URL` / `API_PORTAL_BASE_URL` / `PUBLIC_API_BASE_URL`

## 本番リバースプロキシ例

- `app.example.com` → メインフロント (5000)
- `developers.example.com` → API管理フロント (5001)
- `api.example.com` → APIサーバー (5002)

APIサーバーでは `/v1/chat/completions` を外部公開し、`/api/webhooks/paypal` 等も到達可能にしてください。

## 顧客向け API

- エンドポイント: `GET /v1/models` / `POST /v1/chat/completions`
- 認証: `Authorization: Bearer ngx_...`
- OpenAI 互換の `tools` / `tool_choice` / `tool` ロール / `tool_calls` に対応（DeepSeek へパススルー）
- API Platform: API管理フロント (5001) の `/dash`（旧 `/portal` はリダイレクト）
- メインアプリ (5000) からは `/api/auth/go-portal` で SSO ログイン後に開く

## CORS

`PUBLIC_API_CORS_ORIGIN` で `/v1/*` の `Access-Control-Allow-Origin` を制御します。
