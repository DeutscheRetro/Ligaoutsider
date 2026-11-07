// spieler.js – verlinkt Spielernamen in Artikeln und zeigt ein Profil aus spieler_db.json.
// Wird von kommentare.js auf Artikelseiten nachgeladen, funktioniert daher auch in alten Artikeln.

(function () {
  const text = document.querySelector('.artikel-text');
  if (!text) return;

  const esc = t => String(t ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const schluessel = n => String(n || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/ø/g, 'o').replace(/ß/g, 'ss').replace(/ł/g, 'l').replace(/æ/g, 'ae').replace(/[^a-z ]/g, ' ').trim();

  const falteVorab = t => String(t).normalize('NFD').replace(/\p{M}/gu, '').replace(/ø/g, 'o').replace(/ł/g, 'l').toLowerCase();

  function alterAus(geb) {
    const m = /(\d\d)\.(\d\d)\.(\d{4})/.exec(geb || '');
    if (!m) return '';
    const g = new Date(+m[3], +m[2] - 1, +m[1]), h = new Date();
    return h.getFullYear() - g.getFullYear() - (h < new Date(h.getFullYear(), g.getMonth(), g.getDate()) ? 1 : 0);
  }

  // ─── Modal ───────────────────────────────────────────────────────────────────
  function modal() {
    let m = document.getElementById('lo-spieler-modal');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'lo-spieler-modal';
    m.className = 'lo-sp-modal';
    m.innerHTML = '<div class="lo-sp-box" role="dialog" aria-modal="true"><button class="lo-sp-zu" aria-label="Schließen">×</button><div class="lo-sp-inhalt"></div></div>';
    const zu = () => { m.style.display = 'none'; document.body.style.overflow = ''; };
    m.addEventListener('click', e => { if (e.target === m || e.target.classList.contains('lo-sp-zu')) zu(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && m.style.display === 'block') zu(); });
    document.body.appendChild(m);
    return m;
  }

  function zeige(s) {
    const m = modal();
    const infos = [s.position, (s.nation || []).join(' / '), alterAus(s.geboren) && alterAus(s.geboren) + ' Jahre', s.verein]
      .filter(Boolean).map(esc).join('<span class="lo-sp-punkt"> · </span>');
    const zeilen = [
      ['Rückennummer', s.nr], ['Geboren', s.geboren], ['Starker Fuß', s.fuss],
      ['Marktwert', s.tm_marktwert], ['Vertrag bis', s.vertrag_bis],
      ['Kickbase-Position', s.kickbase && s.kickbase.position],
    ].filter(([, v]) => v);
    m.querySelector('.lo-sp-inhalt').innerHTML = `
      <div class="lo-sp-kopf">
        ${s.logo ? `<img src="/${esc(s.logo)}" alt="">` : ''}
        <div>
          <div class="lo-sp-name">${esc(s.name)}${s.kapitaen ? ' <span title="Kapitän">(C)</span>' : ''}</div>
          <div class="lo-sp-infos">${infos}</div>
        </div>
      </div>
      ${(s.tm_hinweise || []).length ? `<div class="lo-sp-hinweis">${s.tm_hinweise.map(esc).join('<br>')}</div>` : ''}
      <div class="lo-sp-tabelle">${zeilen.map(([k, v]) => `<div><span>${k}</span><span>${esc(v)}</span></div>`).join('')}</div>
      <div class="lo-sp-news"></div>
      <a class="lo-sp-mehr" href="${esc(s.seite)}">Zum Spielerprofil →</a>
      <a class="lo-sp-mehr" href="/aufstellung.html?team=${encodeURIComponent(s.verein)}">Voraussichtliche Elf fürs nächste Bundesliga-Spiel →</a>`;
    m.style.display = 'block';
    document.body.style.overflow = 'hidden';
    zeigeNews(m.querySelector('.lo-sp-news'), s.tm_id);
  }

  // Letzte Artikel zum Spieler (spieler_news.json, vom Generator erzeugt)
  let newsIndex = null;
  async function zeigeNews(ziel, tmId) {
    newsIndex = newsIndex || fetch('/spieler_news.json').then(r => r.ok ? r.json() : {}).catch(() => ({}));
    const hier = location.pathname.replace(/^\//, '');
    const liste = ((await newsIndex)[String(tmId)] || []).filter(n => n.pfad !== hier);
    if (!liste.length) return;
    ziel.innerHTML = `<div class="lo-sp-news-t">Letzte News</div>` + liste.map(n =>
      `<a href="/${esc(n.pfad)}"><span>${esc(n.titel)}</span><small>${esc(n.datum.split(' ')[0])}</small></a>`).join('');
  }
  window.loSpielerNews = zeigeNews;

  // ─── Namen im Artikel finden ─────────────────────────────────────────────────
  fetch('/spieler_db.json').then(r => r.ok ? r.json() : null).then(db => {
    if (!db) return;
    // Vereine des Artikels (Tags unter dem Text) – Nachnamen allein nur bei diesen Vereinen
    const tags = [...document.querySelectorAll('.verein-tag')].map(a => schluessel(a.textContent));
    const wappen = (document.querySelector('.artikel-wappen') || {}).src || '';
    const artikelVereine = Object.keys(db.teams).filter(tn => {
      const k = schluessel(tn);
      return tags.some(t => t.split(' ').some(w => w.length > 3 && k.includes(w)))
        || (db.teams[tn].logo && wappen.endsWith('/' + db.teams[tn].logo));
    });

    const alle = [];
    for (const [tn, t] of Object.entries(db.teams)) for (const s of t.spieler) alle.push({ ...s, verein: tn, logo: t.logo });
    const slugBasis = n => n.replace(/ø/g, 'o').replace(/Ø/g, 'O').replace(/ß/g, 'ss').replace(/ł/g, 'l').replace(/æ/g, 'ae').replace(/đ/g, 'd')
      .normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'spieler';
    const slugZahl = {};
    alle.forEach(s => { const b = slugBasis(s.name); slugZahl[b] = (slugZahl[b] || 0) + 1; });
    alle.forEach(s => { const b = slugBasis(s.name); s.seite = '/spieler/' + b + (slugZahl[b] > 1 ? '-' + s.tm_id : '') + '.html'; });

    // Nachnamen, die im Artikelkontext eindeutig sind
    // Wer mit vollem Namen genannt wird, ist auch später per Nachname gemeint
    const volltext = falteVorab(text.textContent);
    const genannt = new Set(alle.filter(s => s.name.split(' ').length > 1 && volltext.includes(falteVorab(s.name))).map(s => s.tm_id));
    const nachnamen = {};
    alle.filter(s => artikelVereine.includes(s.verein) || genannt.has(s.tm_id)).forEach(s => {
      const teile = s.name.split(' ');
      const nach = teile.length > 1 ? teile.slice(1).join(' ') : s.name;
      if (nach.length < 4) return;
      (nachnamen[nach] = nachnamen[nach] || []).push(s);
    });

    const muster = [];  // [Text, Spieler] – längere Namen zuerst
    alle.forEach(s => { if (s.name.split(' ').length > 1) muster.push([s.name, s]); });
    Object.entries(nachnamen).forEach(([n, liste]) => { if (liste.length === 1) muster.push([n, liste[0]]); });
    muster.sort((a, b) => b[0].length - a[0].length);
    if (!muster.length) return;

    // Akzentunabhängig: "Pavlovic" (Datenbank) trifft auch "Pavlović" (Artikel), "ae" auch "æ".
    // Wortweise Suche in einer Map statt eines Riesen-Regex: der fror Handys mehrere Sekunden ein.
    const falte = t => t.normalize('NFD').replace(/\p{M}/gu, '').replace(/ø/g, 'o').replace(/Ø/g, 'O')
      .replace(/ł/g, 'l').replace(/đ/g, 'd').replace(/æ/g, 'ae').replace(/Æ/g, 'Ae').toLowerCase();
    const nachText = new Map();
    muster.forEach(([n, sp]) => { const k = falte(n); if (!nachText.has(k)) nachText.set(k, sp); });
    const maxWoerter = Math.max(...muster.map(([n]) => n.split(' ').length));

    const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
    const knoten = [];
    while (walker.nextNode()) if (!walker.currentNode.parentElement.closest('a')) knoten.push(walker.currentNode);

    const verlinkt = new Set();  // jeder Spieler nur beim ersten Vorkommen
    knoten.forEach(k => {
      const inhalt = k.nodeValue;
      const woerter = [...inhalt.matchAll(/[\p{L}\p{M}\p{N}'’-]+/gu)];
      const treffer = [];
      for (let i = 0; i < woerter.length; i++) {
        // Groß-/Kleinschreibung zählt: "Neuer" ja, "neuer Trainer" nein
        if (!/\p{Lu}/u.test(woerter[i][0][0])) continue;
        for (let w = Math.min(maxWoerter, woerter.length - i); w >= 1; w--) {
          const start = woerter[i].index, ende = woerter[i + w - 1].index + woerter[i + w - 1][0].length;
          const stueck = inhalt.slice(start, ende);
          const s = nachText.get(falte(stueck));
          if (!s) continue;
          if (!verlinkt.has(s.tm_id)) { verlinkt.add(s.tm_id); treffer.push([start, ende, stueck, s]); }
          i += w - 1;
          break;
        }
      }
      if (!treffer.length) return;
      const frag = document.createDocumentFragment();
      let pos = 0;
      treffer.forEach(([start, ende, stueck, s]) => {
        frag.appendChild(document.createTextNode(inhalt.slice(pos, start)));
        const a = document.createElement('a');
        a.href = s.seite;
        a.className = 'spieler-link';
        a.textContent = stueck;
        a.addEventListener('click', e => { e.preventDefault(); zeige(s); });
        frag.appendChild(a);
        pos = ende;
      });
      frag.appendChild(document.createTextNode(inhalt.slice(pos)));
      k.parentNode.replaceChild(frag, k);
    });
  }).catch(() => {});
})();
