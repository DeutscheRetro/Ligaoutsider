// avatar.js – Spieler-Avatare ohne Foto: Mini-Trikot oder runder Avatar in den Vereinsfarben.
//
// Reines SVG, keine Bilddateien, keine Rechte Dritter. Die Rückennummer (oder, wenn es
// keine gibt, die Initialen) steht in der Farbe mit dem besten Kontrast zum Trikot.
//
//   LoAvatar.html({ name: 'Harry Kane', nr: 9, logo: 'logos/bayern.png', size: 40 })
//   LoAvatar.html({ name: 'Harry Kane', primary: '#DC052D', secondary: '#FFFFFF', form: 'kreis' })
//   LoAvatar.svg(...)  // wie html(), nur der nackte SVG-Text
//
// Vereinsfarben: LoAvatar.FARBEN, Schlüssel = Dateiname des Wappens ohne Endung
// (logos/bayern.png → "bayern"), so wie ihn spieler_db.json schon liefert.
(function () {
  const FARBEN = {
    bayern:     { primary: '#DC052D', secondary: '#FFFFFF' },
    dortmund:   { primary: '#FDE100', secondary: '#111111' },
    leverkusen: { primary: '#E32221', secondary: '#111111' },
    leipzig:    { primary: '#DD013F', secondary: '#0C2043' },
    frankfurt:  { primary: '#E1000F', secondary: '#111111' },
    stuttgart:  { primary: '#E32219', secondary: '#FFFFFF' },
    freiburg:   { primary: '#E2001A', secondary: '#111111' },
    hoffenheim: { primary: '#1961B5', secondary: '#FFFFFF' },
    werder:     { primary: '#1D9053', secondary: '#FFFFFF' },
    gladbach:   { primary: '#00A651', secondary: '#111111' },
    mainz:      { primary: '#C3141E', secondary: '#FFFFFF' },
    augsburg:   { primary: '#BA3733', secondary: '#006633' },
    union:      { primary: '#EB1923', secondary: '#FDE100' },
    koeln:      { primary: '#EC1C24', secondary: '#FFFFFF' },
    hsv:        { primary: '#0A3A7C', secondary: '#FFFFFF' },
    schalke:    { primary: '#004D9D', secondary: '#FFFFFF' },
    paderborn:  { primary: '#0063AF', secondary: '#111111' },
    elversberg: { primary: '#1A1A1A', secondary: '#FFFFFF' },
  };
  const STANDARD = { primary: '#4A5568', secondary: '#FFFFFF' };

  const esc = t => String(t ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function hex(c) {
    c = String(c || '').replace('#', '');
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    return /^[0-9a-f]{6}$/i.test(c) ? c : null;
  }
  function luminanz(c) {
    const h = hex(c); if (!h) return 0;
    const k = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255)
      .map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  }
  const kontrast = (a, b) => { const x = luminanz(a), y = luminanz(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  // Lesbare Schriftfarbe: Weiß oder Fast-Schwarz, je nachdem was vom Trikot besser absetzt
  const textfarbe = bg => kontrast(bg, '#FFFFFF') >= kontrast(bg, '#111111') ? '#FFFFFF' : '#111111';

  function farbenFuer(o) {
    if (o.primary) return { primary: o.primary, secondary: o.secondary || textfarbe(o.primary) };
    const schluessel = String(o.logo || o.verein || '').split('/').pop().replace(/\.\w+$/, '').toLowerCase();
    return FARBEN[schluessel] || STANDARD;
  }

  function initialen(name) {
    const t = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!t.length) return '?';
    const erster = t[0][0], letzter = t.length > 1 ? t[t.length - 1][0] : (t[0][1] || '');
    return (erster + letzter).toUpperCase();
  }

  let zaehler = 0;
  function svg(o) {
    o = o || {};
    const { primary, secondary } = farbenFuer(o);
    const gross = Math.max(16, Number(o.size) || 40);
    const hatNr = o.nr !== undefined && o.nr !== null && String(o.nr).trim() !== '';
    const inhalt = hatNr ? String(o.nr).trim().slice(0, 2) : initialen(o.name);
    const schrift = textfarbe(primary);
    // Rand/Kragen in der Zweitfarbe, aber nur wenn sie sich vom Trikot abhebt
    const akzent = kontrast(primary, secondary) >= 1.6 ? secondary : textfarbe(primary);
    const id = 'lo-av-' + (++zaehler);
    const titel = esc(o.name || '');
    const fs = inhalt.length > 1 ? (hatNr ? 31 : 27) : 42;      // zwei Zeichen müssen in die 46 Einheiten Trikotbreite passen

    if (o.form === 'kreis') {
      return `<svg class="lo-avatar" role="img" aria-label="${titel}" width="${gross}" height="${gross}" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="flex:none">`
        + `<circle cx="50" cy="50" r="47" fill="${primary}"/>`
        + `<circle cx="50" cy="50" r="47" fill="none" stroke="${akzent}" stroke-width="5"/>`
        + `<text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-family="Inter,system-ui,sans-serif" font-weight="800" font-size="${fs + 4}" fill="${schrift}">${esc(inhalt)}</text></svg>`;
    }
    // Mini-Trikot: Körper, Ärmel mit Bündchen, Kragen
    return `<svg class="lo-avatar" role="img" aria-label="${titel}" width="${gross}" height="${gross}" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="flex:none">`
      + `<defs><clipPath id="${id}"><path d="M31 10 L43 6 Q50 15 57 6 L69 10 L95 27 L85 47 L73 40 L73 92 L27 92 L27 40 L15 47 L5 27 Z"/></clipPath></defs>`
      + `<g clip-path="url(#${id})">`
      + `<rect x="0" y="0" width="100" height="100" fill="${primary}"/>`
      + `<path d="M0 36 L21 49 L15 58 L-6 45 Z" fill="${akzent}"/>`            // Bündchen links
      + `<path d="M100 36 L79 49 L85 58 L106 45 Z" fill="${akzent}"/>`        // Bündchen rechts
      + `<rect x="27" y="86" width="46" height="6" fill="${akzent}"/>`        // Saum
      + `</g>`
      + `<path d="M31 10 L43 6 Q50 15 57 6 L69 10 L95 27 L85 47 L73 40 L73 92 L27 92 L27 40 L15 47 L5 27 Z" fill="none" stroke="rgba(0,0,0,.28)" stroke-width="2" stroke-linejoin="round"/>`
      + `<path d="M43 6 Q50 15 57 6" fill="none" stroke="${akzent}" stroke-width="5" stroke-linecap="round"/>`  // Kragen
      + `<text x="50" y="58" text-anchor="middle" dominant-baseline="central" font-family="Inter,system-ui,sans-serif" font-weight="800" font-size="${fs}" fill="${schrift}">${esc(inhalt)}</text></svg>`;
  }

  window.LoAvatar = { FARBEN, svg, html: svg, farbenFuer, textfarbe, initialen };
})();
