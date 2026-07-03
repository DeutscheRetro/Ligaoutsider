// kommentare.js – Ligaoutsider Kommentarsystem
// Erwartet als Globals: SUPABASE_URL, SUPABASE_ANON, ADMIN_EMAIL
// Optional: ARTIKEL_ID (nur auf Artikelseiten)

(function () {
  let sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON);
  let aktuellerUser = null;
  let isAdmin = false;
  let ignorierteListe = JSON.parse(localStorage.getItem('lo_ignore') || '[]');

  // ─── Theme ───────────────────────────────────────────────────────────────────
  function applyTheme(t) {
    document.body.classList.toggle('light', t === 'light');
    const icon  = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');
    if (icon)  icon.textContent  = t === 'light' ? '🌙' : '☀️';
    if (label) label.textContent = t === 'light' ? 'Dunkel' : 'Hell';
  }
  applyTheme(localStorage.getItem('theme') || (document.body.classList.contains('light') ? 'light' : 'dark'));
  document.getElementById('theme-toggle')?.addEventListener('click', () => {
    const t = document.body.classList.contains('light') ? 'dark' : 'light';
    localStorage.setItem('theme', t); applyTheme(t);
  });

  // ─── Auth ────────────────────────────────────────────────────────────────────
  function anzeigeName(user) { return user.user_metadata?.full_name || user.email; }

  async function setUser(user) {
    aktuellerUser = user;
    isAdmin = user.email === ADMIN_EMAIL;
    // Netlify JWT an Supabase übergeben damit RLS Policies greifen
    try {
      const token = await user.jwt();
      sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON, {
        global: { headers: { Authorization: `Bearer ${token}` } }
      });
    } catch(e) { /* anon bleibt */ }
    const name = anzeigeName(user);
    const el = document.getElementById('user-name');
    if (el) {
      el.textContent = name;
      el.style.cursor = 'pointer';
      el.onclick = () => window._zeigeProfil(name, user.email);
    }
    document.getElementById('user-info')?.style && (document.getElementById('user-info').style.display = 'flex');
    document.getElementById('login-btn')  && (document.getElementById('login-btn').style.display = 'none');
    document.getElementById('signup-btn') && (document.getElementById('signup-btn').style.display = 'none');
    if (document.getElementById('k-gasthinweis')) document.getElementById('k-gasthinweis').style.display = 'none';
    if (document.getElementById('kommentar-form')) document.getElementById('kommentar-form').style.display = 'block';
    if (document.getElementById('k-username'))     document.getElementById('k-username').textContent = name;
    if (typeof ARTIKEL_ID !== 'undefined') ladeKommentare();
  }

  function clearUser() {
    aktuellerUser = null; isAdmin = false;
    sb = supabase.createClient(SUPABASE_URL, SUPABASE_ANON);
    document.getElementById('user-info')  && (document.getElementById('user-info').style.display = 'none');
    document.getElementById('login-btn')  && (document.getElementById('login-btn').style.display = '');
    document.getElementById('signup-btn') && (document.getElementById('signup-btn').style.display = '');
    if (document.getElementById('k-gasthinweis')) document.getElementById('k-gasthinweis').style.display = 'block';
    if (document.getElementById('kommentar-form')) document.getElementById('kommentar-form').style.display = 'none';
    if (typeof ARTIKEL_ID !== 'undefined') ladeKommentare();
  }

  if (window.netlifyIdentity) {
    netlifyIdentity.on('init',   u => { if (u) setUser(u); });
    netlifyIdentity.on('login',  u => { setUser(u); netlifyIdentity.close(); });
    netlifyIdentity.on('logout', clearUser);
  }
  document.getElementById('login-btn')  ?.addEventListener('click', e => { e.preventDefault(); netlifyIdentity.open('login'); });
  document.getElementById('signup-btn') ?.addEventListener('click', e => { e.preventDefault(); netlifyIdentity.open('signup'); });
  document.getElementById('logout-btn') ?.addEventListener('click', e => { e.preventDefault(); netlifyIdentity.logout(); });

  // ─── Ban-Check ───────────────────────────────────────────────────────────────
  async function pruefeBan(email) {
    const { data } = await sb.from('user_bans').select('gebannt_bis, grund').eq('email', email).maybeSingle();
    if (!data) return null;
    if (data.gebannt_bis && new Date(data.gebannt_bis) < new Date()) {
      await sb.from('user_bans').delete().eq('email', email);
      return null;
    }
    return data;
  }

  // ─── Bereinigen ──────────────────────────────────────────────────────────────
  function bereinigen(text) {
    return text
      .replace(/<[^>]*>/g, '')
      .replace(/https?:\/\/\S+/gi, '')
      .replace(/www\.\S+/gi, '')
      .trim();
  }

  // ─── Votes ───────────────────────────────────────────────────────────────────
  async function vote(kommentarId, wert) {
    if (!aktuellerUser) return;
    const email = aktuellerUser.email;
    const { data: existing } = await sb.from('kommentar_votes')
      .select('id, vote').eq('kommentar_id', kommentarId).eq('voter_email', email).maybeSingle();
    if (existing) {
      if (existing.vote === wert) await sb.from('kommentar_votes').delete().eq('id', existing.id);
      else await sb.from('kommentar_votes').update({ vote: wert }).eq('id', existing.id);
    } else {
      await sb.from('kommentar_votes').insert({ kommentar_id: kommentarId, voter_email: email, vote: wert });
    }
    ladeKommentare();
  }
  window._vote = vote;

  // ─── Ignore ──────────────────────────────────────────────────────────────────
  window._ignoriereUser = function(email) {
    if (!ignorierteListe.includes(email)) {
      ignorierteListe.push(email);
      localStorage.setItem('lo_ignore', JSON.stringify(ignorierteListe));
    }
    ladeKommentare();
  };
  window._entIgnoriereUser = function(email) {
    ignorierteListe = ignorierteListe.filter(e => e !== email);
    localStorage.setItem('lo_ignore', JSON.stringify(ignorierteListe));
    ladeKommentare();
  };

  // ─── Ban-Modal (Admin) ───────────────────────────────────────────────────────
  window._zeigeBanModal = function(email, name) {
    let m = document.getElementById('ban-modal');
    if (m) m.remove();
    m = document.createElement('div');
    m.id = 'ban-modal';
    m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:2000;display:flex;align-items:center;justify-content:center';
    m.innerHTML = `
      <div style="background:var(--bg2);border:1px solid #c62828;border-radius:10px;padding:24px;max-width:320px;width:90%">
        <div style="font-size:15px;font-weight:800;color:#e53935;margin-bottom:16px">🚫 User bannen</div>
        <div style="font-size:13px;color:var(--text3);margin-bottom:12px">${name} (${email})</div>
        <select id="ban-dauer" style="width:100%;background:var(--bg4);border:1px solid var(--border2);border-radius:5px;color:var(--text);padding:8px;font-size:13px;margin-bottom:10px">
          <option value="1">1 Tag</option>
          <option value="7">7 Tage</option>
          <option value="30">30 Tage</option>
          <option value="0">Permanent</option>
        </select>
        <input id="ban-grund" placeholder="Grund (optional)" maxlength="200" style="width:100%;background:var(--bg4);border:1px solid var(--border2);border-radius:5px;color:var(--text);padding:8px;font-size:13px;margin-bottom:14px;box-sizing:border-box"/>
        <div style="display:flex;gap:8px">
          <button onclick="window._banUser('${email}','${name}')" style="flex:1;background:#c62828;color:#fff;border:none;border-radius:5px;padding:8px;font-weight:700;font-size:13px;cursor:pointer">Bannen</button>
          <button onclick="document.getElementById('ban-modal').remove()" style="flex:1;background:var(--bg4);color:var(--text);border:1px solid var(--border2);border-radius:5px;padding:8px;font-size:13px;cursor:pointer">Abbrechen</button>
        </div>
      </div>`;
    document.body.appendChild(m);
    m.addEventListener('click', e => { if (e.target === m) m.remove(); });
  };

  window._banUser = async function(email, name) {
    const tage = parseInt(document.getElementById('ban-dauer').value);
    const grund = document.getElementById('ban-grund').value.trim();
    const bis = tage === 0 ? null : new Date(Date.now() + tage * 86400000).toISOString();
    await sb.from('user_bans').upsert({
      email, grund: grund || null, gebannt_bis: bis, gebannt_von: aktuellerUser.email
    }, { onConflict: 'email' });
    document.getElementById('ban-modal')?.remove();
    document.getElementById('profil-modal')?.remove();
    ladeKommentare();
  };

  window._entbanneUser = async function(email) {
    await sb.from('user_bans').delete().eq('email', email);
    document.getElementById('profil-modal')?.remove();
    ladeKommentare();
  };

  // ─── Profil-Modal ────────────────────────────────────────────────────────────
  window._zeigeProfil = async function(name, email) {
    console.log('[Profil] öffne für', name, email);
    try {
    const [{ data: komms }, { data: banInfo }] = await Promise.all([
      sb.from('kommentare').select('id, erstellt_am').eq('email', email).neq('geloescht', true),
      sb.from('user_bans').select('gebannt_bis, grund').eq('email', email).maybeSingle()
    ]);

    const anzahl = komms?.length || 0;
    const dates  = komms?.map(k => new Date(k.erstellt_am)) || [];
    const dabei  = dates.length ? new Date(Math.min(...dates)).toLocaleDateString('de-DE') : '–';
    let ups = 0, downs = 0;
    if (komms?.length) {
      const ids = komms.map(k => k.id);
      const { data: voten } = await sb.from('kommentar_votes').select('vote').in('kommentar_id', ids);
      voten?.forEach(v => v.vote === 1 ? ups++ : downs++);
    }

    const istEigen   = aktuellerUser?.email === email;
    const istIgn     = ignorierteListe.includes(email);
    const istGebannt = !!banInfo;
    const banText    = istGebannt
      ? (banInfo.gebannt_bis ? `Gebannt bis ${new Date(banInfo.gebannt_bis).toLocaleDateString('de-DE')}` : 'Permanent gebannt')
      : '';

    let m = document.getElementById('profil-modal');
    if (!m) { m = document.createElement('div'); m.id = 'profil-modal'; document.body.appendChild(m); }
    m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:1000;display:flex;align-items:center;justify-content:center';
    m.innerHTML = `
      <div style="background:var(--bg2);border:1px solid var(--border2);border-radius:10px;padding:28px;max-width:340px;width:90%;position:relative">
        <button onclick="document.getElementById('profil-modal').remove()" style="position:absolute;top:12px;right:16px;background:none;border:none;color:var(--text3);font-size:18px;cursor:pointer">✕</button>
        ${istGebannt ? `<div style="background:#c62828;color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:4px;margin-bottom:12px;display:inline-block">🚫 ${banText}</div>` : ''}
        <div style="font-size:17px;font-weight:800;color:var(--accent);margin-bottom:2px">${name}</div>
        <div style="font-size:11px;color:var(--text4);margin-bottom:16px">${email}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:16px">
          <div style="background:var(--bg4);border-radius:6px;padding:10px;text-align:center">
            <div style="font-size:18px;font-weight:800;color:var(--text)">${anzahl}</div>
            <div style="font-size:10px;color:var(--text4)">Kommentare</div>
          </div>
          <div style="background:var(--bg4);border-radius:6px;padding:10px;text-align:center">
            <div style="font-size:14px;font-weight:700;color:#4caf50">▲ ${ups}</div>
            <div style="font-size:10px;color:var(--text4)">Upvotes</div>
          </div>
          <div style="background:var(--bg4);border-radius:6px;padding:10px;text-align:center">
            <div style="font-size:14px;font-weight:700;color:#e53935">▼ ${downs}</div>
            <div style="font-size:10px;color:var(--text4)">Downvotes</div>
          </div>
        </div>
        <div style="font-size:12px;color:var(--text4);margin-bottom:16px">Dabei seit: <span style="color:var(--text3)">${dabei}</span></div>
        ${!istEigen && aktuellerUser ? `
          <div style="display:flex;flex-direction:column;gap:8px">
            <button onclick="window._${istIgn ? 'entIgnoriereUser' : 'ignoriereUser'}('${email}');document.getElementById('profil-modal').remove()"
              style="padding:8px;background:${istIgn ? 'var(--bg4)' : 'var(--bg4)'};color:${istIgn ? 'var(--accent)' : 'var(--text)'};border:1px solid var(--border2);border-radius:5px;font-size:12px;font-weight:700;cursor:pointer">
              ${istIgn ? '✓ Nicht mehr ignorieren' : '🙈 Ignorieren'}
            </button>
            ${isAdmin ? `
              ${istGebannt
                ? `<button onclick="window._entbanneUser('${email}')" style="padding:8px;background:var(--bg4);color:#4caf50;border:1px solid #4caf50;border-radius:5px;font-size:12px;font-weight:700;cursor:pointer">✓ Entbannen</button>`
                : `<button onclick="window._zeigeBanModal('${email}','${name}')" style="padding:8px;background:#c62828;color:#fff;border:none;border-radius:5px;font-size:12px;font-weight:700;cursor:pointer">🚫 Bannen</button>`
              }` : ''}
          </div>` : ''}
      </div>`;
    m.addEventListener('click', e => { if (e.target === m) m.remove(); });
    } catch(err) { console.error('[Profil] Fehler:', err); }
  };

  // ─── Edit ────────────────────────────────────────────────────────────────────
  window._editKommentar = function(id) {
    const textEl = document.getElementById('kt-' + id);
    if (!textEl || textEl.dataset.editing) return;
    textEl.dataset.editing = '1';
    const original = textEl.textContent.trim();
    textEl.dataset.original = original;
    const ta = document.createElement('textarea');
    ta.id = 'edit-ta-' + id;
    ta.value = original;
    ta.style.cssText = 'width:100%;background:var(--bg4);border:1px solid var(--border2);border-radius:5px;color:var(--text);padding:8px;font-size:14px;min-height:80px;resize:vertical;font-family:inherit;box-sizing:border-box';
    const btnRow = document.createElement('div');
    btnRow.style.cssText = 'display:flex;gap:8px;margin-top:6px';
    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Speichern';
    saveBtn.style.cssText = 'background:var(--accent);color:#000;border:none;border-radius:4px;padding:5px 14px;font-size:12px;font-weight:700;cursor:pointer';
    saveBtn.addEventListener('click', () => window._saveEdit(id));
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Abbrechen';
    cancelBtn.style.cssText = 'background:var(--bg4);color:var(--text);border:1px solid var(--border2);border-radius:4px;padding:5px 12px;font-size:12px;cursor:pointer';
    cancelBtn.addEventListener('click', () => window._cancelEdit(id));
    btnRow.appendChild(saveBtn);
    btnRow.appendChild(cancelBtn);
    textEl.textContent = '';
    textEl.appendChild(ta);
    textEl.appendChild(btnRow);
  };

  window._cancelEdit = function(id) {
    const textEl = document.getElementById('kt-' + id);
    if (!textEl) return;
    const original = textEl.dataset.original || '';
    delete textEl.dataset.editing;
    delete textEl.dataset.original;
    textEl.textContent = original;
  };

  window._saveEdit = async function(id) {
    const ta = document.getElementById('edit-ta-' + id);
    if (!ta) return;
    const sauber = bereinigen(ta.value).slice(0, 1000);
    if (!sauber) return;
    await sb.from('kommentare').update({ inhalt: sauber, geaendert_am: new Date().toISOString() }).eq('id', id);
    ladeKommentare();
  };

  // ─── Löschen ─────────────────────────────────────────────────────────────────
  window._loescheKommentar = async function(id, hardDelete) {
    if (!confirm('Kommentar wirklich löschen?')) return;
    if (hardDelete) {
      await sb.from('kommentare').delete().eq('id', id);
    } else {
      await sb.from('kommentare').update({ geloescht: true, inhalt: '' }).eq('id', id);
    }
    ladeKommentare();
  };

  // ─── Kommentare laden ────────────────────────────────────────────────────────
  async function ladeKommentare() {
    const liste = document.getElementById('kommentar-liste');
    if (!liste || typeof ARTIKEL_ID === 'undefined') return;

    const { data, error } = await sb.from('kommentare')
      .select('id, name, email, inhalt, erstellt_am, geaendert_am, geloescht')
      .eq('artikel_id', ARTIKEL_ID)
      .neq('geloescht', true)
      .order('erstellt_am', { ascending: true });

    if (error) {
      console.error('[Kommentare] Supabase Fehler:', error);
      liste.innerHTML = '<p class="kommentar-leer">Fehler beim Laden.</p>';
      return;
    }
    if (!data?.length) {
      liste.innerHTML = '<p class="kommentar-leer">Noch keine Kommentare. Sei der Erste!</p>';
      return;
    }

    const ids = data.map(k => k.id);
    const { data: votes } = await sb.from('kommentar_votes')
      .select('kommentar_id, voter_email, vote').in('kommentar_id', ids);

    const voteMap = {};
    votes?.forEach(v => {
      if (!voteMap[v.kommentar_id]) voteMap[v.kommentar_id] = { up: 0, down: 0, mine: 0 };
      v.vote === 1 ? voteMap[v.kommentar_id].up++ : voteMap[v.kommentar_id].down++;
      if (aktuellerUser?.email === v.voter_email) voteMap[v.kommentar_id].mine = v.vote;
    });

    // Check ban for current user
    let banStatus = null;
    if (aktuellerUser) banStatus = await pruefeBan(aktuellerUser.email);

    // Lookup map für Event Delegation
    const kommentarMeta = {};

    liste.innerHTML = data.map(k => {
      if (k.geloescht) return `<div class="kommentar-item"><span style="font-size:13px;color:var(--text4);font-style:italic">— Kommentar gelöscht —</span></div>`;

      const ignoriert = ignorierteListe.includes(k.email);
      if (ignoriert) return `<div class="kommentar-item" data-ignoriert-email="${k.email}">
        <span style="font-size:12px;color:var(--text4);font-style:italic">Kommentar von ignoriertem Nutzer.
          <button data-action="entignoriere" data-email="${k.email}" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:12px;padding:0">Anzeigen</button>
        </span></div>`;

      kommentarMeta[k.id] = { name: k.name, email: k.email };

      const datum = new Date(k.erstellt_am).toLocaleDateString('de-DE', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
      const editTag = k.geaendert_am ? `<em style="font-size:10px;color:var(--text4)"> · editiert ${new Date(k.geaendert_am).toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'})}</em>` : '';

      const v = voteMap[k.id] || { up: 0, down: 0, mine: 0 };
      const upStyle   = v.mine === 1  ? 'color:#4caf50;font-weight:800' : 'color:var(--text4)';
      const downStyle = v.mine === -1 ? 'color:#e53935;font-weight:800' : 'color:var(--text4)';

      const istEigen = aktuellerUser?.email === k.email;

      const aktionen = `<div style="display:flex;gap:10px;margin-top:8px;align-items:center;flex-wrap:wrap">
        ${aktuellerUser ? `
          <button data-action="vote" data-id="${k.id}" data-wert="1"  style="background:none;border:none;cursor:pointer;font-size:13px;padding:0;${upStyle}">▲ ${v.up}</button>
          <button data-action="vote" data-id="${k.id}" data-wert="-1" style="background:none;border:none;cursor:pointer;font-size:13px;padding:0;${downStyle}">▼ ${v.down}</button>
          ${istEigen ? `<button data-action="edit" data-id="${k.id}" style="background:none;border:none;cursor:pointer;font-size:11px;color:var(--text4);padding:0">✏ Bearbeiten</button>` : ''}
          ${istEigen || isAdmin ? `<button data-action="loeschen" data-id="${k.id}" data-hard="${isAdmin && !istEigen}" style="background:none;border:none;cursor:pointer;font-size:11px;color:var(--text4);padding:0">🗑 Löschen</button>` : ''}
          <button data-action="profil" data-id="${k.id}" style="background:none;border:none;cursor:pointer;font-size:11px;color:var(--text4);padding:0">👤</button>
        ` : `<span style="font-size:13px;color:var(--text4)">▲ ${v.up}</span><span style="font-size:13px;color:var(--text4)">▼ ${v.down}</span>`}
      </div>`;

      return `<div class="kommentar-item" id="k-${k.id}">
        <div class="kommentar-kopf">
          <span class="kommentar-name" style="cursor:pointer" data-action="profil" data-id="${k.id}">${k.name}</span>
          <span class="kommentar-datum">${datum}${editTag}</span>
        </div>
        <div class="kommentar-text" id="kt-${k.id}">${k.inhalt.replace(/</g,'&lt;')}</div>
        ${aktionen}
      </div>`;
    }).join('');

    // Event Delegation — ein Listener für alle Aktionen
    liste.onclick = async e => {
      const el = e.target.closest('[data-action]');
      if (!el) return;
      const action = el.dataset.action;
      const id     = el.dataset.id;
      const meta   = id ? kommentarMeta[id] : null;
      if (action === 'profil')      window._zeigeProfil(meta.name, meta.email);
      if (action === 'vote')        vote(id, parseInt(el.dataset.wert));
      if (action === 'edit')        window._editKommentar(id);
      if (action === 'loeschen')    window._loescheKommentar(id, el.dataset.hard === 'true');
      if (action === 'entignoriere') window._entIgnoriereUser(el.dataset.email);
    };

    // Ban-Hinweis im Formular anzeigen
    const form = document.getElementById('kommentar-form');
    const hint = document.getElementById('k-gasthinweis');
    if (banStatus && form && hint) {
      form.style.display = 'none';
      hint.style.display = 'block';
      hint.innerHTML = banStatus.gebannt_bis
        ? `⛔ Deine Kommentarfunktion ist bis <strong>${new Date(banStatus.gebannt_bis).toLocaleDateString('de-DE')}</strong> gesperrt.${banStatus.grund ? ` Grund: ${banStatus.grund}` : ''}`
        : `⛔ Du wurdest permanent gesperrt.${banStatus.grund ? ` Grund: ${banStatus.grund}` : ''}`;
    }
  }

  // ─── Neuer Kommentar ─────────────────────────────────────────────────────────
  document.getElementById('kommentar-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    if (!aktuellerUser) return;

    const ban = await pruefeBan(aktuellerUser.email);
    if (ban) { ladeKommentare(); return; }

    const status  = document.getElementById('kommentar-status');
    const inhalt  = document.getElementById('k-text').value.trim();
    if (!inhalt) return;

    const name         = anzeigeName(aktuellerUser);
    const sauberName   = bereinigen(name).slice(0, 60);
    const sauberInhalt = bereinigen(inhalt).slice(0, 1000);
    if (!sauberName || !sauberInhalt) { status.textContent = 'Kein HTML oder Links erlaubt.'; return; }

    status.textContent = 'Wird gesendet…';
    const { error } = await sb.from('kommentare').insert({
      artikel_id: ARTIKEL_ID, name: sauberName, email: aktuellerUser.email, inhalt: sauberInhalt
    });

    if (error) {
      status.textContent = 'Fehler: ' + error.message;
    } else {
      status.textContent = '✓ Gespeichert!';
      document.getElementById('k-text').value = '';
      setTimeout(() => { status.textContent = ''; }, 3000);
      ladeKommentare();
    }
  });

  ladeKommentare();
})();
