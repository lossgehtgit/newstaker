/* News-Taker - Frontend.
   Vanilla JS ohne Buildstep: der Rechner hier hat kein Node.

   Die Zustandsfuehrung ist absichtlich schlicht: der Server liefert ein
   fertiges Board, das Frontend rendert es. Gelesen/Gemerkt geht sofort an den
   Server zurueck, damit Mac und iPhone denselben Stand zeigen. */

'use strict';

const $ = (id) => document.getElementById(id);

const state = {
  board: null,
  weather: null,
  markets: null,
  topic: '',
  hideRead: false,
  open: new Set(),      // aufgeklappte Teaser
  searchMode: 'all',
};

/* ----------------------------------------------------------------- Hilfen */

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.error || `HTTP ${res.status}`);
  }
  return res.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function openArticle(url) {
  window.open(url, '_blank', 'noopener');
}

/* ------------------------------------------------------------- Kopfbereich */

function renderClock() {
  const now = new Date();
  $('clock').textContent =
    String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');

  const weekday = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'][now.getDay()];
  const month = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli',
                 'August', 'September', 'Oktober', 'November', 'Dezember'][now.getMonth()];
  $('headdate').textContent =
    `${weekday.slice(0, 2).toUpperCase()} ${String(now.getDate()).padStart(2, '0')}.` +
    `${String(now.getMonth() + 1).padStart(2, '0')}.${now.getFullYear()}`;
  document.title = `News-Taker · ${now.getDate()}. ${month}`;
}

function renderFetchLine() {
  const stats = state.board ? state.board.stats : null;
  if (!stats) return;
  let when = '–';
  if (state.board.lastFetchAt) {
    const then = new Date(state.board.lastFetchAt);
    const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
    when = mins < 1 ? 'GERADE' : mins < 60 ? `VOR ${mins} MIN` : `VOR ${Math.round(mins / 60)} STD`;
  }
  $('fetchline').textContent = `${stats.sources} QUELLEN · ${when}`;
}

function renderWeather() {
  const wx = state.weather;
  if (!wx) return;
  $('weathercity').textContent = wx.cityLabel;
  const rail = $('weatherdays');
  rail.replaceChildren();
  wx.days.forEach((day) => {
    const box = el('div', 'weather-day');
    box.appendChild(el('div', 'd', day.day));
    const icon = el('div', 'i', day.icon);
    icon.title = day.label;
    box.appendChild(icon);
    const temp = el('div', 't');
    temp.append(`${day.hi}°`);
    const lo = el('span');
    lo.textContent = `/${day.lo}`;
    temp.appendChild(lo);
    box.appendChild(temp);
    rail.appendChild(box);
  });
}

/* --------------------------------------------------------- Marktuebersicht
   Ersetzt die fruehere Cluster-Uebersicht. Reine Kennzahlen aus echten
   Kursdaten (Tagespreis, Veraenderung ueber mehrere Jahre) - keine Bewertung,
   keine Anlageempfehlung, siehe newstaker/markets.py. */

function renderMarketColumn(elementId, rows) {
  const box = $(elementId);
  box.replaceChildren();
  rows.forEach((row) => {
    const line = el('div', 'mk-row');
    line.appendChild(el('div', 'mk-name', row.name));
    const meta = el('div', 'mk-line');
    meta.appendChild(el('span', 'mk-price', `${row.price} ${row.currency}`));
    const sign = row.changePct >= 0 ? '+' : '';
    const chg = el('span', 'mk-chg ' + (row.changePct >= 0 ? 'is-pos' : 'is-neg'), `${sign}${row.changePct}%`);
    meta.appendChild(chg);
    line.appendChild(meta);
    box.appendChild(line);
  });
}

function renderMarkets() {
  const mk = state.markets;
  const section = $('markets');
  if (!mk || (!mk.etfs.length && !mk.stocks.length)) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  $('marketsage').textContent = `${mk.lookbackYears} JAHRE`;
  renderMarketColumn('markets-etf', mk.etfs);
  renderMarketColumn('markets-stock', mk.stocks);
}

/* ------------------------------------------------------------ Themen-Pills */

function renderPills() {
  const nav = $('pills');
  nav.replaceChildren();

  const entries = [{ key: '', label: 'Alle', count: state.board.stats.total }]
    .concat(state.board.topics);

  entries.forEach((topic) => {
    const pill = el('button', 'pill');
    pill.type = 'button';
    pill.textContent = topic.label;
    if (topic.count) {
      const n = el('span', 'n', topic.count);
      pill.appendChild(n);
    }
    if (topic.key === state.topic) pill.classList.add('is-active');
    pill.addEventListener('click', () => {
      state.topic = topic.key;
      loadBoard();
    });
    nav.appendChild(pill);
  });
}

/* ------------------------------------------------------------------ Feed */

