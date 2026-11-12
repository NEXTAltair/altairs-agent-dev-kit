# TypeScript / JavaScript Style Rules

TypeScript / JavaScript のスタイルは、散文のルールではなく型チェッカと linter / formatter の設定で定義する。
インデント、引用符、import 順序、命名の形式、未使用変数のような機械で検出できる事項はここに書かず、設定と
検査結果に委ねる。本ファイルが持つのは次の 4 つ:

1. 置く設定 (tsconfig / linter / package.json の scripts)
2. 検査結果の扱い方 (commit 前に直す、抑制しない)
3. 設定では決まらない判断 (外部入力の型、エラー、構文の選択)
4. レビューする人がこの言語を読まない場合の成果の示し方

> **プロジェクト固有:** 採用している linter / formatter と package manager、検査を一括実行するコマンド名、
> レビューする人が TypeScript を読むかどうかは導入先で追記する。

設定例は TypeScript 7.0.2 / Biome 2.6.6 / Node.js 24 で動作を確認した (2026-11-12)。

## 型チェック / lint / format の設定

新規コードは TypeScript で書く。JavaScript のまま残すファイルも `allowJs` + `checkJs` で型チェックに含める。

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "es2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "verbatimModuleSyntax": true,
    "erasableSyntaxOnly": true,
    "skipLibCheck": true,
    "noEmit": true
  },
  "include": ["src", "tests"]
}
```

- `noUncheckedIndexedAccess`: `xs[0]` や `map[key]` の型に `undefined` を含める。存在しない要素の参照を型で止める
- `erasableSyntaxOnly`: `enum` / `namespace` / コンストラクタ引数のプロパティ宣言など、実行時コードを生む構文を
  禁止する。型を消すだけで動くので、Node.js が `.ts` をそのまま実行できる
- `include` にテストを入れる。テストだけ型チェックから外さない

linter / formatter は 1 つに決める。既に ESLint + typescript-eslint や oxlint を使っている repository では
それを使い続け、2 つ目を足さない。未導入なら Biome (lint と format を 1 つの設定で持てる) を使う。

`biome.json`:

```json
{
  "$schema": "https://biomejs.dev/schemas/2.6.6/schema.json",
  "vcs": { "enabled": true, "clientKind": "git", "useIgnoreFile": true },
  "linter": {
    "rules": {
      "preset": "recommended",
      "suspicious": { "noExplicitAny": "error" },
      "nursery": { "noFloatingPromises": "error", "noMisusedPromises": "error" }
    }
  }
}
```

- `noFloatingPromises` / `noMisusedPromises`: `await` し忘れた Promise を検出する。型チェッカは通してしまうので
  linter 側で止める。Biome では nursery (仕様が変わり得る) の rule。ESLint を使う場合の対応する rule は
  `@typescript-eslint/no-floating-promises` と `@typescript-eslint/no-misused-promises`
- `// @ts-ignore` は型チェッカを黙らせるので `tsc` では検出できない。Biome の `noTsIgnore` (recommended) が検出する

`package.json` の scripts は検査を 1 コマンドにまとめる:

```json
{
  "type": "module",
  "scripts": {
    "typecheck": "tsc --noEmit",
    "lint": "biome check --error-on-warnings .",
    "format": "biome check --write .",
    "test": "vitest run",
    "check": "tsc --noEmit && biome check --error-on-warnings . && vitest run"
  }
}
```

## 検査結果の扱い

- commit 前に `check` を通す。指摘が残った状態で commit しない。
- 整形は formatter の出力をそのまま使う。手で整形し直さない。
- 指摘は根本原因を直す。次の書き方で黙らせない:

```ts
// 禁止
// @ts-ignore
const user = data as any;
const id = (payload as unknown as { id: string }).id;
const name = maybeName!;

// 例外: 対象を限定し理由を書く。@ts-expect-error はエラーが消えた時点で検査に落ちるので残骸にならない
// @ts-expect-error 外部ライブラリの型定義が引数 2 つの呼び出しを持たない
legacyCall(a, b);
// biome-ignore lint/suspicious/noExplicitAny: 生成コードの型が any を返す
const raw: any = generated();
```

- 設定側を緩めて通さない。`strict` を切る、rule を off にする、`include` から外す、といった全体を緩める変更はしない。
- 自動修正 (`biome check --write`) を使ったら、何が変わったかを diff で確認してから commit する。

## 設定では決まらない判断

- **外部入力は `unknown` で受ける。** `JSON.parse`、HTTP 応答、環境変数、ファイルの内容は、境界で検証してから
  型を付ける。`as` で型を付けて済ませない (実行時には何も検査されない)。
- **エラーを握りつぶさない。** `catch` した値は `unknown` として扱い、`instanceof Error` で絞る。投げるのは `Error` の
  サブクラス。空の `catch {}` を書かない。
- **Promise は `await` する。** 意図して待たない場合は `void` を付け、待たない理由を同じ行に書く。
- **ESM で書く。** `require` / `module.exports` を新規に書かない。
- **`enum` の代わりに literal の union か `as const` のオブジェクトを使う。**

## レビューする人がこの言語を読まない場合

エージェントが言語を選んだプロジェクトでは、依頼した人が TypeScript を読まないことがある。その場合、コードを
引用した説明は確認の手段にならない。

- 完了の報告は、実行したコマンドとその出力 (`check` の結果、テストの件数) と、変更後に観察できる動作
  (実行例、画面、HTTP 応答) で示す。
- テスト名は「何が保証されたか」をプロジェクトの言語で書く (`test("空の入力では何も送信しない", ...)`)。
  テスト一覧が仕様の一覧として読めるようにする。
- どのファイルから読めば全体が分かるか (入口) を README に 1 か所書き、構成を変えたら更新する。
- 依存の追加、ビルド設定の変更、生成物の追加は、何のために必要かを報告に書く。差分の量からは判断できない。
