# Agentic Staff

Use the `staff` skill only when the user explicitly invokes `/staff`, `$staff`, or the harness's staff skill command for the current request. Quoting or discussing the command is not an invocation. The skill passes through to the Python graph. Ordinary requests, including the first request and all later followups, use the base model directly. Do not call Jev or start the workforce automatically. While carrying out an explicit invocation, preserve its run ID and use the graph's pending actions until it completes or is blocked.
