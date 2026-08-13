(function () {
  const DURATION_MS = 2600;
  const COLORS = [
    "#ff6b6b",
    "#ffd93d",
    "#6bcb77",
    "#4d96ff",
    "#ff6bd6",
    "#c77dff",
    "#ffa94d",
    "#ffffff",
  ];

  function prefersReducedMotion() {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
  }

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  function pickColor() {
    return COLORS[Math.floor(Math.random() * COLORS.length)];
  }

  function createParticle(w, h, burst) {
    const angle = burst ? randomBetween(0, Math.PI * 2) : randomBetween(-0.4, 0.4);
    const speed = burst ? randomBetween(4, 11) : randomBetween(2, 7);
    const originX = burst ? burst.x : randomBetween(0, w);
    const originY = burst ? burst.y : randomBetween(-20, -4);
    return {
      x: originX,
      y: originY,
      vx: Math.cos(angle) * speed + randomBetween(-1.5, 1.5),
      vy: Math.sin(angle) * speed + (burst ? randomBetween(-2, 0) : randomBetween(2, 6)),
      w: randomBetween(6, 12),
      h: randomBetween(4, 9),
      rot: randomBetween(0, Math.PI * 2),
      spin: randomBetween(-0.2, 0.2),
      color: pickColor(),
      shape: Math.random() < 0.35 ? "circle" : "rect",
      drag: burst ? 0.985 : 0.992,
      gravity: burst ? 0.12 : randomBetween(0.14, 0.22),
      life: 1,
      decay: randomBetween(0.006, 0.012),
    };
  }

  function drawParticle(ctx, p) {
    ctx.save();
    ctx.translate(p.x, p.y);
    ctx.rotate(p.rot);
    ctx.globalAlpha = Math.max(0, p.life);
    ctx.fillStyle = p.color;
    if (p.shape === "circle") {
      ctx.beginPath();
      ctx.arc(0, 0, p.w * 0.45, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.fillRect(-p.w * 0.5, -p.h * 0.5, p.w, p.h);
    }
    ctx.restore();
  }

  function drawSpark(ctx, x, y, radius, alpha) {
    const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
    gradient.addColorStop(0, `rgba(255, 240, 180, ${alpha})`);
    gradient.addColorStop(0.35, `rgba(255, 120, 80, ${alpha * 0.7})`);
    gradient.addColorStop(1, "rgba(120, 80, 255, 0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  function celebrate(options = {}) {
    if (prefersReducedMotion()) return false;

    const durationMs = options.durationMs ?? DURATION_MS;
    const canvas = document.createElement("canvas");
    canvas.className = "nex-celebrate-canvas";
    canvas.setAttribute("aria-hidden", "true");
    document.body.appendChild(canvas);

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      canvas.remove();
      return false;
    }

    let width = 0;
    let height = 0;
    let particles = [];
    let sparks = [];
    let rafId = 0;
    const start = performance.now();
    let lastBurst = 0;

    function resize() {
      width = window.innerWidth;
      height = window.innerHeight;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function spawnBurst() {
      const x = randomBetween(width * 0.2, width * 0.8);
      const y = randomBetween(height * 0.25, height * 0.55);
      sparks.push({ x, y, radius: 4, alpha: 1, decay: 0.045 });
      const count = Math.floor(randomBetween(28, 42));
      for (let i = 0; i < count; i += 1) {
        particles.push(createParticle(width, height, { x, y }));
      }
    }

    function tick(now) {
      const elapsed = now - start;
      if (elapsed >= durationMs) {
        cancelAnimationFrame(rafId);
        window.removeEventListener("resize", resize);
        canvas.remove();
        return;
      }

      if (elapsed - lastBurst > 420 && sparks.length < 6) {
        spawnBurst();
        lastBurst = elapsed;
      }

      if (particles.length < 140 && Math.random() < 0.35) {
        particles.push(createParticle(width, height, null));
      }

      ctx.clearRect(0, 0, width, height);

      sparks = sparks.filter((s) => {
        s.radius += 2.8;
        s.alpha -= s.decay;
        if (s.alpha <= 0) return false;
        drawSpark(ctx, s.x, s.y, s.radius, s.alpha);
        return true;
      });

      particles = particles.filter((p) => {
        p.vx *= p.drag;
        p.vy = p.vy * p.drag + p.gravity;
        p.x += p.vx;
        p.y += p.vy;
        p.rot += p.spin;
        p.life -= p.decay;
        if (p.life <= 0 || p.y > height + 40) return false;
        drawParticle(ctx, p);
        return true;
      });

      rafId = requestAnimationFrame(tick);
    }

    resize();
    window.addEventListener("resize", resize);
    for (let i = 0; i < 90; i += 1) {
      particles.push(createParticle(width, height, null));
    }
    spawnBurst();
    window.setTimeout(spawnBurst, 180);
    window.setTimeout(spawnBurst, 520);
    rafId = requestAnimationFrame(tick);
    return true;
  }

  window.NexCelebrate = { celebrate, prefersReducedMotion };
})();
