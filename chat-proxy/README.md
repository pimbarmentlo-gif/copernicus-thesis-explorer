# Thesis chatbot OpenAI proxy

A tiny [Cloudflare Worker](https://workers.cloudflare.com/) that holds the
OpenAI API key and forwards chat requests for the dashboard's floating chatbot
widget. The key lives only here — it is **never** sent to visitors' browsers.

```
browser widget  ──POST {messages}──▶  this Worker  ──+ key──▶  OpenAI
                ◀──── answer JSON ─────              ◀─────────
```

## One-time deploy (~5 min, free tier)

1. Install the CLI and sign in (creates a free account if needed):
   ```bash
   npm install -g wrangler
   wrangler login
   ```

2. From this folder, store your OpenAI key as an encrypted secret:
   ```bash
   cd chat-proxy
   wrangler secret put OPENAI_API_KEY
   # paste your sk-... key when prompted
   ```

3. Deploy:
   ```bash
   wrangler deploy
   ```
   Wrangler prints a URL like
   `https://thesis-chat-proxy.<your-subdomain>.workers.dev`.

4. **Lock it to your site.** Edit `wrangler.toml` and set `ALLOWED_ORIGIN` to
   your deployed Streamlit URL (the origin only — no path), then redeploy:
   ```toml
   [vars]
   ALLOWED_ORIGIN = "https://your-app.streamlit.app"
   ```
   ```bash
   wrangler deploy
   ```

5. **Tell the dashboard where the proxy is.** In Streamlit Cloud →
   your app → **Settings → Secrets**, add:
   ```toml
   CHAT_PROXY_URL = "https://thesis-chat-proxy.<your-subdomain>.workers.dev"
   ```
   (For local testing, `export CHAT_PROXY_URL=...` before `streamlit run`.)

The widget reads `CHAT_PROXY_URL`; the Worker holds `OPENAI_API_KEY`. Neither
the key nor the dashboard secrets file is ever committed to git.

## Protecting against abuse

CORS/`ALLOWED_ORIGIN` stops other *websites* from using your proxy via a
browser, but it cannot stop someone who scripts requests directly. Two cheap
safeguards:

- **Set a hard monthly spend limit in your OpenAI billing settings.** This is
  the real backstop — do it regardless of anything else.
- In the Cloudflare dashboard, add a **Rate Limiting** rule on the Worker route
  (e.g. 20 requests/min per IP).

The Worker already pins the model to `gpt-4o-mini` and caps prompt size, so the
per-request cost is bounded.
