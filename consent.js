// Einwilligung für Google Analytics: ohne Zustimmung wird nichts von Google geladen.
(function () {
  var ID = 'G-SP8DWFL2SE', KEY = 'lo_consent';
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { dataLayer.push(arguments); };   // Aufrufe bleiben ohne Einwilligung wirkungslos
  var stand = null;
  try { stand = localStorage.getItem(KEY); } catch (e) {}

  function laden() {
    if (window._loGa) return;
    window._loGa = true;
    var s = document.createElement('script');
    s.async = true; s.src = 'https://www.googletagmanager.com/gtag/js?id=' + ID;
    document.head.appendChild(s);
    gtag('js', new Date());
    gtag('config', ID);
  }
  function speichern(w) {
    try { localStorage.setItem(KEY, w); } catch (e) {}
    var b = document.getElementById('lo-consent'); if (b) b.remove();
    if (w === 'ja') laden();
    else if (window._loGa) location.reload();   // Widerruf: Google-Skript wieder loswerden
  }
  function banner() {
    if (document.getElementById('lo-consent')) return;
    var d = document.createElement('div');
    d.id = 'lo-consent'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-label', 'Cookie-Einwilligung');
    d.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;max-width:560px;margin:0 auto;' +
      'background:var(--bg2,#151515);color:var(--text,#eee);border:1px solid var(--border2,#333);border-radius:12px;' +
      'padding:16px 18px;box-shadow:0 10px 40px rgba(0,0,0,.5);font:14px/1.5 inherit;font-family:inherit';
    d.innerHTML = '<p style="margin:0 0 12px">Wir nutzen Google Analytics, um zu sehen, welche Artikel gelesen werden. ' +
      'Dafür setzt Google Cookies. Das passiert nur mit deiner Zustimmung. ' +
      '<a href="/datenschutz.html" style="color:var(--accent,#e8c000)">Mehr in der Datenschutzerklärung</a>.</p>' +
      '<div style="display:flex;gap:10px;flex-wrap:wrap">' +
      '<button type="button" data-w="ja" style="flex:1;min-width:130px;background:var(--accent,#e8c000);color:#000;border:0;border-radius:8px;padding:10px 14px;font-weight:800;cursor:pointer">Akzeptieren</button>' +
      '<button type="button" data-w="nein" style="flex:1;min-width:130px;background:transparent;color:inherit;border:1px solid var(--border2,#444);border-radius:8px;padding:10px 14px;font-weight:700;cursor:pointer">Ablehnen</button></div>';
    d.addEventListener('click', function (e) { var w = e.target.getAttribute && e.target.getAttribute('data-w'); if (w) speichern(w); });
    document.body.appendChild(d);
  }
  window.loCookieEinstellungen = banner;
  if (stand === 'ja') laden();
  else if (stand !== 'nein') {
    if (document.body) banner(); else document.addEventListener('DOMContentLoaded', banner);
  }
})();
