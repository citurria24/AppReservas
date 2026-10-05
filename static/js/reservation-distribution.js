(() => {
  const data = document.getElementById('reservation-distribution-data');
  const container = document.querySelector('[data-reservation-distribution]');
  if (!data || !container) return;

  const summary = JSON.parse(data.textContent);
  const confirmed = summary.total - summary.attended - summary.absent
    - summary.cancelled_client - summary.cancelled_salon;
  const states = [
    { label: 'Atendidas', count: summary.attended, color: '#14745a' },
    { label: 'Ausentes', count: summary.absent, color: '#79539e' },
    { label: 'Canceladas por cliente', count: summary.cancelled_client, color: '#b94343' },
    { label: 'Canceladas por local', count: summary.cancelled_salon, color: '#c47a18' },
    { label: 'Confirmadas', count: confirmed, color: '#346ca6' },
  ].filter(state => state.count > 0);

  const percentage = new Intl.NumberFormat('es-UY', { maximumFractionDigits: 1 });
  const legend = container.querySelector('.distribution-legend');
  const segments = [];
  const descriptions = [];
  let cumulative = 0;

  states.forEach((state, index) => {
    const start = cumulative / summary.total * 100;
    cumulative += state.count;
    const end = index === states.length - 1 ? 100 : cumulative / summary.total * 100;
    segments.push(`${state.color} ${start}% ${end}%`);
    const percent = `${percentage.format(state.count / summary.total * 100)}%`;

    const item = document.createElement('li');
    const swatch = document.createElement('span');
    swatch.className = 'distribution-swatch';
    swatch.style.backgroundColor = state.color;
    swatch.setAttribute('aria-hidden', 'true');
    const label = document.createElement('span');
    label.textContent = state.label;
    const value = document.createElement('strong');
    value.textContent = `${state.count} · ${percent}`;
    item.append(swatch, label, value);
    legend.append(item);
    descriptions.push(`${state.label}: ${state.count} (${percent})`);
  });

  const donut = container.querySelector('.reservation-donut');
  donut.style.backgroundImage = `conic-gradient(${segments.join(', ')})`;
  donut.setAttribute('aria-label', `Distribución de ${summary.total} reservas. ${descriptions.join('. ')}`);
  container.hidden = false;
})();
