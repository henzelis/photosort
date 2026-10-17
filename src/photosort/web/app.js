/* PhotoSort web app */
'use strict';
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const S = { state: 'empty', src: null, dst: null, mode: 'date_location',
            network: true, move: false, tree: null, poll: null,
            lastLogLen: {scan: 0, run: 0} };

/* ---------------- view switching ---------------- */
function show(view) {
  $$('.view').forEach(v => v.hidden = v.id !== 'view-' + view);
  $$('#nav button').forEach(b => {
    if (b.dataset.go === view) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  if (view === 'explore') setTimeout(drawCharts, 60);
  if (view === 'plan') setTimeout(drawTree, 60);
}
const navAvail = { setup: true, explore: false, plan: false };
function setNav() {
  $$('#nav button').forEach(b => b.disabled = !navAvail[b.dataset.go]);
  $('#step1').classList.toggle('done', navAvail.explore);
  $('#step2').classList.toggle('done', navAvail.plan);
}
$$('#nav button').forEach(b => b.addEventListener('click', () => {
  if (!b.disabled) show(b.dataset.go);
}));

/* ---------------- polling ---------------- */
async function api(path, body) {
  const r = await fetch(path, body ? {method: 'POST', body: JSON.stringify(body),
    headers: {'Content-Type': 'application/json'}} : undefined);
  return r.json();
}

let lastState = null;
async function poll() {
  const st = await api('/api/state');
  const changed = st.state !== lastState;
  lastState = st.state;
  S.state = st.state;
  $('#ftVer').textContent = 'v' + st.version;
  $('#ver').textContent = 'v' + st.version;

  // sidebar status
  const dot = $('#stDot'), name = $('#stName');
  const map = {
    empty:   ['', 'Очікування'],
    scanning:['run', 'Сканування…'],
    ready:   ['ok', 'Фото прочитано'],
    planning:['run', 'Геокодинг…'],
    planned: ['ok', 'План готовий'],
    running: ['run', 'Сортування…'],
    done:    ['ok', 'Завершено ✓'],
    error:   ['crit', 'Помилка'],
  };
  const [cls, label] = map[st.state] || ['', st.state];
  dot.className = 'dot ' + cls; name.textContent = label;

  // progress meter in sidebar (hide when nothing to show)
  const p = st.prog || {};
  const frac = p.total ? p.done / p.total : 0;
  $('#ingestCard').hidden = !p.total;
  $('#progM').style.width = (frac * 100).toFixed(1) + '%';
  $('#progV').textContent = p.total ? `${p.done} / ${p.total}` : '—';
  const phaseK = {scan: 'сканування', geo: 'геокодинг', copy: 'копіювання'};
  $('#progK').textContent = phaseK[p.phase] || 'прогрес';

  $('#btnCancel').hidden = !(st.busy && (st.state === 'scanning' || st.state === 'planning' || st.state === 'running'));

  // per-view updates
  if (st.state === 'scanning' && changed) {
    show('scan');
  }
  if (st.state === 'scanning' || (changed && st.state === 'scanning')) {
    $('#scanM').style.width = (frac * 100).toFixed(1) + '%';
    $('#scanCnt').textContent = p.total ? `${p.done} / ${p.total}` : '…';
    fillLog($('#logScan'), st.log);
  }
  if (st.state === 'ready' || st.state === 'planning') {
    navAvail.explore = true; setNav();
    if (changed) { if (st.state === 'ready') show('explore'); else show('plan'); }
    fillKcards(st);
    fillLog($('#logRun'), st.log);
    if (st.tree) { S.tree = st.tree; drawTree(st.tree); }
  }
  if (st.state === 'planned' || st.state === 'running' || st.state === 'done' ||
      (st.state === 'error' && st.tree)) {
    navAvail.plan = true; setNav();
    if (changed && st.state !== 'planning') show('plan');
    renderRunPanel(st);
    fillLog($('#logRun'), st.log);
  }
  if (st.state === 'empty' && changed) {
    navAvail.explore = navAvail.plan = false; setNav();
    show('setup');
  }
  if (st.state === 'error' && !st.tree && changed) {
    show(S.src ? 'scan' : 'setup');
    $('#setupHint') && ($('#setupHint').textContent = 'Помилка: ' + (st.error || ''));
  }
}

function fillLog(el, log) {
  if (!el) return;
  const txt = log.join('\n');
  if (el.dataset.h !== String(log.length)) {
    el.textContent = txt;
    el.dataset.h = String(log.length);
    el.scrollTop = el.scrollHeight;
  }
}

/* ---------------- setup view ---------------- */
function updateSetup() {
  $('#srcChip').textContent = S.src || 'папку не обрано';
  $('#srcChip').className = 'val' + (S.src ? '' : ' empty');
  $('#dstChip').textContent = S.dst || 'папку не обрано';
  $('#dstChip').className = 'val' + (S.dst ? '' : ' empty');
  $('#srcPath').textContent = S.src || 'разом із вкладеними папками';
  $('#dstPath').textContent = S.dst || 'порожня папка — радимо створити нову';
  $('#pickSrc').classList.toggle('filled', !!S.src);
  $('#pickDst').classList.toggle('filled', !!S.dst);
  const ready = S.src && S.dst;
  $('#btnScan').disabled = !ready;
  $('#setupHint').textContent = ready ? 'Все готово — фото копіюватимуться безпечно'
    : 'Оберіть обидві папки, щоб почати';
}

$$('#modes .mode').forEach(b => b.addEventListener('click', () => {
  $$('#modes .mode').forEach(x => x.classList.toggle('on', x === b));
  S.mode = b.dataset.mode;
  syncSeg();
}));
function syncSeg() {
  $$('#segMode button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === S.mode)));
}
$$('#segMode button').forEach(b => b.addEventListener('click', async () => {
  S.mode = b.dataset.mode; syncSeg();
  $('#btnPlan').textContent = 'Побудувати план →';
  await api('/api/plan', {mode: S.mode, network: S.network, lang: 'uk'});
}));
$('#netTgl').addEventListener('change', e => S.network = e.target.checked);
$('#moveTgl').addEventListener('change', e => S.move = e.target.checked);

$('#btnScan').addEventListener('click', async () => {
  S.lastLogLen = {scan: 0, run: 0};
  show('scan');
  $('#scanTitle').textContent = 'Читаємо EXIF та геотеги…';
  await api('/api/scan', {src: S.src, network: S.network});
});
$('#btnPlan').addEventListener('click', async () => {
  show('plan');
  $('#runInfo').textContent = 'Готуємо план…';
  await api('/api/plan', {mode: S.mode, network: S.network, lang: 'uk'});
});
$('#btnRun').addEventListener('click', async () => {
  await api('/api/run', {dst: S.dst, move: S.move});
});
$('#btnCancel').addEventListener('click', () => api('/api/cancel', {}));
$('#btnReset').addEventListener('click', async () => {
  await api('/api/reset', {});
  navAvail.explore = navAvail.plan = false; setNav();
  S.lastLogLen = {scan: 0, run: 0};
  show('setup');
});

/* ---------------- folder browser modal ---------------- */
let browseTarget = null, browsePath = '';
$('#pickSrc').addEventListener('click', () => openBrowse('src'));
$('#pickDst').addEventListener('click', () => openBrowse('dst'));
$('#btnClose').addEventListener('click', () => $('#modal').hidden = true);
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') $('#modal').hidden = true; });

async function openBrowse(target) {
  browseTarget = target;
  $('#browseTitle').textContent = target === 'src' ? 'Звідки брати фотографії' : 'Куди складати відсортовані';
  const st = await api('/api/state');
  const start = (target === 'src' ? S.src : S.dst) || st.home;
  renderBrowse(await api('/api/browse?path=' + encodeURIComponent(start || '')));
  $('#modal').hidden = false;
}
$('#crumbs').addEventListener('click', async e => {
  const b = e.target.closest('button[data-p]');
  if (b) renderBrowse(await api('/api/browse?path=' + encodeURIComponent(b.dataset.p)));
});
$('#dirlist').addEventListener('click', async e => {
  const b = e.target.closest('button[data-p]');
  if (b) renderBrowse(await api('/api/browse?path=' + encodeURIComponent(b.dataset.p)));
});
$('#btnPickHere').addEventListener('click', () => {
  if (browseTarget === 'src') S.src = browsePath; else S.dst = browsePath;
  $('#modal').hidden = true;
  updateSetup();
});

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function renderBrowse(r) {
  browsePath = r.path;
  $('#browsePath').textContent = r.path || '';
  const parts = (r.path || '').split(/[\\/]+/).filter(Boolean);
  let acc = r.path && r.path[1] === ':' ? r.path.slice(0, 2) : '';
  const crumbs = [];
  parts.forEach((p, i) => {
    acc = acc ? acc + (r.path[1] === ':' ? '\\' : '/') + p : p;
    crumbs.push(`<button data-p="${esc(acc)}">${esc(p)}</button>`);
  });
  $('#crumbs').innerHTML = crumbs.length ? crumbs.join('<span>›</span>') : '<span>/</span>';
  let html = '';
  if (r.parent !== null && r.parent !== undefined)
    html += `<button class="drow up" data-p="${esc(r.parent)}"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M8 12V4M4.5 7.5 8 4l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>… вгору</button>`;
  html += r.dirs.map(d => `<button class="drow" data-p="${esc(d.path)}"><svg width="15" height="15" viewBox="0 0 16 16"><path d="M1.5 4.5A1.5 1.5 0 0 1 3 3h3l1.5 2H13a1.5 1.5 0 0 1 1.5 1.5v5A1.5 1.5 0 0 1 13 13H3a1.5 1.5 0 0 1-1.5-1.5z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>${esc(d.name)}</button>`).join('');
  if (!r.dirs.length && r.parent === null) html += '<div class="empty">немає доступних папок</div>';
  $('#dirlist').innerHTML = html;
}

/* ---------------- explore view ---------------- */
function fillKcards(st) {
  $('#kTotal').textContent = st.stats.total ?? 0;
  $('#kGeo').textContent = st.stats.geo ?? 0;
  $('#kDated').textContent = st.stats.dated ?? 0;
  $('#kPlaces').textContent = (st.map || []).length;
  // sidebar mini-stats
  $('#ministats').hidden = !(st.stats.total > 0);
  $('#msTotal').textContent = st.stats.total ?? 0;
  $('#msGeo').textContent = st.stats.geo ?? 0;
  $('#msDated').textContent = st.stats.dated ?? 0;
  $('#msPlaces').textContent = st.stats.places ?? (st.map || []).length;
  const total = st.stats.total || 1;
  $('#places').innerHTML = (st.places || []).map(([n, c]) => {
    const pct = Math.round(c / total * 100);
    return `<div class="brow"><span class="nm">${esc(n)}</span><span class="n">${c}</span>` +
      `<span class="pct">${pct}%</span>` +
      `<div class="bar"><i style="width:${pct}%"></i></div></div>`;
  }).join('') || '<div class="empty">немає геотегів</div>';
  const nth = st.thumbs || [];
  $('#thumbs').innerHTML = nth.map(i => `<img loading="lazy" src="/api/thumb?i=${i}" alt="">`).join('') ||
    '<div class="empty">немає прев’ю</div>';
}

let mapChart = null, monthChart = null;
function drawCharts() {
  if (!window.echarts) return;
  api('/api/state').then(st => {
    // world map
    const el = $('#map');
    if (mapChart) mapChart.dispose();
    mapChart = echarts.init(el, null, {renderer: 'canvas'});
    const pts = st.map || [];
    mapChart.setOption({
      backgroundColor: 'transparent',
      geo: {map: 'world', roam: true, zoom: 1.35, center: [20, 40],
        scaleLimit: {min: 1, max: 12},
        itemStyle: {areaColor: '#17397c', borderColor: '#5F9CFF', borderWidth: 0.9},
        emphasis: {itemStyle: {areaColor: '#22509f'}, label: {show: false}}},
      tooltip: {trigger: 'item', backgroundColor: 'rgba(10,20,46,.92)',
        borderColor: 'rgba(130,175,255,.45)', textStyle: {color: '#EAF0FF', fontSize: 12},
        formatter: p => p.data.place ? `<b>${p.data.place}</b><br>${p.data.value[2]} фото` : `${p.data.value[2]} фото`},
      series: [{
        type: 'scatter', coordinateSystem: 'geo',
        data: pts.map(p => ({name: p.name, place: p.name,
          value: [p.lon, p.lat, p.count]})),
        symbolSize: v => Math.max(14, Math.min(46, 10 + Math.sqrt(v[2]) * 3.4)),
        itemStyle: {color: new echarts.graphic.RadialGradient(0.4, 0.3, 1, [
          {offset: 0, color: 'rgba(190,245,255,.98)'},
          {offset: 1, color: 'rgba(47,123,255,.65)'}]),
          borderColor: 'rgba(210,240,255,.9)', borderWidth: 1.2,
          shadowColor: 'rgba(39,211,245,.95)', shadowBlur: 16}
      }]
    });
    // months timeline — honest continuous axis: fill gaps with 0
    const el2 = $('#months');
    if (monthChart) monthChart.dispose();
    monthChart = echarts.init(el2, null, {renderer: 'canvas'});
    const ms = st.months || [];
    let full = ms, vals = ms.map(m => m.n);
    if (ms.length >= 2) {
      const parse = s => { const [y, m] = s.split('-').map(Number); return y * 12 + m - 1; };
      const fmt = i => `${String(Math.floor(i / 12)).padStart(4, '0')}-${String(i % 12 + 1).padStart(2, '0')}`;
      const a = parse(ms[0].m), b = parse(ms[ms.length - 1].m);
      if (b - a + 1 <= 240) {           // cap at 20 years of buckets
        full = []; vals = [];
        for (let i = a; i <= b; i++) { const k = fmt(i); full.push({m: k}); vals.push(0); }
        ms.forEach(m => { vals[parse(m.m) - a] = m.n; });
      }
    }
    const step = Math.max(1, Math.ceil(full.length / 12));
    monthChart.setOption({
      backgroundColor: 'transparent',
      grid: {left: 44, right: 16, top: 26, bottom: 30},
      tooltip: {trigger: 'axis', backgroundColor: 'rgba(10,20,46,.92)',
        borderColor: 'rgba(130,175,255,.45)', textStyle: {color: '#EAF0FF'}},
      xAxis: {type: 'category', data: full.map(x => x.m),
        axisLabel: {color: '#8294BC', fontFamily: 'JetBrains Mono', fontSize: 10,
          interval: i => i % step === 0},
        axisLine: {lineStyle: {color: 'rgba(92,140,255,.3)'}}, axisTick: {show: false}},
      yAxis: {type: 'value', axisLabel: {color: '#8294BC', fontFamily: 'JetBrains Mono'},
        splitLine: {lineStyle: {color: 'rgba(120,160,255,.10)'}}},
      series: [{type: 'bar', data: vals, barMaxWidth: 26,
        itemStyle: {borderRadius: [5, 5, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {offset: 0, color: '#4C93FF'}, {offset: 1, color: 'rgba(47,123,255,.15)'}])}}]
    });
  });
}
window.addEventListener('resize', () => { mapChart && mapChart.resize(); monthChart && monthChart.resize(); });

/* ---------------- plan / run view ---------------- */
function renderRunPanel(st) {
  $('#planDst').textContent = st.dst ? '→ ' + st.dst : '';
  S.tree = st.tree || S.tree;
  if (S.tree && st.dst) S.tree.name = st.dst;
  const modeK = {date_location: 'дата + місце', date: 'тільки дата', location: 'тільки місце'};
  $('#runInfo').innerHTML =
    ` фото: <b>${st.stats.total ?? 0}</b> · локацій: <b>${(st.map || []).length}</b><br>` +
    ` режим: <b>${modeK[st.mode] || st.mode}</b> · ` +
    `${st.move ? '<b>переміщення</b>' : '<b>копіювання</b>'}`;
  const p = st.prog || {};
  if (st.state === 'running' && p.phase === 'copy') {
    $('#runMeter').hidden = false;
    $('#runM').style.width = (p.total ? p.done / p.total * 100 : 0) + '%';
    $('#runLabel').textContent = `Сортуємо… ${p.done}/${p.total}`;
    $('#btnRun').disabled = true;
    $('#btnRun').style.display = '';
  } else if (st.state === 'done') {
    // one clear success indicator, not five
    $('#runMeter').hidden = true;
    $('#btnRun').style.display = 'none';
    $('#btnReset').hidden = false;
    const r = st.result || {};
    $('#donebox').hidden = false;
    $('#doneH').textContent = 'Готово!';
    $('#doneStats').innerHTML =
      `<div><b>${(r.copied || 0) + (r.moved || 0)}</b><span>${r.moved ? 'переміщено' : 'скопійовано'}</span></div>` +
      `<div><b>${st.stats.places ?? (st.map || []).length}</b><span>локацій</span></div>` +
      `<div><b>${(st.tree && countLeaves(st.tree)) || st.stats.total || 0}</b><span>папок структури</span></div>`;
    $('#doneDst').textContent = st.dst || '';
  } else {
    $('#btnRun').style.display = '';
    $('#btnRun').disabled = !(st.state === 'planned' || st.state === 'ready');
    $('#runLabel').textContent = st.move ? 'Перемістити фото' : 'Сортувати (копіювати)';
    $('#runMeter').hidden = st.state !== 'planned';
    $('#runM').style.width = st.state === 'planned' ? '100%' : '0';
  }
  drawTree(S.tree);
}
function countLeaves(node) {
  let n = 0;
  (node.children || []).forEach(c => { n += 1 + countLeaves(c); });
  return n;
}

function drawTree(tree) {
  const el = $('#tree');
  tree = tree || S.tree;
  if (!tree) { el.innerHTML = '<div class="empty">—</div>'; return; }
  const sig = tree.name + '|' + (tree.children || []).length + ':' + (tree.files || 0);
  if (el.dataset.h === sig) return;
  el.dataset.h = sig;
  const nm = tree.name || '…';
  el.innerHTML = `<div class="tnode d0"><span class="fd"></span><span class="nm2">${esc(nm)}</span><span class="cnt">${tree.files} фото</span></div>` +
    kidsHtml(tree);
}
function kidsHtml(node) {
  if (!node.children || !node.children.length) return '';
  return '<div class="tkids">' + node.children.map(c =>
    `<div class="tnode d${c.depth || 1}"><span class="fd"></span><span class="nm2">${esc(c.name)}</span><span class="cnt">${c.files}</span></div>` +
    kidsHtml(c)).join('') + '</div>';
}

/* ---------------- boot ---------------- */
updateSetup();
setNav();
show('setup');
S.poll = setInterval(poll, 700);
poll();
