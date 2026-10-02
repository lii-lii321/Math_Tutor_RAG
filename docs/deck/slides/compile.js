/**
 * Compile the MathMaster Edu design deck.
 * Run from anywhere:  node slides/compile.js
 *
 * Also emits an optional element-map sidecar next to the .pptx so later edit
 * requests can resolve a preview selection back to a stable elementId.
 * The sidecar is metadata only: it never changes the visible deck.
 */
const path = require('path');
const fs = require('fs');

process.chdir(path.resolve(__dirname, '..'));

const pptxgen = require('pptxgenjs');

const LAYOUT = { name: 'LAYOUT_16x9', widthIn: 10, heightIn: 5.625 };
const OUT_NAME = 'mathmaster-ui-redesign-v1.pptx';

const theme = {
  primary: '16294A',   // navy - titles and structural blocks
  secondary: '64748B', // slate - supporting text
  accent: '2563EB',    // brand blue - interactive emphasis
  light: 'FFFFFF',     // card surface
  bg: 'F7F8FA',        // page background
};

const ORDER = [
  'slide-01', 'slide-02', 'slide-03', 'slide-04', 'slide-05',
  'slide-06', 'slide-07', 'slide-08', 'slide-09', 'slide-10',
  'slide-11', 'slide-12', 'slide-13', 'slide-14', 'slide-15',
  'slide-16', 'slide-17', 'slide-18', 'slide-19', 'slide-20',
  'slide-21', 'slide-22', 'slide-23', 'slide-24', 'slide-25',
];

/* ------------------------------------------------------------------ *
 * Element-map recorder
 * Wraps addSlide so every addText/addShape/addImage is captured with a
 * stable id, its rect, and a trimmed style subset -- without touching
 * the slide modules themselves.
 * ------------------------------------------------------------------ */
function createRecorder() {
  const slides = [];
  let current = null;
  let counter = 0;

  const STYLE_KEYS = ['fontSize', 'fontFace', 'color', 'bold', 'italic', 'align', 'valign', 'charSpacing'];
  const norm = (r) => ({
    x: +(r.x / LAYOUT.widthIn).toFixed(4),
    y: +(r.y / LAYOUT.heightIn).toFixed(4),
    w: +(r.w / LAYOUT.widthIn).toFixed(4),
    h: +(r.h / LAYOUT.heightIn).toFixed(4),
  });
  const pick = (o) => {
    const out = {};
    STYLE_KEYS.forEach((k) => { if (o && o[k] !== undefined) out[k] = o[k]; });
    return out;
  };
  const rectOf = (o) => ({ x: o.x || 0, y: o.y || 0, w: o.w || 0, h: o.h || 0 });
  const textOf = (t) => {
    if (typeof t === 'string') return t;
    if (Array.isArray(t)) return t.map((r) => (r && r.text) || '').join('');
    return '';
  };

  function record(kind, role, payload, opts) {
    if (!current) return;
    const r = rectOf(opts);
    current.elements.push({
      elementId: 's' + current.slideNumber + '.' + (++counter),
      kind: kind,
      role: role,
      text: textOf(payload).slice(0, 120),
      rectIn: r,
      normalizedRect: norm(r),
      style: pick(opts),
      source: { file: 'slides/' + ORDER[current.slideNumber - 1] + '.js', method: opts.__method },
    });
  }

  function attach(pres) {
    const original = pres.addSlide.bind(pres);
    pres.addSlide = function (...args) {
      const slide = original(...args);
      current = { slideNumber: slides.length + 1, slideId: 'slide-' + (slides.length + 1), title: '', elements: [] };
      slides.push(current);

      const rawText = slide.addText.bind(slide);
      const rawShape = slide.addShape.bind(slide);
      const rawImage = slide.addImage.bind(slide);

      slide.addText = (t, o = {}) => { record('text', o.__role || 'body', t, o); return rawText(t, o); };
      slide.addShape = (s, o = {}) => { record('shape', 'card', '', o); return rawShape(s, o); };
      slide.addImage = (o = {}) => { record('image', 'image', o.altText || '', o); return rawImage(o); };
      return slide;
    };
  }

  return {
    attach: attach,
    write: (filePath) => {
      fs.writeFileSync(
        filePath,
        JSON.stringify(
          {
            schema: 'mavis.ppt_element_map.v1',
            artifact: {
              fileName: OUT_NAME,
              filePath: './output/' + OUT_NAME,
              createdAtMs: Date.now(),
              generator: 'presentations-skill',
            },
            layout: LAYOUT,
            slides: slides,
          },
          null,
          2,
        ),
        'utf-8',
      );
      return slides.reduce((n, s) => n + s.elements.length, 0);
    },
  };
}

/* -------------------------- build -------------------------- */
const pres = new pptxgen();
pres.layout = LAYOUT.name;
pres.author = 'Mavis';
pres.company = 'MathMaster Edu';
pres.title = 'MathMaster Edu 界面重设计方案 v1.0';
pres.subject = '信息架构 / 视觉层级 / 交互密度 重做方案';

const recorder = createRecorder();
recorder.attach(pres);

ORDER.forEach(function (name) {
  const mod = require('./' + name + '.js');
  if (typeof mod.createSlide !== 'function') throw new Error(name + ' does not export createSlide()');
  mod.createSlide(pres, theme);
});

const outDir = path.resolve(__dirname, 'output');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
const outFile = path.join(outDir, OUT_NAME);

pres.writeFile({ fileName: outFile })
  .then(function () {
    const n = recorder.write(outFile.replace(/\.pptx$/, '.mavis-ppt-map.json'));
    console.log('WROTE ' + outFile);
    console.log('slides: ' + ORDER.length + '  size: ' + Math.round(fs.statSync(outFile).size / 1024) + ' KB');
    console.log('element-map: ' + n + ' elements');
  })
  .catch(function (err) {
    console.error('COMPILE FAILED: ' + err.message);
    process.exit(1);
  });
