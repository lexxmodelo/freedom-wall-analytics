/* Data fetcher for the institutional dashboard. */
window.InstData = (function () {
  let _meta = null;
  let _summary = null;

  async function meta() {
    if (!_meta) _meta = await DashUtils.loadJSON("../data/_meta.json");
    return _meta;
  }

  async function summary() {
    if (!_summary) _summary = await DashUtils.loadJSON("../data/_summary.json");
    return _summary;
  }

  async function univ(code) {
    return DashUtils.loadJSON(`../data/institutional/${code}.json`);
  }

  return { meta, summary, univ };
})();
