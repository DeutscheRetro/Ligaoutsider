// auth.js – Anmeldung über Supabase Auth.
//
// Stellt dieselbe Schnittstelle bereit wie früher das Netlify-Identity-Widget
// (window.netlifyIdentity), damit alle Seiten unverändert weiterlaufen:
//   open('login' | 'signup'), close(), logout(), init(),
//   currentUser() -> { email, user_metadata, app_metadata, jwt() },
//   on('init' | 'login' | 'logout', callback)
// Die Sitzung liegt im localStorage, das Zugriffstoken wird vor Ablauf erneuert.

(function () {
  const SUPA_URL = 'https://rsodjlglzwlscamdlwev.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJzb2RqbGdsendsc2NhbWRsd2V2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEzNjk1MzIsImV4cCI6MjA5Njk0NTUzMn0.ETR6sL-b-ZmjuqWFmj3jgP2vzq70J0Yb4JgATOCekns';
  const SPEICHER = 'lo-sitzung';
  const handler = { init: [], login: [], logout: [] };
  let sitzung = null;
  let initFertig = false;

  // ─── Sitzung ────────────────────────────────────────────────────────────────
  function laden() {
    try { return JSON.parse(localStorage.getItem(SPEICHER)); } catch (e) { return null; }
  }
  function speichern(s) {
    sitzung = s;
    try { s ? localStorage.setItem(SPEICHER, JSON.stringify(s)) : localStorage.removeItem(SPEICHER); } catch (e) {}
  }
  function ausAntwort(d) {
    return {
      access: d.access_token,
      refresh: d.refresh_token,
      ablauf: d.expires_at ? d.expires_at * 1000 : Date.now() + (d.expires_in || 3600) * 1000,
      user: d.user,
    };
  }

  const FEHLER = [
    [/invalid login credentials/i, 'E-Mail oder Passwort stimmt nicht.'],
    [/email not confirmed/i, 'Bitte bestätige zuerst deine E-Mail-Adresse – der Link steht in der Mail von uns.'],
    [/already registered|already been registered/i, 'Für diese E-Mail-Adresse gibt es schon ein Konto. Melde dich an oder setze das Passwort zurück.'],
    [/password should be at least|weak password/i, 'Das Passwort braucht mindestens 8 Zeichen.'],
    [/rate limit|too many/i, 'Zu viele Versuche. Bitte warte ein paar Minuten.'],
    [/invalid email|unable to validate email/i, 'Diese E-Mail-Adresse sieht nicht gültig aus.'],
  ];
  function fehlertext(d) {
    const roh = (d && (d.msg || d.error_description || d.message || d.error)) || 'Unbekannter Fehler';
    const treffer = FEHLER.find(([m]) => m.test(roh));
    return treffer ? treffer[1] : roh;
  }

  async function auth(pfad, body, token, methode) {
    const r = await fetch(`${SUPA_URL}/auth/v1/${pfad}`, {
      method: methode || 'POST',
      headers: { apikey: SUPA_KEY, 'Content-Type': 'application/json',
                 ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(fehlertext(d));
    return d;
  }

  // Gültiges Zugriffstoken, notfalls erneuert
  async function frischesToken() {
    if (!sitzung) return null;
    if (Date.now() < sitzung.ablauf - 60000) return sitzung.access;
    try {
      speichern(ausAntwort(await auth('token?grant_type=refresh_token', { refresh_token: sitzung.refresh })));
      return sitzung.access;
    } catch (e) {
      speichern(null);
      feuern('logout');
      return null;
    }
  }

  // Nur über Google angemeldet und noch kein eigener Benutzername gewählt?
  function nameOffen(u) {
    if (!u || (u.user_metadata || {}).benutzername) return false;
    const am = u.app_metadata || {};
    const p = am.providers || [am.provider];
    return p.includes('google') && !p.includes('email');
  }

  function nutzer() {
    if (!sitzung || !sitzung.user) return null;
    const u = sitzung.user;
    // Seiten zeigen user_metadata.full_name an – dort steht der gewählte
    // Benutzername, nie der echte Name aus dem Google-Konto
    const meta = { ...(u.user_metadata || {}) };
    if (meta.benutzername) meta.full_name = meta.benutzername;
    else if (nameOffen(u)) meta.full_name = 'Neuer Fan';
    return {
      id: u.id,
      email: u.email,
      user_metadata: meta,
      app_metadata: { roles: (u.app_metadata && u.app_metadata.roles) || [] },
      jwt: async () => {
        const t = await frischesToken();
        if (!t) throw new Error('Nicht angemeldet');
        return t;
      },
    };
  }

  function feuern(ereignis, wert) {
    (handler[ereignis] || []).forEach(f => { try { f(wert); } catch (e) { console.error(e); } });
  }

  // ─── Dialog ─────────────────────────────────────────────────────────────────
  let box = null;
  const esc = t => String(t ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function stil() {
    if (document.getElementById('lo-auth-stil')) return;
    const s = document.createElement('style');
    s.id = 'lo-auth-stil';
    s.textContent = `
      .lo-auth{position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;padding:16px}
      .lo-auth-box{position:relative;width:100%;max-width:380px;background:var(--bg2,#151515);color:var(--text1,#fff);border:1px solid var(--border2,#333);border-radius:12px;padding:24px;box-shadow:0 20px 60px rgba(0,0,0,.5);font-family:inherit}
      .lo-auth-box h2{margin:0 0 16px;font-size:20px}
      .lo-auth-box label{display:block;font-size:12px;color:var(--text3,#aaa);margin:12px 0 4px}
      .lo-auth-box input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid var(--border2,#333);background:var(--bg3,#1d1d1d);color:var(--text1,#fff);font-size:15px}
      .lo-auth-box button.lo-auth-los{width:100%;margin-top:18px;padding:11px;border:0;border-radius:8px;background:var(--accent,#e8c000);color:#000;font-weight:700;font-size:15px;cursor:pointer}
      .lo-auth-box button.lo-auth-los:disabled{opacity:.6;cursor:wait}
      .lo-auth-zu{position:absolute;top:8px;right:12px;background:none;border:0;color:var(--text3,#aaa);font-size:24px;cursor:pointer}
      .lo-auth-links{margin-top:14px;font-size:13px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
      .lo-auth-links a{color:var(--accent,#e8c000);cursor:pointer}
      .lo-auth-meldung{margin-top:12px;font-size:13px;line-height:1.5}
      .lo-auth-meldung.fehler{color:#ff6b6b}
      .lo-auth-meldung.ok{color:#5fd38d}
      .lo-auth-meldung.info{color:var(--text3,#aaa)}
      .lo-auth-google{width:100%;margin-top:4px;margin-bottom:6px;padding:10px;border:1px solid var(--border2,#333);border-radius:8px;background:#fff;color:#1f1f1f;font-weight:600;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px}
      .lo-auth-oder{text-align:center;font-size:12px;color:var(--text4,#888);margin:10px 0 0}
      .lo-auth-hinweis{font-size:12px;color:var(--text4,#888);margin-top:10px;line-height:1.5}`;
    document.head.appendChild(s);
  }

  const ANSICHTEN = {
    anmelden: {
      titel: 'Anmelden',
      felder: [['email', 'E-Mail', 'email', 'email'], ['passwort', 'Passwort', 'password', 'current-password']],
      knopf: 'Anmelden',
      google: 'anmelden',
      links: [['registrieren', 'Noch kein Konto? Registrieren'], ['vergessen', 'Passwort vergessen?']],
    },
    registrieren: {
      titel: 'Konto erstellen',
      felder: [['name', 'Name (wird bei Kommentaren angezeigt)', 'text', 'nickname'],
               ['email', 'E-Mail', 'email', 'email'], ['passwort', 'Passwort (mind. 8 Zeichen)', 'password', 'new-password']],
      knopf: 'Registrieren',
      google: 'registrieren',
      links: [['anmelden', 'Schon ein Konto? Anmelden']],
      hinweis: 'Nach der Registrierung bekommst du eine E-Mail mit einem Bestätigungslink.',
    },
    vergessen: {
      titel: 'Passwort zurücksetzen',
      felder: [['email', 'E-Mail', 'email', 'email']],
      knopf: 'Link schicken',
      links: [['anmelden', 'Zurück zur Anmeldung']],
    },
    name_waehlen: {
      titel: 'Wähle deinen Benutzernamen',
      felder: [['benutzername', 'Benutzername (3–30 Zeichen)', 'text', 'nickname']],
      knopf: 'Speichern',
      links: [],
      hinweis: 'Unter diesem Namen erscheinen deine Kommentare und Forenbeiträge. Jeden Namen gibt es nur einmal. Dein Name aus dem Google-Konto wird nicht angezeigt.',
    },
    neues_passwort: {
      titel: 'Neues Passwort festlegen',
      felder: [['passwort', 'Neues Passwort (mind. 8 Zeichen)', 'password', 'new-password']],
      knopf: 'Speichern',
      links: [],
    },
  };

  function oeffnen(ansicht, meldung) {
    stil();
    schliessen();
    const a = ANSICHTEN[ansicht];
    box = document.createElement('div');
    box.className = 'lo-auth';
    box.innerHTML = `
      <form class="lo-auth-box" novalidate>
        <button type="button" class="lo-auth-zu" aria-label="Schließen">×</button>
        <h2>${esc(a.titel)}</h2>
        ${a.google ? `<button type="button" class="lo-auth-google"><svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/><path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/><path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/><path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>Mit Google ${a.google}</button>
        <div class="lo-auth-oder">oder mit E-Mail</div>` : ''}
        ${a.felder.map(([n, l, t, ac]) => `<label for="lo-auth-${n}">${esc(l)}</label>
          <input id="lo-auth-${n}" name="${n}" type="${t}" autocomplete="${ac}" required>`).join('')}
        <button type="submit" class="lo-auth-los">${esc(a.knopf)}</button>
        <div class="lo-auth-meldung"></div>
        ${a.hinweis ? `<div class="lo-auth-hinweis">${esc(a.hinweis)}</div>` : ''}
        <div class="lo-auth-links">${a.links.map(([z, t]) => `<a data-ziel="${z}">${esc(t)}</a>`).join('')}</div>
      </form>`;
    document.body.appendChild(box);
    const form = box.querySelector('form');
    box.addEventListener('click', e => {
      if (e.target === box || e.target.classList.contains('lo-auth-zu')) schliessen();
      const z = e.target.getAttribute && e.target.getAttribute('data-ziel');
      if (z) oeffnen(z);
    });
    form.addEventListener('submit', e => { e.preventDefault(); absenden(ansicht, form); });
    const google = form.querySelector('.lo-auth-google');
    if (google) google.addEventListener('click', () => {
      // Google-Anmeldung läuft über Supabase; zurück kommt man mit #access_token
      location.href = `${SUPA_URL}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(location.href.split('#')[0])}`;
    });
    if (meldung) zeigeMeldung(meldung[0], meldung[1]);
    const erstes = form.querySelector('input');
    if (erstes) erstes.focus();
  }

  function schliessen() {
    if (box) { box.remove(); box = null; }
  }

  function zeigeMeldung(text, art) {
    const m = box && box.querySelector('.lo-auth-meldung');
    if (m) { m.textContent = text; m.className = 'lo-auth-meldung ' + (art || ''); }
  }

  async function absenden(ansicht, form) {
    const wert = n => (form.elements[n] ? form.elements[n].value.trim() : '');
    const knopf = form.querySelector('.lo-auth-los');
    const knopfText = knopf.textContent;
    knopf.disabled = true;
    knopf.textContent = { anmelden: 'Anmeldung läuft …', registrieren: 'Registrierung läuft …', vergessen: 'Wird gesendet …' }[ansicht] || 'Bitte warten …';
    zeigeMeldung(ansicht === 'registrieren' || ansicht === 'vergessen' ? 'Einen Moment bitte, die E-Mail wird verschickt. Das kann bis zu 15 Sekunden dauern.' : '', 'info');
    const zurueck = encodeURIComponent(location.origin + '/');
    try {
      if (ansicht === 'anmelden') {
        const d = await auth('token?grant_type=password', { email: wert('email'), password: form.elements.passwort.value });
        speichern(ausAntwort(d));
        schliessen();
        feuern('login', nutzer());
      } else if (ansicht === 'registrieren') {
        if (!wert('name')) throw new Error('Bitte gib einen Namen an.');
        if (form.elements.passwort.value.length < 8) throw new Error('Das Passwort braucht mindestens 8 Zeichen.');
        const d = await auth(`signup?redirect_to=${zurueck}`, {
          email: wert('email'), password: form.elements.passwort.value, data: { full_name: wert('name') } });
        if (d.access_token) {          // ohne E-Mail-Bestätigung direkt angemeldet
          speichern(ausAntwort(d));
          schliessen();
          feuern('login', nutzer());
        } else {
          zeigeMeldung('Fast geschafft: Wir haben dir eine E-Mail geschickt. Klicke auf den Link darin, dann bist du angemeldet.', 'ok');
        }
      } else if (ansicht === 'vergessen') {
        await auth(`recover?redirect_to=${zurueck}`, { email: wert('email') });
        zeigeMeldung('Wenn es ein Konto mit dieser Adresse gibt, ist jetzt eine E-Mail mit einem Link unterwegs.', 'ok');
      } else if (ansicht === 'name_waehlen') {
        const t = await frischesToken();
        const r = await fetch('/api', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` },
          body: JSON.stringify({ aktion: 'name_waehlen', name: wert('benutzername') }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.fehler || 'Speichern fehlgeschlagen');
        const u = await auth('user', null, t, 'GET');
        speichern({ ...sitzung, user: u });
        schliessen();
        feuern('login', nutzer());
      } else if (ansicht === 'neues_passwort') {
        if (form.elements.passwort.value.length < 8) throw new Error('Das Passwort braucht mindestens 8 Zeichen.');
        const t = await frischesToken();
        const u = await auth('user', { password: form.elements.passwort.value }, t, 'PUT');
        speichern({ ...sitzung, user: u });
        schliessen();
        feuern('login', nutzer());
      }
    } catch (e) {
      zeigeMeldung(e.message, 'fehler');
    } finally {
      knopf.disabled = false;
      knopf.textContent = knopfText;
    }
  }

  // Links aus den E-Mails (Bestätigung, Passwort zurücksetzen) landen mit
  // #access_token=…&type=… auf der Seite
  async function linkAusMail() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get('error_description')) {
      history.replaceState(null, '', location.pathname + location.search);
      return { fehler: h.get('error_description') };
    }
    if (!h.get('access_token')) return null;
    const d = { access_token: h.get('access_token'), refresh_token: h.get('refresh_token'),
                expires_in: Number(h.get('expires_in')) || 3600 };
    d.user = await auth('user', null, d.access_token, 'GET');
    speichern(ausAntwort(d));
    history.replaceState(null, '', location.pathname + location.search);
    return { typ: h.get('type') };
  }

  // ─── Öffentliche Schnittstelle (wie das frühere Netlify-Widget) ─────────────
  window.netlifyIdentity = {
    on(ereignis, f) {
      (handler[ereignis] = handler[ereignis] || []).push(f);
      if (ereignis === 'init' && initFertig) f(nutzer());
    },
    off() {},
    init() {},
    currentUser: nutzer,
    open(art) { oeffnen(art === 'signup' ? 'registrieren' : 'anmelden'); },
    close: schliessen,
    async logout() {
      const t = sitzung && sitzung.access;
      speichern(null);
      if (t) auth('logout', null, t).catch(() => {});
      feuern('logout');
    },
  };

  // ─── Admin-Link für Redaktion (auf jeder Seite mit Anmeldung) ───────────────
  async function adminLinkPruefen(u) {
    const alt = document.getElementById('admin-link');
    if (!u) { if (alt) alt.remove(); return; }
    const ui = document.getElementById('user-info');
    if (!ui || alt) return;
    try {
      const t = await u.jwt();
      const r = await fetch('/api', { method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + t },
        body: JSON.stringify({ aktion: 'wer_bin_ich' }) });
      const w = await r.json();
      if (!w.darfLoeschen || document.getElementById('admin-link')) return;
      const a = document.createElement('a');
      a.id = 'admin-link'; a.href = '/chefred.html'; a.textContent = '⚙ Admin';
      a.style.cssText = 'margin-right:8px;text-decoration:none;font-weight:700;color:var(--accent,#e8c000)';
      ui.prepend(a);
    } catch (e) { /* ohne Link weiterarbeiten */ }
  }
  window.netlifyIdentity.on('init', u => { if (u) adminLinkPruefen(u); });
  window.netlifyIdentity.on('login', adminLinkPruefen);
  window.netlifyIdentity.on('logout', () => adminLinkPruefen(null));

  // ─── Persönlicher Bereich: Mein Verein, Favoriten, Menüpunkt ────────────────
  const konto = { daten: null, laufend: null };
  async function kontoApi(aktion, daten) {
    const u = nutzer();
    if (!u) throw new Error('Nicht angemeldet');
    const t = await u.jwt();
    const r = await fetch('/api', { method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + t },
      body: JSON.stringify({ aktion, ...(daten || {}) }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.fehler || 'Fehler ' + r.status);
    return d;
  }
  window.loKonto = {
    laden() {
      if (!konto.laufend) konto.laufend = kontoApi('konto_lesen').then(d => (konto.daten = d)).catch(() => (konto.daten = null));
      return konto.laufend;
    },
    async favorit(tmId) {
      const d = await kontoApi('favorit_umschalten', { tm_id: tmId });
      konto.daten = { ...(konto.daten || {}), favoriten: d.favoriten };
      return d;
    },
    async verein(slug) {
      const d = await kontoApi('mein_verein_setzen', { verein: slug });
      konto.daten = { ...(konto.daten || {}), verein: d.verein };
      return d;
    },
  };

  function menuPunkt(u) {
    const alt = document.getElementById('mein-bereich-link');
    if (!u) { if (alt) alt.remove(); return; }
    const nav = document.querySelector('.section-nav-inner');
    if (!nav || alt) return;
    const tiefe = /^\/(artikel|spieler|verein)\//.test(location.pathname) ? '../' : '';
    const a = document.createElement('a');
    a.id = 'mein-bereich-link'; a.className = 'section-nav-link';
    a.href = tiefe + 'mein-bereich.html'; a.textContent = '⭐ Mein Bereich';
    nav.insertBefore(a, nav.querySelector('a[href$="community.html"]'));
    if (location.pathname.endsWith('/mein-bereich.html')) a.classList.add('active');
  }

  // Stern-Knöpfe: <button data-fav-tm="ID"> auf Spielerseiten
  async function sterneVerdrahten(u) {
    const knoepfe = document.querySelectorAll('[data-fav-tm]');
    if (!knoepfe.length) return;
    const zeigen = () => knoepfe.forEach(b => {
      const an = ((konto.daten && konto.daten.favoriten) || []).map(String).includes(b.dataset.favTm);
      b.textContent = an ? '★ Favorit' : '☆ Zu Favoriten';
      b.classList.toggle('fav-an', an);
    });
    knoepfe.forEach(b => {
      b.hidden = false;
      b.onclick = async () => {
        if (!nutzer()) { oeffnen('registrieren'); return; }
        b.disabled = true;
        try { await window.loKonto.favorit(b.dataset.favTm); } catch (e) { alert(e.message); }
        b.disabled = false; zeigen();
      };
    });
    if (u) { await window.loKonto.laden(); }
    zeigen();
  }

  // <button data-mein-verein="bayern"> auf Vereinsseiten
  async function vereinKnopf(u) {
    const b = document.querySelector('[data-mein-verein]');
    if (!b) return;
    const slug = b.dataset.meinVerein;
    const zeigen = () => {
      const an = konto.daten && konto.daten.verein === slug;
      b.textContent = an ? '⭐ Mein Verein' : '☆ Als Mein Verein wählen';
      b.classList.toggle('fav-an', !!an);
    };
    b.hidden = false;
    b.onclick = async () => {
      if (!nutzer()) { oeffnen('registrieren'); return; }
      b.disabled = true;
      try { await window.loKonto.verein(konto.daten && konto.daten.verein === slug ? '' : slug); } catch (e) { alert(e.message); }
      b.disabled = false; zeigen();
    };
    if (u) await window.loKonto.laden();
    zeigen();
  }

  // Startseite: Hinweisleiste mit dem eigenen Verein (nur eingeloggt, nur wenn gewählt)
  async function meinVereinLeiste(u) {
    const alt = document.getElementById('mein-verein-leiste');
    if (alt) alt.remove();
    const nav = document.querySelector('nav.team-nav');
    if (!u || !nav || !/^\/(index\.html)?$/.test(location.pathname)) return;
    await window.loKonto.laden();
    const slug = konto.daten && konto.daten.verein;
    const KURZ = { bayern: 'Bayern', dortmund: 'Dortmund', leipzig: 'Leipzig', leverkusen: 'Leverkusen', frankfurt: 'Frankfurt',
      stuttgart: 'Stuttgart', gladbach: 'Gladbach', freiburg: 'Freiburg', union: 'Union', mainz: 'Mainz', augsburg: 'Augsburg',
      werder: 'Werder', hoffenheim: 'Hoffenheim', hsv: 'Hamburger', koeln: 'Köln', schalke: 'Schalke', paderborn: 'Paderborn', elversberg: 'Elversberg' };
    const leiste = document.createElement('div');
    leiste.id = 'mein-verein-leiste';
    leiste.style.cssText = 'max-width:1100px;margin:10px auto;padding:10px 14px;background:var(--bg2,#151515);border:1px solid var(--border2,#333);border-radius:10px;font-size:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap';
    leiste.innerHTML = slug && KURZ[slug]
      ? `<img src="logos/${slug}.png" alt="" width="24" height="24" style="object-fit:contain"><span>Dein Verein: <strong>${KURZ[slug]}</strong></span>
         <a href="index.html?filter=${encodeURIComponent(KURZ[slug])}" style="color:var(--accent,#e8c000);font-weight:700">Nur seine News</a>
         <a href="mein-bereich.html" style="color:var(--text3,#aaa);margin-left:auto">Mein Bereich</a>`
      : `<span>⭐ Wähle deinen Verein und sieh seine News zuerst.</span>
         <a href="mein-bereich.html" style="color:var(--accent,#e8c000);font-weight:700">Verein wählen</a>`;
    nav.insertAdjacentElement('afterend', leiste);
  }

  function kontoHaken(u) {
    menuPunkt(u);
    if (!u) konto.laufend = konto.daten = null;
    const los = () => { sterneVerdrahten(u); vereinKnopf(u); meinVereinLeiste(u); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', los); else los();
  }
  window.netlifyIdentity.on('init', u => kontoHaken(u));
  window.netlifyIdentity.on('login', u => kontoHaken(u));
  window.netlifyIdentity.on('logout', () => kontoHaken(null));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => { sterneVerdrahten(null); vereinKnopf(null); });
  else { sterneVerdrahten(null); vereinKnopf(null); }

  sitzung = laden();
  (async () => {
    let ausMail = null;
    try { ausMail = await linkAusMail(); } catch (e) { ausMail = { fehler: e.message }; }
    if (sitzung) await frischesToken();
    initFertig = true;
    const start = () => {
      feuern('init', nutzer());
      if (ausMail && ausMail.typ === 'recovery') oeffnen('neues_passwort');
      else if (sitzung && nameOffen(sitzung.user)) oeffnen('name_waehlen');
      else if (ausMail && ausMail.typ && sitzung) feuern('login', nutzer());
      else if (ausMail && ausMail.fehler) oeffnen('anmelden', ['Der Link ist ungültig oder abgelaufen. Bitte melde dich an oder fordere einen neuen an.', 'fehler']);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
  })();
})();
