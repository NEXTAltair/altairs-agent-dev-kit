# サードパーティ skills

本 kit にはライセンス・更新追従の観点から他リポジトリ由来の skills を同梱しない。
代わりに、実運用で有用と確認済みのサードパーティ skill を `npx skills add` でのインストールリストとして記載する。

導入コマンドの形式:

```bash
npx skills add github:<owner>/<repo> --skill <skill-name>
```

## wshobson/agents 由来

| skill | source | install |
|---|---|---|
| python-error-handling | wshobson/agents | `npx skills add github:wshobson/agents --skill python-error-handling` |
| python-performance-optimization | wshobson/agents | `npx skills add github:wshobson/agents --skill python-performance-optimization` |
| python-testing-patterns | wshobson/agents | `npx skills add github:wshobson/agents --skill python-testing-patterns` |
| python-type-safety | wshobson/agents | `npx skills add github:wshobson/agents --skill python-type-safety` |
| sql-optimization-patterns | wshobson/agents | `npx skills add github:wshobson/agents --skill sql-optimization-patterns` |
| database-migration | wshobson/agents | `npx skills add github:wshobson/agents --skill database-migration` |

## vercel-labs/agent-skills 由来

| skill | source | install |
|---|---|---|
| deploy-to-vercel | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill deploy-to-vercel` |
| vercel-cli-with-tokens | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill vercel-cli-with-tokens` |
| vercel-composition-patterns | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill vercel-composition-patterns` |
| vercel-react-best-practices | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill vercel-react-best-practices` |
| vercel-react-native-skills | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill vercel-react-native-skills` |
| vercel-react-view-transitions | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill vercel-react-view-transitions` |
| web-design-guidelines | vercel-labs/agent-skills | `npx skills add github:vercel-labs/agent-skills --skill web-design-guidelines` |

## 個別インストールの例

Python の型安全 skill だけ導入したい場合:

```bash
npx skills add github:wshobson/agents --skill python-type-safety
```

Vercel 系をまとめて導入したい場合は、必要な skill 名それぞれについて上記コマンドを繰り返す
(`npx skills add` は 1 コマンドにつき 1 skill を対象とする)。

## 一覧の出典

この表は `NEXTAltair/LoRAIro` の `skills-lock.json` (`sourceType: "github"` のエントリ) を転記したもの。
各リポジトリの skill 構成が更新された場合は転記元を再確認すること。
