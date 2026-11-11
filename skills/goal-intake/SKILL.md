---
name: goal-intake
description: Stage 0 Investor Financial Goal Discovery (/goal-intake). Establishes target return multiple, horizon, drawdown pain budget, market-cap runway, and NSE sector interests before scanning.
---

# Goal Intake (`/goal-intake`)

1. Ask or infer the investor's **Target Multiple** (`2x_3x` | `3x_5x` | `5x_10x_plus`), **Horizon** (`3`, `5`, `7`, `10` years), **Max Drawdown Tolerance** (`low_15pct` | `moderate_30pct` | `high_45pct`), **NSE Sector Interests**, and **Hard Red Lines**.
2. Call `set_investor_mandate` via MCP (`indian-investor-mcp`) or `AgentWorkspace.set_investor_mandate` so `recommend_archetype_from_goals` sets the bounded 6-layer weights and cap focus (`small_mid` for 5x-10x+ hunters).
