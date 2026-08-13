# ComputeLab（Nexgate AI 統合）

## エンドポイント

| 用途 | URL |
|------|-----|
| ダッシュボード（API キー発行） | https://dash.cl.nextvps.online |
| API ベース | 同上（`/api/...`, `/auth/me`） |

環境変数 `COMPUTELAB_API_BASE` で上書き可能。

## 認証

- `Authorization: Bearer cl_live_…` または `X-API-Key: cl_live_…`
- 接続確認: `GET /auth/me`
- API キーはダッシュボードの API 画面で発行（平文は発行時のみ）

## エージェントツール一覧

| ツール | API |
|--------|-----|
| `computelab_catalog` | GET /api/catalog |
| `computelab_balance` | GET /api/billing/balance |
| `computelab_list_instances` | GET /api/instances |
| `computelab_get_instance` | GET /api/instances/:id または …/connection |
| `computelab_wait_running` | ポーリング（PROVISIONING → RUNNING） |
| `computelab_create_instance` | POST /api/instances |
| `computelab_add_port` | POST /api/instances/:id/ports |
| `computelab_instance_action` | start / stop / restart / delete |
| `computelab_list_files` | GET …/data/files |
| `computelab_read_file` | GET …/data/text |
| `computelab_write_file` | PUT …/data/text |
| `computelab_mkdir` | POST …/data/mkdir |
| `computelab_exec` | POST …/exec |

## インスタンス状態

`PROVISIONING` → `RUNNING` | `STOPPED` | `ERROR` | `DELETED`

- **exec / add_port** は `RUNNING` のみ
- 作成直後は `computelab_wait_running` を使う

## エラー（よくある）

| HTTP | 意味 |
|------|------|
| 401 | API キー無効 |
| 402 | 残高不足（`required`, `balance`） |
| 409 | 非 RUNNING / 既に起動済み等 |
| 500 | exec 失敗（`details` に Docker 要約） |

## データ領域

- コンテナ内 `/data`（ツールの path は相対: `app/…`, `mc/…`）
- 編集は `write_file` / `read_file` / `list_files`

## ポート公開

- `container_port`: コンテナ内（8080=Web, 25565=マイクラ）
- 応答の **publicTcpEndpoint**（`IP:hostPort`）をゲーム接続先に使う
- Web は **suggestedPublicUrl**（`http://IP:hostPort`）

## 典型フロー

1. catalog → balance → create_instance
2. wait_running
3. mkdir / write_file / exec（`cwd`, 短いコマンド、`timeout_ms`）
4. add_port → exec で再起動・確認

## API リファレンス

OpenAPI 相当の詳細 JSON は `docs/computelab_api_reference.json`（提供仕様）を参照。

## 検証ロジック

`computelab_setup_verify.py` がツール結果のみでセットアップ完了を判定（完了報告の hallucination 防止）。
