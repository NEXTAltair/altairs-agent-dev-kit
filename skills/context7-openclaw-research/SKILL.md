---
name: context7-openclaw-research
version: "2.0.0"
description: Library research via web search and long-term memory via OpenClaw LTM. OpenClaw may enrich stored content using Context7/Perplexity.
metadata:
  short-description: ライブラリ調査（web検索 + OpenClaw委譲）と長期記憶（OpenClaw LTM）。
allowed-tools:
  # Web research (Claude Code)
  - WebSearch
  - WebFetch
  # Serena tools (for code integration)
  - Grep
  - Grep
  - Grep
  - Grep
  # Bash for OpenClaw LTM operations
  - Bash
---

# Complex Analysis (Library Research + Long-Term Memory)

Complex analysis using web research and OpenClaw LTM for design pattern memory and strategic decisions.
利用可能な場合のみ OpenClaw LTM 連携を使う。プロジェクトに OpenClaw webhook や長期記憶スキルが無ければ、
LTM 関連の手順はスキップし WebSearch/Web 調査のみで代替する。

Note: ライブラリ調査は WebSearch/WebFetch で実施し、LTM 保存時に OpenClaw が Context7/Perplexity を使って内容をブラッシュアップして保存します。

## When to Use

Use this skill when:
- **Design pattern search**: Researching past similar designs (OpenClaw LTM)
- **Library research**: WebSearch で公式ドキュメント/仕様を確認し、保存時に OpenClaw が補強
- **Long-term memory**: Storing design decisions and rationale (OpenClaw LTM)
- **Dependency analysis**: Understanding architectural relationships
- **Strategic decisions**: Evaluating approaches and trade-offs

## Core Patterns

### 1. Design Knowledge Search (OpenClaw LTM)

**ltm_search.py** - Past design patterns
- Searches design decisions, implementation patterns, lessons learned
- Usage:
```bash
python3 <project-memory-skill>/scripts/ltm_search.py <<'JSON'
{"limit": 10, "filters": {"type": ["decision", "howto"], "tags": ["repository-pattern"]}}
JSON
```

**ltm_latest.py** - Recent entries
```bash
python3 <project-memory-skill>/scripts/ltm_latest.py <<'JSON'
{"limit": 5}
JSON
```

### 2. Long-term Memory Storage (OpenClaw LTM)

**POST /hooks/&lt;project&gt;-memory** - Store knowledge (webhook path/name is project-specific)
- Stores design knowledge with proper metadata
- Use: After implementation, after major decisions
- Content: Design approach, rationale, results, lessons learned

```bash
HOOK_TOKEN=$(jq -r '.hooks.token' ~/.clawdbot/clawdbot.json)

curl -sS -X POST http://host.docker.internal:18789/hooks/<project>-memory \
  -H "Authorization: Bearer $HOOK_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "[Project] [Feature] Design Decision",
    "summary": "Brief summary of the decision",
    "body": "# Design Details\n\n## Background\n...\n\n## Decision\n...\n\n## Rationale\n...",
    "type": "decision",
    "importance": "High",
    "tags": ["architecture", "pattern-name"],
    "source": "Container"
  }'
```

### 3. Library Research (Web + OpenClaw)

ライブラリ調査は WebSearch で公式ドキュメントを確認し、要点をまとめて LTM 保存時に OpenClaw が補強します。

Example (web search):
```
WebSearch: "PySide6 Signal Slot QThread official docs"
```

### 4. Web Research

**WebSearch** - Latest information
- Searches official docs, blogs, case studies, recent updates
- Use: When you need up-to-date or external sources

## Workflow Guidelines

### Design Phase
```
1. LTM search (ltm_search.py) - Past designs
2. Library research (WebSearch) - Technical details
3. Store decision (POST /hooks/<project>-memory) - For future
```

### Implementation Phase
```
1. LTM search - Implementation patterns
2. Web docs - API details
3. Code integration (Serena tools)
4. Store knowledge - After completion
```

## Code Search vs OpenClaw LTM

**Code Search (fast)** - Use for:
- Symbol search (Grep/Glob)
- File structure exploration
- Current implementation details

**OpenClaw LTM (1-3s)** - Use for:
- Design pattern search
- Long-term memory
- Strategic decisions
- Cross-project knowledge

### Combined Workflow
```
1. docs/decisions/: Check past design decisions
2. OpenClaw: Search past designs (ltm_search.py)
3. Web: Research library (WebSearch)
4. Code: Implement with Grep/Glob/Read/Edit
5. docs/lessons-learned.md: Record lessons
6. OpenClaw: Store knowledge (POST /hooks/<project>-memory)
```

## Example Usage (illustrative, adapt to the project's stack)

### Design Decisions to Store
- Architecture patterns (Repository, Service Layer, component communication style)
- Technical choices (ORM, UI framework, test framework rationale)
- Performance improvements (caching, async decisions)
- Refactoring (intent and effects)

### Libraries to Research
- UI framework: Signal/Slot equivalents, threading, designer tooling
- ORM: transactions, migrations
- Test framework: fixtures, mocks, parametrization
- Any domain-specific library the project depends on

### Query Examples (OpenClaw LTM)
```bash
# Widget patterns
python3 <project-memory-skill>/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"tags": ["widget", "signal-slot", "direct-communication"]}}
JSON

# Repository patterns
python3 <project-memory-skill>/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"tags": ["repository-pattern", "sqlalchemy"]}}
JSON

# Testing patterns
python3 <project-memory-skill>/scripts/ltm_search.py <<'JSON'
{"limit": 5, "filters": {"tags": ["pytest", "testing"]}}
JSON
```

## Performance Characteristics

| Operation | Tool | Time |
|-----------|------|------|
| LTM search | ltm_search.py | 2-5s |
| LTM write | POST /hooks/<project>-memory | 1-3s |
| Web search | WebSearch | 2-5s |
| Code search | Grep/Glob/Read | 0.1-0.3s |

## Examples

See [examples.md](./examples.md) for detailed scenarios.

## Reference

See [reference.md](./reference.md) for OpenClaw LTM + WebSearch reference.
