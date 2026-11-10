const $ = (selector) => document.querySelector(selector);
const labels = {up: 'Доступен', down: 'Недоступен', pending: 'Ожидание', paused: 'На паузе'};
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const date = (value) => value ? new Date(value).toLocaleString('ru-RU') : 'Ещё не проверялся';
const ms = (value) => value == null ? '—' : `${Math.round(value)} мс`;
let services = [], selected = null, editing = null, loading = false, toastTimer, searchTimer;

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4500);
}

async function api(path, method = 'GET', data) {
  const response = await fetch(path, {method, headers: {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || result.message || 'Ошибка запроса');
  return result;
}

function render() {
  const totalChecks = services.reduce((sum, s) => sum + s.total, 0);
  const successful = services.reduce((sum, s) => sum + (s.successful || 0), 0);
  const average = services.reduce((sum, s) => sum + (s.avg_ms || 0) * s.total, 0);
  const up = services.filter(s => s.status === 'up').length;
  const down = services.filter(s => s.status === 'down').length;
  $('#total').textContent = services.length;
  $('#up').textContent = up;
  $('#down').textContent = down;
  $('#uptime').textContent = totalChecks ? `${(100 * successful / totalChecks).toFixed(2)}%` : '—';
  $('#avg').textContent = totalChecks ? `Средний отклик · ${ms(average / totalChecks)}` : 'Ожидание результатов';
  const overall = $('#overall');
  const unknown = services.some(s => s.status === 'pending');
  overall.className = `pill ${down ? 'down' : up && !unknown ? 'up' : 'neutral'}`;
  overall.textContent = down ? `● Сбоев: ${down}` : unknown ? '● Есть непроверенные сервисы' : up ? '● Активные сервисы доступны' : '● Нет активных проверенных сервисов';
  const categories = [...new Set(services.map(s => s.category))].sort();
  const currentCategory = $('#category').value;
  $('#category').innerHTML = '<option value="">Все группы</option>' + categories.map(c => `<option value="${escapeHTML(c)}">${escapeHTML(c)}</option>`).join('');
  $('#category').value = categories.includes(currentCategory) ? currentCategory : '';
  const query = $('#search').value.trim().toLowerCase();
  const filtered = services.filter(s => `${s.name} ${s.url}`.toLowerCase().includes(query) && (!$('#status').value || s.status === $('#status').value) && (!$('#category').value || s.category === $('#category').value));
  $('#count').textContent = filtered.length;
  $('#services').innerHTML = filtered.map(s => `<tr><td><button class="service-name" data-id="${s.id}">${escapeHTML(s.name)}</button><span class="service-group">${escapeHTML(s.category)}</span><span class="service-url" title="${escapeHTML(s.url)}">${escapeHTML(s.url)}</span></td><td><span class="pill ${s.status}">● ${labels[s.status]}</span></td><td>${ms(s.response_ms)}</td><td class="${s.uptime >= 99 && s.uptime !== null ? 'uptime-good' : ''}">${s.uptime === null ? '—' : s.uptime.toFixed(2) + '%'}</td><td>${date(s.checked_at)}</td><td><button class="row-open" data-id="${s.id}" aria-label="Открыть ${escapeHTML(s.name)}">↗</button></td></tr>`).join('');
  $('#empty').hidden = filtered.length > 0;
  if (!filtered.length) {
    $('#empty h3').textContent = services.length ? 'Ничего не найдено' : 'Начните с первого сервиса';
    $('#empty p').textContent = services.length ? 'Попробуйте другой запрос или измените фильтры.' : 'Добавьте адрес сайта или API. Пульс автоматически начнёт проверять его доступность.';
    $('#empty-add').hidden = services.length > 0;
  }
  $('#export').href = `/api/report.csv?hours=${$('#period').value}`;
}

async function refresh() {
  if (loading) return;
  loading = true;
  try {
    services = await api(`/api/services?hours=${$('#period').value}`);
    render();
    $('#sync').textContent = `Обновлено ${new Date().toLocaleTimeString('ru-RU')}`;
    if (selected) {
      if (services.some(s => s.id === selected)) await showDetail(selected, false);
      else { selected = null; $('#detail').hidden = true; }
    }
  } catch (error) {
    $('#sync').textContent = 'Нет связи с сервером';
    toast(error.message);
  } finally { loading = false; }
}

function openForm(service = null) {
  editing = service;
  $('#form').reset();
  $('#modal-title').textContent = service ? 'Редактирование сервиса' : 'Новый сервис';
  $('#form-error').textContent = '';
  if (service) for (const key of ['name', 'url', 'category', 'interval', 'timeout', 'expected_code']) $('#form').elements[key].value = service[key];
  $('#modal').showModal();
}

$('#add').onclick = $('#empty-add').onclick = () => openForm();
$('#cancel').onclick = () => $('#modal').close();
$('#form').onsubmit = async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  for (const key of ['interval', 'timeout', 'expected_code']) data[key] = Number(data[key]);
  data.enabled = editing ? Boolean(editing.enabled) : true;
  const button = $('#form .save');
  button.disabled = true;
  try {
    await api(editing ? `/api/services/${editing.id}` : '/api/services', editing ? 'PUT' : 'POST', data);
    $('#modal').close(); toast('Сервис сохранён'); await refresh();
  } catch (error) { $('#form-error').textContent = error.message; }
  finally { button.disabled = false; }
};
$('#services').onclick = (event) => {
  const button = event.target.closest('[data-id]');
  if (button) showDetail(Number(button.dataset.id)).catch(error => toast(error.message));
};
$('#search').oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(render, 100); };
$('#status').onchange = $('#category').onchange = render;
$('#period').onchange = refresh;
$('#close-detail').onclick = () => { selected = null; $('#detail').hidden = true; };