function actionButtons(item, onChange) {
  const star = el('button', 'act' + (item.saved ? ' is-on' : ''));
  star.type = 'button';
  star.textContent = item.saved ? '★︎' : '☆︎';
  star.title = item.saved ? 'Gemerkt' : 'Für später merken';
  star.addEventListener('click', (ev) => {
    ev.stopPropagation();
    toggle(item, 'saved', onChange);
  });

  const check = el('button', 'act act-check' + (item.read ? ' is-on' : ''));
  check.type = 'button';
  check.textContent = item.read ? '✓' : '○';
  check.title = item.read ? 'Gelesen' : 'Als gelesen markieren';
  check.addEventListener('click', (ev) => {
    ev.stopPropagation();
    toggle(item, 'read', onChange);
  });

  return [star, check];
}

async function toggle(item, field, onChange) {
  const next = !item[field];
  item[field] = next;                       // sofort sichtbar
  if (onChange) onChange();
  try {
    const res = await api('/api/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: item.id, field, value: next }),
    });
    if (state.board) {
      state.board.stats.read = res.read;
      state.board.stats.saved = res.saved;
      renderFootline();
    }
  } catch (err) {
    item[field] = !next;                    // zuruecknehmen
    if (onChange) onChange();
    console.error('Status konnte nicht gespeichert werden:', err);
  }
}

function imageFor(item, className) {
  const img = el('img', className);
  img.src = item.image;
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.referrerPolicy = 'no-referrer';
  // Faellt ein Verlagsbild aus, springt die generierte Kachel ein - so bleibt
  // die Zusage "Bild bei jeder Headline" auch im Fehlerfall bestehen.
  img.addEventListener('error', () => {
    if (!img.dataset.fellBack) {
      img.dataset.fellBack = '1';
      img.src = `/tile/${item.id}.svg?s=${encodeURIComponent(item.source)}&t=${encodeURIComponent(item.topicLabel)}`;
    }
  }, { once: true });
  return img;
}

function clusterSources(item) {
  if (!item.cluster || item.cluster.sourceCount < 2) return null;
  const box = el('div', 'sources');
  const others = item.cluster.others || [];
  const seen = new Set([item.source]);
  others.forEach((other) => {
    if (seen.has(other.source)) return;
    seen.add(other.source);
    const chip = el('a', 'source-chip', other.source);
    chip.href = other.url;
    chip.target = '_blank';
    chip.rel = 'noopener';
    chip.title = other.title;
    box.appendChild(chip);
  });
  return box.childElementCount ? box : null;
}

function renderLead(item, rerender) {
  const node = el('article', 'lead' + (item.read ? ' is-read' : ''));

  const img = imageFor(item, 'lead-img');
  img.addEventListener('click', () => openArticle(item.url));
  node.appendChild(img);

  node.appendChild(el('div', 'lead-kicker', item.kicker));

  const title = el('div', 'lead-title', item.title);
  title.addEventListener('click', () => openArticle(item.url));
  node.appendChild(title);

  if (item.teaser) node.appendChild(el('div', 'lead-teaser', item.teaser));

  const foot = el('div', 'lead-foot');
  const meta = el('div', 'lead-meta');
  meta.textContent = item.meta;
  if (item.cluster && item.cluster.sourceCount > 1) {
    meta.appendChild(el('span', 'cluster-note', `+${item.cluster.sourceCount - 1} QUELLEN`));
  }
  foot.appendChild(meta);
  actionButtons(item, rerender).forEach((b) => foot.appendChild(b));
  node.appendChild(foot);

  const sources = clusterSources(item);
  if (sources) node.appendChild(sources);

  return node;
}

function renderBrief(item, rerender) {
  const node = el('article', 'brief' + (item.read ? ' is-read' : ''));

  const img = imageFor(item, 'brief-img');
  img.addEventListener('click', () => openArticle(item.url));
  node.appendChild(img);

  const body = el('div', 'brief-body');
  const title = el('div', 'brief-title', item.title);
  title.addEventListener('click', () => openArticle(item.url));
  body.appendChild(title);

  const bits = [`${item.dateShort} ${item.time}`, item.kicker, item.source.toUpperCase()];
  if (item.cluster && item.cluster.sourceCount > 1) {
    bits.push(`${item.cluster.sourceCount} QUELLEN`);
  }
  const foot = el('div', 'brief-foot');
  foot.appendChild(el('div', 'brief-meta', bits.join(' · ')));
  actionButtons(item, rerender).forEach((b) => foot.appendChild(b));
  body.appendChild(foot);

  // Aufklappbarer Teaser - uebernommen aus Entwurf 1b
  if (item.teaser) {
    const isOpen = state.open.has(item.id);
    if (isOpen) body.appendChild(el('div', 'brief-teaser', item.teaser));
    const more = el('button', 'brief-more', isOpen ? 'WENIGER' : 'MEHR');
    more.type = 'button';
    more.addEventListener('click', () => {
      if (isOpen) state.open.delete(item.id);
      else state.open.add(item.id);
      rerender();
    });
    body.appendChild(more);

    if (isOpen) {
      const sources = clusterSources(item);
      if (sources) body.appendChild(sources);
    }
  }

  node.appendChild(body);
  return node;
}

