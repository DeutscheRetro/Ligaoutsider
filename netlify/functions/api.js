// Einziger Schreibweg zur Datenbank.
//
// Der Browser darf ueber den anon-Key nur noch lesen. Jede Aenderung laeuft
// hier durch: Netlify prueft das Identity-JWT und legt den verifizierten User
// in context.clientContext.user. Identitaet und Rolle kommen also vom Server,
// nie aus dem Request-Body - vorher konnte der Client beides frei behaupten.
//
// Rollen werden im Netlify-Dashboard unter Identity am User gesetzt:
//   admin      - darf alles
//   moderator  - darf fremde Beitraege loeschen, bannen, Artikel ausblenden
//   (ohne)     - darf nur eigene Beitraege schreiben und aendern

const SUPABASE_URL = "https://rsodjlglzwlscamdlwev.supabase.co";
const SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY;

const json = (code, body) => ({
  statusCode: code,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

async function db(pfad, options = {}) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${pfad}`, {
    ...options,
    headers: {
      apikey: SERVICE_KEY,
      Authorization: `Bearer ${SERVICE_KEY}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`DB ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : null;
}

const hole = (pfad) => db(pfad);
const lege_an = (tabelle, daten) =>
  db(tabelle, { method: "POST", body: JSON.stringify(daten), headers: { Prefer: "return=representation" } });
const aendere = (tabelle, filter, daten) =>
  db(`${tabelle}?${filter}`, { method: "PATCH", body: JSON.stringify(daten) });
const loesche = (tabelle, filter) => db(`${tabelle}?${filter}`, { method: "DELETE" });

const sauber = (s, max) => String(s ?? "").replace(/<[^>]*>/g, "").trim().slice(0, max);

async function istGebannt(email) {
  const treffer = await hole(`user_bans?email=eq.${encodeURIComponent(email)}&select=gebannt_bis`);
  if (!treffer || !treffer.length) return false;
  const bis = treffer[0].gebannt_bis;
  return !bis || new Date(bis) > new Date();
}

exports.handler = async (event, context) => {
  if (event.httpMethod !== "POST") return json(405, { fehler: "Nur POST" });
  if (!SERVICE_KEY) return json(500, { fehler: "SUPABASE_SERVICE_KEY fehlt in den Netlify-Variablen" });

  const user = context.clientContext && context.clientContext.user;
  if (!user) return json(401, { fehler: "Nicht angemeldet" });

  const email = user.email;
  const name = (user.user_metadata && user.user_metadata.full_name) || email;
  const rollen = (user.app_metadata && user.app_metadata.roles) || [];
  const istAdmin = rollen.includes("admin");
  const darfLoeschen = istAdmin || rollen.includes("moderator");

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return json(400, { fehler: "Ungueltiges JSON" });
  }
  const { aktion } = body;

  try {
    switch (aktion) {
      // ─── Kommentare ────────────────────────────────────────────────────────
      case "kommentar_neu": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const inhalt = sauber(body.inhalt, 1000);
        const artikel_id = sauber(body.artikel_id, 64);
        if (!inhalt || !artikel_id) return json(400, { fehler: "Inhalt oder Artikel fehlt" });
        const [zeile] = await lege_an("kommentare", { artikel_id, name, email, inhalt });
        return json(200, { ok: true, id: zeile.id });
      }

      case "kommentar_edit": {
        const inhalt = sauber(body.inhalt, 1000);
        if (!inhalt || !body.id) return json(400, { fehler: "Inhalt oder ID fehlt" });
        const [k] = await hole(`kommentare?id=eq.${body.id}&select=email`);
        if (!k) return json(404, { fehler: "Kommentar nicht gefunden" });
        // Fremde Kommentare darf auch ein Moderator nicht umschreiben
        if (k.email !== email) return json(403, { fehler: "Nicht dein Kommentar" });
        await aendere("kommentare", `id=eq.${body.id}`, {
          inhalt,
          geaendert_am: new Date().toISOString(),
        });
        return json(200, { ok: true });
      }

      case "kommentar_loeschen": {
        if (!body.id) return json(400, { fehler: "ID fehlt" });
        const [k] = await hole(`kommentare?id=eq.${body.id}&select=email`);
        if (!k) return json(404, { fehler: "Kommentar nicht gefunden" });
        if (k.email !== email && !darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        if (body.hart && darfLoeschen) {
          await loesche("kommentare", `id=eq.${body.id}`);
        } else {
          await aendere("kommentare", `id=eq.${body.id}`, { geloescht: true, inhalt: "" });
        }
        return json(200, { ok: true });
      }

      case "vote": {
        const wert = Number(body.wert);
        if (![1, -1].includes(wert) || !body.kommentar_id) return json(400, { fehler: "Ungueltiger Vote" });
        const vorhanden = await hole(
          `kommentar_votes?kommentar_id=eq.${body.kommentar_id}&voter_email=eq.${encodeURIComponent(email)}&select=id,vote`
        );
        if (vorhanden && vorhanden.length) {
          if (vorhanden[0].vote === wert) await loesche("kommentar_votes", `id=eq.${vorhanden[0].id}`);
          else await aendere("kommentar_votes", `id=eq.${vorhanden[0].id}`, { vote: wert });
        } else {
          await lege_an("kommentar_votes", { kommentar_id: body.kommentar_id, voter_email: email, vote: wert });
        }
        return json(200, { ok: true });
      }

      // ─── Moderation ────────────────────────────────────────────────────────
      case "ban": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const ziel = sauber(body.email, 200);
        if (!ziel) return json(400, { fehler: "E-Mail fehlt" });
        await db("user_bans", {
          method: "POST",
          headers: { Prefer: "resolution=merge-duplicates" },
          body: JSON.stringify({
            email: ziel,
            grund: sauber(body.grund, 300) || null,
            gebannt_bis: body.gebannt_bis || null,
            gebannt_von: email,
          }),
        });
        return json(200, { ok: true });
      }

      case "unban": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const ziel = sauber(body.email, 200);
        if (!ziel) return json(400, { fehler: "E-Mail fehlt" });
        await loesche("user_bans", `email=eq.${encodeURIComponent(ziel)}`);
        return json(200, { ok: true });
      }

      // ─── Forum ─────────────────────────────────────────────────────────────
      case "forum_thread_neu": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const titel = sauber(body.titel, 200);
        const inhalt = sauber(body.inhalt, 5000);
        const kategorie = sauber(body.kategorie, 64);
        if (!titel || !inhalt || !kategorie) return json(400, { fehler: "Felder fehlen" });
        const [thread] = await lege_an("forum_threads", {
          kategorie, titel, autor_name: name, autor_email: email,
        });
        await lege_an("forum_posts", {
          thread_id: thread.id, inhalt, autor_name: name, autor_email: email,
        });
        return json(200, { ok: true, thread_id: thread.id });
      }

      case "forum_post_neu": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const inhalt = sauber(body.inhalt, 5000);
        if (!inhalt || !body.thread_id) return json(400, { fehler: "Felder fehlen" });
        await lege_an("forum_posts", {
          thread_id: body.thread_id, inhalt, autor_name: name, autor_email: email,
        });
        // Zaehler serverseitig fortschreiben, damit ihn niemand frei setzen kann
        const antworten = await hole(`forum_posts?thread_id=eq.${body.thread_id}&select=id`);
        await aendere("forum_threads", `id=eq.${body.thread_id}`, {
          letzter_beitrag: new Date().toISOString(),
          antworten: Math.max(0, (antworten || []).length - 1),
        });
        return json(200, { ok: true, antworten: Math.max(0, (antworten || []).length - 1) });
      }

      case "forum_post_loeschen": {
        if (!body.id) return json(400, { fehler: "ID fehlt" });
        const [p] = await hole(`forum_posts?id=eq.${body.id}&select=autor_email`);
        if (!p) return json(404, { fehler: "Beitrag nicht gefunden" });
        if (p.autor_email !== email && !darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        await loesche("forum_posts", `id=eq.${body.id}`);
        return json(200, { ok: true });
      }

      case "forum_thread_loeschen": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        if (!body.id) return json(400, { fehler: "ID fehlt" });
        await loesche("forum_posts", `thread_id=eq.${body.id}`);
        await loesche("forum_threads", `id=eq.${body.id}`);
        return json(200, { ok: true });
      }

      case "user_purge": {
        if (!istAdmin) return json(403, { fehler: "Nur Admin" });
        const ziel = sauber(body.email, 200);
        if (!ziel) return json(400, { fehler: "E-Mail fehlt" });
        const e = encodeURIComponent(ziel);
        await loesche("forum_posts", `autor_email=eq.${e}`);
        await loesche("forum_threads", `autor_email=eq.${e}`);
        await loesche("kommentare", `email=eq.${e}`);
        return json(200, { ok: true });
      }

      // ─── Artikel sofort ausblenden ─────────────────────────────────────────
      // Das eigentliche Loeschen passiert weiter ueber chefred und Git; bis der
      // naechste Build durch ist, filtert die Seite gegen diese Tabelle.
      case "artikel_ausblenden": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const aid = sauber(body.artikel_id, 64);
        if (!aid) return json(400, { fehler: "Artikel-ID fehlt" });
        await db("hidden_articles", {
          method: "POST",
          headers: { Prefer: "resolution=merge-duplicates" },
          body: JSON.stringify({ artikel_id: aid, versteckt_von: email }),
        });
        return json(200, { ok: true });
      }

      case "artikel_einblenden": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const aid = sauber(body.artikel_id, 64);
        if (!aid) return json(400, { fehler: "Artikel-ID fehlt" });
        await loesche("hidden_articles", `artikel_id=eq.${encodeURIComponent(aid)}`);
        return json(200, { ok: true });
      }

      // ─── Leser-Einsendungen ────────────────────────────────────────────────
      case "news_einsenden": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const url = String(body.url ?? "").trim().slice(0, 500);
        if (!/^https?:\/\/\S+$/i.test(url)) return json(400, { fehler: "Bitte gueltige URL eingeben" });
        await lege_an("submitted_urls", { url, eingereicht_von: email });
        return json(200, { ok: true });
      }

      case "wer_bin_ich":
        return json(200, { email, name, rollen, istAdmin, darfLoeschen });

      default:
        return json(400, { fehler: `Unbekannte Aktion: ${aktion}` });
    }
  } catch (e) {
    console.error("api-Fehler:", aktion, e.message);
    return json(500, { fehler: "Serverfehler" });
  }
};