async function showDetail(id, scroll = true) {
  selected = id;
  const service = services.find(s => s.id === id);
  const history = await api(`/api/services/${id}/history?hours=${$('#period').value}`);
  if (selected !== id) return;
  $('#detail').hidden = false;
  $('#detail-title').textContent = service.name;
  $('#detail-url').textContent = service.url;
  $('#settings').textContent = `Интервал ${service.interval} с · таймаут ${service.timeout} с · HTTP ${service.expected_code}`;
  $('#pause').textContent = service.enabled ? 'Пауза' : 'Продолжить';
  $('#checks').innerHTML = history.checks.slice(0, 50).map(c => `<div class="history-item"><div><span class="pill ${c.ok ? 'up' : 'down'}">${c.ok ? 'Успешно' : 'Сбой'}</span><small>${date(c.checked_at)}</small>${c.error ? `<small class="error">${escapeHTML(c.error)}</small>` : ''}</div><div>${ms(c.response_ms)}<small>HTTP ${c.status_code ?? '—'}</small></div></div>`).join('') || '<p>Проверок за период пока нет.</p>';
  $('#incidents').innerHTML = history.incidents.map(i => `<div class="history-item"><div><span class="pill ${i.resolved_at ? 'up' : 'down'}">${i.resolved_at ? 'Восстановлен' : 'Открыт'}</span><small>${date(i.started_at)}</small><small class="error">${escapeHTML(i.reason)}</small><small>${i.resolved_at ? 'Восстановлен: ' + date(i.resolved_at) : 'Ожидает восстановления'}</small></div><span>${Math.max(0, Math.round(((i.resolved_at ? new Date(i.resolved_at) : new Date()) - new Date(i.started_at)) / 60000))} мин</span></div>`).join('') || '<p>За период инцидентов нет.</p>';
  drawChart([...history.checks].reverse());
  $('#edit').onclick = () => openForm(service);
  $('#pause').onclick = () => mutate(() => api(`/api/services/${id}`, 'PUT', {...service, enabled: !service.enabled}), service.enabled ? 'Автопроверки приостановлены' : 'Автопроверки включены');
  $('#check').onclick = () => mutate(() => api(`/api/services/${id}/check`, 'POST', {}), 'Проверка запущена. Результат появится после обновления.');
  $('#delete').onclick = () => {
    if (confirm(`Удалить «${service.name}» вместе с историей проверок и инцидентов?`)) {
      mutate(async () => { await api(`/api/services/${id}`, 'DELETE'); selected = null; $('#detail').hidden = true; }, 'Сервис удалён');
    }
  };
  if (scroll) $('#detail').scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function mutate(action, message) {
  try { await action(); toast(message); await refresh(); }
  catch (error) { toast(error.message); }
}

let chartChecks = [];
function drawChart(checks) {
  chartChecks = checks;
  const canvas = $('#chart'), ctx = canvas.getContext('2d');
  const width = canvas.clientWidth, height = 200, ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio; canvas.height = height * ratio;
  ctx.scale(ratio, ratio);
  const left = 44, right = width - 16, top = 15, bottom = 169;
  const max = Math.max(100, ...checks.map(c => c.response_ms)) * 1.1;
  ctx.font = '10px Segoe UI';
  for (let i = 0; i <= 4; i++) {
    const y = top + (bottom - top) * i / 4;
    ctx.strokeStyle = '#edf1f5'; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    ctx.fillStyle = '#99a5b1'; ctx.fillText(Math.round(max * (1 - i / 4)), 0, y + 3);
  }
  if (checks.length) {
    const points = checks.map((c, i) => [checks.length === 1 ? (left + right) / 2 : left + i * (right - left) / (checks.length - 1), bottom - c.response_ms / max * (bottom - top)]);
    ctx.strokeStyle = '#1b9e85'; ctx.lineWidth = 2; ctx.beginPath();
    points.forEach(([x,y], i) => i ? ctx.lineTo(x,y) : ctx.moveTo(x,y)); ctx.stroke();
    points.forEach(([x,y], i) => { ctx.fillStyle = checks[i].ok ? '#1b9e85' : '#d46b7a'; ctx.beginPath(); ctx.arc(x,y,3,0,Math.PI*2); ctx.fill(); });
    ctx.fillStyle = '#99a5b1';
    ctx.fillText(new Date(checks[0].checked_at).toLocaleTimeString('ru-RU'), left, 193);
    if (checks.length > 1) ctx.fillText(new Date(checks.at(-1).checked_at).toLocaleTimeString('ru-RU'), Math.max(left + 80, right - 50), 193);
  }
  $('#chart-note').textContent = checks.length ? 'Зелёный — успешная проверка, красный — ошибка. Таймауты и ошибки соединения также входят в отклик.' : 'График появится после первой проверки.';
}
window.addEventListener('resize', () => { if (selected) drawChart(chartChecks); });
refresh();
setInterval(refresh, 5000);
