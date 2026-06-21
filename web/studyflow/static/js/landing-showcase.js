/* Landing page "Dashboard showcase" section — crossfades between the two
   static, decorative product screenshots (sample data baked into the
   images) and wires up the manual dot toggles. No API calls, no real
   user data, no DOM building — just an opacity/class swap. */
(function () {
  var shots = document.getElementById('showcaseShots');
  if (!shots) return;
  var imgs = Array.prototype.slice.call(shots.querySelectorAll('.showcase__img'));
  var dots = Array.prototype.slice.call(document.querySelectorAll('.shotdot'));
  if (!imgs.length) return;

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var cur = 0, rotMs = 12000, timer = null, paused = false;

  function setScreen(idx) {
    cur = idx;
    imgs.forEach(function (img, i) { img.classList.toggle('is-on', i === idx); });
    dots.forEach(function (d, i) { d.classList.toggle('on', i === idx); });
  }

  function restart() {
    if (timer) clearInterval(timer);
    // Manual dot toggles still work; just don't auto-advance.
    if (reduceMotion) return;
    timer = setInterval(function () {
      if (paused || document.hidden) return;
      setScreen((cur + 1) % imgs.length);
    }, rotMs);
  }

  dots.forEach(function (d, i) {
    d.addEventListener('click', function () {
      setScreen(i);
      restart();
    });
  });

  shots.addEventListener('mouseenter', function () { paused = true; });
  shots.addEventListener('mouseleave', function () { paused = false; });

  setScreen(0);
  restart();
})();