function renderFeed() {
  const feed = $('feed');
  const board = state.board;
  feed.replaceChildren();

  const total = board.leads.length + board.briefs.length;
  $('empty').hidden = total > 0;
  if (total === 0) return;

  board.leads.forEach((item) => feed.appendChild(renderLead(item, renderFeed)));

  if (board.briefs.length) {
    feed.appendChild(el('div', 'brief-head', `KURZMELDUNGEN · ${board.briefs.length}`));
    board.briefs.forEach((item) => feed.appendChild(renderBrief(item, renderFeed)));
  }
}

function renderFootline() {
  const s = state.board.stats;
  $('readline').textContent = `${s.read} GELESEN · ${s.saved} GEMERKT`;
  $('hideread').textContent = state.hideRead ? 'GELESENE ZEIGEN' : 'GELESENE AUSBLENDEN';
}

/* ------------------------------------------------------------------ Laden */

async function loadBoard() {
  const params = new URLSearchParams();
  if (state.topic) params.set('topic', state.topic);
  if (state.hideRead) params.set('hide_read', '1');

  try {
    state.board = await api('/api/board?' + params.toString());
  } catch (err) {
    $('fetchline').textContent = 'SERVER NICHT ERREICHBAR';
    console.error(err);
    return;
  }
  renderFetchLine();
  renderPills();
  renderFeed();
  renderFootline();
}

async function loadMarkets() {
  try {
    state.markets = await api('/api/markets');
    renderMarkets();
  } catch (err) {
    console.error('Marktdaten nicht verfügbar:', err);
  }
}

async function loadWeather(city) {
  const params = city ? '?city=' + encodeURIComponent(city) : '';
  try {
    state.weather = await api('/api/weather' + params);
    renderWeather();
  } catch (err) {
    console.error('Wetter nicht verfügbar:', err);
  }
}

/* ------------------------------------------------------------------ Suche */

function renderSearchResults(results, query) {
  const box = $('searchresults');
  box.replaceChildren();

  if (!results.length) {
    const hint = state.searchMode === 'saved' && !query
      ? 'Noch nichts gemerkt.\nMit ☆ eine Meldung für später ablegen.'
      : query ? `Nichts gefunden für „${query}“.` : 'Suchbegriff eingeben.';
    const node = el('div', 'search-hint');
    hint.split('\n').forEach((line, i) => {
      if (i) node.appendChild(document.createElement('br'));
      node.appendChild(document.createTextNode(line));
    });
    box.appendChild(node);
    return;
  }

  results.forEach((item) => {
    item.cluster = item.cluster || { sourceCount: 1, others: [] };
    box.appendChild(renderBrief(item, () => runSearch()));
  });
}

let searchTimer = null;

async function runSearch() {
  const query = $('searchinput').value.trim();
  const params = new URLSearchParams();
  params.set('q', query);
  if (state.searchMode === 'saved') params.set('saved', '1');

  if (!query && state.searchMode === 'all') {
    renderSearchResults([], '');
    return;
  }
  try {
    const res = await api('/api/search?' + params.toString());
    renderSearchResults(res.results, query);
  } catch (err) {
    console.error(err);
  }
}

function openSearch() {
  $('search').hidden = false;
  $('searchinput').focus();
  runSearch();
}

function closeSearch() {
  $('search').hidden = true;
  loadBoard();          // Status kann sich in der Suche geaendert haben
}

/* --------------------------------------------------------------- Bedienung */

function wire() {
  $('weather').addEventListener('click', () => {
    if (!state.weather) return;
    const cities = state.weather.cities;
    const next = cities[(cities.indexOf(state.weather.city) + 1) % cities.length];
    loadWeather(next);
  });

  $('hideread').addEventListener('click', () => {
    state.hideRead = !state.hideRead;
    loadBoard();
  });

  $('emptyreset').addEventListener('click', () => {
    state.topic = '';
    state.hideRead = false;
    loadBoard();
  });

  $('searchopen').addEventListener('click', openSearch);
  $('searchclose').addEventListener('click', closeSearch);

  $('searchinput').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runSearch, 180);
  });

  $('tab-all').addEventListener('click', () => {
    state.searchMode = 'all';
    $('tab-all').classList.add('is-active');
    $('tab-saved').classList.remove('is-active');
    runSearch();
  });

  $('tab-saved').addEventListener('click', () => {
    state.searchMode = 'saved';
    $('tab-saved').classList.add('is-active');
    $('tab-all').classList.remove('is-active');
    runSearch();
  });

  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && !$('search').hidden) closeSearch();
  });

  // Beim Zurueckkommen auf den Tab neu laden, damit der Abrufzeitpunkt stimmt.
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && $('search').hidden) {
      renderClock();
      loadBoard();
    }
  });
}

/* ------------------------------------------------------------------ Start */

renderClock();
setInterval(renderClock, 30000);
wire();
loadWeather();
loadMarkets();
loadBoard();
