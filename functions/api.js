// Einziger Schreibweg zur Datenbank (Cloudflare Pages Function, erreichbar unter /api).
//
// Der Browser darf über den anon-Key nur lesen. Jede Änderung läuft hier durch:
// Die Funktion prüft das Supabase-Anmeldetoken direkt bei Supabase Auth.
// Identität und Rolle kommen also vom Server, nie aus dem Request-Body.
//
// Rollen stehen in der Tabelle benutzer_rollen:
//   admin      - darf alles
//   moderator  - darf fremde Beiträge löschen, bannen, Artikel ausblenden
//   (ohne)     - darf nur eigene Beiträge schreiben und ändern
//
// Umgebungsvariable im Cloudflare-Dashboard: SUPABASE_SERVICE_KEY

const SUPABASE_URL = "https://rsodjlglzwlscamdlwev.supabase.co";
let SERVICE_KEY = "";   // pro Anfrage aus env gesetzt
const UUID = /^[0-9a-f-]{36}$/i;

// Konten verwalten (Liste, Löschen) über die Admin-Schnittstelle von Supabase Auth
async function authAdmin(pfad, options = {}) {
  const res = await fetch(`${SUPABASE_URL}/auth/v1/admin${pfad}`, {
    ...options,
    headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}`,
               "Content-Type": "application/json", ...(options.headers || {}) } });
  const text = await res.text();
  if (!res.ok) throw new Error(`Auth ${res.status}: ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

const json = (code, body) => new Response(JSON.stringify(body), {
  status: code,
  headers: { "Content-Type": "application/json" },
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

// Wen meint eine Moderationsaktion? Der Browser kennt keine fremden E-Mail-Adressen mehr,
// sondern nur Kommentar-ID oder Profilnamen; die Adresse wird hier aufgelöst.
async function zielEmail(body) {
  if (body.kommentar_id && UUID.test(String(body.kommentar_id))) {
    const [k] = await hole(`kommentare?id=eq.${body.kommentar_id}&select=email`);
    if (k) return k.email;
  }
  if (body.handle && /^[a-z0-9-]{3,30}$/.test(String(body.handle))) {
    const [p] = await hole(`profile?handle=eq.${encodeURIComponent(body.handle)}&select=email`);
    if (p) return p.email;
  }
  return sauber(body.email, 200) || null;
}

async function banVon(mail) {
  const [b] = await hole(`user_bans?email=eq.${encodeURIComponent(mail)}&select=gebannt_bis,grund`);
  if (!b || (b.gebannt_bis && new Date(b.gebannt_bis) < new Date())) return null;
  return { gebannt_bis: b.gebannt_bis, grund: b.grund || null };
}

// ─── Profile ─────────────────────────────────────────────────────────────────
// Öffentlich zeigt sich jeder Nutzer nur unter seinem Profilnamen (handle).
// Die E-Mail verlässt den Server nie in Richtung fremder Nutzer.
const HANDLE = /^[a-z0-9-]{3,30}$/;
const LIEBLINGS_FELDER = ["verein", "spieler", "stadion", "trainer", "film", "serie", "musik", "song",
  "buch", "game", "essen", "getraenk", "reiseziel", "sport"];

function handleAus(text) {
  let h = String(text || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase()
    .replace(/ß/g, "ss").replace(/@.*$/, "").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 26);
  if (h.length < 3) h = ("fan-" + h).replace(/-+$/, "") || "fan";
  return h.length < 3 ? "fan-" + Math.random().toString(36).slice(2, 6) : h;
}

// Liefert das Profil, legt es beim ersten Mal an. Gibt null zurück, wenn die
// Profiltabelle (noch) nicht existiert – dann laufen Kommentare trotzdem.
async function profilSicher(email, name) {
  try {
    const da = await hole(`profile?email=eq.${encodeURIComponent(email)}&select=handle,anzeigename`);
    if (da && da.length) return da[0];
    const basis = handleAus(name && name !== email ? name : email);
    for (let i = 0; i < 20; i++) {
      const versuch = i ? `${basis.slice(0, 26)}-${i + 1}` : basis;
      const belegt = await hole(`profile?handle=eq.${encodeURIComponent(versuch)}&select=handle`);
      if (belegt && belegt.length) continue;
      // Anzeigename muss einmalig sein: bei Gleichstand eine Zahl anhängen
      let anzeige = sauber(name && name !== email ? name : versuch, 56) || versuch;
      for (let n = 2; await nameVergeben(anzeige, email) && n < 50; n++) anzeige = `${sauber(name, 52) || versuch} ${n}`;
      const [neu] = await lege_an("profile", { email, handle: versuch, anzeigename: anzeige });
      return { handle: neu.handle, anzeigename: neu.anzeigename };
    }
  } catch (e) {
    console.error("Profil nicht verfügbar:", e.message);
  }
  return null;
}

const BENUTZERNAME = /^[\p{L}\p{N}][\p{L}\p{N} ._-]{1,28}[\p{L}\p{N}]$/u;

// Nur über Google angemeldet (kein E-Mail-Konto mit selbst gewähltem Namen)?
function nurGoogle(user) {
  const am = user.app_metadata || {};
  const p = am.providers || [am.provider];
  return p.includes("google") && !p.includes("email");
}

// ilike ohne Platzhalter: prüft Gleichheit ohne Rücksicht auf Groß-/Kleinschreibung
const ilikeGenau = t => encodeURIComponent(String(t).replace(/[\\%_]/g, m => "\\" + m));
async function nameVergeben(anzeigename, ausserEmail) {
  const t = await hole(`profile?anzeigename=ilike.${ilikeGenau(anzeigename)}&select=email`);
  return (t || []).some(p => p.email !== ausserEmail);
}

async function emailVonHandle(handle) {
  const h = String(handle || "").toLowerCase();
  if (!HANDLE.test(h)) return null;
  const t = await hole(`profile?handle=eq.${encodeURIComponent(h)}&select=email,handle,anzeigename,gaestebuch_offen`);
  return t && t.length ? t[0] : null;
}

// Blockiert einer von beiden den anderen?
async function blockiertZwischen(a, b) {
  const A = encodeURIComponent(a), B = encodeURIComponent(b);
  const t = await hole(`blockierungen?or=(and(blocker_email.eq.${A},blockiert_email.eq.${B}),` +
    `and(blocker_email.eq.${B},blockiert_email.eq.${A}))&select=blocker_email`);
  return (t || []).map(x => x.blocker_email);
}

async function handlesVon(emails) {
  const liste = [...new Set(emails)].filter(Boolean);
  if (!liste.length) return {};
  const t = await hole(`profile?email=in.(${liste.map(e => `"${encodeURIComponent(e)}"`).join(",")})&select=email,handle,anzeigename`);
  return Object.fromEntries((t || []).map(p => [p.email, p]));
}

// ─── Community-Stats (öffentlich, ohne E-Mail-Adressen) ─────────────────────
async function communityStats() {
  const [komm, votes, profile, threads, posts] = await Promise.all([
    hole("kommentare?select=id,artikel_id,email,name,autor_handle,inhalt,erstellt_am&geloescht=is.false&limit=20000"),
    hole("kommentar_votes?select=kommentar_id,vote&limit=50000"),
    hole("profile?select=email,handle,anzeigename,lieblings,erstellt_am&limit=20000"),
    hole("forum_threads?select=id&limit=20000").catch(() => []),
    hole("forum_posts?select=id&limit=50000").catch(() => []),
  ]);
  const prof = Object.fromEntries((profile || []).map(p => [String(p.email).toLowerCase(), p]));
  const person = mail => {
    const p = prof[String(mail || "").toLowerCase()];
    return p ? { name: p.anzeigename || p.handle, handle: p.handle } : null;
  };
  const proKomm = {};
  (votes || []).forEach(v => {
    const z = proKomm[v.kommentar_id] = proKomm[v.kommentar_id] || { up: 0, down: 0 };
    v.vote === 1 ? z.up++ : z.down++;
  });
  const leute = {};
  const wochentag = [0, 0, 0, 0, 0, 0, 0], stunde = new Array(24).fill(0), artikel = {};
  (komm || []).forEach(k => {
    const p = person(k.email) || { name: k.name, handle: k.autor_handle || null };
    const key = p.handle || p.name;
    const l = leute[key] = leute[key] || { ...p, kommentare: 0, up: 0, down: 0 };
    const v = proKomm[k.id] || { up: 0, down: 0 };
    l.kommentare++; l.up += v.up; l.down += v.down;
    const d = new Date(k.erstellt_am);
    const berlin = new Date(d.toLocaleString("en-US", { timeZone: "Europe/Berlin" }));
    wochentag[(berlin.getDay() + 6) % 7]++; stunde[berlin.getHours()]++;
    artikel[k.artikel_id] = (artikel[k.artikel_id] || 0) + 1;
  });
  const L = Object.values(leute);
  const top = (arr, f, n = 10) => arr.filter(x => f(x) > 0).sort((a, b) => f(b) - f(a)).slice(0, n);
  const kommentarListe = (komm || []).map(k => ({
    id: k.id, artikel_id: k.artikel_id, text: String(k.inhalt || "").slice(0, 160), datum: k.erstellt_am,
    autor: person(k.email) || { name: k.name, handle: k.autor_handle || null }, ...(proKomm[k.id] || { up: 0, down: 0 }) }));
  const fans = {};
  (profile || []).forEach(p => { const v = (p.lieblings || {}).verein; if (v) fans[v] = (fans[v] || 0) + 1; });
  const mitglieder = (profile || []).filter(p => p.erstellt_am)
    .sort((a, b) => a.erstellt_am.localeCompare(b.erstellt_am))
    .map(p => ({ name: p.anzeigename || p.handle, handle: p.handle, seit: p.erstellt_am }));
  return {
    stand: new Date().toISOString(),
    meiste_kommentare: top(L, x => x.kommentare).map(x => ({ ...x, wert: x.kommentare })),
    meiste_upvotes: top(L, x => x.up).map(x => ({ ...x, wert: x.up })),
    meiste_downvotes: top(L, x => x.down).map(x => ({ ...x, wert: x.down })),
    bester_saldo: top(L.filter(x => x.up + x.down >= 3), x => x.up - x.down).map(x => ({ ...x, wert: x.up - x.down })),
    beste_quote: L.filter(x => x.up + x.down >= 5).map(x => ({ ...x, wert: Math.round(100 * x.up / (x.up + x.down)) }))
      .sort((a, b) => b.wert - a.wert || (b.up + b.down) - (a.up + a.down)).slice(0, 10),
    top_kommentare: top(kommentarListe, k => k.up, 5),
    kontrovers: kommentarListe.filter(k => k.up >= 2 && k.down >= 2)
      .sort((a, b) => Math.min(b.up, b.down) - Math.min(a.up, a.down) || (b.up + b.down) - (a.up + a.down)).slice(0, 5),
    meistdiskutiert: Object.entries(artikel).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([id, n]) => ({ artikel_id: id, wert: n })),
    fans: Object.entries(fans).sort((a, b) => b[1] - a[1]).map(([verein, n]) => ({ verein, wert: n })),
    dienstaelteste: mitglieder.slice(0, 10),
    neu_dabei: mitglieder.slice(-5).reverse(),
    wochentag, stunde,
  };
}

export async function onRequest({ request, env }) {
  SERVICE_KEY = env.SUPABASE_SERVICE_KEY || "";
  // Öffentlich lesbar: Profilbilder zu Profilnamen (für Kommentare), nur diese eine Angabe
  if (request.method === "GET" && new URL(request.url).searchParams.has("community")) {
    if (!SERVICE_KEY) return json(500, { fehler: "SUPABASE_SERVICE_KEY fehlt" });
    try {
      return new Response(JSON.stringify(await communityStats()), { status: 200,
        headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=300" } });
    } catch (e) { return json(500, { fehler: "Stats nicht verfügbar" }); }
  }
  if (request.method === "GET") {
    const roh = new URL(request.url).searchParams.get("avatare") || "";
    const handles = [...new Set(roh.split(",").map(h => h.trim().toLowerCase()).filter(h => HANDLE.test(h)))].slice(0, 60);
    if (!SERVICE_KEY || !handles.length) return json(200, {});
    try {
      const zeilen = await hole(`profile?handle=in.(${handles.map(h => `"${h}"`).join(",")})&select=handle,lieblings`);
      const aus = {};
      (zeilen || []).forEach(z => { if (z.lieblings && z.lieblings.avatar) aus[z.handle] = z.lieblings.avatar; });
      return new Response(JSON.stringify(aus), { status: 200,
        headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=60" } });
    } catch (e) { return json(200, {}); }
  }
  if (request.method !== "POST") return json(405, { fehler: "Nur POST oder GET" });
  if (!SERVICE_KEY) return json(500, { fehler: "SUPABASE_SERVICE_KEY fehlt in den Cloudflare-Variablen" });

  // Anmeldetoken bei Supabase prüfen – gefälschte oder abgelaufene Tokens fallen hier durch
  const token = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  if (!token) return json(401, { fehler: "Nicht angemeldet" });
  const pruef = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { apikey: SERVICE_KEY, Authorization: `Bearer ${token}` } });
  if (!pruef.ok) return json(401, { fehler: "Nicht angemeldet" });
  const user = await pruef.json();
  if (!user || !user.email) return json(401, { fehler: "Nicht angemeldet" });

  const email = user.email;
  const meta = user.user_metadata || {};
  // Wer nur über Google angemeldet ist, wählt zuerst einen Benutzernamen –
  // der echte Name aus dem Google-Konto wird nie angezeigt
  const nameOffen = nurGoogle(user) && !meta.benutzername;
  const name = meta.benutzername || (nameOffen ? null : meta.full_name) || email;
  const rollen = await rollenVon(email, (user.app_metadata || {}).roles);
  const istAdmin = rollen.includes("admin");
  const darfLoeschen = istAdmin || rollen.includes("moderator");

  let body;
  try {
    body = JSON.parse((await request.text()) || "{}");
  } catch {
    return json(400, { fehler: "Ungueltiges JSON" });
  }
  const { aktion } = body;
  if (nameOffen && !["wer_bin_ich", "name_waehlen"].includes(aktion))
    return json(403, { fehler: "Bitte wähle zuerst deinen Benutzernamen" });

  try {
    switch (aktion) {
      // ─── Kommentare ────────────────────────────────────────────────────────
      case "kommentar_neu": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const inhalt = sauber(body.inhalt, 1000);
        const artikel_id = sauber(body.artikel_id, 64);
        if (!inhalt || !artikel_id) return json(400, { fehler: "Inhalt oder Artikel fehlt" });
        const profil = await profilSicher(email, name);
        const [zeile] = await lege_an("kommentare", { artikel_id, name, email, inhalt,
          ...(profil ? { autor_handle: profil.handle } : {}) });
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
        if (![1, -1].includes(wert) || !body.kommentar_id || !UUID.test(String(body.kommentar_id))) return json(400, { fehler: "Ungueltiger Vote" });
        const ziel = await hole(`kommentare?id=eq.${body.kommentar_id}&select=email`);
        if (!ziel || !ziel.length) return json(404, { fehler: "Kommentar nicht gefunden" });
        if (ziel[0].email === email) return json(403, { fehler: "Eigene Kommentare kannst du nicht bewerten" });
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
        const ziel = await zielEmail(body);
        if (!ziel) return json(400, { fehler: "Nutzer nicht gefunden" });
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
        const ziel = await zielEmail(body);
        if (!ziel) return json(400, { fehler: "Nutzer nicht gefunden" });
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
        const profil = await profilSicher(email, name);
        const ah = profil ? { autor_handle: profil.handle } : {};
        const [thread] = await lege_an("forum_threads", {
          kategorie, titel, autor_name: name, autor_email: email, ...ah,
        });
        await lege_an("forum_posts", {
          thread_id: thread.id, inhalt, autor_name: name, autor_email: email, ...ah,
        });
        return json(200, { ok: true, thread_id: thread.id });
      }

      case "forum_post_neu": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        const inhalt = sauber(body.inhalt, 5000);
        if (!inhalt || !body.thread_id) return json(400, { fehler: "Felder fehlen" });
        const profil = await profilSicher(email, name);
        await lege_an("forum_posts", {
          thread_id: body.thread_id, inhalt, autor_name: name, autor_email: email,
          ...(profil ? { autor_handle: profil.handle } : {}),
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

      // ─── Kommentarverwaltung ───────────────────────────────────────────────
      case "kommentar_liste": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const nur = sauber(body.artikel_id, 64);
        const filter = nur ? `&artikel_id=eq.${encodeURIComponent(nur)}` : "";
        const zeilen = await hole(
          `kommentare?select=id,artikel_id,name,email,inhalt,erstellt_am,geloescht` +
          `${filter}&order=erstellt_am.desc&limit=500`);
        return json(200, { kommentare: zeilen || [] });
      }

      case "kommentare_loeschen": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const ids = (Array.isArray(body.ids) ? body.ids : [])
          .map(i => String(i).trim())
          .filter(i => /^[0-9a-f-]{36}$/i.test(i));
        if (!ids.length) return json(400, { fehler: "Keine gueltigen IDs" });
        if (ids.length > 200) return json(400, { fehler: "Hoechstens 200 auf einmal" });
        const liste = ids.map(i => `"${i}"`).join(",");
        if (body.hart) {
          await loesche("kommentare", `id=in.(${liste})`);
        } else {
          await aendere("kommentare", `id=in.(${liste})`, { geloescht: true, inhalt: "" });
        }
        return json(200, { ok: true, anzahl: ids.length });
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

        // Registrierte Konten dazunehmen, damit auch stille Mitglieder
        // auftauchen und nicht nur, wer schon geschrieben hat.
        let kontenQuelle = "nur eigene Daten";
        try {
          const konten = [];
          for (let seite = 1; seite <= 10; seite++) {
            const teil = await authAdmin(`/users?per_page=500&page=${seite}`);
            const zeilen = (teil && teil.users) || [];
            konten.push(...zeilen);
            if (zeilen.length < 500) break;
          }
          kontenQuelle = "Supabase";
          konten.forEach(k => {
            const p = eintrag(k.email);
            if (!p) return;
            p.konto_id = k.id;
            p.registriert = k.created_at;
            p.bestaetigt = !!(k.email_confirmed_at || k.confirmed_at);
            p.letzter_login = k.last_sign_in_at || null;
            const anzeige = (k.user_metadata || {}).full_name;
            if (anzeige && p.name === p.email) p.name = anzeige;
          });
        } catch (e) {
          console.error("Konten nicht abrufbar:", e.message);
          kontenQuelle = "Konten-Abruf fehlgeschlagen";
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
        if (!body.konto_id) return json(400, { fehler: "Konto-ID fehlt" });
        // Erst Inhalte, dann das Konto - sonst bleiben verwaiste Beitraege
        const e2 = encodeURIComponent(ziel);
        await loesche("forum_posts", `autor_email=eq.${e2}`);
        await loesche("forum_threads", `autor_email=eq.${e2}`);
        await loesche("kommentare", `email=eq.${e2}`);
        await loesche("benutzer_rollen", `email=eq.${e2}`);
        await authAdmin(`/users/${encodeURIComponent(body.konto_id)}`, { method: "DELETE" });
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
        let an = sauber(body.an, 200).toLowerCase();
        if (body.an_handle) {
          const ziel = await emailVonHandle(body.an_handle);
          if (!ziel) return json(404, { fehler: "Profil nicht gefunden" });
          an = ziel.email.toLowerCase();
        }
        const inhalt = sauber(body.inhalt, 2000);
        if (!an || !inhalt) return json(400, { fehler: "Empfaenger oder Text fehlt" });
        try {
          if ((await blockiertZwischen(email, an)).length)
            return json(403, { fehler: "Nachricht nicht möglich: einer von euch hat den anderen blockiert" });
        } catch (e) { /* Tabelle fehlt noch: keine Blockierungen */ }
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
        // Profilnamen statt E-Mail-Adressen anzeigen
        try {
          const profile = await handlesVon(liste.map(g => g.partner));
          liste.forEach(g => {
            const pr = profile[g.partner];
            if (pr) { g.partner_handle = pr.handle; g.partner_name = pr.anzeigename; }
          });
        } catch (e) { /* ohne Profile bleibt es beim Namen aus der Nachricht */ }
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


      // ─── Profile, Gästebuch, Freunde, Blockieren ──────────────────────────────
      case "profil_meins": {
        const profil = await profilSicher(email, name);
        if (!profil) return json(503, { fehler: "Profile sind noch nicht eingerichtet" });
        const [voll] = await hole(`profile?email=eq.${encodeURIComponent(email)}&select=handle,anzeigename,ueber_mich,wohnort,lieblings,gaestebuch_offen`);
        const E = encodeURIComponent(email);
        const fr = await hole(`freundschaften?or=(von_email.eq.${E},an_email.eq.${E})&select=von_email,an_email,status`) || [];
        const bl = await hole(`blockierungen?blocker_email=eq.${E}&select=blockiert_email`) || [];
        const namen = await handlesVon([...fr.flatMap(f => [f.von_email, f.an_email]), ...bl.map(b => b.blockiert_email)]);
        const aussen = f => namen[f.von_email === email ? f.an_email : f.von_email];
        const kurz = p => p ? { handle: p.handle, name: p.anzeigename } : null;
        return json(200, {
          profil: voll,
          freunde: fr.filter(f => f.status === "ok").map(aussen).map(kurz).filter(Boolean),
          anfragen_ein: fr.filter(f => f.status === "offen" && f.an_email === email).map(aussen).map(kurz).filter(Boolean),
          anfragen_aus: fr.filter(f => f.status === "offen" && f.von_email === email).map(aussen).map(kurz).filter(Boolean),
          blockiert: bl.map(b => kurz(namen[b.blockiert_email])).filter(Boolean),
        });
      }

      case "avatar_speichern": {
        const profil = await profilSicher(email, name);
        if (!profil) return json(503, { fehler: "Profile sind noch nicht eingerichtet" });
        const bild = body.bild == null ? null : String(body.bild);
        if (bild !== null && !/^data:image\/(webp|jpeg|png);base64,[A-Za-z0-9+/=]+$/.test(bild))
          return json(400, { fehler: "Bild nicht lesbar" });
        if (bild !== null && bild.length > 60000) return json(400, { fehler: "Bild zu groß" });
        const [alt] = await hole(`profile?email=eq.${encodeURIComponent(email)}&select=lieblings`);
        const lieb = { ...((alt && alt.lieblings) || {}) };
        if (bild) lieb.avatar = bild; else delete lieb.avatar;
        await aendere("profile", `email=eq.${encodeURIComponent(email)}`, { lieblings: lieb });
        return json(200, { ok: true });
      }

      case "profil_speichern": {
        const profil = await profilSicher(email, name);
        if (!profil) return json(503, { fehler: "Profile sind noch nicht eingerichtet" });
        const handle = sauber(body.handle, 30).toLowerCase();
        if (!HANDLE.test(handle)) return json(400, { fehler: "Profilname: 3–30 Zeichen, nur a–z, 0–9 und Bindestrich" });
        if (handle !== profil.handle) {
          const belegt = await hole(`profile?handle=eq.${encodeURIComponent(handle)}&select=email`);
          if (belegt && belegt.length) return json(409, { fehler: "Dieser Profilname ist schon vergeben" });
        }
        const anzeigename = sauber(body.anzeigename, 60) || handle;
        if (await nameVergeben(anzeigename, email))
          return json(409, { fehler: "Dieser Anzeigename ist schon vergeben" });
        const lieblings = {};
        for (const k of LIEBLINGS_FELDER) {
          const v = sauber((body.lieblings || {})[k], 120);
          if (v) lieblings[k] = v;
        }
        const [vorher] = await hole(`profile?email=eq.${encodeURIComponent(email)}&select=lieblings`);
        if (vorher && vorher.lieblings && vorher.lieblings.avatar) lieblings.avatar = vorher.lieblings.avatar;
        await aendere("profile", `email=eq.${encodeURIComponent(email)}`, {
          handle,
          anzeigename,
          ueber_mich: sauber(body.ueber_mich, 1500),
          wohnort: sauber(body.wohnort, 80),
          lieblings,
          gaestebuch_offen: body.gaestebuch_offen !== false,
          aktualisiert_am: new Date().toISOString(),
        });
        // Anzeigename ist zugleich der Benutzername bei Kommentaren und im Forum
        if (anzeigename !== name) {
          await authAdmin(`/users/${encodeURIComponent(user.id)}`, {
            method: "PUT", body: JSON.stringify({ user_metadata: { ...meta, benutzername: anzeigename } }) });
          const E = encodeURIComponent(email);
          await aendere("kommentare", `email=eq.${E}`, { name: anzeigename });
          await aendere("forum_posts", `autor_email=eq.${E}`, { autor_name: anzeigename });
          await aendere("forum_threads", `autor_email=eq.${E}`, { autor_name: anzeigename });
        }
        // Profilnamen in eigenen Beiträgen mitziehen
        if (handle !== profil.handle) {
          const E = encodeURIComponent(email);
          await aendere("kommentare", `email=eq.${E}`, { autor_handle: handle });
          await aendere("forum_posts", `autor_email=eq.${E}`, { autor_handle: handle });
          await aendere("forum_threads", `autor_email=eq.${E}`, { autor_handle: handle });
        }
        return json(200, { ok: true, handle });
      }

      case "profil_status": {
        const ziel = await emailVonHandle(body.handle);
        if (!ziel) return json(404, { fehler: "Profil nicht gefunden" });
        if (ziel.email === email) return json(200, { selbst: true });
        const A = encodeURIComponent(email), B = encodeURIComponent(ziel.email);
        const fr = await hole(`freundschaften?or=(and(von_email.eq.${A},an_email.eq.${B}),and(von_email.eq.${B},an_email.eq.${A}))&select=von_email,status`) || [];
        const bl = await blockiertZwischen(email, ziel.email);
        let freund = "keine";
        if (fr.length) freund = fr[0].status === "ok" ? "ok" : (fr[0].von_email === email ? "gesendet" : "erhalten");
        return json(200, { selbst: false, freund, ich_blockiere: bl.includes(email), blockiert_mich: bl.includes(ziel.email) });
      }

      case "gaestebuch_neu": {
        if (await istGebannt(email)) return json(403, { fehler: "Du bist gesperrt" });
        await profilSicher(email, name);
        const ziel = await emailVonHandle(body.handle);
        if (!ziel) return json(404, { fehler: "Profil nicht gefunden" });
        const inhalt = sauber(body.inhalt, 1000);
        if (!inhalt) return json(400, { fehler: "Text fehlt" });
        if (!ziel.gaestebuch_offen && ziel.email !== email) return json(403, { fehler: "Das Gästebuch ist geschlossen" });
        if ((await blockiertZwischen(email, ziel.email)).length) return json(403, { fehler: "Eintrag nicht möglich" });
        const grenze = new Date(Date.now() - 10 * 60 * 1000).toISOString();
        const letzte = await hole(`gaestebuch?autor_email=eq.${encodeURIComponent(email)}&erstellt_am=gt.${grenze}&select=id`);
        if ((letzte || []).length >= 10) return json(429, { fehler: "Zu viele Einträge. Bitte kurz warten." });
        await lege_an("gaestebuch", { profil_email: ziel.email, autor_email: email, inhalt });
        return json(200, { ok: true });
      }

      case "gaestebuch_loeschen": {
        if (!UUID.test(String(body.id || ""))) return json(400, { fehler: "ID fehlt" });
        const [eintrag] = await hole(`gaestebuch?id=eq.${body.id}&select=profil_email,autor_email`) || [];
        if (!eintrag) return json(404, { fehler: "Eintrag nicht gefunden" });
        if (![eintrag.profil_email, eintrag.autor_email].includes(email) && !darfLoeschen)
          return json(403, { fehler: "Keine Berechtigung" });
        await aendere("gaestebuch", `id=eq.${body.id}`, { geloescht: true });
        return json(200, { ok: true });
      }

      case "freund_anfrage": {
        await profilSicher(email, name);
        const ziel = await emailVonHandle(body.handle);
        if (!ziel || ziel.email === email) return json(400, { fehler: "Ungültiges Profil" });
        if ((await blockiertZwischen(email, ziel.email)).length) return json(403, { fehler: "Anfrage nicht möglich" });
        const A = encodeURIComponent(email), B = encodeURIComponent(ziel.email);
        const da = await hole(`freundschaften?or=(and(von_email.eq.${A},an_email.eq.${B}),and(von_email.eq.${B},an_email.eq.${A}))&select=id,von_email,status`) || [];
        if (da.length) {
          // Liegt schon eine Anfrage in Gegenrichtung vor, ist das eine Zusage
          if (da[0].status === "offen" && da[0].von_email === ziel.email)
            await aendere("freundschaften", `id=eq.${da[0].id}`, { status: "ok" });
          return json(200, { ok: true });
        }
        await lege_an("freundschaften", { von_email: email, an_email: ziel.email, status: "offen" });
        return json(200, { ok: true });
      }

      case "freund_annehmen": {
        const ziel = await emailVonHandle(body.handle);
        if (!ziel) return json(404, { fehler: "Profil nicht gefunden" });
        await aendere("freundschaften",
          `von_email=eq.${encodeURIComponent(ziel.email)}&an_email=eq.${encodeURIComponent(email)}&status=eq.offen`,
          { status: "ok" });
        return json(200, { ok: true });
      }

      case "freund_entfernen": {
        // deckt Ablehnen, Zurückziehen und Entfreunden ab
        const ziel = await emailVonHandle(body.handle);
        if (!ziel) return json(404, { fehler: "Profil nicht gefunden" });
        const A = encodeURIComponent(email), B = encodeURIComponent(ziel.email);
        await loesche("freundschaften", `or=(and(von_email.eq.${A},an_email.eq.${B}),and(von_email.eq.${B},an_email.eq.${A}))`);
        return json(200, { ok: true });
      }

      case "blockieren": {
        const ziel = await emailVonHandle(body.handle);
        if (!ziel || ziel.email === email) return json(400, { fehler: "Ungültiges Profil" });
        await db("blockierungen", { method: "POST", body: JSON.stringify({ blocker_email: email, blockiert_email: ziel.email }),
                                    headers: { Prefer: "resolution=ignore-duplicates" } });
        const A = encodeURIComponent(email), B = encodeURIComponent(ziel.email);
        await loesche("freundschaften", `or=(and(von_email.eq.${A},an_email.eq.${B}),and(von_email.eq.${B},an_email.eq.${A}))`);
        return json(200, { ok: true });
      }

      case "entblocken": {
        const ziel = await emailVonHandle(body.handle);
        if (!ziel) return json(404, { fehler: "Profil nicht gefunden" });
        await loesche("blockierungen",
          `blocker_email=eq.${encodeURIComponent(email)}&blockiert_email=eq.${encodeURIComponent(ziel.email)}`);
        return json(200, { ok: true });
      }

      case "name_waehlen": {
        const neu = sauber(body.name, 30).replace(/\s+/g, " ");
        if (!BENUTZERNAME.test(neu))
          return json(400, { fehler: "Benutzername: 3–30 Zeichen, nur Buchstaben, Zahlen, Leerzeichen, Punkt, Binde- und Unterstrich" });
        if (await nameVergeben(neu, email)) return json(409, { fehler: "Dieser Benutzername ist schon vergeben" });
        // Profilname (Adresse /profil/<handle>) aus dem Benutzernamen ableiten
        const basis = handleAus(neu);
        let handle = null;
        for (let i = 0; i < 20 && !handle; i++) {
          const versuch = i ? `${basis.slice(0, 26)}-${i + 1}` : basis;
          const belegt = await hole(`profile?handle=eq.${encodeURIComponent(versuch)}&select=email`);
          if (!belegt || !belegt.length || belegt[0].email === email) handle = versuch;
        }
        if (!handle) return json(409, { fehler: "Dieser Benutzername ist schon vergeben" });
        const E = encodeURIComponent(email);
        const da = await hole(`profile?email=eq.${E}&select=handle`);
        if (da && da.length) await aendere("profile", `email=eq.${E}`, { handle, anzeigename: neu });
        else await lege_an("profile", { email, handle, anzeigename: neu });
        await authAdmin(`/users/${encodeURIComponent(user.id)}`, {
          method: "PUT", body: JSON.stringify({ user_metadata: { ...meta, benutzername: neu } }) });
        // Bisherige Beiträge auf den neuen Namen umstellen
        await aendere("kommentare", `email=eq.${E}`, { name: neu, autor_handle: handle });
        await aendere("forum_posts", `autor_email=eq.${E}`, { autor_name: neu, autor_handle: handle });
        await aendere("forum_threads", `autor_email=eq.${E}`, { autor_name: neu, autor_handle: handle });
        return json(200, { ok: true, name: neu, handle });
      }

      case "kommentar_meins": {
        // Welche der angezeigten Kommentare sind meine, und wie habe ich bewertet?
        const ids = (Array.isArray(body.ids) ? body.ids : []).map(String).filter(i => UUID.test(i)).slice(0, 500);
        if (!ids.length) return json(200, { eigene: [], votes: {} });
        const liste = ids.join(",");
        const E = encodeURIComponent(email);
        const [eigene, votes] = await Promise.all([
          hole(`kommentare?id=in.(${liste})&email=eq.${E}&select=id`),
          hole(`kommentar_votes?kommentar_id=in.(${liste})&voter_email=eq.${E}&select=kommentar_id,vote`),
        ]);
        return json(200, { eigene: (eigene || []).map(k => k.id),
                           votes: Object.fromEntries((votes || []).map(v => [v.kommentar_id, v.vote])) });
      }

      case "ban_info": {
        if (!darfLoeschen) return json(403, { fehler: "Keine Berechtigung" });
        const ziel = await zielEmail(body);
        return json(200, { ban: ziel ? await banVon(ziel) : null });
      }

      case "wer_bin_ich": {
        if (nameOffen) return json(200, { email, name: null, name_offen: true, rollen, istAdmin, darfLoeschen, handle: null, anfragen: 0 });
        const profil = await profilSicher(email, name);
        let anfragen = 0;
        if (profil) {
          try {
            const t = await hole(`freundschaften?an_email=eq.${encodeURIComponent(email)}&status=eq.offen&select=id`);
            anfragen = (t || []).length;
          } catch (e) { /* ohne Tabelle keine Anfragen */ }
        }
        return json(200, { email, name, rollen, istAdmin, darfLoeschen,
                           handle: profil ? profil.handle : null, anfragen, ban: await banVon(email) });
      }

      default:
        return json(400, { fehler: `Unbekannte Aktion: ${aktion}` });
    }
  } catch (e) {
    console.error("api-Fehler:", aktion, e.message);
    return json(500, { fehler: "Serverfehler" });
  }
}
