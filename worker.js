// Einstieg für Cloudflare: /api geht an die Funktion, alles andere sind statische Dateien
import { onRequest as api } from "./functions/api.js";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api") return api({ request, env });
    return env.ASSETS.fetch(request);
  },
};
