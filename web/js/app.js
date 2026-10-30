/* 极简 hash 路由 */
const views = {
  home: document.getElementById('view-home'),
  new: document.getElementById('view-new'),
  song: document.getElementById('view-song'),
};
function show(name) {
  for (const k in views) views[k].hidden = k !== name;
  window.scrollTo(0, 0);
}

window.addEventListener('hashchange', route);
function route() {
  const h = location.hash || '#/home';
  if (h.startsWith('#/new')) { PracticeView?.teardown?.(); show('new'); NewView.enter(); }
  else if (h.startsWith('#/song')) {
    show('song');
    const id = new URLSearchParams(h.split('?')[1] || '').get('id');
    PracticeView.enter(id);
  } else {
    PracticeView?.teardown?.(); show('home'); HomeView.refresh();
  }
}

document.getElementById('brand-home').onclick = () => location.hash = '#/home';
document.getElementById('nav-home').onclick = () => location.hash = '#/home';
document.getElementById('nav-new').onclick = () => location.hash = '#/new';
document.getElementById('home-new-card').onclick = () => location.hash = '#/new';

route();
