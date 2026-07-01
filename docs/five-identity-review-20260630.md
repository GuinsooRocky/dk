# 🧬 Five Identity Review — GROWING

**Project**: DK (chat-cc-bot) · **Scope**: the entire project
**Stage**: growing · **Active identities**: 🏗️ Builder (medium), 🧹 Sweeper (heavy), 🌱 Grower (heavy), 🔧 Maintainer (light)
**Date**: 2026-06-30 · **Agents**: 8 · **Tool calls**: 134

---

## 🚨 P0 — Critical (adversary-confirmed)

None. Both Builder P0s were downgraded to P1 by adversary — real bugs, but not critical-tier for a personal tool.

---

## ⚠️ P1 — Important

**🏗️ Builder** · `bug` · ⭐ corroborated by 🧹 Sweeper + 🔧 Maintainer (3 independent finds)
> **Supervisor backoff reset window is zero + no circuit breaker** — alive for one 2s tick resets backoff to 1; no max-restart park. Runtime proof: telegram restarts=5405, backoff=1.
> Files: `supervisor.py:393` (reset), `:408-411` (no cap), `~/.chat-cc-bot/supervisor.json`
> Action: gate reset on ≥60s uptime (track `started_at`); add max-restart → park channel in distinct `failed` state.

**🏗️ Builder** · `bug` (downgraded P0→P1)
> **Telegram channel has no proxy route → DNS/connect fail crash-loop** — `supervisor.py:184` deliberately gives telegram no proxy; `telegram_bot.py:13` says Telegram is blocked in CN. Result: `httpx.ConnectError` ×5405.
> Files: `supervisor.py:179-186`, `telegram/telegram_bot.py:13`
> Action: per-channel `proxy` key in config.toml (fallback to global / explicit empty = direct). Pairs with the circuit-breaker above so an unreachable channel parks instead of hammering.

**🏗️ Builder** · `bug`
> **`last_error` always null despite rc=1** — operators get "5405 restarts, cause unknown." `supervisor.py:404` reads `stderr_tail` at crash detection; consistent null points to a pump-thread/read race or EOF timing.
> Files: `supervisor.py:278-307, 403-404`
> Action: `pump_thread.join(timeout=1.0)` before reading, or capture last_error on stderr EOF inside the pump thread.

**🏗️ Builder** · `bug` (Soliloquy)
> **Silent refresh failure on Supabase reconnect → stale data** — `LinkerPage.tsx:80` & `NewsPage.tsx:117` `refresh().catch(() => {})` is the `onResubscribed` handler; postgres_changes don't replay missed INSERTs.
> Files: `soliloquy/src/pages/LinkerPage.tsx:76-91`, `NewsPage.tsx:113-122`
> Action: `.catch((e) => setError(...))` or a subtle "refresh failed" indicator + one retry.

**🧹 Sweeper** · `cleanup`
> **Telegram crash log runaway — 19.7MB / 329,067 lines** — each of 5405 cycles appends a full traceback, unbounded, no rotation.
> Files: `~/claude-telegram-workdir/.logs/telegram.log`, `supervisor.py`
> Action: `truncate -s 0 ~/claude-telegram-workdir/.logs/telegram.log` now; add `RotatingFileHandler` (5MB×3) — fix crash-loop root cause first.

**🧹 Sweeper** · `cleanup`
> **Home-root orphaned package.json + 52MB node_modules** — empty `dependencies`, 7 `@fontsource/*` devDeps, no consumer, abandoned font experiment.
> Files: `~/package.json`, `~/node_modules/`, `~/bun.lock`
> Action: `mv ~/package.json ~/node_modules ~/bun.lock ~/.Trash` (recovers 52MB, zero impact)

**🌱 Grower** · `improvement`
> **DK shows "connected" while crash-looping 5405×** — `_derive_state` (`supervisor.py:225`) returns "connected" whenever alive+backoff==1; backoff bug makes that permanently true for a dead channel. README §9 health check returns green on a dead service.
> Files: `supervisor.py:217-227`, `使用说明.md`
> Action: surface `crashing`/`degraded` when restarts>threshold & last_rc!=0.

