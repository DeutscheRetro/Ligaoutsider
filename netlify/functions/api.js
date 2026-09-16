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

// Die Konten selbst liegen bei Netlify Identity, nicht bei uns. Ohne Token
// faellt die Nutzerliste auf das zurueck, was wir aus eigenen Daten kennen.
const NETLIFY_TOKEN = process.env.NETLIFY_AUTH_TOKEN;
const NETLIFY_SITE = "cb939f1a-0538-4e1d-ad3d-9ca81bed209a";
const NETLIFY_IDENTITY = "6a467b53e81902b5ccd77424";

async function netlifyIdentityApi(pfad, options = {}) {
  if (!NETLIFY_TOKEN) return null;
  const res = await fetch(
    `https://api.netlify.com/api/v1/sites/${NETLIFY_SITE}/identity/${NETLIFY_IDENTITY}${pfad}`,
    { ...options, headers: { Authorization: `Bearer ${NETLIFY_TOKEN}`,
                             "Content-Type": "application/json",
                             ...(options.headers || {}) } });
  if (!res.ok) throw new Error(`Netlify ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

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

// Rollen kommen aus der Datenbank und zusaetzlich aus dem Identity-Token.
// Die Vereinigung beider Quellen sorgt dafuer, dass niemand ausgesperrt wird,
// wenn eine Seite leer ist - und dass Aenderungen in der Datenbank sofort
// greifen, statt erst nach einem erneuten Login.
async function rollenVon(email, tokenRollen) {
  let ausDb = [];
  try {
    const treffer = await hole(
      `benutzer_rollen?email=eq.${encodeURIComponent(email)}&select=rollen`);
    if (treffer && treffer.length) ausDb = treffer[0].rollen || [];
  } catch (e) {
    console.error("Rollen konnten nicht geladen werden:", e.message);
  }
  return [...new Set([...(tokenRollen || []), ...ausDb])];
}

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
  const rollen = await rollenVon(email, (user.app_metadata || {}).roles);
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

      // ─── Nutzerverwaltung ──────────────────────────────────────────────────
      case "nutzer_liste": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        // Die Konten selbst liegen bei Netlify Identity. Ohne Netlify-Token
        // stellen wir die Liste aus dem zusammen, was wir selbst kennen:
        // Kommentatoren, Forenautoren, vergebene Rollen und Sperren.
        const [kommentare, threads, posts, rollenZeilen, bans] = await Promise.all([
          hole("kommentare?select=name,email,erstellt_am"),
          hole("forum_threads?select=autor_name,autor_email,erstellt_am"),
          hole("forum_posts?select=autor_name,autor_email,erstellt_am"),
          hole("benutzer_rollen?select=email,rollen,notiz,geaendert_am"),
          hole("user_bans?select=email,grund,gebannt_bis"),
        ]);

        const leute = {};
        const eintrag = (mail) => {
          const e = String(mail || "").toLowerCase();
          if (!e) return null;
          if (!leute[e]) leute[e] = { email: e, name: e, kommentare: 0, threads: 0,
                                      posts: 0, letzte_aktivitaet: null, rollen: [],
                                      notiz: "", gebannt: false };
          return leute[e];
        };
        const zaehle = (mail, anzeige, datum, feld) => {
          const p = eintrag(mail);
          if (!p) return;
          if (anzeige) p.name = anzeige;
          p[feld]++;
          if (datum && (!p.letzte_aktivitaet || datum > p.letzte_aktivitaet))
            p.letzte_aktivitaet = datum;
        };
        (kommentare || []).forEach(k => zaehle(k.email, k.name, k.erstellt_am, "kommentare"));
        (threads || []).forEach(t => zaehle(t.autor_email, t.autor_name, t.erstellt_am, "threads"));
        (posts || []).forEach(p => zaehle(p.autor_email, p.autor_name, p.erstellt_am, "posts"));

        // Auch wer nur eine Rolle oder eine Sperre hat, gehoert in die Liste
        (rollenZeilen || []).forEach(r => {
          const p = eintrag(r.email);
          if (p) { p.rollen = r.rollen || []; p.notiz = r.notiz || ""; }
        });
        (bans || []).forEach(b => {
          const p = eintrag(b.email);
          if (p) {
            p.gebannt = !b.gebannt_bis || new Date(b.gebannt_bis) > new Date();
            p.ban_grund = b.grund || "";
            p.ban_bis = b.gebannt_bis;
          }
        });

        // Registrierte Konten von Netlify dazunehmen, damit auch stille
        // Mitglieder auftauchen und nicht nur, wer schon geschrieben hat.
        let kontenQuelle = "nur eigene Daten";
        try {
          // Netlify erlaubt hoechstens 500 pro Seite und blaettert danach
          const konten = [];
          for (let seite = 1; seite <= 10; seite++) {
            const teil = await netlifyIdentityApi(`/users?per_page=500&page=${seite}`);
            const zeilen = Array.isArray(teil) ? teil : (teil && teil.users) || [];
            konten.push(...zeilen);
            if (zeilen.length < 500) break;
          }
          if (NETLIFY_TOKEN) {
            kontenQuelle = "Netlify";
            konten.forEach(k => {
              const p = eintrag(k.email);
              if (!p) return;
              p.konto_id = k.id;
              p.registriert = k.created_at;
              p.bestaetigt = !!k.confirmed_at;
              p.letzter_login = k.last_login_at || null;
              const anzeige = (k.user_metadata || {}).full_name;
              if (anzeige && p.name === p.email) p.name = anzeige;
            });
          }
        } catch (e) {
          console.error("Netlify-Konten nicht abrufbar:", e.message);
          kontenQuelle = "Netlify-Abruf fehlgeschlagen";
        }

        const liste = Object.values(leute);
        liste.sort((a, b) =>
          (b.letzte_aktivitaet || b.registriert || "").localeCompare(
            a.letzte_aktivitaet || a.registriert || ""));
        return json(200, { nutzer: liste, quelle: kontenQuelle });
      }

      case "konto_loeschen": {
        if (!istAdmin) return json(403, { fehler: "Nur Admin" });
        const ziel = sauber(body.email, 200).toLowerCase();
        if (!ziel) return json(400, { fehler: "E-Mail fehlt" });
        if (ziel === email.toLowerCase())
          return json(400, { fehler: "Du kannst dein eigenes Konto hier nicht loeschen" });
        if (!NETLIFY_TOKEN)
          return json(400, { fehler: "Ohne NETLIFY_AUTH_TOKEN koennen Konten nicht geloescht werden" });
        if (!body.konto_id) return json(400, { fehler: "Konto-ID fehlt" });
        // Erst Inhalte, dann das Konto - sonst bleiben verwaiste Beitraege
        const e2 = encodeURIComponent(ziel);
        await loesche("forum_posts", `autor_email=eq.${e2}`);
        await loesche("forum_threads", `autor_email=eq.${e2}`);
        await loesche("kommentare", `email=eq.${e2}`);
        await loesche("benutzer_rollen", `email=eq.${e2}`);
        await netlifyIdentityApi(`/users/${body.konto_id}`, { method: "DELETE" });
        return json(200, { ok: true });
      }

      case "rolle_setzen": {
        if (!istAdmin) return json(403, { fehler: "Nur Admin" });
        const ziel = sauber(body.email, 200).toLowerCase();
        if (!ziel) return json(400, { fehler: "E-Mail fehlt" });
        const erlaubt = ["admin", "moderator"];
        const neue = (Array.isArray(body.rollen) ? body.rollen : [])
          .map(r => String(r).trim().toLowerCase())
          .filter(r => erlaubt.includes(r));
        // Wer sich selbst die Adminrolle nimmt, sperrt sich aus
        if (ziel === email.toLowerCase() && !neue.includes("admin"))
          return json(400, { fehler: "Du kannst dir die Adminrolle nicht selbst entziehen" });
        await db("benutzer_rollen", {
          method: "POST",
          headers: { Prefer: "resolution=merge-duplicates" },
          body: JSON.stringify({
            email: ziel, rollen: neue, notiz: sauber(body.notiz, 200) || null,
            geaendert_am: new Date().toISOString(), geaendert_von: email,
          }),
        });
        return json(200, { ok: true, rollen: neue });
      }

      // ─── Direktnachrichten ─────────────────────────────────────────────────
      case "nachricht_senden": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const an = sauber(body.an, 200).toLowerCase();
        const inhalt = sauber(body.inhalt, 2000);
        if (!an || !inhalt) return json(400, { fehler: "Empfaenger oder Text fehlt" });
        if (an === email.toLowerCase()) return json(400, { fehler: "Nicht an dich selbst" });
        // Flut bremsen: hoechstens 20 Nachrichten in 10 Minuten
        const grenze = new Date(Date.now() - 10 * 60 * 1000).toISOString();
        const letzte = await hole(
          `nachrichten?von_email=eq.${encodeURIComponent(email)}&erstellt_am=gt.${grenze}&select=id`);
        if ((letzte || []).length >= 20)
          return json(429, { fehler: "Zu viele Nachrichten. Bitte kurz warten." });
        await lege_an("nachrichten", { von_email: email, von_name: name, an_email: an, inhalt });
        return json(200, { ok: true });
      }

      case "postfach": {
        const alle = await hole(
          `nachrichten?or=(von_email.eq.${encodeURIComponent(email)},an_email.eq.${encodeURIComponent(email)})` +
          `&order=erstellt_am.desc&limit=500`);
        const meine = (alle || []).filter(n => !(n.geloescht_von || []).includes(email));
        // Nach Gespraechspartner buendeln
        const gespraeche = {};
        for (const n of meine) {
          const partner = n.von_email === email ? n.an_email : n.von_email;
          if (!gespraeche[partner]) {
            gespraeche[partner] = {
              partner,
              partner_name: n.von_email === email ? partner : n.von_name,
              letzte: n.inhalt, letzte_am: n.erstellt_am, ungelesen: 0, nachrichten: [],
            };
          }
          if (n.an_email === email && !n.gelesen) gespraeche[partner].ungelesen++;
          gespraeche[partner].nachrichten.push({
            id: n.id, von: n.von_email, name: n.von_name,
            inhalt: n.inhalt, am: n.erstellt_am, gelesen: n.gelesen,
          });
        }
        const liste = Object.values(gespraeche);
        liste.forEach(g => g.nachrichten.reverse());
        liste.sort((a, b) => (b.letzte_am || "").localeCompare(a.letzte_am || ""));
        return json(200, {
          gespraeche: liste,
          ungelesen: liste.reduce((s, g) => s + g.ungelesen, 0),
        });
      }

      case "nachrichten_gelesen": {
        const partner = sauber(body.partner, 200).toLowerCase();
        if (!partner) return json(400, { fehler: "Partner fehlt" });
        await aendere("nachrichten",
          `an_email=eq.${encodeURIComponent(email)}&von_email=eq.${encodeURIComponent(partner)}&gelesen=is.false`,
          { gelesen: true });
        return json(200, { ok: true });
      }

      case "gespraech_loeschen": {
        const partner = sauber(body.partner, 200).toLowerCase();
        if (!partner) return json(400, { fehler: "Partner fehlt" });
        // Nur fuer einen selbst ausblenden, der andere behaelt seinen Verlauf
        const betroffen = await hole(
          `nachrichten?or=(and(von_email.eq.${encodeURIComponent(email)},an_email.eq.${encodeURIComponent(partner)}),` +
          `and(von_email.eq.${encodeURIComponent(partner)},an_email.eq.${encodeURIComponent(email)}))&select=id,geloescht_von`);
        for (const n of betroffen || []) {
          const markiert = new Set(n.geloescht_von || []);
          markiert.add(email);
          await aendere("nachrichten", `id=eq.${n.id}`, { geloescht_von: [...markiert] });
        }
        return json(200, { ok: true, betroffen: (betroffen || []).length });
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
