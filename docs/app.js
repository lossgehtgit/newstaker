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
const FEED_PAGE_SIZE = 10;
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
  sourceFilter: '',
  feedVisible: FEED_PAGE_SIZE,
  marketFilter: {
    etf: { query: '', sort: 'default' },
    stock: { query: '', sort: 'default' },
  },
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

function weatherDetailRow(label, value) {
  const row = el('div', 'wd-row');
  row.appendChild(el('span', 'wd-label', label));
  row.appendChild(el('span', 'wd-value', value));
  return row;
}

function showWeatherDetail(day) {
  const panel = $('weatherdetail');
  panel.replaceChildren();
  if (!day) return;
  panel.appendChild(el('div', 'wd-title', day.day));
  panel.appendChild(weatherDetailRow('Sonnenaufgang', day.sunrise || '–'));
  panel.appendChild(weatherDetailRow('Sonnenuntergang', day.sunset || '–'));
  panel.appendChild(weatherDetailRow('Wärmste Zeit', day.hot ? `${day.hot.time} · ${day.hot.temp}°` : '–'));
  panel.appendChild(weatherDetailRow('Kälteste Zeit', day.cold ? `${day.cold.time} · ${day.cold.temp}°` : '–'));
}

function renderWeather() {
  const wx = state.weather;
  if (!wx) return;
  $('weathercity').textContent = wx.cityLabel;
  const rail = $('weatherdays');
  rail.replaceChildren();
  const pages = $('weatherpages');
  wx.days.forEach((day, i) => {
    const box = el('div', 'weather-day' + (i === 0 ? ' is-active' : ''));
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
    box.addEventListener('click', () => {
      rail.querySelectorAll('.weather-day').forEach((n) => n.classList.remove('is-active'));
      box.classList.add('is-active');
      showWeatherDetail(day);
      pages.scrollTo({ left: pages.clientWidth, behavior: 'smooth' });
    });
    rail.appendChild(box);
  });

  showWeatherDetail(wx.days[0]);
  const detail = $('weatherdetail');
  if (!detail.dataset.wired) {
    detail.dataset.wired = '1';
    detail.addEventListener('click', () => {
      $('weatherpages').scrollTo({ left: 0, behavior: 'smooth' });
    });
  }
}

/* --------------------------------------------------- Filtern (wie im Server)
   Reihenfolge bewusst identisch zu pipeline.build_board(): erst Thema, dann
   Gelesen-Status. Erst danach wird auf BOARD_LIMIT gekappt und in Aufmacher/
   Kurzmeldungen aufgeteilt. */

function applyFilters() {
  let items = state.allItems;
  if (state.topic) items = items.filter((e) => e.topic === state.topic);
  if (state.hideRead) items = items.filter((e) => !isRead(e.id));
  if (state.sourceFilter) items = items.filter((e) => e.source === state.sourceFilter);
  return items;
}

/* --------------------------------------------------------- Marktuebersicht
   Ersetzt die fruehere Cluster-Uebersicht. Reine Kennzahlen aus echten
   Kursdaten (Tagespreis, Veraenderung ueber mehrere Jahre) - keine Bewertung,
   keine Anlageempfehlung, siehe newstaker/markets.py. */

const SVG_NS = 'http://www.w3.org/2000/svg';

function sparkSvg(values, isPositive) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'mk-spark ' + (isPositive ? 'is-pos' : 'is-neg'));
  if (!values || values.length < 2) return svg;
  svg.setAttribute('viewBox', '0 0 100 30');
  svg.setAttribute('preserveAspectRatio', 'none');
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 100;
      const y = 28 - ((v - min) / span) * 26;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const line = document.createElementNS(SVG_NS, 'polyline');
  line.setAttribute('points', points);
  svg.appendChild(line);
  return svg;
}

function openMarketModal(row) {
  $('mkmodalname').textContent = row.name;
  const sign = row.changePct >= 0 ? '+' : '';
  $('mkmodalline').textContent = `${row.price} ${row.currency} · ${sign}${row.changePct}% / ${state.markets.lookbackYears}J`;
  const chart = $('mkmodalchart');
  chart.replaceChildren();
  chart.appendChild(sparkSvg(row.spark, row.changePct >= 0));
  $('mkmodal').hidden = false;
}

