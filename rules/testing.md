# Testing Rules

テスト要件とベストプラクティス。

> **プロジェクト固有:** 実際のカバレッジ数値目標、CI ワークフローの pytest filter 表、サブモジュール/monorepo package ごとのテスト実行コマンドは導入先で追記する。

## カバレッジ要件

- **最小カバレッジ**: 75%以上を目安に維持する (数値は導入先で調整)
- **新機能**: 対応するテストを必ず作成
- **バグ修正**: リグレッションテストを追加

## テスト構造

### ディレクトリ構成
```
tests/
├── unit/           # ユニットテスト（外部依存はモック）
├── integration/    # 統合テスト（内部コンポーネント結合）
├── gui/            # GUIテスト（pytest-qt 等）
├── bdd/            # BDD振る舞い仕様テスト（pytest-bdd）
│   ├── conftest.py     # bddマーカー自動付与
│   ├── features/       # Gherkin featureファイル
│   └── steps/          # ステップ定義（test_*.py）
└── resources/      # テストリソース
```

### テストマーカー
```python
@pytest.mark.unit        # ユニットテスト
@pytest.mark.integration # 統合テスト
@pytest.mark.gui         # GUIテスト
@pytest.mark.bdd         # BDDテスト（tests/bdd/配下は自動付与）
@pytest.mark.slow        # 時間のかかるテスト
```

## pytest-qtベストプラクティス

Qt / PySide6 系 GUI を使うプロジェクト向け。

### シグナル待機
```python
# 正しい: waitSignalでタイムアウト付き待機
with qtbot.waitSignal(widget.completed, timeout=5000):
    widget.start_operation()

# 禁止: 固定時間待機
qtbot.wait(1000)  # 避ける
```

### UI状態待機
```python
# 正しい: waitUntilで条件待機
qtbot.waitUntil(lambda: widget.isEnabled(), timeout=5000)

# 禁止: processEventsの直接呼び出し
QCoreApplication.processEvents()  # 避ける
```

### ダイアログモック
```python
# QMessageBoxは必ずモック
def test_delete_confirmation(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args: QMessageBox.Yes
    )
    widget.delete_item()
```

## モック戦略

### モック対象
- 外部API（OpenAI, Anthropic, Google 等）
- ファイルシステム操作（大量ファイル処理）
- ネットワーク通信
- 時間依存処理

### モック非対象
- 内部サービス間の連携（統合テストで検証）
- データベース操作（テストDBを使用）
- Qt Signal/Slot（実際の動作を検証）

```python
# 外部APIのモック例
@pytest.fixture
def mock_openai(monkeypatch):
    def mock_complete(*args, **kwargs):
        return MockResponse(content="mocked response")
    monkeypatch.setattr(openai.ChatCompletion, "create", mock_complete)
```

## テスト実行

### 基本コマンド
```bash
# プロジェクト本体のテスト
uv run pytest

# ユニットテストのみ
uv run pytest -m unit

# BDDテストのみ
uv run pytest -m bdd

# カバレッジ付き
uv run pytest --cov=src --cov-report=html

# 特定ファイル
uv run pytest tests/unit/path/to/test_file.py
```

### サブモジュール / monorepo package のテスト

複数の独立した package (submodule 等、それぞれ独自の pytest 設定を持つもの) がある場合、
それぞれを独立した pytest セッションとして起動し、単一の pytest invocation に混ぜない。
package 間の venv 共有方針は `parallel-execution.md` の「venv 分離粒度: package 間」を参照。

> **プロジェクト固有:** package ごとのテスト実行コマンド (Makefile ターゲット等) をここに追記する。

### GUI テスト環境
```bash
# Linux/コンテナ: ヘッドレス実行
QT_QPA_PLATFORM=offscreen uv run pytest -m gui

# Windows: ネイティブウィンドウ
uv run pytest -m gui
```

## 長時間実行テストの待機パターン

テストスイート全体の実行に数十秒〜数分かかる場合、テストは長時間ジョブとなりやすく、待機方法を誤ると `sleep + tail` ループがランタイムによってブロックされる。以下のパターンに従うこと。

### 禁止パターン

