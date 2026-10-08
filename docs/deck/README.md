# docs/deck — UI redesign 幻灯片工具链

- `slides/*.js` 为 25 页幻灯片源码，`compile.js` 编译出 `slides/output/*.pptx`（npm 依赖见 `package-lock.json`，含 jszip）。
- `render_qa.py` / `render_mockups.py` 用 LibreOffice 把 PPTX 渲染成 `qa/slide-*.png` 截图；
  `qa/loprofile/` 是传给 LibreOffice 的确定性用户配置档（`-env:UserInstallation`），仅本机使用，勿提交。
- Python 渲染环境 `.qaenv/` 曾被误提交（见 CHANGELOG，2026-10 已清理出索引），依赖钉死在
  `requirements-qa.txt`。本机重建：

  ```
  py -3.13 -m venv .qaenv
  .qaenv\Scripts\python -m pip install -r requirements-qa.txt
  ```

三个目录（`.qaenv/`、`node_modules/`、`qa/loprofile/`）均已在 `.gitignore`，由本机自持。
