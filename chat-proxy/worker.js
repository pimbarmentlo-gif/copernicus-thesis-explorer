// Cloudflare Worker — OpenAI proxy for the thesis-platform chatbot widget.
//
// Why this exists: the chat widget runs in the visitor's browser, so it must
// NOT contain the OpenAI API key (anyone could read it from page source).
// Instead the widget POSTs only the conversation to this Worker, which holds
// the key as an encrypted secret and forwards the request to OpenAI.
//
// The Worker also locks down the model and generation parameters so a visitor
// cannot repurpose your OpenAI quota for arbitrary/expensive requests.
//
// Secrets / vars (set via `wrangler secret put` or the CF dashboard):
//   OPENAI_API_KEY  (secret)  — your OpenAI key.
//   ALLOWED_ORIGIN  (var)     — comma-separated list of allowed site origins,
//                               e.g. "https://your-app.streamlit.app".
//                               Leave unset only for local testing.

const MODEL = "gpt-4o-mini";
const MAX_MESSAGES = 20;      // system + recent turns; widget sends ~8
const MAX_TOTAL_CHARS = 60000; // guard against oversized prompts

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin, env);

    // Preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }

    if (request.method !== "POST") {
      return json({ error: { message: "Method not allowed" } }, 405, cors);
    }

    // Reject browsers from disallowed origins (does not stop curl, but stops
    // other websites from spending your quota via a user's browser).
    if (!originAllowed(origin, env)) {
      return json({ error: { message: "Origin not allowed" } }, 403, cors);
    }

    if (!env.OPENAI_API_KEY) {
      return json({ error: { message: "Proxy missing OPENAI_API_KEY" } }, 500, cors);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: { message: "Invalid JSON" } }, 400, cors);
    }

    const messages = body && body.messages;
    if (!Array.isArray(messages) || messages.length === 0) {
      return json({ error: { message: "Missing messages[]" } }, 400, cors);
    }
    if (messages.length > MAX_MESSAGES) {
      return json({ error: { message: "Too many messages" } }, 400, cors);
    }
    let total = 0;
    for (const m of messages) {
      if (!m || typeof m.role !== "string" || typeof m.content !== "string") {
        return json({ error: { message: "Malformed message" } }, 400, cors);
      }
      total += m.content.length;
    }
    if (total > MAX_TOTAL_CHARS) {
      return json({ error: { message: "Prompt too large" } }, 413, cors);
    }

    // Build the OpenAI request server-side — client cannot change model/params.
    const upstream = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + env.OPENAI_API_KEY,
      },
      body: JSON.stringify({
        model: MODEL,
        messages,
        temperature: 0.2,
        max_tokens: 1200,
        response_format: { type: "json_object" },
      }),
    });

    // Pass OpenAI's response (success or error) straight back to the widget,
    // adding CORS headers. The widget already understands this shape.
    const text = await upstream.text();
    return new Response(text, {
      status: upstream.status,
      headers: { ...cors, "Content-Type": "application/json" },
    });
  },
};

function originAllowed(origin, env) {
  const allow = (env.ALLOWED_ORIGIN || "").trim();
  if (!allow) return true;               // unset → allow all (testing only)
  if (!origin) return false;             // configured but no Origin header
  return allow.split(",").map((s) => s.trim()).includes(origin);
}

function corsHeaders(origin, env) {
  const allow = (env.ALLOWED_ORIGIN || "").trim();
  const allowOrigin = !allow ? "*" : (originAllowed(origin, env) ? origin : "");
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}
