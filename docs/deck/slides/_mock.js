/** Shared mockup slide template: full-bleed product mockup + change annotations. */
const fs = require('fs');
const path = require('path');
const L = require('./_lib.js');

/** Read intrinsic PNG dimensions synchronously (keeps aspect ratio honest). */
function pngSize(file) {
  const buf = fs.readFileSync(path.resolve(__dirname, '..', file));
  return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
}

const IMG_X = 0.5;
const IMG_Y = 1.4;
const IMG_MAX_H = 3.92;
const IMG_MAX_W = 5.55;
const COL_X = 6.35;
const COL_W = 2.85;

/**
 * cfg = { kicker, title, sub, img, changes: [[before, after], ...], foot }
 */
function mockSlide(pres, theme, cfg, pageNo) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  L.kicker(slide, theme, cfg.kicker);
  L.slideTitle(slide, theme, cfg.title, cfg.sub);

  // Image, aspect-ratio preserved
  const size = pngSize(cfg.img);
  const ratio = size.w / size.h;
  let h = IMG_MAX_H;
  let w = h * ratio;
  if (w > IMG_MAX_W) {
    w = IMG_MAX_W;
    h = w / ratio;
  }
  const ix = IMG_X + (IMG_MAX_W - w) / 2;
  const iy = IMG_Y + (IMG_MAX_H - h) / 2;

  slide.addShape('rect', {
    x: ix - 0.04, y: iy - 0.04, w: w + 0.08, h: h + 0.08,
    fill: { color: theme.light }, line: { color: L.LINE, width: 0.75 }, shadow: L.shadow(),
  });
  slide.addImage({ path: cfg.img, x: ix, y: iy, w: w, h: h });

  // Change annotations
  slide.addText('关键改动', {
    x: COL_X, y: 1.4, w: COL_W, h: 0.22, margin: 0,
    fontSize: 11, bold: true, color: theme.primary, fontFace: L.CN,
  });

  const rowH = 0.62;
  cfg.changes.forEach(function (c, i) {
    const y = 1.66 + i * rowH;
    // before
    slide.addShape('rect', {
      x: COL_X, y: y, w: 0.045, h: rowH - 0.08,
      fill: { color: L.LINE }, line: { width: 0 },
    });
    slide.addText(c[0], {
      x: COL_X + 0.14, y: y - 0.02, w: COL_W - 0.14, h: 0.26, margin: 0,
      fontSize: 7.2, color: L.MUTED, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.1,
    });
    slide.addText(c[1], {
      x: COL_X + 0.14, y: y + 0.25, w: COL_W - 0.14, h: 0.34, margin: 0,
      fontSize: 8.6, bold: true, color: theme.primary, fontFace: L.CN, valign: 'top', lineSpacingMultiple: 1.16,
    });
  });

  // Foot note
  if (cfg.foot) {
    const fy = 1.66 + cfg.changes.length * rowH + 0.04;
    slide.addShape('roundRect', {
      x: COL_X, y: fy, w: COL_W, h: 0.5, rectRadius: 0.05,
      fill: { color: L.GOOD_BG }, line: { color: L.GOOD_LN, width: 0.75 },
    });
    slide.addText(cfg.foot, {
      x: COL_X + 0.14, y: fy + 0.05, w: COL_W - 0.28, h: 0.42, margin: 0,
      fontSize: 7.8, color: '047857', fontFace: L.CN, lineSpacingMultiple: 1.2,
    });
  }

  L.pageBadge(slide, theme, pageNo);
  return slide;
}

module.exports = { mockSlide: mockSlide, pngSize: pngSize };