```bash
# 禁止: ブロックされる: sleep を含むコマンドの後に追加の処理を chain
sleep 30 && tail -15 /tmp/.../task.output

# 禁止: ブロックされる: 複数 sleep の連鎖でポーリング代替
for i in 1 2 3; do sleep 10; tail log; done

# 禁止: 意味がない: 自分で時間を当てる方法
qtbot.wait(1000)  # 固定時間待機（テスト内でも禁止）
```

ランタイムは「先頭に長い `sleep` がある」「`sleep` の後に別コマンドが続く」を検知してブロックする。回避のために sleep を複数に分割しても同様にブロックされる（チェーンも検知される）。

### 推奨パターン1: 同期実行（デフォルト）

多くのエージェント実行環境の Bash ツールは既定で長いタイムアウトを持つ。テストスイート全体が短時間 (数十秒〜数分) であれば同期実行で十分。

```
Bash(command="uv run pytest --cov=src", description="Run full test suite")
# 完了までブロック → 完了後に stdout/stderr が直接返る
```

**利点**: 追加の待機ロジック不要。出力が即座に context に入る。
**使う場面**: テスト結果が次のステップに必要な場合（殆どのケース）。

### 推奨パターン2: バックグラウンド実行 + 完了通知

他の独立した作業と並行したい場合のみ使用。バックグラウンド実行フラグを設定すると、ランタイムが完了時に自動通知する。

```
Bash(command="uv run pytest -v", run_in_background=True, description="Run tests in background")
# → タスクIDが返る。他作業を継続。
# → 完了時に通知。出力ファイルを読む。
```

**重要**: 通知が来る前に自分で `sleep` してポーリングしない。ランタイムに任せる。

### 推奨パターン3: 条件待機（Monitor + until ループ）

特定の条件成立を待ちたい場合のみ使用。監視ツールを使うか、`until` ループの脱出を待つ。

```bash
# 許可されているパターン: until ループ内の sleep
until grep -q "PASSED" /tmp/results.log; do sleep 2; done
```

このパターンは単発の `sleep && next` と異なり、条件成立時に脱出する明示的な待機なので許可されている。

### 判断フロー

| 状況 | 使うパターン |
|------|------------|
| テスト結果がすぐ必要 | パターン1（同期実行） |
| 並行して他作業を進めたい | パターン2（バックグラウンド + 通知） |
| 特定ログ出力を待ちたい | パターン3（Monitor + until） |
| ジョブ完了を `sleep` で待ちたい | **どれも該当しない → 設計を見直す** |

### よくある間違い

- 「タスク開始から30秒経ったら結果を見る」と決め打ちで `sleep 30` する → 完了通知を待つべき
- バックグラウンド実行後に `tail` で進捗を確認したくなる → 完了通知が来てから読む
- 短い `sleep` を複数回挟んで回避を試みる → ランタイムが検知してブロックする

## BDD テスト（pytest-bdd）

BDDはE2Eに限定せず「振る舞い仕様の表現形式」としてService層以上に適用する。

### 適用レイヤー

| レイヤー | BDD の適用 | 理由 |
|---------|-----------|------|
| ユーザー向け機能フロー | ◎ | 仕様そのもの |
| Service 層の振る舞い | ○ | ビジネスルールの表現に向く |
| Repository 層の CRUD | △ | 技術的すぎて Gherkin が冗長 |
| 内部ロジック・ユーティリティ | ✕ | 通常の pytest が適切 |

### BDDシナリオを書くべきケース

- 新しいユーザー向け機能
- Service層のビジネスルール（重複排除、バリデーション等）
- バグ修正のリグレッション防止（再現シナリオを書いてから修正）

### BDDシナリオを書かないケース

- 内部リファクタリング
- UIの見た目の調整
- Repository層の単純CRUD

### 新しいBDDテストの追加方法

1. `tests/bdd/features/` に `.feature` ファイルを作成（日本語Gherkin）
2. `tests/bdd/steps/` に `test_<feature名>.py` を作成
3. `scenarios()` で feature ファイルを参照:
   ```python
   from pathlib import Path
   from pytest_bdd import scenarios
   _FEATURE_FILE = Path(__file__).parent.parent / "features" / "<feature名>.feature"
   scenarios(str(_FEATURE_FILE))
   ```
4. `@given`, `@when`, `@then` でステップ定義を実装

### pytest-bdd ベストプラクティス

要点:

