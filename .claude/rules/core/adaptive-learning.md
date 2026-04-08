# Adaptive Learning

> **Goal**: Continuously learn from interactions to adapt to user preferences, project patterns, and coding style.

## Detection Triggers (Always Active)

| Signal | What It Means | Action |
|--------|---------------|--------|
| User corrects your output | Style/approach mismatch | `/learn` the correction |
| User rewrites your code | Coding style preference | `/learn` the pattern |
| User says "no", "wrong", "not like that" | Direct correction | `/learn` what was wrong and the right way |
| User rephrases your text | Communication style preference | `/learn` the tone/format |
| User undoes your change | Unwanted modification | `/learn` the boundary |
| User repeats an instruction | You forgot or ignored it | `/learn` as high-priority rule |
| User shows frustration | Repeated mistake | STOP, `/learn`, then adjust |
| User says "always" or "never" | Hard rule | `/learn` as permanent rule |
| User manually edits after you | Missed preference | Compare diff, `/learn` the delta |
| User picks Option B after you defaulted A | Preference signal | `/learn` the preference |
| You self-correct 2+ times same pattern | Recurring self-mistake | `/learn` the pattern (see `self-correction-prevention.md` for full list) |

## Learning Categories

| Priority | Trigger | Persistence |
|----------|---------|-------------|
| **P0 — Hard Rules** | User said "always"/"never" | `/learn` + MEMORY.md immediately |
| **P1 — Corrections** | User fixed your output | `/learn`, apply next interaction onward |
| **P2 — Preferences** | Inferred from behavior | Memory files, confirm if unsure |
| **P3 — Context** | Project-specific knowledge | Project memory, update as project evolves |

## How to Learn

- **Same conversation**: Acknowledge briefly ("Got it"), invoke `/learn`, apply immediately
- **Across conversations**: Update MEMORY.md or topic-specific memory files for significant patterns
- **Session start**: MEMORY.md is auto-loaded; search episodic memory for corrections if relevant

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| Silently ignore corrections | Acknowledge and `/learn` |
| Over-ask "should I learn this?" | Just learn it, mention briefly |
| Learn one-off exceptions as rules | Only learn repeated patterns |
| Forget lessons between conversations | Persist to memory files |
| Apply project-specific rules globally | Scope learning appropriately |

When finishing a significant task, briefly reflect: did the user correct anything worth remembering? If yes → `/learn` and update memory.
