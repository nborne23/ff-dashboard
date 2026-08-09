# scaffold-gridiron

Initial planning: build GridIron, a single-user fantasy football dashboard aggregating Yahoo + ESPN leagues into one Apple Health-styled view with live SSE updates. Self-hosted on the user's 2019 iMac (FastAPI + SQLite + APScheduler under launchd), reachable from phone/laptop over Tailscale.

Design source of truth: `GridIron.html` in the Claude Design project
<https://claude.ai/design/p/1692dcc6-8418-4f8f-9139-5d19358beaca?file=GridIron.html> — import via the claude_design MCP (`https://api.anthropic.com/v1/design/mcp`, auth via `/design-login`) before starting Phase 1.