**🌱 Grower** · `improvement` (Soliloquy)
> **LinkerPage saved links render as unclickable raw text** — `LinkerPage.tsx:177-184` dumps `item.text`; the captured `{url,title,excerpt}` metadata (saved at `:134-139`) is discarded, while NewsPage renders rich cards from the same Message type.
> Files: `soliloquy/src/pages/LinkerPage.tsx:177-184`
> Action: render a card with clickable title + excerpt + share action. (Note: `shareableFromItem` is NOT imported at line 3 — needs to be added.)

**🌱 Grower** · `improvement` (Soliloquy)
> **News empty-state dead-ends new users** — `NewsPage.tsx:341-343` points to an external `news-bridge` CLI; adding a source (`:494`) takes effect "next 6h cron round." First run = 6h blank wait.
> Files: `soliloquy/src/pages/NewsPage.tsx:340-344, 437-496`
> Action: add a "Fetch now" trigger in the source panel; replace CLI hint with in-app CTA.

**🌱 Grower** · `improvement` (MK)
> **MK Gatekeeper right-click ritual blocks cold conversions** — public release, self-signed (`README.md:62-71`); first double-click is hard-blocked, Developer ID is backlog (`:413`).
> Files: `mk/README.md:62-71, 413`
> Action: ship $99 Developer ID before promotion; interim — front-load Gatekeeper note above download link with a screenshot.

---

## 💡 P2 — Nice to Have

- **🧹 Sweeper** `CINCO_FIXED_ID` dead constant — `soliloquy/src/types/db.ts:149`, zero call sites → delete line 149 + comment 148.
- **🧹 Sweeper** stale `vite-env.d.ts` after Rsbuild migration — vite absent from package.json, `global.d.ts` already covers `ImportMeta.env` → delete `soliloquy/src/vite-env.d.ts`.
- **🧹 Sweeper** `UNFINISHED.md` severely stale (≥7 of 9 resolved) → update doc to 2 open items.
- **🔧 Maintainer** new-conversation gender write fire-and-forget — `soliloquy/src/components/Sidebar.tsx:346` `.catch(() => {})` can persist a conversation without its gender → remove inner catch.
- **🌱 Grower** MK auto-learning invisible — no in-app review of `correction-dictionary-learned.txt`; retention hook doesn't land → menubar "Recently learned (N)" list.
- **🌱 Grower** MK domain packs need JSON editing — onboarding survey is backlog → first-launch domain-checkbox window.
- **🌱 Grower** DK cold-start routes new users through terminal log-reading — `使用说明.md:51-52`; menubar `/pending` flow exists (`:54`) but isn't the documented primary path → lead with the panel.

---

## 📊 Summary

| Identity | Weight | P0 | P1 | P2 | Strongest signal |
|----------|--------|----|----|----|----|
| 🏗️ Builder | medium | 0 | 4 | 0 | Backoff+proxy crash-loop, runtime-proven (5405 restarts) |
| 🧹 Sweeper | heavy | 0 | 2 | 3 | 19.7MB/329k-line runaway log on disk |
| 🌱 Grower | heavy | 0 | 4 | 3 | Links archive writes but can't be retrieved (raw-text render) |
| 🔧 Maintainer | light | 0 | 1* | 1 | Crash-loop circuit-breaker gap (*same root as Builder) |

**Total**: ~17 unique findings · P0: 0 · P1: 10 · P2: 7
**Skipped identities**: 💡 Prototyper (not relevant for growing stage)

**Recommended first action**: Fix `supervisor.py` — gate backoff reset on ≥60s uptime + add max-restart circuit breaker → parks the dead Telegram channel, stops 5405× churn, ends the 20MB log runaway, removes the false "connected" status. Then decide: disable Telegram, or give it a working proxy.
