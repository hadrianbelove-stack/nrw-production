/* NRW Admin — Morning Desk dashboard interactions.
   All writes go through existing admin endpoints:
   /toggle-status, /regenerate, /pull-quotes/*, /api/capsule/*  */

// ---------- helpers ----------

let toastTimer;
function toast(msg, isErr) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.toggle('err', !!isErr);
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

async function api(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Request failed');
  return json;
}

function filmData(cardEl) {
  const el = cardEl.querySelector('.film-data');
  return el ? JSON.parse(el.textContent) : {};
}

function markPendingSave() {
  const btn = document.getElementById('save-btn');
  btn.classList.add('pending');
  if (!btn.textContent.includes('•')) btn.textContent = 'Save Changes •';
}

// ---------- header / tools ----------

async function saveChanges() {
  const btn = document.getElementById('save-btn');
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = 'Saving… (can take a minute)';
  try {
    await api('/regenerate', {});
    btn.classList.remove('pending');
    btn.textContent = 'Save Changes';
    toast('Saved — site data regenerated');
  } catch (e) {
    btn.textContent = prev;
    toast('Save failed: ' + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

function toggleTools() {
  const p = document.getElementById('tools-panel');
  const showing = p.style.display !== 'none';
  p.style.display = showing ? 'none' : 'grid';
  document.getElementById('tools-tab').classList.toggle('active', !showing);
}

// ---------- day groups / progress ----------

function toggleDay(hdr) {
  const films = document.querySelector('.day-films[data-day="' + hdr.dataset.day + '"]');
  if (!films) return;
  const closed = films.classList.toggle('closed');
  hdr.querySelector('.dh-chev').textContent = closed ? '▸' : '▾';
}

function recountProgress() {
  const cards = document.querySelectorAll('#queue .mcard');
  const done = document.querySelectorAll('#queue .mcard.done-card').length;
  const total = cards.length;
  document.getElementById('pfill').style.width = (total ? (done / total) * 100 : 100) + '%';
  document.getElementById('ptxt').textContent = done + ' of ' + total + ' done';

  document.querySelectorAll('.day-hdr').forEach((hdr) => {
    const films = document.querySelector('.day-films[data-day="' + hdr.dataset.day + '"]');
    if (!films) return;
    const dayCards = films.querySelectorAll('.mcard');
    const dayDone = films.querySelectorAll('.mcard.done-card').length;
    const count = hdr.querySelector('.dh-count');
    const allDone = dayCards.length > 0 && dayDone === dayCards.length;
    hdr.classList.toggle('day-done', allDone);
    count.textContent = allDone ? '✓ done' : dayDone + ' / ' + dayCards.length;
  });

  const slopLeft = document.querySelectorAll('#slop-queue .mcard').length;
  document.getElementById('slop-count').textContent = slopLeft;
  document.getElementById('queue-badge').textContent = (total - done) + slopLeft;
}

// ---------- slop ----------

async function markSlop(movieId) {
  try {
    await api('/toggle-status', { movie_id: movieId, status_type: 'slop', value: true });
    removeCard(document.getElementById('card-' + movieId));
    markPendingSave();
    toast('Marked slop — hidden in slop-free mode');
  } catch (e) {
    toast(e.message, true);
  }
}

async function resolveSlop(movieId, isSlop) {
  const row = document.getElementById('slop-' + movieId);
  row.querySelectorAll('.sbtn').forEach((b) => (b.disabled = true));
  try {
    await api('/toggle-status', { movie_id: movieId, status_type: 'slop', value: isSlop });
    removeCard(row);
    markPendingSave();
    toast(isSlop ? 'Confirmed slop' : 'Rescued — marked NOT slop');
  } catch (e) {
    row.querySelectorAll('.sbtn').forEach((b) => (b.disabled = false));
    toast(e.message, true);
  }
}

function removeCard(el) {
  if (!el) return;
  el.style.transition = 'all 0.3s';
  el.style.opacity = '0';
  el.style.transform = 'translateX(40px)';
  setTimeout(() => {
    el.remove();
    recountProgress();
  }, 300);
}

// ---------- category tags (independent — a film can have several) ----------

async function setCategory(movieId, btn) {
  const wasOn = btn.dataset.on === '1';
  btn.disabled = true;
  try {
    await api('/toggle-status', { movie_id: movieId, status_type: btn.dataset.type, value: !wasOn });
    btn.dataset.on = wasOn ? '0' : '1';
    btn.classList.toggle('cat-on', !wasOn);
    markPendingSave();
    toast(wasOn ? 'Tag removed' : 'Tag added');
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
  }
}

// ---------- capsule modal ----------

let capCtx = null;

function openCapsule(movieId) {
  const card = document.getElementById('card-' + movieId);
  const data = filmData(card);
  capCtx = { id: movieId, title: data.title };
  document.getElementById('capsule-title').textContent = 'Capsule — ' + data.title;
  document.getElementById('capsule-text').value = data.capsule || '';
  document.getElementById('capsule-variants').innerHTML = '';
  document.getElementById('capsule-primer').textContent = '';
  document.getElementById('capsule-status').textContent = data.capsule
    ? '' : 'No capsule yet — generate variants to start.';
  document.getElementById('capsule-modal').style.display = 'block';
}

async function generateCapsule(force) {
  if (!capCtx) return;
  const status = document.getElementById('capsule-status');
  const genBtn = document.getElementById('capsule-gen-btn');
  status.textContent = 'Generating 3 variants — gathering sources + writing. This can take a minute or two…';
  genBtn.disabled = true;
  try {
    const res = await api('/api/capsule/generate', { movie_id: capCtx.id, force: !!force });
    status.textContent = '';
    const wrap = document.getElementById('capsule-variants');
    wrap.innerHTML = '';
    res.capsules.forEach((text, i) => {
      const div = document.createElement('div');
      div.className = 'variant';
      const words = text.trim().split(/\s+/).length;
      div.innerHTML = '<span class="v-num">' + (i + 1) + '.</span>' +
        '<span class="v-text"></span><span class="v-words">(' + words + ' words)</span>';
      div.querySelector('.v-text').textContent = text;
      div.onclick = () => {
        document.getElementById('capsule-text').value = text;
        toast('Variant ' + (i + 1) + ' loaded — edit freely, then approve');
      };
      wrap.appendChild(div);
    });
    document.getElementById('capsule-primer').textContent =
      res.factoid_primer ? 'FACTOID PRIMER\n' + res.factoid_primer : '';
  } catch (e) {
    status.textContent = 'Generation failed: ' + e.message;
  } finally {
    genBtn.disabled = false;
  }
}

async function approveCapsule() {
  if (!capCtx) return;
  const text = document.getElementById('capsule-text').value.trim();
  if (!text) { toast('Capsule text is empty', true); return; }
  const btn = document.getElementById('capsule-approve-btn');
  btn.disabled = true;
  try {
    await api('/api/capsule/approve', { movie_id: capCtx.id, text: text });
    const card = document.getElementById('card-' + capCtx.id);
    if (card) {
      card.classList.add('done-card');
      const step = card.querySelector('[data-step="capsule"]');
      step.classList.add('on');
      step.textContent = '✓ Capsule';
      const dataEl = card.querySelector('.film-data');
      const data = JSON.parse(dataEl.textContent);
      data.capsule = text;
      dataEl.textContent = JSON.stringify(data);
      const title = card.querySelector('.m-title');
      if (!title.textContent.startsWith('✅')) title.textContent = '✅ ' + title.textContent;
    }
    recountProgress();
    closeModal('capsule-modal');
    toast('Capsule approved — live in data.json + training bank');
  } catch (e) {
    toast(e.message, true);
  } finally {
    btn.disabled = false;
  }
}

// ---------- quotes modal ----------

let quoteCtx = null;

async function openQuotes(movieId) {
  const card = document.getElementById('card-' + movieId);
  const data = filmData(card);
  quoteCtx = { id: movieId, cacheKey: null, quotes: [] };
  document.getElementById('quotes-title').textContent = 'Pull Quotes — ' + data.title;
  document.getElementById('quotes-list').innerHTML = '';
  document.getElementById('quotes-status').textContent = 'Loading quotes…';
  document.getElementById('quotes-modal').style.display = 'block';
  await loadQuotes();
}

async function loadQuotes() {
  const status = document.getElementById('quotes-status');
  try {
    const res = await fetch('/api/pull-quotes/' + quoteCtx.id);
    const json = await res.json();
    quoteCtx.cacheKey = json.cache_key;
    quoteCtx.quotes = json.quotes || [];
    status.textContent = quoteCtx.quotes.length
      ? '' : 'No quotes scraped yet for this film — add one manually below.';
    renderQuotes();
  } catch (e) {
    status.textContent = 'Failed to load quotes: ' + e.message;
  }
}

function renderQuotes() {
  const list = document.getElementById('quotes-list');
  list.innerHTML = '';
  quoteCtx.quotes.forEach((q, i) => {
    const row = document.createElement('div');
    row.className = 'quote-row' + (q.selected ? ' sel' : '');
    row.innerHTML =
      '<span class="q-num">' + (i + 1) + '</span>' +
      '<div class="q-main"><div class="q-text"></div><div class="q-src"></div></div>' +
      '<button class="q-edit" title="Trim / edit">✎</button>';
    row.querySelector('.q-text').textContent = '“' + q.text + '”';
    row.querySelector('.q-src').textContent = (q.source || '—') + (q.pool === 'lb_quotes' ? ' · Letterboxd' : '');
    row.onclick = () => toggleQuote(i, row);
    row.querySelector('.q-edit').onclick = (ev) => { ev.stopPropagation(); editQuote(i, row); };
    list.appendChild(row);
  });
}

async function toggleQuote(i, row) {
  const q = quoteCtx.quotes[i];
  try {
    const res = await api('/pull-quotes/toggle', { cache_key: quoteCtx.cacheKey, source: q.pool, index: q.index });
    q.selected = res.selected;
    row.classList.toggle('sel', q.selected);
    updateQuoteStep();
    markPendingSave();
  } catch (e) {
    toast(e.message, true);
  }
}

function editQuote(i, row) {
  const q = quoteCtx.quotes[i];
  const main = row.querySelector('.q-main');
  main.innerHTML = '';
  const ta = document.createElement('textarea');
  ta.rows = 3;
  ta.value = q.text;
  const save = document.createElement('button');
  save.className = 'xbtn primary';
  save.style.marginTop = '6px';
  save.textContent = 'Save trim';
  save.onclick = async (ev) => {
    ev.stopPropagation();
    try {
      await api('/pull-quotes/edit', {
        cache_key: quoteCtx.cacheKey, source: q.pool, index: q.index, text: ta.value.trim(),
      });
      q.text = ta.value.trim();
      renderQuotes();
      markPendingSave();
      toast('Quote updated in cache');
    } catch (e) {
      toast(e.message, true);
    }
  };
  ta.onclick = (ev) => ev.stopPropagation();
  main.appendChild(ta);
  main.appendChild(save);
}

async function addQuote() {
  const text = document.getElementById('quote-add-text').value.trim();
  const critic = document.getElementById('quote-add-critic').value.trim();
  if (!text) { toast('Quote text is empty', true); return; }
  try {
    await api('/pull-quotes/add', { cache_key: quoteCtx.cacheKey, text: text, critic: critic });
    document.getElementById('quote-add-text').value = '';
    document.getElementById('quote-add-critic').value = '';
    await loadQuotes();
    toast('Quote added');
  } catch (e) {
    toast(e.message, true);
  }
}

function updateQuoteStep() {
  const card = document.getElementById('card-' + quoteCtx.id);
  if (!card) return;
  const n = quoteCtx.quotes.filter((q) => q.selected).length;
  const step = card.querySelector('[data-step="quotes"]');
  step.classList.toggle('on', n > 0);
  step.textContent = (n > 0 ? '✓ ' : '') + 'Quotes' + (n > 0 ? ' (' + n + ')' : '');
}

// ---------- modals ----------

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeModal('capsule-modal');
    closeModal('quotes-modal');
  }
});
