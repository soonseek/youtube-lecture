const player = document.getElementById('lecture-player');
const search = document.getElementById('transcript-search');
const rows = [...document.querySelectorAll('[data-transcript-row]')];
const count = document.getElementById('transcript-count');
const empty = document.getElementById('search-empty');

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
