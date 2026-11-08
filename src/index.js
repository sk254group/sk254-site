// SK254 store backend: product data, photo uploads, admin login.
import seed from "./seed.json";

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

const enc = new TextEncoder();
async function hmac(secret, msg) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function sameText(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}
async function makeToken(env) {
  const exp = Date.now() + 30 * 24 * 3600 * 1000; // 30 days
  return exp + "." + (await hmac(env.ADMIN_PASSWORD, "sk254-admin." + exp));
}
async function isAdmin(req, env) {
  if (!env.ADMIN_PASSWORD) return false;
  const t = (req.headers.get("authorization") || "").replace(/^Bearer\s+/, "");
  const [exp, sig] = t.split(".");
  if (!exp || !sig || +exp < Date.now()) return false;
  return sameText(sig, await hmac(env.ADMIN_PASSWORD, "sk254-admin." + exp));
}

async function getStore(env) {
  return (await env.KV.get("store", "json")) || seed;
}

async function saveImage(env, bytes, type) {
  const id = crypto.randomUUID().replace(/-/g, "");
  await env.KV.put("img:" + id, bytes, { metadata: { type } });
  return "/img/" + id;
}

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname;

    // Public: store data
    if (path === "/api/store" && req.method === "GET") return json(await getStore(env));

    // Public: product photos
    if (path.startsWith("/img/") && req.method === "GET") {
      const cache = caches.default;
      const hit = await cache.match(req);
      if (hit) return hit;
      const { value, metadata } = await env.KV.getWithMetadata("img:" + path.slice(5), "arrayBuffer");
      if (!value) return new Response("Not found", { status: 404 });
      const res = new Response(value, {
        headers: { "content-type": metadata?.type || "image/jpeg", "cache-control": "public, max-age=31536000, immutable" },
      });
      ctx.waitUntil(cache.put(req, res.clone()));
      return res;
    }

    // Admin login
    if (path === "/api/login" && req.method === "POST") {
      if (!env.ADMIN_PASSWORD) return json({ error: "Admin password is not set up yet." }, 503);
      const { password } = await req.json().catch(() => ({}));
      if (typeof password === "string" && sameText(password, env.ADMIN_PASSWORD)) return json({ token: await makeToken(env) });
      await new Promise((r) => setTimeout(r, 900)); // slow down guessing
      return json({ error: "Wrong password" }, 401);
    }

    if (path.startsWith("/api/")) {
      if (!(await isAdmin(req, env))) return json({ error: "Please log in again." }, 401);

      // Save whole store
      if (path === "/api/store" && req.method === "PUT") {
        const text = await req.text();
        if (text.length > 2_000_000) return json({ error: "Too big" }, 413);
        let data;
        try { data = JSON.parse(text); } catch { return json({ error: "Bad data" }, 400); }
        if (!data || !Array.isArray(data.products) || !Array.isArray(data.categories) || typeof data.settings !== "object")
          return json({ error: "Bad data" }, 400);
        await env.KV.put("store", JSON.stringify(data));
        return json({ ok: true });
      }

      // Upload a photo
      if (path === "/api/upload" && req.method === "POST") {
        const type = (req.headers.get("content-type") || "").split(";")[0];
        if (!IMAGE_TYPES.includes(type)) return json({ error: "Photos only (JPG, PNG, WebP)" }, 415);
        const bytes = await req.arrayBuffer();
        if (bytes.byteLength > 8_000_000) return json({ error: "Photo too big" }, 413);
        return json({ url: await saveImage(env, bytes, type) });
      }

      // Copy photos still hosted on Take.app into our own storage
      if (path === "/api/import-images" && req.method === "POST") {
        const store = await getStore(env);
        let moved = 0, failed = 0;
        const move = async (src) => {
          if (!src || src.startsWith("/img/")) return src;
          if (moved + failed >= 40) return src; // stay under per-request limits; run again for the rest
          try {
            const r = await fetch(src);
            const type = (r.headers.get("content-type") || "").split(";")[0];
            if (!r.ok || !IMAGE_TYPES.includes(type)) throw new Error("bad");
            const url = await saveImage(env, await r.arrayBuffer(), type);
            moved++;
            return url;
          } catch { failed++; return src; }
        };
        for (const p of store.products) p.imgs = await Promise.all((p.imgs || []).map(move));
        store.settings.logo = await move(store.settings.logo);
        store.settings.customImg = await move(store.settings.customImg);
        await env.KV.put("store", JSON.stringify(store));
        const left = [...store.products.flatMap((p) => p.imgs), store.settings.logo, store.settings.customImg]
          .filter((s) => s && !s.startsWith("/img/")).length;
        return json({ moved, failed, left, store });
      }

      return json({ error: "Not found" }, 404);
    }

    return env.ASSETS.fetch(req);
  },
};
