// Schnelltipp "Wer gewinnt?" in der Spielleiste: Gold-Schimmer nach Tipps, Hinweis beim Überfahren,
// Pop-up beim Klick. Gezählt wird pro Person einmal, ein genauer Tipp aus dem Tippspiel geht vor.
(function () {
  const MIN_TIPPS = 3;   // darunter kein Schimmer, sonst zeigt ein einziger Tipp 100 %
  let tendenz = {}, pop = null, aktuell = null;

  const summe = z => (z || []).reduce((a, b) => a + b, 0);
  const anteil = (z, i) => { const s = summe(z); return s ? Math.round(100 * z[i] / s) : 0; };
  const offen = z => !z.dataset.fertig || z.dataset.fertig === '0'
    ? new Date(z.dataset.anpfiff).getTime() - 5 * 60 * 1000 > Date.now() : false;
  const namen = z => [z.querySelector('.sp-h').textContent.trim(), z.querySelector('.sp-g').textContent.trim()];

  function zeichnen(z) {
    const zahlen = tendenz[z.dataset.spiel] || [0, 0, 0], [h, g] = namen(z);
    const ph = anteil(zahlen, 0), pu = anteil(zahlen, 1), pg = anteil(zahlen, 2);
    const genug = summe(zahlen) >= MIN_TIPPS;
    z.classList.toggle('sp-leer', !genug);
    z.style.setProperty('--sp-h', ph + '%');
    z.style.setProperty('--sp-g', pg + '%');
    z.querySelector('.sp-h').classList.toggle('sp-fav', genug && ph >= pg + 10);
    z.querySelector('.sp-g').classList.toggle('sp-fav', genug && pg >= ph + 10);
    z.querySelector('.sp-hint').textContent = genug
      ? `${ph} % ${h} · ${pu} % Remis · ${pg} % ${g}`
      : (offen(z) ? 'Noch keine Tipps · klicken zum Tippen' : 'Zu wenige Tipps');
  }

  function aufbauen(z) {
    if (z.dataset.bereit) return;
    z.dataset.bereit = '1';
    z.classList.add('sp-klick');
    z.tabIndex = 0;
    z.setAttribute('role', 'button');
    const [h, g] = namen(z);
    z.setAttribute('aria-label', `${h} gegen ${g}: Wer gewinnt?`);
    const bar = document.createElement('span'); bar.className = 'sp-bar';
    bar.append(document.createElement('i'), document.createElement('i'), document.createElement('i'));
    const hint = document.createElement('span'); hint.className = 'sp-hint';
    z.append(bar, hint);
    z.addEventListener('click', () => oeffnen(z));
    z.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); oeffnen(z); } });
  }

  async function laden(liste) {
    const zeilen = [...liste.querySelectorAll('.sp-zeile')];
    if (!zeilen.length) return;
    zeilen.forEach(aufbauen);
    // sortiert, damit der Cache-Schlüssel für alle Besucher gleich ist
    const ids = [...new Set(zeilen.map(z => z.dataset.spiel))].sort();
    try {
      const r = await fetch('/api?spiel_tendenz=' + ids.join(','));
      if (r.ok) tendenz = await r.json();
    } catch (e) { /* ohne Daten bleibt die Leiste wie gehabt */ }
    zeilen.forEach(zeichnen);
  }

  // ─── Pop-up ────────────────────────────────────────────────────────────────
  function bauen() {
    pop = document.createElement('div');
    pop.className = 'sp-hinter';
    pop.innerHTML = `<div class="sp-pop" role="dialog" aria-modal="true" aria-labelledby="sp-frage">
      <div class="sp-kopf"><span class="sp-wann"></span><button type="button" class="sp-zu" aria-label="Schließen">×</button></div>
      <div class="sp-paarung"><strong class="sp-n-h"></strong><span>gegen</span><strong class="sp-n-g"></strong></div>
      <h3 id="sp-frage">Wer gewinnt?</h3>
      <div class="sp-wahl"><button type="button" data-i="0"></button><button type="button" data-i="1">Unent&shy;schieden</button><button type="button" data-i="2"></button></div>
      <p class="sp-info" hidden></p>
      <div class="sp-erg"></div>
      <p class="sp-fuss"></p>
    </div>`;
    document.body.append(pop);
    pop.querySelector('.sp-zu').addEventListener('click', schliessen);
    pop.addEventListener('click', e => { if (e.target === pop) schliessen(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && pop.classList.contains('offen')) schliessen(); });
    pop.querySelectorAll('.sp-wahl button').forEach(b => b.addEventListener('click', () => tippen(Number(b.dataset.i))));
  }

  function schliessen() {
    pop.classList.remove('offen');
    if (aktuell) aktuell.focus();
  }

  function ergebnis(zahlen, meine) {
    const erg = pop.querySelector('.sp-erg'), [h, g] = namen(aktuell);
    erg.textContent = '';
    if (!summe(zahlen)) return;
    [h, 'Unentschieden', g].forEach((n, i) => {
      const zeile = document.createElement('div');
      zeile.className = 'sp-balk' + (i === meine ? ' meins' : '');
      const f = document.createElement('i'), name = document.createElement('span'), wert = document.createElement('b');
      name.textContent = n;
      wert.textContent = anteil(zahlen, i) + ' %';
      zeile.append(f, name, wert);
      erg.append(zeile);
      requestAnimationFrame(() => { f.style.width = anteil(zahlen, i) + '%'; });
    });
    const s = summe(zahlen);
    pop.querySelector('.sp-fuss').textContent = s >= 20 ? `${s} Tipps` : '';
  }

  function wahlZeigen(an, meine) {
    const wahl = pop.querySelector('.sp-wahl');
    wahl.hidden = !an;
    wahl.querySelectorAll('button').forEach((b, i) => { b.disabled = false; b.classList.toggle('meins', i === meine); });
  }

  function info(text, link) {
    const p = pop.querySelector('.sp-info');
    p.textContent = text || '';
    if (link) {
      const a = document.createElement('a');
      a.href = link.href; a.textContent = link.text;
      if (link.klick) a.addEventListener('click', link.klick);
      p.append(' ', a);
    }
    p.hidden = !text;
  }

  const angemeldet = () => window.netlifyIdentity && netlifyIdentity.currentUser();
  async function api(aktion, daten) {
    const token = await angemeldet().jwt();
    const r = await fetch('/api', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ aktion, ...daten }) });
    const a = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(a.fehler || 'Fehler ' + r.status);
    return a;
  }

  async function oeffnen(z) {
    if (!pop) bauen();
    aktuell = z;
    const [h, g] = namen(z), d = new Date(z.dataset.anpfiff);
    pop.querySelector('.sp-n-h').textContent = h;
    pop.querySelector('.sp-n-g').textContent = g;
    pop.querySelector('.sp-wahl [data-i="0"]').textContent = h;
    pop.querySelector('.sp-wahl [data-i="2"]').textContent = g;
    pop.querySelector('.sp-wann').textContent = `${z.dataset.wettbewerb} · ` +
      d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' ' +
      d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
    pop.querySelector('.sp-fuss').textContent = '';
    ergebnis(tendenz[z.dataset.spiel], -1);
    pop.classList.add('offen');
    pop.querySelector('.sp-zu').focus();

    if (!offen(z)) { wahlZeigen(false); info('Tippschluss: Tipps gehen nur bis 5 Minuten vor Anpfiff.'); return; }
    if (!angemeldet()) {
      wahlZeigen(false);
      info('Tippen können nur angemeldete Nutzer.', { href: '#', text: 'Anmelden', klick: e => {
        e.preventDefault(); schliessen(); netlifyIdentity.open('login'); } });
      return;
    }
    wahlZeigen(true, -1);
    info('');
    try {
      const st = await api('spiel_tipp_status', { spiel_id: Number(z.dataset.spiel) });
      if (aktuell !== z) return;   // inzwischen ein anderes Spiel geöffnet
      if (st.genau) {
        wahlZeigen(false);
        info(`Dein Tipp im Tippspiel: ${st.genau.h}:${st.genau.g}.`, { href: '/tippspiel.html', text: 'Im Tippspiel ändern →' });
        ergebnis(st.zaehler, [st.genau.h, st.genau.g].reduce((a, b) => a > b ? 0 : a === b ? 1 : 2));
      } else {
        wahlZeigen(true, st.schnell ?? -1);
        info('', { href: '/tippspiel.html', text: 'Genaues Ergebnis im Tippspiel tippen →' });
        pop.querySelector('.sp-info').hidden = false;
        if (st.schnell != null) ergebnis(st.zaehler, st.schnell);
      }
    } catch (e) { /* Status nicht ladbar: Knöpfe bleiben nutzbar */ }
  }

  async function tippen(i) {
    const z = aktuell;
    pop.querySelectorAll('.sp-wahl button').forEach(b => { b.disabled = true; });
    try {
      const a = await api('spiel_tipp', { spiel_id: Number(z.dataset.spiel), antwort: i });
      tendenz[z.dataset.spiel] = a.zaehler;
      zeichnen(z);
      if (aktuell !== z) return;   // Pop-up zeigt schon ein anderes Spiel
      wahlZeigen(true, i);
      ergebnis(a.zaehler, i);
      pop.querySelector('.sp-fuss').textContent = 'Danke für deinen Tipp. Ändern geht bis 5 Minuten vor Anpfiff.';
    } catch (e) {
      if (aktuell !== z) return;
      wahlZeigen(true, -1);
      info(e.message);
    }
  }

  window.loSpieltipp = laden;
  const liste = document.getElementById('spiele-list');
  if (liste && liste.querySelector('.sp-zeile')) laden(liste);
})();
