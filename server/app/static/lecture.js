const player = document.getElementById('lecture-player');
const search = document.getElementById('transcript-search');
const rows = [...document.querySelectorAll('[data-transcript-row]')];
const count = document.getElementById('transcript-count');
const empty = document.getElementById('search-empty');

const tabs = [...document.querySelectorAll('[role="tab"]')];
if (tabs.length) {
  const activateTab = (activeTab, moveFocus = false) => {
    tabs.forEach((tab) => {
      const active = tab === activeTab;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
    });
    if (moveFocus) activeTab.focus();
  };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateTab(tab));
    tab.addEventListener('keydown', (event) => {
      let next = index;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = tabs.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabs[next], true);
    });
  });
  activateTab(tabs[0]);
}

document.querySelectorAll('[data-seek-ms]').forEach((link) => {
  link.addEventListener('click', (event) => {
    if (!player) return;
    event.preventDefault();
    const seconds = Math.floor(Number(link.dataset.seekMs) / 1000);
    const url = new URL(player.src);
    url.searchParams.set('start', String(seconds));
    url.searchParams.set('autoplay', '1');
    player.src = url.toString();
    player.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
});

if (search) {
  search.addEventListener('input', () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    rows.forEach((row) => {
      const match = row.textContent.toLocaleLowerCase().includes(query);
      row.hidden = !match;
      if (match) visible += 1;
    });
    count.textContent = `${visible}개 구간`;
    empty.hidden = visible !== 0;
  });
}

const copyButton = document.getElementById('copy-link');
if (copyButton) {
  copyButton.addEventListener('click', async () => {
    const label = copyButton.querySelector('span');
    try {
      await navigator.clipboard.writeText(window.location.href);
      label.textContent = '복사했습니다';
      setTimeout(() => { label.textContent = '링크 복사'; }, 2200);
    } catch {
      label.textContent = '복사할 수 없습니다';
    }
  });
}
