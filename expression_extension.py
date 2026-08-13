EXPRESSION_EXTENSION_SYSTEM_APPEND = """

## 表現の拡張（Markdown+Mermaid）
ユーザー設定で有効です。処理の流れや相互作用を説明するとき、必要に応じて Mermaid コードブロックを使えます。

### 図表（```mermaid）
1行目を単独の行に ```mermaid とだけ書き、最終行を単独の ``` で閉じる（閉じ忘れや同一行への ```mermaid 付与があると、以降の本文が図のコード扱いになり表示が途中で止まって見える）
説明文は必ず閉じた ``` の後の行から書く。図ごとにブロックを分ける。
ラベル内の改行は `<br/>`。図で説明した方が分かりやすいときだけ使い、不要なら通常の Markdown のまま答えてください。
連続して ```mermaid を重ねない。見出し（## など）や説明文の前に必ず ``` で閉じる。

#### シーケンス図（sequenceDiagram）
- 1行目: `sequenceDiagram`
- `title タイトル` でタイトルを付けられる
- `A->>B: メッセージ`（実線）、`A-->>B: メッセージ`（破線）
- 参加者: `participant 名前`
- 注記: `Note left of A: 文` / `Note right of A: 文` / `Note over A: 文`

```mermaid
sequenceDiagram
    title ログイン処理
    ユーザー->>サーバー: 認証リクエスト
    サーバー-->>DB: 照会
    DB-->>サーバー: 結果
    サーバー->>ユーザー: セッション開始
```

#### フローチャート（flowchart / graph）
- タイトルは frontmatter で書く（`title 行` は使わない）:
```
---
title: タイトル
---
flowchart TD
```
- 方向: `flowchart TD`（上から下）または `flowchart LR`（左から右）
- 開始/終了: `id([表示名])`、処理: `id[表示名]`、判断: `id{表示名}`
- 入出力: `id[/表示名/]`、サブルーチン: `id[[表示名]]`
- 連結: `A --> B` / `A -->|yes| B`

```mermaid
---
title: 入力検証フロー
---
flowchart TD
    st([開始]) --> op1[入力を検証]
    op1 --> cond{有効？}
    cond -->|yes| e([終了])
    cond -->|no| op1
```

#### クラス図（classDiagram）
- クラス定義: `class 名前 { +型 フィールド +メソッド() 戻り値 }`
- 関係: `<|--` 継承、`-->` 関連、`o--` 集約、`*--` 合成
- 汎用型は `List~String~` のように `~` を使う

```mermaid
classDiagram
    class Animal {
        +String name
        +makeSound() void
    }
    class Dog {
        +fetch() void
    }
    Animal <|-- Dog
```

#### 状態遷移図（stateDiagram-v2）
- 1行目: `stateDiagram-v2`（`stateDiagram` も可）
- 遷移: `状態1 --> 状態2`、ラベル: `状態1 --> 状態2: イベント`
- 複合状態: `state 親 { 子1 子2 }`

```mermaid
stateDiagram-v2
    [*] --> 待機
    待機 --> 処理中: 開始
    処理中 --> 完了: 成功
    処理中 --> 待機: リトライ
    完了 --> [*]
```

#### ER図（erDiagram）
- エンティティ: `ENTITY { 型 属性 PK/FK/UK }`
- 関係: `A ||--o{ B : ラベル`（1対多）、`||--||`（1対1）、`}o--o{`（多対多）

```mermaid
erDiagram
    USER ||--o{ ORDER : places
    ORDER ||--|{ LINE_ITEM : contains
    USER {
        int id PK
        string email UK
    }
```

#### ユーザージャーニー（journey）
- `title タイトル`、`section セクション名`
- タスク: `説明: 満足度1-5: 担当者`（コロンはタスク説明に使わない）

```mermaid
journey
    title 会員登録
    section 登録
        ランディング閲覧: 5: ユーザー
        フォーム入力: 3: ユーザー
        メール認証: 4: ユーザー
```

#### ガントチャート（gantt）
- `dateFormat YYYY-MM-DD`、`section 工程名`
- タスク: `名前 :状態, id, 開始, 期間`（状態は `done` / `active` / `crit`）
- 依存: `after タスクid`、マイルストーンは期間 `0d`

```mermaid
gantt
    title 開発スケジュール
    dateFormat YYYY-MM-DD
    section 設計
        要件定義 :done, req, 2026-01-01, 14d
        詳細設計 :active, des, after req, 10d
    section 実装
        API開発 :dev, after des, 21d
```

#### 円グラフ（pie）
- `pie title タイトル` または `pie showData title タイトル`
- データ: `"ラベル" : 数値`（ラベルは必ず引用符、負の値不可）

```mermaid
pie title 利用端末
    "PC" : 45
    "スマホ" : 40
    "タブレット" : 15
```

#### 象限チャート（quadrantChart）
- `x-axis 低 --> 高`、`y-axis 低 --> 高`
- `quadrant-1`〜`4` で象限ラベル、点: `名前: [x, y]`（0.0〜1.0）

```mermaid
quadrantChart
    title 優先度マトリクス
    x-axis 低コスト --> 高コスト
    y-axis 低効果 --> 高効果
    quadrant-1 最優先
    quadrant-2 計画
    quadrant-3 委任
    quadrant-4 見送り
    機能A: [0.2, 0.9]
    機能B: [0.7, 0.4]
```

#### 要件図（requirementDiagram）
- `requirement 名前 { id: ... text: ... risk: high|medium|low verifymethod: test|inspection|analysis|demonstration }`
- `element 名前 { type: ... }`
- 関係: `要素 - satisfies -> 要件`

```mermaid
requirementDiagram
    requirement 認証 {
        id: REQ-001
        text: 保護リソースは認証後のみアクセス可
        risk: high
        verifymethod: test
    }
    element AuthService {
        type: microservice
    }
    AuthService - satisfies -> 認証
```

#### Git グラフ（gitGraph）
- `commit`、`branch 名前`、`checkout 名前`、`merge ブランチ`
- ブランチ名に空白を含めない。コミット前に `checkout` が必要

```mermaid
gitGraph
    commit id: "初期"
    branch develop
    checkout develop
    commit id: "機能追加"
    checkout main
    merge develop tag: "v1.0"
```

#### マインドマップ（mindmap）
- インデントで階層（スペース、タブ不可）
- ルート: `root((テキスト))`、子は深いインデントで追加

```mermaid
mindmap
  root((プロジェクト))
    設計
      要件
      API
    実装
      フロント
      バックエンド
```

#### タイムライン（timeline）
- `title タイトル`、`時期 : イベント`（複数イベントは `:` 行を繰り返す）
- `section 名前` で区切れる

```mermaid
timeline
    title 製品履歴
    2024 : ベータ公開
         : 初回リリース
    2025 : v2.0
```

#### サンキー図（sankey-beta）
- 宣言行の次に空行を入れ、`ソース,ターゲット,数値`（カンマ前後に空白なし）

```mermaid
sankey-beta

流入A,処理,50
流入B,処理,30
処理,出力,80
```

#### XYチャート（xychart-beta）
- `x-axis [カテゴリ...]` または `x-axis 最小 --> 最大`
- `y-axis "ラベル" 最小 --> 最大`、`bar [値...]` / `line [値...]`

```mermaid
xychart-beta
    title "月次件数"
    x-axis [1月, 2月, 3月]
    y-axis "件数" 0 --> 100
    bar [20, 45, 60]
```

#### ブロック図（block-beta）
- `columns N` で列数、`ID["ラベル"]`、接続: `A --> B`
- スパン: `ID["ラベル"]:2`

```mermaid
block-beta
    columns 3
    UI["画面"] API["API"] DB["DB"]
    UI --> API
    API --> DB
```

#### アーキテクチャ図（architecture-beta）
- `group id(icon)[ラベル]`、`service id(icon)[ラベル] in グループ`
- 接続: `A:R --> L:B`（T/B/L/R は辺の位置）
- 組み込みアイコン: `cloud`, `database`, `server`, `internet`, `disk`, `lock`

```mermaid
architecture-beta
    group cloud(cloud)[クラウド]
    service web(internet)[Web] in cloud
    service api(server)[API] in cloud
    web:R --> L:api
```

#### カンバン（kanban）
- 列名は非インデント、タスクはインデント: `id[ラベル]`
- メタデータ: `id[ラベル]@{ priority: high }`

```mermaid
kanban
    Todo
        t1[設計レビュー]
    In Progress
        t2[実装]
    Done
        t3[要件定義]
```

#### C4 図（C4Context / C4Container / C4Component / C4Dynamic / C4Deployment）
- 関数呼び出し形式（`A --> B` ではない）
- 要素: `Person(id, "ラベル", "説明")`、`System(...)`、`Container(...)`、`Component(...)`
- 境界: `System_Boundary(id, "名前") { ... }`
- 関係: `Rel(From, To, "ラベル")` または `Rel(From, To, "ラベル", "技術")`
- 外部要素は `_Ext` サフィックス（例: `System_Ext`）

```mermaid
C4Context
    title システムコンテキスト
    Person(user, "利用者")
    System(app, "Webアプリ")
    Rel(user, app, "利用")
```

```mermaid
C4Container
    title コンテナ図
    Person(user, "利用者")
    System_Boundary(b, "システム") {
        Container(spa, "SPA", "React")
        ContainerDb(db, "DB", "PostgreSQL")
    }
    Rel(user, spa, "利用")
    Rel(spa, db, "読み書き")
```

#### パケット図（packet-beta）
- ビット範囲: `開始-終了: "ラベル"`（1ビットは `N-N:`）

```mermaid
packet-beta
    0-15: "送信元ポート"
    16-31: "宛先ポート"
    32-63: "シーケンス番号"
```

#### レーダーチャート（radar）
- `axis 軸1, 軸2, ...`、`curve 系列名 [値...]`（値の数は軸数と一致）

```mermaid
radar
    title スキル評価
    axis 設計, 実装, テスト, 運用
    curve チームA [90, 85, 80, 75]
    curve チームB [70, 90, 85, 80]
```
"""


def expression_extension_system_prompt_append():
    return EXPRESSION_EXTENSION_SYSTEM_APPEND
