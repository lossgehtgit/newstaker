/* News-Taker - statische Cloud-Variante fuer GitHub Pages.
   Vanilla JS ohne Buildstep.

   Unterschied zur lokalen Live-Version (web/app.js): es gibt keinen Server.
   GitHub Actions legt alle 30 Minuten frische board.json/weather.json/
   markets.json/search.json unter data/ ab, egal ob der Mac laeuft oder
   schlaeft. Themen- und Gelesen-Filter laufen deshalb hier im Browser statt
   als Serverabfrage - in genau der Reihenfolge, in der es der Server bisher
   tat: erst Thema, dann Gelesen-Status, dann die ersten drei als Aufmacher.

   Gelesen/Gemerkt liegt in localStorage statt in einer Datenbank. Das heisst:
   der Status ist pro Geraet, Mac und iPhone sehen nicht mehr denselben Stand.
   Der Preis dafuer ist, dass das Board auch dann aktuell ist, wenn kein
   eigener Rechner laeuft - nur der GitHub-Actions-Runner muss wach sein,
   und das ist er immer. */

'use strict';

const $ = (id) => document.getElementById(id);

const LEAD_COUNT = 3;
const BOARD_LIMIT = 120;
const READ_KEY = 'newstaker.read';
const SAVED_KEY = 'newstaker.saved';

const state = {
  allItems: [],         // vollstaendige, nach Score sortierte Liste aus board.json
  topics: [],
  totalSources: 0,
  lastFetchAt: '',
  weather: null,
  markets: null,
  searchIndex: null,    // erst bei Bedarf geladen
  topic: '',
  hideRead: false,
  open: new Set(),      // aufgeklappte Teaser (nur diese Sitzung)
  searchMode: 'all',
};

/* ----------------------------------------------------------------- Hilfen */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function openArticle(url) {
  window.open(url, '_blank', 'noopener');
}

async function getJSON(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`HTTP ${res.status} bei ${path}`);
  return res.json();
}

/* --------------------------------------------------------- Lokaler Status */

function loadIdSet(key) {
  try {
    return new Set(JSON.parse(localStorage.getItem(key) || '[]'));
  } catch {
    return new Set();
  }
}

function saveIdSet(key, set) {
  try {
    localStorage.setItem(key, JSON.stringify([...set]));
  } catch (err) {
    console.error('localStorage nicht verfügbar:', err);
  }
}

const readSet = loadIdSet(READ_KEY);
const savedSet = loadIdSet(SAVED_KEY);

function isRead(id) { return readSet.has(id); }
function isSaved(id) { return savedSet.has(id); }

function setFlag(set, key, id, on) {
  if (on) set.add(id); else set.delete(id);
  saveIdSet(key, set);
}

/* ------------------------------------------------------------- Textfaltung
   Spiegelt newstaker/normalize.py:fold() - dieselbe Faltung wie beim
   Clustering/Suchindex auf der Python-Seite, damit "Zölle" und "zoelle"
   dasselbe finden. */

function fold(text) {
  return text
    .toLowerCase()
    .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '');   // kombinierende Diakritika (Akzente etc.)
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
  let when = '–';
  if (state.lastFetchAt) {
    const then = new Date(state.lastFetchAt);
    const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
    when = mins < 1 ? 'GERADE' : mins < 60 ? `VOR ${mins} MIN` : `VOR ${Math.round(mins / 60)} STD`;
  }
  $('fetchline').textContent = `${state.totalSources} QUELLEN · ${when}`;
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

/* --------------------------------------------------- Filtern (wie im Server)
   Reihenfolge bewusst identisch zu pipeline.build_board(): erst Thema, dann
   Gelesen-Status. Erst danach wird auf BOARD_LIMIT gekappt und in Aufmacher/
   Kurzmeldungen aufgeteilt. */

function applyFilters() {
  let items = state.allItems;
  if (state.topic) items = items.filter((e) => e.topic === state.topic);
  if (state.hideRead) items = items.filter((e) => !isRead(e.id));
  return items;
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

  const entries = [{ key: '', label: 'Alle', count: state.allItems.length }].concat(state.topics);

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
      renderBoard();
    });
    nav.appendChild(pill);
  });
}

/* ------------------------------------------------------------------ Feed */

function actionButtons(item, onChange) {
  const star = el('button', 'act' + (isSaved(item.id) ? ' is-on' : ''));
  star.type = 'button';
  star.textContent = isSaved(item.id) ? '★︎' : '☆︎';
  star.title = isSaved(item.id) ? 'Gemerkt' : 'Für später merken';
  star.addEventListener('click', (ev) => {
    ev.stopPropagation();
    setFlag(savedSet, SAVED_KEY, item.id, !isSaved(item.id));
    onChange();
  });

  const check = el('button', 'act act-check' + (isRead(item.id) ? ' is-on' : ''));
  check.type = 'button';
  check.textContent = isRead(item.id) ? '✓' : '○';
  check.title = isRead(item.id) ? 'Gelesen' : 'Als gelesen markieren';
  check.addEventListener('click', (ev) => {
    ev.stopPropagation();
    setFlag(readSet, READ_KEY, item.id, !isRead(item.id));
    onChange();
  });

  return [star, check];
}

