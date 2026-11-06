// Ein-Klick-Umfrage unter Artikeln. Ergebnis erst nach der eigenen Stimme, eine Stimme pro Gerät.
// Die Geräte-ID entsteht erst beim Abstimmen (vom Leser ausgelöst), nicht beim Laden der Seite.
(function () {
  const box = document.querySelector('.umfrage');
  if (!box) return;
  const id = box.dataset.id, typ = box.dataset.typ;
  const knoepfe = [...box.querySelectorAll('.u-knopf')];
  const ergebnis = box.querySelector('.u-ergebnis'), fuss = box.querySelector('.u-fuss');
  const merker = 'lo_umfrage_' + id;
  const lies = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const schreib = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };
  const ohneSymbol = t => t.replace(/^[^\p{L}\p{N}]+/u, '').trim();
  let meine = lies(merker);

  function geraet() {
    let g = lies('lo_geraet');
    if (!g) { g = crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2); schreib('lo_geraet', g); }
    return g;
  }

  function zeigen(zaehler) {
    if (typ === 'reaktion') {
      const k = knoepfe[0], z = k.querySelector('.u-zahl') || k.appendChild(document.createElement('span'));
      z.className = 'u-zahl';
      z.textContent = zaehler[0] ? String(zaehler[0]) : '';
      if (meine !== null) { k.classList.add('an'); k.disabled = true; }
      return;
    }
    if (meine === null) return;
    const summe = zaehler.reduce((a, b) => a + b, 0) || 1;
    ergebnis.textContent = '';
    knoepfe.forEach((k, i) => {
      const pro = Math.round(100 * (zaehler[i] || 0) / summe);
      const zeile = document.createElement('div');
      zeile.className = 'u-balken' + (String(i) === meine ? ' meins' : '');
      const fuell = document.createElement('i'), name = document.createElement('span'), wert = document.createElement('b');
      name.textContent = k.textContent;
      wert.textContent = pro + ' %';
      zeile.append(fuell, name, wert);
      ergebnis.append(zeile);
      requestAnimationFrame(() => { fuell.style.width = pro + '%'; });
    });
    const gesamt = zaehler.reduce((a, b) => a + b, 0);
    if (gesamt >= 20) {
      const s = document.createElement('p');
      s.className = 'u-stimmen';
      s.textContent = gesamt + ' Stimmen';
      ergebnis.append(s);
    }
    box.querySelector('.u-knoepfe').hidden = true;
    ergebnis.hidden = false;
    if (fuss) fuss.hidden = false;
  }

  async function laden() {
    const r = await fetch('/api?umfrage=' + id);
    if (!r.ok) throw new Error('umfrage ' + r.status);
    return (await r.json()).zaehler || [];
  }

  knoepfe.forEach((k, i) => k.addEventListener('click', async () => {
    if (meine !== null) return;
    knoepfe.forEach(x => { x.disabled = true; });
    try {
      const r = await fetch('/api?umfrage', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, antwort: i, geraet: geraet() }) });
      if (!r.ok) throw new Error('umfrage ' + r.status);
      meine = String(i);
      schreib(merker, meine);
      zeigen((await r.json()).zaehler || []);
    } catch (e) {
      box.hidden = true;
    }
  }));

  const warum = box.querySelector('.u-warum');
  if (warum) warum.addEventListener('click', e => {
    e.preventDefault();
    const form = document.getElementById('kommentar-form'), feld = document.getElementById('k-text');
    if (form && feld && getComputedStyle(form).display !== 'none') {
      if (!feld.value.trim() && meine !== null) feld.value = ohneSymbol(knoepfe[Number(meine)].textContent) + ', weil ';
      feld.scrollIntoView({ behavior: 'smooth', block: 'center' });
      feld.focus();
      feld.setSelectionRange(feld.value.length, feld.value.length);
    } else {
      (document.querySelector('.kommentare') || document.body).scrollIntoView({ behavior: 'smooth' });
    }
  });

  // Ohne Verbindung zur Datenbank bleibt die Box unsichtbar, die Seite funktioniert weiter
  if (typ === 'reaktion' || meine !== null) {
    laden().then(z => { box.hidden = false; zeigen(z); }).catch(() => {});
  } else {
    box.hidden = false;
  }
})();
