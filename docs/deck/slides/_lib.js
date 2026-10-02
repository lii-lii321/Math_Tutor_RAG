/**
 * Shared layout helpers for the MathMaster Edu design deck.
 * Every helper returns fresh option objects (PptxGenJS mutates them in place).
 */

const CN = 'Microsoft YaHei';

const INK = '1F2937';
const MUTED = '64748B';
const LINE = 'E5E7EB';
const SOFT = 'F1F5F9';
const WEAK = 'DC2626';
const WEAK_BG = 'FEF2F2';
const WEAK_LN = 'FECACA';
const SHAKY = 'D97706';
const SHAKY_BG = 'FFFBEB';
const SHAKY_LN = 'FDE68A';
const GOOD = '059669';
const GOOD_BG = 'ECFDF5';
const GOOD_LN = 'A7F3D0';
const BRAND_BG = 'EFF6FF';
const BRAND_LN = 'BFDBFE';

const shadow = () => ({ type: 'outer', color: '1F2937', blur: 8, offset: 1, angle: 90, opacity: 0.06 });

/** Page-number badge, mandatory on every non-cover slide. */
function pageBadge(slide, theme, n) {
  slide.addShape('rect', {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28,
    fill: { color: theme.light }, line: { color: LINE, width: 0.75 },
  });
  slide.addText(String(n).padStart(2, '0'), {
    x: 9.3, y: 5.1, w: 0.42, h: 0.28, margin: 0,
    fontSize: 10, color: MUTED, align: 'center', valign: 'middle', fontFace: CN,
  });
}

/** Small kicker label above a slide title. */
function kicker(slide, theme, text, y) {
  slide.addShape('rect', {
    x: 0.5, y: y === undefined ? 0.3 : y, w: 0.09, h: 0.2,
    fill: { color: theme.accent },
  });
  slide.addText(text, {
    x: 0.68, y: y === undefined ? 0.3 : y, w: 6, h: 0.2, margin: 0,
    fontSize: 10.5, color: theme.accent, bold: true, charSpacing: 1.2,
    fontFace: CN, valign: 'middle',
  });
}

/** Standard content-slide title block. */
function slideTitle(slide, theme, title, sub) {
  slide.addText(title, {
    x: 0.5, y: 0.55, w: 8.8, h: 0.46, margin: 0,
    fontSize: 27, bold: true, color: theme.primary, fontFace: CN, fit: 'shrink',
  });
  if (sub) {
    slide.addText(sub, {
      x: 0.5, y: 1.02, w: 8.8, h: 0.3, margin: 0,
      fontSize: 12.5, color: theme.secondary, fontFace: CN,
    });
  }
}

/** Rounded card container. */
function card(slide, theme, x, y, w, h, fillColor) {
  slide.addShape('roundRect', {
    x: x, y: y, w: w, h: h,
    fill: { color: fillColor || theme.light },
    line: { color: LINE, width: 0.75 },
    rectRadius: 0.06,
    shadow: shadow(),
  });
}

/** Severity chip: tone is 'weak' | 'shaky' | 'good' | 'brand'. */
function chip(slide, tone, text, x, y, w, h) {
  const map = {
    weak: { fg: WEAK, bg: WEAK_BG, ln: WEAK_LN },
    shaky: { fg: SHAKY, bg: SHAKY_BG, ln: SHAKY_LN },
    good: { fg: GOOD, bg: GOOD_BG, ln: GOOD_LN },
    brand: { fg: '2563EB', bg: BRAND_BG, ln: BRAND_LN },
  };
  const c = map[tone];
  slide.addShape('roundRect', {
    x: x, y: y, w: w, h: h, rectRadius: 0.04,
    fill: { color: c.bg }, line: { color: c.ln, width: 0.75 },
  });
  slide.addText(text, {
    x: x, y: y, w: w, h: h, margin: 0,
    fontSize: 9.5, bold: true, color: c.fg, align: 'center', valign: 'middle', fontFace: CN,
  });
}

/** Bullet list with custom square markers drawn as shapes. */
function bullets(slide, theme, items, x, y, w, opts) {
  const o = opts || {};
  const size = o.size || 12;
  const gap = o.gap || 0.42;
  const markerColor = o.markerColor || theme.accent;
  items.forEach(function (it, i) {
    const yy = y + i * gap;
    slide.addShape('rect', {
      x: x, y: yy + 0.07, w: 0.07, h: 0.07,
      fill: { color: typeof it === 'object' && it.m ? markerColor : markerColor },
    });
    const head = typeof it === 'object' ? it.t : it;
    const body = typeof it === 'object' ? it.d : null;
    if (body) {
      slide.addText([
        { text: head, options: { bold: true, color: INK } },
        { text: '  ' + body, options: { color: theme.secondary } },
      ], {
        x: x + 0.18, y: yy - 0.03, w: w - 0.18, h: gap, margin: 0,
        fontSize: size, fontFace: CN, valign: 'top', lineSpacingMultiple: 1.25,
      });
    } else {
      slide.addText(head, {
        x: x + 0.18, y: yy - 0.03, w: w - 0.18, h: gap, margin: 0,
        fontSize: size, color: INK, fontFace: CN, valign: 'top', lineSpacingMultiple: 1.25,
      });
    }
  });
}

/** Horizontal progress / share bar. */
function bar(slide, x, y, w, h, pct, color, trackColor) {
  slide.addShape('rect', {
    x: x, y: y, w: w, h: h,
    fill: { color: trackColor || SOFT }, line: { color: trackColor || SOFT, width: 0 },
  });
  slide.addShape('rect', {
    x: x, y: y, w: Math.max(0.04, (w * pct) / 100), h: h,
    fill: { color: color }, line: { color: color, width: 0 },
  });
}

/** Section divider body. */
function divider(slide, theme, num, title, intro) {
  slide.background = { color: theme.primary };
  slide.addShape('rect', { x: 0, y: 0, w: 3.2, h: 5.625, fill: { color: '0F1F3A' }, line: { width: 0 } });
  slide.addText(num, {
    x: 0.5, y: 1.9, w: 2.4, h: 1.5, margin: 0,
    fontSize: 96, bold: true, color: '2C5A92', fontFace: 'Arial', valign: 'middle',
  });
  slide.addText(title, {
    x: 3.7, y: 2.15, w: 5.8, h: 0.6, margin: 0,
    fontSize: 32, bold: true, color: 'FFFFFF', fontFace: CN, fit: 'shrink',
  });
  if (intro) {
    slide.addText(intro, {
      x: 3.7, y: 2.85, w: 5.8, h: 0.6, margin: 0,
      fontSize: 12.5, color: 'A9BCD4', fontFace: CN, lineSpacingMultiple: 1.35,
    });
  }
}

module.exports = {
  CN: CN, INK: INK, MUTED: MUTED, LINE: LINE, SOFT: SOFT,
  WEAK: WEAK, WEAK_BG: WEAK_BG, WEAK_LN: WEAK_LN,
  SHAKY: SHAKY, SHAKY_BG: SHAKY_BG, SHAKY_LN: SHAKY_LN,
  GOOD: GOOD, GOOD_BG: GOOD_BG, GOOD_LN: GOOD_LN,
  BRAND_BG: BRAND_BG, BRAND_LN: BRAND_LN,
  shadow: shadow, pageBadge: pageBadge, kicker: kicker, slideTitle: slideTitle,
  card: card, chip: chip, bullets: bullets, bar: bar, divider: divider,
};
