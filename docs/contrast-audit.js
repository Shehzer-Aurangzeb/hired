(() => {
  const L = (r,g,b) => { const f = v => { v/=255; return v<=0.03928 ? v/12.92 : ((v+0.055)/1.055)**2.4; };
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
  const parse = s => (s.match(/\d+(\.\d+)?/g)||[]).map(Number);
  const bgOf = el => { let n = el;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c.length >= 3 && (c[3] === undefined || c[3] > 0.5)) return c;
      n = n.parentElement;
    }
    return [255,255,255];
  };
  const bad = [];
  for (const el of document.querySelectorAll('*')) {
    const t = Array.from(el.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join('');
    if (!t) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.5) continue;
    const fg = parse(cs.color), bg = bgOf(el);
    const lf = L(fg[0],fg[1],fg[2]), lb = L(bg[0],bg[1],bg[2]);
    const ratio = (Math.max(lf,lb)+0.05)/(Math.min(lf,lb)+0.05);
    const px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 700;
    const need = (px >= 24 || (px >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) bad.push(`${ratio.toFixed(2)}<${need} ${px}px ${cs.color} on rgb(${bg.slice(0,3)}) :: ${t.slice(0,45)}`);
  }
  return bad.length ? bad.slice(0,15).join('\n') : 'ALL TEXT PASSES WCAG AA';
})()