function closeMarketModal() {
  $('mkmodal').hidden = true;
}

function applyMarketFilter(rows, filter) {
  let out = rows;
  if (filter.query) {
    const needle = filter.query.toLowerCase();
    out = out.filter((row) =>
      row.name.toLowerCase().includes(needle) || row.symbol.toLowerCase().includes(needle)
    );
  }
  out = out.slice();
  if (filter.sort === 'change-desc') out.sort((a, b) => b.changePct - a.changePct);
  else if (filter.sort === 'change-asc') out.sort((a, b) => a.changePct - b.changePct);
  return out;
}

function renderMarketColumn(kind, elementId, rows) {
  const box = $(elementId);
  box.replaceChildren();
  const filtered = applyMarketFilter(rows, state.marketFilter[kind]);
  filtered.forEach((row) => {
    const line = el('div', 'mk-row');
    line.addEventListener('click', () => openMarketModal(row));
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
  renderMarketColumn('etf', 'markets-etf', mk.etfs);
  renderMarketColumn('stock', 'markets-stock', mk.stocks);
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
      state.feedVisible = FEED_PAGE_SIZE;
      renderBoard();
    });
    nav.appendChild(pill);
  });
}

function renderSourceFilter() {
  const select = $('sourcefilter');
  if (!select) return;
  const sources = Array.from(new Set(state.allItems.map((item) => item.source))).sort((a, b) => a.localeCompare(b, 'de'));
  const current = state.sourceFilter;
  select.replaceChildren();
  select.appendChild(new Option('Alle Quellen', ''));
  sources.forEach((s) => select.appendChild(new Option(s, s)));
  select.value = sources.includes(current) ? current : '';
  state.sourceFilter = select.value;
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
  $('feedmore').hidden = true;
  if (total === 0) return;

  if (leads.length) {
    const leadsBox = el('div', 'leads-grid');
    leads.forEach((item) => leadsBox.appendChild(renderLead(item, renderBoard)));
    feed.appendChild(leadsBox);
  }

  // "Qualitaet vor Menge": das Board liefert bereits nach Score sortiert
  // (Quellen-Tier, Clustergroesse, Aktualitaet, Thema, siehe rank.py); hier
  // wird nur noch die standardmaessig sichtbare Menge auf FEED_PAGE_SIZE
  // Kurzmeldungen gedeckelt, mit "mehr laden" fuer den Rest.
  const visibleBriefs = briefs.slice(0, state.feedVisible);
  if (visibleBriefs.length) {
    feed.appendChild(el('div', 'brief-head', `KURZMELDUNGEN · ${briefs.length}`));
    const briefsBox = el('div', 'briefs-grid');
    visibleBriefs.forEach((item) => briefsBox.appendChild(renderBrief(item, renderBoard)));
    feed.appendChild(briefsBox);
  }
  if (briefs.length > visibleBriefs.length) {
    $('feedmore').hidden = false;
  }
}

function renderFootline() {
  const text = `${readSet.size} GELESEN · ${savedSet.size} GEMERKT`;
  $('readline').textContent = text;
  const dText = $('desktop-readline');
  if (dText) dText.textContent = text;

  const hideText = state.hideRead ? 'GELESENE ZEIGEN' : 'GELESENE AUSBLENDEN';
  $('hideread').textContent = hideText;
  const dHide = $('desktop-hideread');
  if (dHide) dHide.textContent = hideText;
}

/* -------------------------------------------------------- Board zeichnen */

