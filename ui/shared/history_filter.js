/* History in Motion filtering, applied to a design example.

   HiM (Veuskens et al., SCF 2023) finds the features that created or
   modified a selected geometry element by comparing the geometry before and
   after each feature. Here the designer's steps play the role of features:
   a step is relevant to a picked point when the surface under that point
   is new or different after the step (the nearest triangle after the step
   does not exist before it). "Show more" then follows the steps it builds
   on (dependencies stated by the designer or derived from the CAD timeline),
   one level per click, as HiM follows the sketches' supporting faces.
   Pure functions; tested in tests/test_history_filter.py via Node. */
(function (root) {
  "use strict";

  const round = (v) => Math.round(v * 1000) / 1000;
  function triKey(a, b, c) {
    return [a, b, c].map((p) => p.map(round).join(",")).sort().join("|");
  }

  function trianglesOf(meshes) {
    const tris = [];
    for (const m of meshes) for (const t of m.triangles) {
      const a = m.vertices[t[0]], b = m.vertices[t[1]], c = m.vertices[t[2]];
      tris.push({ a, b, c, key: triKey(a, b, c) });
    }
    return tris;
  }

  /* Closest point on triangle (Ericson, Real-Time Collision Detection). */
  function sub(u, v) { return [u[0] - v[0], u[1] - v[1], u[2] - v[2]]; }
  function dot(u, v) { return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]; }
  function add(u, v, s) { return [u[0] + v[0] * s, u[1] + v[1] * s, u[2] + v[2] * s]; }
  function closest(p, a, b, c) {
    const ab = sub(b, a), ac = sub(c, a), ap = sub(p, a);
    const d1 = dot(ab, ap), d2 = dot(ac, ap);
    if (d1 <= 0 && d2 <= 0) return a;
    const bp = sub(p, b), d3 = dot(ab, bp), d4 = dot(ac, bp);
    if (d3 >= 0 && d4 <= d3) return b;
    const vc = d1 * d4 - d3 * d2;
    if (vc <= 0 && d1 >= 0 && d3 <= 0) return add(a, ab, d1 / (d1 - d3));
    const cp = sub(p, c), d5 = dot(ab, cp), d6 = dot(ac, cp);
    if (d6 >= 0 && d5 <= d6) return c;
    const vb = d5 * d2 - d1 * d6;
    if (vb <= 0 && d2 >= 0 && d6 <= 0) return add(a, ac, d2 / (d2 - d6));
    const va = d3 * d6 - d5 * d4;
    if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) return add(b, sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6)));
    const denom = 1 / (va + vb + vc);
    return add(add(a, ab, vb * denom), ac, vc * denom);
  }
  function nearest(tris, p) {
    let best = null, bestD = Infinity;
    for (const t of tris) {
      const q = closest(p, t.a, t.b, t.c);
      const d = Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
      if (d < bestD) { bestD = d; best = t; }
    }
    return { tri: best, distance: bestD };
  }

  /* steps: [{id, geometry:{meshes}, depends_on?, depends_on_derived?}] */
  function buildIndex(steps) {
    const after = steps.map((s) => trianglesOf(s.geometry.meshes));
    const keys = after.map((tris) => new Set(tris.map((t) => t.key)));
    let size = 1;
    const last = after[after.length - 1] || [];
    if (last.length) {
      const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
      for (const t of last) for (const v of [t.a, t.b, t.c]) for (let i = 0; i < 3; i++) {
        lo[i] = Math.min(lo[i], v[i]); hi[i] = Math.max(hi[i], v[i]);
      }
      size = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) || 1;
    }
    return { steps, after, keys, eps: size * 0.01 };
  }

  /* Steps (indices, up to `upto`) whose surface under the point is new or changed. */
  function changedAt(index, point, upto) {
    const out = [];
    const last = Math.min(upto === undefined ? index.steps.length - 1 : upto, index.steps.length - 1);
    for (let i = 0; i <= last; i++) {
      const hit = nearest(index.after[i], point);
      if (!hit.tri || hit.distance > index.eps) continue;
      const before = i > 0 ? index.keys[i - 1] : new Set();
      if (!before.has(hit.tri.key)) out.push(i);
    }
    return out;
  }

  /* One "show more" level: earlier steps the given steps build on. */
  function buildsOn(index, indices) {
    const ids = index.steps.map((s) => s.id);
    const found = [];
    for (const i of indices) {
      const step = index.steps[i];
      for (const id of (step.depends_on || []).concat(step.depends_on_derived || [])) {
        const j = ids.indexOf(id);
        if (j >= 0 && j < i && !indices.includes(j) && !found.includes(j)) found.push(j);
      }
    }
    return found;
  }

  const api = { buildIndex, changedAt, buildsOn, triKey };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ExcadmpleHistoryFilter = api;
})(typeof window !== "undefined" ? window : this);
