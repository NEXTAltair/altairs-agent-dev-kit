---
name: pytest-qt-bdd
description: "Gotchas for writing and running tests with pytest-qt (PySide6/Qt widgets) and pytest-bdd (Gherkin scenarios): wait on signals and UI state instead of fixed sleeps, mock QMessageBox and dialogs, run GUI tests headless with QT_QPA_PLATFORM=offscreen, decide which layer deserves a BDD scenario, and add a feature file + step module the way this stack expects. Use when writing or fixing a test under tests/gui/ or tests/bdd/, when a Qt test hangs or flakes in CI, or when asked to 「GUI テスト書いて」「pytest-qt」「BDD シナリオ追加」「feature ファイル」「Gherkin」. Do NOT use for: coverage policy, CI-equivalent filters, or mock strategy (those live in rules/testing.md), or for non-Qt / non-BDD pytest work."
metadata:
  short-description: "pytest-qt (シグナル/UI 待機・ダイアログモック・headless 実行) と pytest-bdd (適用レイヤー・feature/steps の追加手順) の落とし穴集。"
---

# pytest-qt / pytest-bdd Gotchas

Qt / PySide6 の GUI テストと pytest-bdd の振る舞い仕様テストで、この stack 特有に踏みやすい点だけをまとめる。
カバレッジ方針・CI-equivalent filter・モック対象の線引きは [rules/testing.md](../../rules/testing.md) が持つので、ここでは繰り返さない。

## pytest-qt

### 固定時間待機ではなく、シグナルか条件を待つ

`qtbot.wait(ms)` の決め打ちは CI の負荷で簡単に flake する。完了はシグナルで、状態は条件で待つ。

```python
# 正しい: waitSignal でタイムアウト付き待機
with qtbot.waitSignal(widget.completed, timeout=5000):
    widget.start_operation()

# 正しい: waitUntil で条件待機
qtbot.waitUntil(lambda: widget.isEnabled(), timeout=5000)

# 禁止: 固定時間待機
qtbot.wait(1000)

# 禁止: processEvents の直接呼び出し (イベントループの回し方を手で当てにいく)
QCoreApplication.processEvents()
```

### モーダルダイアログは必ずモックする

`QMessageBox.question` 等はモーダルで止まり、headless ではテストがハングする。静的メソッドを monkeypatch で差し替える。

```python
def test_delete_confirmation(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args: QMessageBox.Yes
    )
    widget.delete_item()
```

### Signal/Slot はモックしない

Qt の Signal/Slot 配線はテストの検証対象そのもの。接続をモックで潰すと配線ミスを検出できない。実際に emit させ、`waitSignal` で受ける。

### headless 実行

Linux / コンテナでは `QT_QPA_PLATFORM=offscreen` を付けて起動する。Windows ではネイティブウィンドウで実行できるため不要。

```bash
# Linux/コンテナ
QT_QPA_PLATFORM=offscreen uv run pytest -m gui

# Windows
uv run pytest -m gui
```

`gui` マーカーは「Qt にアクセスするが表示は不要」、`gui_show` は「実際の描画を伴う」の区別で使う。`gui_show` は headless CI から除外する対象。

## pytest-bdd

BDD は E2E に限定せず、「振る舞い仕様の表現形式」として Service 層以上に適用する。

### 適用レイヤー

| レイヤー | BDD の適用 | 理由 |
|---------|-----------|------|
| ユーザー向け機能フロー | ◎ | 仕様そのもの |
| Service 層の振る舞い | ○ | ビジネスルールの表現に向く |
| Repository 層の CRUD | △ | 技術的すぎて Gherkin が冗長 |
| 内部ロジック・ユーティリティ | ✕ | 通常の pytest が適切 |

**書く**: 新しいユーザー向け機能、Service 層のビジネスルール (重複排除・バリデーション等)、バグ修正のリグレッション防止 (再現シナリオを先に書いてから直す)。
**書かない**: 内部リファクタリング、UI の見た目調整、Repository 層の単純 CRUD。

### feature / steps の追加手順

1. `tests/bdd/features/` に `.feature` を作成 (日本語 Gherkin 可)
2. `tests/bdd/steps/` に `test_<feature名>.py` を作成
3. `scenarios()` で feature を一括登録する

```python
from pathlib import Path
from pytest_bdd import scenarios

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "<feature名>.feature"
scenarios(str(_FEATURE_FILE))
```

4. `@given` / `@when` / `@then` でステップ定義を実装

### 落とし穴

- **`scenarios()` 一括登録を使う**: 個別の `@scenario()` デコレータは書かない。feature を足すたびに登録漏れが起きる。
- **feature パスは `__file__` 基準で絶対解決する**: 相対パスは pytest の起動ディレクトリ依存で壊れる。
- **ステップ間の状態は `target_fixture` で渡す**: `@given(..., target_fixture="ctx")` の戻り値が fixture になり後続ステップへ渡る。モジュールグローバル変数で共有するとテスト間汚染の温床になる。
- **既存 pytest fixture を再利用する**: DB マネージャ等は `conftest.py` の fixture を `given` / `when` / `then` の引数で注入する。
- **ステップ実装は薄く**: Service / Repository を呼ぶだけにし、ビジネスロジックをステップに書かない。
- **引数パースは `parsers.parse`**: `{name:d}` で型変換。正規表現が要るときだけ `parsers.re`、カスタム型は `parsers.cfparse`。
- **`bdd` マーカーは自動付与**: `tests/bdd/conftest.py` の `pytest_collection_modifyitems` が付ける。手で `@pytest.mark.bdd` を書かない。
- **データ駆動は `Scenario Outline` + `Examples`**: ステップ直下の表は `datatable` 引数で受ける。
- **未実装ステップの検出**: `uv run pytest --generate-missing --feature tests/bdd/features tests/bdd/steps/`