function renderBoard() {
  const filtered = applyFilters();
  const capped = filtered.slice(0, BOARD_LIMIT);
  const leads = capped.slice(0, LEAD_COUNT);
  const briefs = capped.slice(LEAD_COUNT);

  renderFetchLine();
  renderPills();
  renderSourceFilter();
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
let searchRequestId = 0;

async function runSearch() {
  const query = $('searchinput').value.trim();

  if (!query && state.searchMode === 'all') {
    searchRequestId += 1;
    renderSearchResults([], '');
    return;
  }

  const requestId = ++searchRequestId;
  let index;
  try {
    index = await ensureSearchIndex();
  } catch (err) {
    console.error('Suchindex nicht verfügbar:', err);
    return;
  }
  // Bei schnellem Tippen kann eine aeltere Anfrage (z. B. der erste Aufruf,
  // der noch den Suchindex nachladen musste) spaeter zurueckkommen als eine
  // neuere - dann darf sie das schon engere Ergebnis nicht ueberschreiben.
  if (requestId !== searchRequestId) return;

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
  $('weathercity').addEventListener('click', () => {
    if (!state.weatherCities) return;
    const idx = state.weatherCities.indexOf(state.weatherCity);
    state.weatherCity = state.weatherCities[(idx + 1) % state.weatherCities.length];
    state.weather = state.weatherData[state.weatherCity];
    renderWeather();
  });

  $('hideread').addEventListener('click', () => {
    state.hideRead = !state.hideRead;
    state.feedVisible = FEED_PAGE_SIZE;
    renderBoard();
  });

  $('sourcefilter').addEventListener('change', () => {
    state.sourceFilter = $('sourcefilter').value;
    state.feedVisible = FEED_PAGE_SIZE;
    renderBoard();
  });

  $('feedmore').addEventListener('click', () => {
    state.feedVisible += FEED_PAGE_SIZE;
    renderBoard();
  });

  ['etf', 'stock'].forEach((kind) => {
    const search = $(`markets-${kind}-search`);
    const sort = $(`markets-${kind}-sort`);
    search.addEventListener('input', () => {
      state.marketFilter[kind].query = search.value.trim();
      renderMarkets();
    });
    sort.addEventListener('change', () => {
      state.marketFilter[kind].sort = sort.value;
      renderMarkets();
    });
  });

  $('mkmodalclose').addEventListener('click', closeMarketModal);
  $('mkmodalbackdrop').addEventListener('click', closeMarketModal);

  $('emptyreset').addEventListener('click', () => {
    state.topic = '';
    state.hideRead = false;
    renderBoard();
  });

  $('searchopen').addEventListener('click', openSearch);
  $('searchclose').addEventListener('click', closeSearch);

  // Marktleiste faehrt beim Runterscrollen der Meldungen ein, damit nur noch
  // die News zu sehen sind - wieder sichtbar sobald man nach oben scrollt.
  $('scroll').addEventListener('scroll', () => {
    $('markets').classList.toggle('is-collapsed', $('scroll').scrollTop > 24);
  }, { passive: true });

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
    if (ev.key !== 'Escape') return;
    if (!$('mkmodal').hidden) closeMarketModal();
    else if (!$('search').hidden) closeSearch();
  });

  const dHide = $('desktop-hideread');
  if (dHide) {
    dHide.addEventListener('click', () => {
      state.hideRead = !state.hideRead;
      renderBoard();
    });
  }

  const dSearch = $('desktop-searchopen');
  if (dSearch) {
    dSearch.addEventListener('click', openSearch);
  }

  const backdrop = $('searchbackdrop');
  if (backdrop) {
    backdrop.addEventListener('click', closeSearch);
  }

  initViewToggle();

  // Beim Zurueckkommen auf den Tab neu laden - die Daten koennten sich in der
  // Zwischenzeit per Cron aktualisiert haben.
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && $('search').hidden) {
      renderClock();
      loadBoard();
    }
  });
}

function initViewToggle() {
  const toggle = $('viewtoggle');
  if (!toggle) return;
  const saved = localStorage.getItem('newstaker.viewMode');
  if (saved === 'mobile') {
    document.body.classList.add('view-mode-mobile');
  }
  updateViewToggle();

  toggle.addEventListener('click', () => {
    const isMobile = document.body.classList.toggle('view-mode-mobile');
    localStorage.setItem('newstaker.viewMode', isMobile ? 'mobile' : 'desktop');
    updateViewToggle();
  });
}

function updateViewToggle() {
  const toggle = $('viewtoggle');
  if (!toggle) return;
  const isMobile = document.body.classList.contains('view-mode-mobile');
  const icon = toggle.querySelector('.vt-icon');
  const text = toggle.querySelector('.vt-text');
  if (icon) icon.textContent = isMobile ? '🖥️' : '📱';
  if (text) text.textContent = isMobile ? 'Desktop' : 'Mobil';
  toggle.title = isMobile ? 'Zu Desktop-Ansicht wechseln' : 'Zu Mobil-Ansicht wechseln';
}

/* ------------------------------------------------------------------ Start */

renderClock();
setInterval(renderClock, 30000);
wire();
loadBoard();
