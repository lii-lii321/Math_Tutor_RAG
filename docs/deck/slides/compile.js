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

const slideModules = [
  require('./slide-01.js'), require('./slide-02.js'), require('./slide-03.js'),
  require('./slide-04.js'), require('./slide-05.js'), require('./slide-06.js'),
  require('./slide-07.js'), require('./slide-08.js'), require('./slide-09.js'),
  require('./slide-10.js'), require('./slide-11.js'), require('./slide-12.js'),
  require('./slide-13.js'), require('./slide-14.js'), require('./slide-15.js'),
  require('./slide-16.js'), require('./slide-17.js'), require('./slide-18.js'),
  require('./slide-19.js'), require('./slide-20.js'), require('./slide-21.js'),
  require('./slide-22.js'), require('./slide-23.js'), require('./slide-24.js'),
  require('./slide-25.js'),
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
      source: {
        file: 'slides/slide-' + String(current.slideNumber).padStart(2, '0') + '.js',
        method: opts.__method,
      },
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

slideModules.forEach(function (mod, i) {
  const name = 'slide-' + String(i + 1).padStart(2, '0');
  if (typeof mod.createSlide !== 'function') throw new Error(name + ' does not export createSlide()');
  mod.createSlide(pres, theme);
});

const outDir = path.resolve(__dirname, 'output');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
const outFile = path.join(outDir, OUT_NAME);
// 输出文件必须落在 output/ 边界内（OUT_NAME 为常量，此处守住未来改动不越界）
if (!outFile.startsWith(outDir + path.sep)) throw new Error('output path escapes outDir: ' + OUT_NAME);

pres.writeFile({ fileName: outFile })
  .then(function () {
    const n = recorder.write(outFile.replace(/\.pptx$/, '.mavis-ppt-map.json'));
    console.log('WROTE ' + outFile);
    console.log('slides: ' + slideModules.length + '  size: ' + Math.round(fs.statSync(outFile).size / 1024) + ' KB');
    console.log('element-map: ' + n + ' elements');
  })
  .catch(function (err) {
    console.error('COMPILE FAILED: ' + err.message);
    process.exit(1);
  });
