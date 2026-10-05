// Einstieg für Cloudflare: /api geht an die Funktion, alles andere sind statische Dateien
import { onRequest as api } from "./functions/api.js";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api") return api({ request, env });
    // Ordneradressen ("/", "/spieler/") zeigen ihre index.html – mit html_handling
    // "none" macht Cloudflare das nicht von selbst
    if (url.pathname.endsWith("/")) {
      url.pathname += "index.html";
      return env.ASSETS.fetch(new Request(url, request));
    }
    return env.ASSETS.fetch(request);
  },
};