function imageFor(item, className) {
  const img = el('img', className);
  img.src = item.image;
  img.alt = '';
  img.loading = 'lazy';
  img.decoding = 'async';
  img.referrerPolicy = 'no-referrer';
  // Faellt ein Verlagsbild aus (z.B. weil der Verlag es spaeter entfernt),
  // springt die vorgerenderte Kachel ein - die liegt bereits als Datei vor,
  // ganz ohne Server der sie auf Zuruf erzeugen koennte.
  img.addEventListener('error', () => {
    if (!img.dataset.fellBack) {
      img.dataset.fellBack = '1';
      img.src = `tiles/${item.id}.svg`;
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
  const node = el('article', 'lead' + (isRead(item.id) ? ' is-read' : ''));

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
  const node = el('article', 'brief' + (isRead(item.id) ? ' is-read' : ''));

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

function renderFeed(leads, briefs) {
  const feed = $('feed');
  feed.replaceChildren();

  const total = leads.length + briefs.length;
  $('empty').hidden = total > 0;
  if (total === 0) return;

  leads.forEach((item) => feed.appendChild(renderLead(item, renderBoard)));

  if (briefs.length) {
    feed.appendChild(el('div', 'brief-head', `KURZMELDUNGEN · ${briefs.length}`));
    briefs.forEach((item) => feed.appendChild(renderBrief(item, renderBoard)));
  }
}

function renderFootline() {
  $('readline').textContent = `${readSet.size} GELESEN · ${savedSet.size} GEMERKT`;
  $('hideread').textContent = state.hideRead ? 'GELESENE ZEIGEN' : 'GELESENE AUSBLENDEN';
}

/* -------------------------------------------------------- Board zeichnen */

function renderBoard() {
  const filtered = applyFilters();
  const capped = filtered.slice(0, BOARD_LIMIT);
  const leads = capped.slice(0, LEAD_COUNT);
  const briefs = capped.slice(LEAD_COUNT);

  renderFetchLine();
  renderPills();
  renderFeed(leads, briefs);
  renderFootline();
}

/* ------------------------------------------------------------------ Laden */

async function loadBoard() {
  try {
    const [board, weather, marketsData] = await Promise.all([
      getJSON('data/board.json'),
      getJSON('data/weather.json'),
      getJSON('data/markets.json'),
    ]);
    state.allItems = board.items;
    state.topics = board.topics;
    state.lastFetchAt = board.lastFetchAt;
    state.totalSources = new Set(board.items.map((e) => e.source)).size;
    state.weatherCities = Object.keys(weather);
    state.weatherData = weather;
    state.weatherCity = state.weatherCity || state.weatherCities[0];
    state.weather = weather[state.weatherCity];
    state.markets = marketsData;
  } catch (err) {
    $('fetchline').textContent = 'DATEN NICHT ERREICHBAR';
    console.error(err);
    return;
  }
  renderWeather();
  renderMarkets();
  renderBoard();
}

/* ------------------------------------------------------------------ Suche */

async function ensureSearchIndex() {
  if (state.searchIndex) return state.searchIndex;
  const raw = await getJSON('data/search.json');
  state.searchIndex = raw.map((item) => ({ ...item, folded: fold(item.title + ' ' + item.teaser) }));
  return state.searchIndex;
}

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

  if (!query && state.searchMode === 'all') {
    renderSearchResults([], '');
    return;
  }

  let index;
  try {
    index = await ensureSearchIndex();
  } catch (err) {
    console.error('Suchindex nicht verfügbar:', err);
    return;
  }

  let results = index;
  if (state.searchMode === 'saved') {
    results = results.filter((item) => isSaved(item.id));
  }
  if (query) {
    const needle = fold(query);
    results = results.filter((item) => item.folded.includes(needle));
  }
  renderSearchResults(results.slice(0, 60), query);
}

function openSearch() {
  $('search').hidden = false;
  $('searchinput').focus();
  runSearch();
}

function closeSearch() {
  $('search').hidden = true;
  renderBoard();          // Status kann sich in der Suche geaendert haben
}

/* --------------------------------------------------------------- Bedienung */

function wire() {
  $('weather').addEventListener('click', () => {
    if (!state.weatherCities) return;
    const idx = state.weatherCities.indexOf(state.weatherCity);
    state.weatherCity = state.weatherCities[(idx + 1) % state.weatherCities.length];
    state.weather = state.weatherData[state.weatherCity];
    renderWeather();
  });

  $('hideread').addEventListener('click', () => {
    state.hideRead = !state.hideRead;
    renderBoard();
  });

  $('emptyreset').addEventListener('click', () => {
    state.topic = '';
    state.hideRead = false;
    renderBoard();
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

  // Beim Zurueckkommen auf den Tab neu laden - die Daten koennten sich in der
  // Zwischenzeit per Cron aktualisiert haben.
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
loadBoard();
