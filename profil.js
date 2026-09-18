// profil.js – Nutzerprofil: Ansicht, Bearbeiten, Gästebuch, Freunde, Blockieren.
// Öffentliche Daten kommen aus den Supabase-Views (ohne E-Mail), alles andere
// über die Netlify Function (window._loApi aus kommentare.js).

(function () {
  const box = document.getElementById('pr');
  const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const api = (aktion, daten) => window._loApi(aktion, daten);
  const rest = pfad => fetch(`${SUPABASE_URL}/rest/v1/${pfad}`, {
    headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` }
  }).then(r => r.ok ? r.json() : Promise.reject(new Error('Laden fehlgeschlagen')));

  const LIEBLINGS = [
    ['Fußball', [['verein', 'Verein'], ['spieler', 'Spieler'], ['stadion', 'Stadion'], ['trainer', 'Trainer']]],
    ['Film & Fernsehen', [['film', 'Film'], ['serie', 'Serie']]],
    ['Musik', [['musik', 'Band / Künstler'], ['song', 'Song']]],
    ['Und sonst', [['buch', 'Buch'], ['game', 'Game'], ['essen', 'Essen'], ['getraenk', 'Getränk'],
                   ['reiseziel', 'Reiseziel'], ['sport', 'Sport neben Fußball']]],
  ];
  const VEREINE = {
    'FC Bayern München': 'bayern', 'Borussia Dortmund': 'dortmund', 'RB Leipzig': 'leipzig', 'Bayer 04 Leverkusen': 'leverkusen',
    'Eintracht Frankfurt': 'frankfurt', 'VfB Stuttgart': 'stuttgart', 'Borussia Mönchengladbach': 'gladbach', 'SC Freiburg': 'freiburg',
    '1. FC Union Berlin': 'union', '1. FSV Mainz 05': 'mainz', 'FC Augsburg': 'augsburg', 'SV Werder Bremen': 'werder',
    'TSG Hoffenheim': 'hoffenheim', 'Hamburger SV': 'hsv', '1. FC Köln': 'koeln', 'FC Schalke 04': 'schalke',
    'SC Paderborn 07': 'paderborn', 'SV Elversberg': 'elversberg',
  };

  let ich = window._loIch;          // { handle, email } sobald angemeldet
  let handle = (new URLSearchParams(location.search).get('u') || '').toLowerCase();
  let profil = null, status = null, meins = null;

  function meldung(text, fehler) {
    let m = document.getElementById('pr-meldung');
    if (!m) { m = document.createElement('div'); m.id = 'pr-meldung'; box.prepend(m); }
    m.className = 'pr-meldung' + (fehler ? ' fehler' : '');
    m.textContent = text;
    clearTimeout(meldung.t);
    meldung.t = setTimeout(() => m.remove(), 4000);
  }
  async function aktion(name, daten, erfolg) {
    try { await api(name, daten); if (erfolg) meldung(erfolg); await laden(); }
    catch (e) { meldung(e.message, true); }
  }

  // ─── Laden ───────────────────────────────────────────────────────────────────
  async function laden() {
    if (!handle) {
      if (ich && ich.handle) { handle = ich.handle; history.replaceState(null, '', '?u=' + encodeURIComponent(handle)); }
      else if (ich === null || ich === undefined) {
        box.innerHTML = `<div class="pr-leer"><h1>Dein Profil</h1><p>Melde dich an, um dein Profil anzulegen und andere Fans zu finden.</p>
          <button class="pr-btn pr-btn--gelb" onclick="netlifyIdentity.open('login')">Anmelden</button></div>`;
        return;
      } else { box.innerHTML = '<p class="kb-loading">Profile sind noch nicht eingerichtet.</p>'; return; }
    }
    try {
      const [p, gb, fr] = await Promise.all([
        rest(`profile_oeffentlich?handle=eq.${encodeURIComponent(handle)}`),
        rest(`gaestebuch_oeffentlich?profil_handle=eq.${encodeURIComponent(handle)}&order=erstellt_am.desc&limit=100`),
        rest(`freunde_oeffentlich?handle=eq.${encodeURIComponent(handle)}&order=freund_name.asc`),
      ]);
      if (!p.length) { box.innerHTML = '<p class="kb-loading">Dieses Profil gibt es nicht.</p>'; return; }
      profil = { ...p[0], gaestebuch: gb, freunde: fr };
    } catch (e) {
      box.innerHTML = '<p class="kb-loading">Profil konnte nicht geladen werden.</p>'; return;
    }
    status = null; meins = null;
    if (ich) {
      try { status = await api('profil_status', { handle }); } catch (e) {}
      if (status && status.selbst) { try { meins = await api('profil_meins'); } catch (e) {} }
    }
    document.title = `${profil.anzeigename} – Ligaoutsider.de`;
    render();
  }

  // ─── Anzeige ─────────────────────────────────────────────────────────────────
  function lieblingsHtml(l) {
    const bloecke = LIEBLINGS.map(([gruppe, felder]) => {
      const zeilen = felder.filter(([k]) => l[k]).map(([k, label]) => {
        let wert = esc(l[k]);
        if (k === 'verein' && VEREINE[l[k]]) wert = `<img src="logos/${VEREINE[l[k]]}.png" alt="">${wert}`;
        return `<div class="pr-lieb"><span>${label}</span><b>${wert}</b></div>`;
      }).join('');
      return zeilen ? `<div class="pr-lieb-gruppe"><h3>${gruppe}</h3>${zeilen}</div>` : '';
    }).join('');
    return bloecke || '<p class="pr-grau">Noch keine Lieblinge eingetragen.</p>';
  }

  function knoepfe() {
    if (!ich) return `<button class="pr-btn" onclick="netlifyIdentity.open('login')">Anmelden, um Freund zu werden</button>`;
    if (status && status.selbst) return `<button class="pr-btn pr-btn--gelb" data-a="bearbeiten">✏ Profil bearbeiten</button>`;
    if (!status) return '';
    if (status.ich_blockiere) return `<button class="pr-btn" data-a="entblocken">Blockierung aufheben</button>`;
    if (status.blockiert_mich) return `<span class="pr-grau">Interaktion nicht möglich</span>`;
    const freund = {
      keine: `<button class="pr-btn pr-btn--gelb" data-a="anfrage">➕ Freund hinzufügen</button>`,
      gesendet: `<button class="pr-btn" data-a="entfernen" title="Anfrage zurückziehen">⏳ Anfrage gesendet</button>`,
      erhalten: `<button class="pr-btn pr-btn--gelb" data-a="annehmen">✓ Anfrage annehmen</button><button class="pr-btn" data-a="entfernen">Ablehnen</button>`,
      ok: `<button class="pr-btn" data-a="entfernen" title="Freundschaft beenden">✓ Befreundet</button>`,
    }[status.freund];
    return `${freund}
      <a class="pr-btn" href="nachrichten.html?u=${encodeURIComponent(handle)}">✉ Nachricht</a>
      <button class="pr-btn pr-btn--rot" data-a="blockieren">Blockieren</button>`;
  }

  function render() {
    const p = profil;
    const seit = new Date(p.erstellt_am).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
    const initial = (p.anzeigename || p.handle).trim().charAt(0).toUpperCase();
    const vereinLogo = VEREINE[(p.lieblings || {}).verein];
    const darfSchreiben = ich && status && !status.ich_blockiere && !status.blockiert_mich && (p.gaestebuch_offen || status.selbst);

    box.innerHTML = `
      <div class="pr-kopf">
        <div class="pr-avatar">${vereinLogo ? `<img src="logos/${vereinLogo}.png" alt="">` : esc(initial)}</div>
        <div class="pr-kopf-text">
          <h1>${esc(p.anzeigename)}</h1>
          <p>@${esc(p.handle)}${p.wohnort ? ' · ' + esc(p.wohnort) : ''} · dabei seit ${seit}</p>
          <div class="pr-knoepfe">${knoepfe()}</div>
        </div>
      </div>

      ${meins ? anfragenHtml() : ''}
      ${p.ueber_mich ? `<section class="pr-sektion"><h2>Über mich</h2><p class="pr-text">${esc(p.ueber_mich)}</p></section>` : ''}

      <section class="pr-sektion"><h2>Lieblinge</h2><div class="pr-lieb-raster">${lieblingsHtml(p.lieblings || {})}</div></section>

      <section class="pr-sektion"><h2>Freunde <small>${p.freunde.length}</small></h2>
        ${p.freunde.length ? `<div class="pr-freunde">${p.freunde.map(f =>
          `<a href="?u=${encodeURIComponent(f.freund_handle)}"><span>${esc((f.freund_name || f.freund_handle).charAt(0).toUpperCase())}</span>${esc(f.freund_name)}</a>`).join('')}</div>`
          : '<p class="pr-grau">Noch keine Freunde.</p>'}
      </section>

      <section class="pr-sektion"><h2>Gästebuch <small>${p.gaestebuch.length}</small></h2>
        ${darfSchreiben ? `<form class="pr-gb-form" id="pr-gb-form">
            <textarea id="pr-gb-text" maxlength="1000" placeholder="Schreib ${status.selbst ? 'etwas in dein' : 'etwas in ' + esc(p.anzeigename) + 's'} Gästebuch…" required></textarea>
            <button class="pr-btn pr-btn--gelb" type="submit">Eintragen</button></form>`
          : (!p.gaestebuch_offen ? '<p class="pr-grau">Das Gästebuch ist geschlossen.</p>'
             : !ich ? '<p class="pr-grau">Melde dich an, um ins Gästebuch zu schreiben.</p>' : '')}
        <div class="pr-gb">${p.gaestebuch.map(g => `
          <div class="pr-gb-eintrag">
            <div class="pr-gb-kopf">
              ${g.autor_handle ? `<a href="?u=${encodeURIComponent(g.autor_handle)}">${esc(g.autor_name)}</a>` : `<b>${esc(g.autor_name)}</b>`}
              <span>${new Date(g.erstellt_am).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
              ${ich && (status?.selbst || g.autor_handle === ich.handle) ? `<button class="pr-gb-weg" data-a="gb-loeschen" data-id="${g.id}" title="Eintrag löschen">🗑</button>` : ''}
            </div>
            <p>${esc(g.inhalt)}</p>
          </div>`).join('') || '<p class="pr-grau">Noch keine Einträge.</p>'}
        </div>
      </section>

      ${meins && meins.blockiert.length ? `<section class="pr-sektion"><h2>Blockiert</h2>${meins.blockiert.map(b =>
        `<div class="pr-zeile"><a href="?u=${encodeURIComponent(b.handle)}">${esc(b.name)}</a>
          <button class="pr-btn" data-a="entblocken" data-h="${esc(b.handle)}">Aufheben</button></div>`).join('')}</section>` : ''}`;

    document.getElementById('pr-gb-form')?.addEventListener('submit', async e => {
      e.preventDefault();
      const ta = document.getElementById('pr-gb-text');
      await aktion('gaestebuch_neu', { handle, inhalt: ta.value }, 'Eingetragen');
    });
  }

  function anfragenHtml() {
    const ein = meins.anfragen_ein, aus = meins.anfragen_aus;
    if (!ein.length && !aus.length) return '';
    return `<section class="pr-sektion pr-anfragen"><h2>Freundschaftsanfragen</h2>
      ${ein.map(a => `<div class="pr-zeile"><a href="?u=${encodeURIComponent(a.handle)}">${esc(a.name)}</a>
        <span><button class="pr-btn pr-btn--gelb" data-a="annehmen" data-h="${esc(a.handle)}">Annehmen</button>
        <button class="pr-btn" data-a="entfernen" data-h="${esc(a.handle)}">Ablehnen</button></span></div>`).join('')}
      ${aus.map(a => `<div class="pr-zeile"><span><a href="?u=${encodeURIComponent(a.handle)}">${esc(a.name)}</a> <small class="pr-grau">wartet auf Antwort</small></span>
        <button class="pr-btn" data-a="entfernen" data-h="${esc(a.handle)}">Zurückziehen</button></div>`).join('')}
    </section>`;
  }

  // ─── Bearbeiten ──────────────────────────────────────────────────────────────
  function bearbeiten() {
    const p = meins.profil, l = p.lieblings || {};
    const feld = (k, label) => k === 'verein'
      ? `<label><span>${label}</span><select name="l_${k}"><option value="">–</option>${Object.keys(VEREINE).map(v =>
          `<option ${l.verein === v ? 'selected' : ''}>${esc(v)}</option>`).join('')}
          ${l.verein && !VEREINE[l.verein] ? `<option selected>${esc(l.verein)}</option>` : ''}</select></label>`
      : `<label><span>${label}</span><input name="l_${k}" maxlength="120" value="${esc(l[k] || '')}"></label>`;
    box.innerHTML = `
      <h1 class="pr-titel">Profil bearbeiten</h1>
      <form id="pr-form" class="pr-form">
        <div class="pr-form-raster">
          <label><span>Anzeigename</span><input name="anzeigename" maxlength="60" value="${esc(p.anzeigename)}" required></label>
          <label><span>Profilname (Adresse: /profil.html?u=…)</span><input name="handle" maxlength="30" pattern="[a-z0-9-]{3,30}" value="${esc(p.handle)}" required></label>
          <label><span>Wohnort</span><input name="wohnort" maxlength="80" value="${esc(p.wohnort)}"></label>
        </div>
        <label><span>Über mich</span><textarea name="ueber_mich" maxlength="1500" rows="4">${esc(p.ueber_mich)}</textarea></label>
        ${LIEBLINGS.map(([gruppe, felder]) => `<fieldset><legend>${gruppe}</legend><div class="pr-form-raster">
          ${felder.map(([k, label]) => feld(k, label)).join('')}</div></fieldset>`).join('')}
        <label class="pr-check"><input type="checkbox" name="gaestebuch_offen" ${p.gaestebuch_offen ? 'checked' : ''}> Gästebuch für andere offen</label>
        <div class="pr-knoepfe">
          <button class="pr-btn pr-btn--gelb" type="submit">Speichern</button>
          <button class="pr-btn" type="button" data-a="abbrechen">Abbrechen</button>
        </div>
      </form>`;
    document.getElementById('pr-form').addEventListener('submit', async e => {
      e.preventDefault();
      const f = new FormData(e.target);
      const lieblings = {};
      LIEBLINGS.forEach(([, felder]) => felder.forEach(([k]) => { const v = (f.get('l_' + k) || '').trim(); if (v) lieblings[k] = v; }));
      try {
        const r = await api('profil_speichern', {
          anzeigename: f.get('anzeigename'), handle: String(f.get('handle')).toLowerCase(), wohnort: f.get('wohnort'),
          ueber_mich: f.get('ueber_mich'), lieblings, gaestebuch_offen: f.get('gaestebuch_offen') === 'on',
        });
        handle = r.handle;
        if (ich) ich.handle = r.handle;
        history.replaceState(null, '', '?u=' + encodeURIComponent(handle));
        await laden();
        meldung('Gespeichert');
      } catch (err) { meldung(err.message, true); }
    });
  }

  // ─── Klicks ──────────────────────────────────────────────────────────────────
  box.addEventListener('click', async e => {
    const b = e.target.closest('[data-a]');
    if (!b) return;
    const h = b.dataset.h || handle;
    switch (b.dataset.a) {
      case 'bearbeiten': return bearbeiten();
      case 'abbrechen': return render();
      case 'anfrage': return aktion('freund_anfrage', { handle: h }, 'Anfrage gesendet');
      case 'annehmen': return aktion('freund_annehmen', { handle: h }, 'Ihr seid jetzt befreundet');
      case 'entfernen':
        if (b.textContent.includes('Befreundet') && !confirm('Freundschaft wirklich beenden?')) return;
        return aktion('freund_entfernen', { handle: h });
      case 'blockieren':
        if (!confirm(`${profil.anzeigename} blockieren? Ihr könnt euch dann keine Nachrichten, Gästebucheinträge oder Anfragen mehr schicken, eine Freundschaft endet.`)) return;
        return aktion('blockieren', { handle: h }, 'Blockiert');
      case 'entblocken': return aktion('entblocken', { handle: h }, 'Blockierung aufgehoben');
      case 'gb-loeschen':
        if (!confirm('Eintrag löschen?')) return;
        return aktion('gaestebuch_loeschen', { id: b.dataset.id }, 'Gelöscht');
    }
  });

  // Anmeldestatus kommt asynchron aus kommentare.js
  let gestartet = false;
  document.addEventListener('lo-ich', ev => { ich = ev.detail; gestartet = true; laden(); });
  // Ohne Anmeldung feuert kein Ereignis: nach kurzer Wartezeit öffentlich laden
  setTimeout(() => { if (!gestartet) { ich = window._loIch || null; laden(); } }, 1200);
})();
