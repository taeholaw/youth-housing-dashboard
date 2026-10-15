/*
 * 독립 웹사이트용 경량 런타임.
 * claude.ai 대시보드의 `dash` API(data · onData · calc · colors)를 같은 이름으로 흉내 내어,
 * 대시보드와 웹사이트가 한 벌의 화면 코드(page.html)를 함께 쓰게 한다.
 */
(function () {
  const DATASETS = window.YH_DATASETS || {};
  const store = {};
  const calcs = {};
  const subs = [];
  let version = 0;
  const memo = {};

  const asRows = (j) => (Array.isArray(j) ? j : j && Array.isArray(j.rows) ? j.rows : [j]);

  function notify() {
    version += 1;
    subs.forEach((fn) => { try { fn(); } catch (e) { console.error('[dash] onData 오류', e); } });
  }

  function load(id, url) {
    store[id] = { status: 'loading', data: [], columns: [] };
    fetch(url, { cache: 'no-cache' })
      .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then((j) => {
        const rows = asRows(j);
        store[id] = { status: 'ok', data: rows, columns: rows.length ? Object.keys(rows[0]) : [] };
      })
      .catch((e) => { store[id] = { status: 'error', data: [], columns: [], message: String(e.message || e) }; })
      .finally(notify);
  }

  function data(id) {
    if (store[id]) return store[id];
    const c = calcs[id];
    if (!c) return { status: 'missing', data: [], columns: [] };
    if (memo[id] && memo[id].v === version) return memo[id].r;
    const inputs = c.inputs.map((i) => data(i));
    let r;
    if (inputs.some((x) => x.status === 'error')) r = { status: 'error', data: [], columns: [], message: '입력 데이터를 불러오지 못했습니다' };
    else if (inputs.some((x) => x.status !== 'ok')) r = { status: 'loading', data: [], columns: [] };
    else {
      try {
        const out = c.fn(...inputs.map((x) => x.data));
        const rows = asRows(out);
        r = { status: 'ok', data: rows, columns: rows.length && typeof rows[0] === 'object' ? Object.keys(rows[0]) : [] };
      } catch (e) {
        console.error('[dash] calc 오류: ' + id, e);
        r = { status: 'error', data: [], columns: [], message: String(e.message || e) };
      }
    }
    memo[id] = { v: version, r };
    return r;
  }

  let lastW = 0;
  let t = null;
  window.addEventListener('resize', () => {
    clearTimeout(t);
    t = setTimeout(() => { const w = document.documentElement.clientWidth; if (w !== lastW) { lastW = w; notify(); } }, 150);
  });

  window.dash = {
    data,
    onData(fn) { subs.push(fn); try { fn(); } catch (e) { console.error('[dash] onData 오류', e); } },
    calc(id, spec) { calcs[id] = { inputs: spec.inputs || [], fn: spec.fn, title: spec.title }; },
    loader() {},
    colors: Array.from({ length: 8 }, (_, i) => `var(--series-${i})`),
    refresh(id) { if (DATASETS[id]) { load(id, DATASETS[id]); notify(); } },
    params: () => ({}), setParams() {}, resetParams() {}, setLink() {},
  };

  Object.entries(DATASETS).forEach(([id, url]) => load(id, url));
  document.addEventListener('DOMContentLoaded', () => { lastW = document.documentElement.clientWidth; });
})();