- **`scenarios()` 一括登録を使う**: `steps/test_<feature>.py` 先頭で `scenarios(str(_FEATURE_FILE))` を 1 行。個別の `@scenario()` デコレータは使わない。
- **feature パスは `__file__` 基準で絶対解決**: `Path(__file__).parent.parent / "features" / "<name>.feature"`。cwd 依存を避ける。
- **ステップ間の状態は `target_fixture` で受け渡す**: `@given(..., target_fixture="ctx")` の戻り値が fixture になり後続ステップへ渡る。モジュールグローバル変数で状態共有しない（テスト間汚染の温床）。
- **既存 pytest fixture を再利用**: DB マネージャ等は `conftest.py` の fixture を `given`/`when`/`then` の引数で注入する。
- **ステップ実装は薄く**: `given`/`when`/`then` は Service/Repository を呼ぶだけ。ビジネスロジックをステップに書かない。
- **引数パースは `parsers.parse`**: `{name:d}` で型変換。正規表現が要るときだけ `parsers.re`、カスタム型は `parsers.cfparse`。
- **`bdd` マーカーは自動付与**: `tests/bdd/conftest.py` の `pytest_collection_modifyitems` が付与する。手動で `@pytest.mark.bdd` を書かない。
- **データ駆動は `Scenario Outline` + `Examples`**、ステップ直下の表は `datatable` 引数で受ける。
- **未実装ステップの検出**: `uv run pytest --generate-missing --feature tests/bdd/features tests/bdd/steps/`。

## テスト命名規則

```python
# ファイル名: test_<module_name>.py
# 関数名: test_<機能>_<条件>_<期待結果>

def test_search_with_empty_query_returns_all_items():
    ...

def test_delete_item_when_not_found_raises_error():
    ...
```

## フィクスチャ管理

### スコープの使い分け
```python
@pytest.fixture(scope="session")  # 全テストで1回
def database():
    ...

@pytest.fixture(scope="function")  # 各テストで毎回
def clean_state():
    ...
```

### conftest.py配置
- `tests/conftest.py`: 共通フィクスチャ
- `tests/unit/conftest.py`: ユニットテスト専用
- `tests/integration/conftest.py`: 統合テスト専用
- `tests/bdd/conftest.py`: BDDマーカー自動付与

## CI-equivalent filter で local 検証する

ローカルでの test 検証は CI workflow の pytest filter と **完全一致** の filter で実行する。短縮 filter (`-m unit` 等) のみで「regression なし」と結論しない。

### 理由

pytest markers は独立した分類 (`unit`, `standard`, `fast`, `heavy` 等)。`-m unit` で検証しても `-m standard` の test は collect されないため、CI 失敗を local 再現できない (発端事例は導入先の記録を参照)。

> **プロジェクト固有:** CI ワークフローの job ごとの pytest filter 一覧表をここに追記する。変更時は本表も更新する運用にする。

### 適用タイミング

- サブモジュール pin 更新 PR 起票 **前**
- ライブラリ側 API 変更 / refactor PR 起票 **前**
- "regression なし" を user に報告する **前**

### 例

```bash
cd <package root>
uv run pytest -m "not downloads_and_runs_model and not calls_real_webapi"
```

### Hook gate

`gh pr create` 実行時にサブモジュール (`submodule_globs` に一致するパス) の pin 変更を含む場合、kit の hook (`hook_pre_pr_submodule_check.py`) が CI-equivalent test 実行確認を要求する。bypass は command 内に `CI-EQUIV-TESTED` marker comment を含める。詳細は hook script のヘッダー参照。

### Worktree / I/O 制約 と package test

venv / 実行環境の分離粒度 (worktree 間・package 間でどこまで環境を共有するか) は `parallel-execution.md` に集約している。低速な I/O 環境 (ネットワークマウント上の checkout 等) で package ごとに専用 venv を作ると実用速度を損なう場合があるため、そちらのルールに従い共有 venv を優先する。

> **プロジェクト固有:** devcontainer / CI 環境固有のマウント構成、Makefile ターゲットの詳細をここに追記する。

## Lazy import refactor との関係

重い native 依存 (torch / tensorflow 等) の lazy import 化を行う場合は、対応する skill (`lazy-import-refactor` 等) が test 副作用 (`@patch("module.torch")` 等) を予測し、本セクションの filter で検証することを義務付ける。
