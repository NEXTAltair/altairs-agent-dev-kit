# TypeScript / JavaScript Dependency Rules

npm パッケージの導入と更新のルール。npm の registry は公開直後の悪意ある版が配布される事故が繰り返されており、
install 時に任意のスクリプトが走る。Python の依存管理より「入れる前」の防御が効く。
設定例は pnpm 12.4.2 で動作を確認した (2026-11-12)。

> **プロジェクト固有:** package manager とその版、build script を許可するパッケージの一覧、
> 最新追従する依存 (AI 推論 SDK 等) の一覧は導入先で追記する。

## package manager は 1 つ

- `package.json` の `packageManager` で版を固定し、lockfile を commit する。
- 他の package manager のコマンドを混ぜない (pnpm の repository で `npm install` を実行しない)。lockfile が
  2 種類できて、どちらが正か分からなくなる。
- CI と検証では lockfile を変えない install を使う (`pnpm install --frozen-lockfile`、`npm ci`)。
- CLI を global に入れない (`npm install -g`)。`pnpm exec` / `pnpm dlx` / `npx` で実行する。
- Git worktree ごとに `pnpm install` を実行する。pnpm は実体を共有の store に置いて link するので、
  worktree ごとの `node_modules` は小さい。

## 入れる前の防御

pnpm では `pnpm-workspace.yaml` に置く:

```yaml
# 公開から 1 日 (分単位) 経っていない版を解決しない
minimumReleaseAge: 1440
# 依存の依存が git / tarball URL を指すことを禁止する
blockExoticSubdeps: true
# install 時の build script を実行してよいパッケージだけを列挙する
allowBuilds:
  esbuild: true
```

- `minimumReleaseAge` は、乗っ取られたパッケージが公開直後に取り込まれるのを防ぐ。緊急の修正で新しい版が
  必要なときは、対象のパッケージだけを `minimumReleaseAgeExclude` に書く。全体を 0 にしない。
- build script は既定で実行されない。必要になったパッケージだけを `allowBuilds` に足し、何のために必要かを
  commit メッセージに書く。

## 依存を足す前に

- Node.js の標準で足りるなら足さない。`fetch`、テストランナー (`node:test`)、引数の解析 (`util.parseArgs`)、
  `.ts` の直接実行は標準にある。
- 足す場合は、最終リリースの時期、週あたりの download 数、依存の数を確認する。1 つの小さな関数のために
  依存の木を増やさない。
- 型定義 (`@types/*`) と実行時の依存を分ける。実行時に要らないものは `devDependencies` に置く。

## 更新

- 更新は lockfile の差分を見てから commit する。意図しないパッケージが増えていないかを確認する。
- 更新後は `check` (型チェック・lint・テスト) を通す。major 更新は変更点を読み、該当箇所を報告に書く。

## hook で止める

kit の `hook_pre_commands.py` を導入している場合、`.claude/hooks/rules/pre_commands.json` に追記して機械的に止められる:

```json
{
  "blocked_commands": [
    {
      "pattern": "\\bnpm\\s+(i|install|add)\\s+(.*\\s)?(-g|--global)\\b",
      "reason": "CLI を global に入れると版がプロジェクトと食い違う",
      "suggestion": "pnpm exec / pnpm dlx / npx で実行する"
    }
  ]
}
```
