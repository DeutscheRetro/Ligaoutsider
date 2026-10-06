// Einstieg für Cloudflare: /api geht an die Funktion, alles andere sind statische Dateien.
// Dazu der Zeitplan der News-Pipeline: Cloudflare startet sie pünktlich über die
// GitHub-API (GitHubs eigene Zeitpläne kamen nachts mehrere Stunden zu spät).
import { onRequest as api } from "./functions/api.js";

// Berliner Zeit, jeden Tag gleich (wie ki_budget.LAUFPLAN_BERLIN)
const LAUFPLAN = ["11:00", "01:00", "06:00", "08:00", "10:00", "12:00", "13:30", "15:00",
                  "16:30", "18:00", "19:30", "21:00", "23:00"];
const QUALITAET = ["12:00", "18:00"];   // danach prüft Opus die neuen Artikel

function berlinZeit(datum) {
  const t = new Intl.DateTimeFormat("de-DE", { timeZone: "Europe/Berlin", hour: "2-digit",
                                               minute: "2-digit", hour12: false }).format(datum);
  return t.replace(/^24/, "00");
}

async function laufStarten(env, zeit) {
  const res = await fetch(
    "https://api.github.com/repos/DeutscheRetro/Ligaoutsider/actions/workflows/update.yml/dispatches", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "ligaoutsider-zeitplan",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs: {
        reason: `Zeitplan ${zeit}`,
        qualitaet: QUALITAET.includes(zeit) ? "true" : "false",
      } }),
    });
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${(await res.text()).slice(0, 200)}`);
}

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

  // Cron-Trigger alle 30 Minuten (UTC); gestartet wird nur zu den Berliner Planzeiten.
  // So stimmt der Plan auch nach der Zeitumstellung, ohne die Cron-Zeiten anzufassen.
  async scheduled(event, env, ctx) {
    const zeit = berlinZeit(new Date(event.scheduledTime));
    if (!LAUFPLAN.includes(zeit)) return;
    if (!env.GH_DISPATCH_TOKEN) {
      console.error("GH_DISPATCH_TOKEN fehlt – Lauf nicht gestartet");
      return;
    }
    ctx.waitUntil(laufStarten(env, zeit).then(
      () => console.log(`Lauf ${zeit} gestartet`),
      (e) => console.error(`Lauf ${zeit} nicht gestartet: ${e.message}`)));
  },
};
