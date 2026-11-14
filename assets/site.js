const key = 'kernel-notes:completed:v1';
function loadProgress() {
  try { const value = JSON.parse(localStorage.getItem(key)); return new Set(Array.isArray(value) ? value : []); }
  catch { return new Set(); }
}
const completed = loadProgress();
const search = document.querySelector('#search');
const cards = [...document.querySelectorAll('.card')];
const filters = [...document.querySelectorAll('[data-filter]')];
const groups = [...document.querySelectorAll('[data-group]')];
const normalize = (value) => value.toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '').replace(/đ/g, 'd');
let filter = 'all';
function renderFilter() {
  const query = normalize(search.value.trim());
  for (const card of cards) {
    card.hidden = (filter !== 'all' && card.dataset.week !== filter) || !normalize(card.dataset.search).includes(query);
  }
  for (const group of groups) group.hidden = !group.querySelector('.card:not([hidden])');
  document.querySelector('#empty').hidden = cards.some(card => !card.hidden);
  for (const button of filters) button.setAttribute('aria-pressed', String(button.dataset.filter === filter));
}
if (search) {
  search.addEventListener('input', renderFilter);
  for (const button of filters) button.addEventListener('click', () => { filter = button.dataset.filter; renderFilter(); });
  const markers = [...document.querySelectorAll('[data-slug]')];
  const finished = markers.filter(marker => completed.has(marker.dataset.slug));
  for (const marker of finished) marker.textContent = 'Đã đọc';
  document.querySelector('[data-progress]').textContent = `${finished.length} / ${cards.length} bài đã đọc`;
  document.querySelector('progress').value = finished.length;
}
const complete = document.querySelector('[data-complete]');
if (complete) {
  const slug = complete.dataset.complete;
  function renderProgress() {
    const done = completed.has(slug);
    complete.setAttribute('aria-pressed', String(done));
    complete.textContent = done ? '✓ Đã đọc · Bỏ đánh dấu' : 'Đánh dấu đã đọc';
  }
  complete.addEventListener('click', () => {
    if (completed.has(slug)) completed.delete(slug); else completed.add(slug);
    try { localStorage.setItem(key, JSON.stringify([...completed])); } catch {}
    renderProgress();
  });
  renderProgress();
}
const bar = document.querySelector('.read-progress');
if (bar) {
  const update = () => {
    const range = document.documentElement.scrollHeight - innerHeight;
    bar.style.width = `${range > 0 ? Math.min(100, Math.max(0, scrollY / range * 100)) : 0}%`;
  };
  addEventListener('scroll', update, {passive:true}); addEventListener('resize', update); update();
}
for (const table of document.querySelectorAll('.prose table')) {
  const wrapper = document.createElement('div');
  wrapper.className = 'table-wrap';
  table.before(wrapper); wrapper.append(table);
}
for (const code of document.querySelectorAll('pre > code:not(.language-mermaid)')) {
  if (!navigator.clipboard) break;
  const button = document.createElement('button');
  button.className = 'copy'; button.type = 'button'; button.textContent = 'Sao chép';
  code.parentElement.before(button);
  button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(code.textContent); button.textContent = 'Đã sao chép'; }
    catch { button.textContent = 'Hãy chọn và sao chép mã'; }
    setTimeout(() => { button.textContent = 'Sao chép'; }, 2000);
  });
}
