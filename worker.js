// Einstieg für Cloudflare: /api geht an die Funktion, alles andere sind statische Dateien.
// Dazu der Zeitplan der News-Pipeline: Cloudflare startet sie pünktlich über die
// GitHub-API (GitHubs eigene Zeitpläne kamen nachts mehrere Stunden zu spät).
import { onRequest as api } from "./functions/api.js";

// Berliner Zeit, jeden Tag gleich (wie ki_budget.LAUFPLAN_BERLIN)
const LAUFPLAN = ["01:00", "06:00", "08:00", "10:00", "12:00", "13:30", "15:00",
                  "16:30", "18:00", "19:30", "21:00", "23:00"];
const QUALITAET = ["12:00", "18:00"];   // danach prüft Opus die neuen Artikel

function berlinZeit(datum) {
  const t = new Intl.DateTimeFormat("de-DE", { timeZone: "Europe/Berlin", hour: "2-digit",
                                               minute: "2-digit", hour12: false }).format(datum);
  return t.replace(/^24/, "00");
}

async function workflowStarten(env, datei, inputs) {
  const res = await fetch(
    `https://api.github.com/repos/DeutscheRetro/Ligaoutsider/actions/workflows/${datei}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "ligaoutsider-zeitplan",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({ ref: "main", inputs }),
    });
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${(await res.text()).slice(0, 200)}`);
}

// Steht ein Bundesliga-Anpfiff in 20 bis 75 Minuten an (oder lief er vor höchstens 20)?
// Dann sind die offiziellen Aufstellungen gleich da bzw. schon raus.
async function anpfiffNah(jetzt) {
  const res = await fetch("https://api.openligadb.de/getmatchdata/bl1", { cf: { cacheTtl: 600, cacheEverything: true } });
  if (!res.ok) return false;
  const spiele = await res.json();
  return spiele.some(s => {
    const min = (new Date(s.matchDateTimeUTC) - jetzt) / 60000;
    return min >= -20 && min <= 75;
  });
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

// Lesezugriffe der Seiten laufen über die eigene Domain. Werbe- und Tracking-Blocker sperren
// sonst die Anfragen an supabase.co (fremde Domain), und Kommentare, Forum, Profile bleiben leer.
// Nur GET/HEAD auf die REST-Schnittstelle; Schreiben geht weiterhin über /api.
async function supabaseLesen(request, url) {
  if (request.method !== "GET" && request.method !== "HEAD")
    return new Response("Nur lesen", { status: 405 });
  const ziel = "https://rsodjlglzwlscamdlwev.supabase.co" + url.pathname.slice(3) + url.search;
  const kopf = new Headers();
  for (const k of ["apikey", "authorization", "accept", "range", "accept-profile", "prefer"]) {
    const v = request.headers.get(k);
    if (v) kopf.set(k, v);
  }
  const res = await fetch(ziel, { method: request.method, headers: kopf });
  const antwort = new Response(res.body, res);
  antwort.headers.set("Cache-Control", "no-store");
  return antwort;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // Nur https ausliefern: http-Aufrufe dauerhaft umleiten (sonst gibt es jede Seite doppelt)
    if (url.protocol === "http:" && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/api") return api({ request, env });
    if (url.pathname.startsWith("/sb/rest/v1/")) return supabaseLesen(request, url);
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
    if (!env.GH_DISPATCH_TOKEN) {
      console.error("GH_DISPATCH_TOKEN fehlt – nichts gestartet");
      return;
    }
    const jetzt = new Date(event.scheduledTime);
    const zeit = berlinZeit(jetzt);
    // News-Pipeline zu den festen Zeiten (Cron läuft alle 15 Minuten, nur volle/halbe Planzeiten zählen)
    if (LAUFPLAN.includes(zeit)) {
      ctx.waitUntil(laufStarten(env, zeit).then(
        () => console.log(`Lauf ${zeit} gestartet`),
        (e) => console.error(`Lauf ${zeit} nicht gestartet: ${e.message}`)));
    }
    // Offizielle Aufstellungen kurz vor dem Anpfiff
    ctx.waitUntil(anpfiffNah(jetzt).then(nah => nah && workflowStarten(env, "aufstellungen.yml", { reason: `Anpfiff nah ${zeit}` })
      .then(() => console.log(`Aufstellungen ${zeit} gestartet`)))
      .catch(e => console.error(`Aufstellungen ${zeit}: ${e.message}`)));
  },
};
