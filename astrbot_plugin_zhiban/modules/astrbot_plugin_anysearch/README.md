# Anysearch for Zhiban

This directory is a Zhiban-adapted copy of `AgIzT/astrbot_plugin_anysearch`, locked at commit `983a7acb2f6940ab441a521be684085e0913738e` (MIT, v0.3). See `UPSTREAM.md` and `LICENSE`.

## Behavior

- `/anysearch 关键词`, `/anysearch extract URL`, `/anysearch batch ...`, and `/anysearch status` are available.
- LLM tools are disabled by default and only registered when `enable_llm_tools=true`.
- A missing API key produces a clear "not configured" result; initialization never sends a search.
- Search and extraction responses are bounded by bytes, timeout, concurrency, and a short TTL/LRU text cache.
- Extraction validates scheme, userinfo, hostname, DNS results, and each redirect hop; localhost, private, link-local, metadata, and other non-global targets are rejected.
- The HTTP session is lazy, reused, and closed on module termination.
- API keys are marked secret in the configuration schema, omitted from public status, and redacted from error text.

## Notes

Anysearch is an external service. Search terms and the final public URL are sent to `https://api.anysearch.com/mcp`; review the provider's terms and costs before enabling LLM tools. Redirect preflight is a best-effort boundary because the remote extraction service ultimately resolves the URL on its own side.