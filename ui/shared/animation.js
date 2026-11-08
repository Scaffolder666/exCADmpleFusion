/* JavaScript port of core/animation.py and core/pointer.py (sampling only).
   Used by the reference viewport (layout A) to compute frames locally.
   Validation stays in Python: packages are validated when they are opened.
   tests/test_js_parity.py checks this port against the Python originals. */
(function (root) {
  "use strict";
  const clamp = (t) => Math.max(0, Math.min(1, Number(t) || 0));
  const TRANSITIONS = ["fillet", "chamfer", "boolean", "split", "combine", "loft", "shell", "thread", "import", "export"];

  function extrudeMesh(a, progress) {
    const t = Math.max(0.0005, clamp(progress));
    const profile = a.profile, dir = a.direction_cm, n = profile.length;
    const vertices = profile.map((p) => p.slice()).concat(profile.map((p) => [0, 1, 2].map((i) => p[i] + t * dir[i])));
    const triangles = [];
    for (const [x, y, z] of a.cap_triangles) {
      triangles.push([z, y, x]);
      triangles.push([x + n, y + n, z + n]);
    }
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      triangles.push([i, j, j + n]);
      triangles.push([i, j + n, i + n]);
    }
    return { vertices, triangles };
  }

  function revealMeshes(a, progress) {
    const t = Math.max(0.001, clamp(progress));
    const context = (a.context_meshes || []).slice();
    if (t >= 1) return context.concat(a.new_meshes);
    return context.concat(a.new_meshes.map((m) => {
      const c = [0, 1, 2].map((i) => m.vertices.reduce((s, p) => s + p[i], 0) / m.vertices.length);
      return { vertices: m.vertices.map((p) => [0, 1, 2].map((i) => c[i] + (p[i] - c[i]) * t)), triangles: m.triangles };
    }));
  }

  function transitionMeshes(a, progress) {
    const t = clamp(progress);
    const before = a.before_meshes, after = a.after_meshes;
    if (t <= 0) return before;
    if (t >= 1) return after;
    const same = before.length === after.length && before.every((m, k) =>
      m.vertices.length === after[k].vertices.length && JSON.stringify(m.triangles) === JSON.stringify(after[k].triangles));
    if (!same) return t < 0.5 ? before : after;
    return before.map((m, k) => ({
      vertices: m.vertices.map((p, v) => [0, 1, 2].map((i) => p[i] * (1 - t) + after[k].vertices[v][i] * t)),
      triangles: after[k].triangles,
    }));
  }

  function rectangularPattern(a, progress) {
    const t = clamp(progress);
    const nx = a.x_count || 1, ny = a.y_count || 1;
    const visible = 1 + Math.floor((nx * ny - 1) * t + 1e-9);
    const dx = a.x_offset_cm || [0, 0, 0], dy = a.y_offset_cm || [0, 0, 0];
    const out = (a.context_meshes || []).slice();
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      if (j * nx + i >= visible) return out;
      for (const m of a.new_meshes) out.push({
        vertices: m.vertices.map((p) => [0, 1, 2].map((k) => p[k] + i * dx[k] + j * dy[k])), triangles: m.triangles,
      });
    }
    return out;
  }

  function operationMeshes(a, progress) {
    const t = clamp(progress);
    const out = (a.context_meshes || []).slice();
    const origin = a.axis_origin_cm || [0, 0, 0];
    let axis = a.axis_direction || [0, 0, 1];
    const len = Math.hypot(axis[0], axis[1], axis[2]);
    axis = axis.map((v) => v / len);
    const rotate = (p, angle) => {
      const v = [0, 1, 2].map((i) => p[i] - origin[i]);
      const c = Math.cos(angle), s = Math.sin(angle);
      const cross = [axis[1] * v[2] - axis[2] * v[1], axis[2] * v[0] - axis[0] * v[2], axis[0] * v[1] - axis[1] * v[0]];
      const dot = axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2];
      return [0, 1, 2].map((i) => origin[i] + v[i] * c + cross[i] * s + axis[i] * dot * (1 - c));
    };
    const map = (m, fn, reverse) => ({ vertices: m.vertices.map(fn),
      triangles: reverse ? m.triangles.map((tr) => [tr[0], tr[2], tr[1]]) : m.triangles });
    const deg = (a.angle_deg === undefined ? 360 : a.angle_deg) * Math.PI / 180;
    if (a.type === "pattern") {
      for (let i = 0; i < a.count; i++) {
        if (i > (a.count - 1) * t + 1e-9) break;
        for (const m of a.new_meshes) out.push(map(m, (p) => rotate(p, deg * i / a.count)));
      }
    } else if (a.type === "revolve") {
      for (const m of a.new_meshes) out.push(map(m, (p) => rotate(p, deg * t)));
    } else if (a.type === "mirror") {
      const nrm = a.plane_normal, nl = Math.hypot(nrm[0], nrm[1], nrm[2]);
      const n = nrm.map((v) => v / nl), o = a.plane_origin_cm;
      for (const m of a.new_meshes) {
        out.push(m);
        if (t > 0) out.push(map(m, (p) => {
          const d = (p[0] - o[0]) * n[0] + (p[1] - o[1]) * n[1] + (p[2] - o[2]) * n[2];
          return [0, 1, 2].map((i) => p[i] - 2 * t * d * n[i]);
        }, true));
      }
    } else if (a.type === "transform") {
      const tr = a.translation_cm;
      for (const m of a.new_meshes) out.push(map(m, (p) => [0, 1, 2].map((i) => p[i] + t * tr[i])));
    }
    return out;
  }

  function animationMeshes(a, progress) {
    switch (a.type) {
      case "snapshots": return a.states[Math.min(a.states.length - 1, Math.floor(clamp(progress) * a.states.length))];
      case "reveal": return revealMeshes(a, progress);
      case "extrude": return (a.context_meshes || []).concat([extrudeMesh(a, progress)]);
      case "rectangular_pattern": return rectangularPattern(a, progress);
      default:
        if (TRANSITIONS.includes(a.type)) return transitionMeshes(a, progress);
        return operationMeshes(a, progress);
    }
  }

  const CLICK_MS = 450;
  function samplePointer(points, atMs, trailMs = 1500) {
    if (!points || !points.length) return null;
    let pos, segment;
    if (atMs <= points[0].at_ms) { pos = points[0].xyz.slice(); segment = 0; }
    else if (atMs >= points[points.length - 1].at_ms) { pos = points[points.length - 1].xyz.slice(); segment = points.length - 1; }
    else {
      segment = 0;
      points.forEach((p, i) => { if (p.at_ms <= atMs) segment = i; });
      const a = points[segment], b = points[segment + 1];
      let t = (atMs - a.at_ms) / Math.max(1e-6, b.at_ms - a.at_ms);
      t = t * t * (3 - 2 * t);
      pos = [0, 1, 2].map((i) => a.xyz[i] + (b.xyz[i] - a.xyz[i]) * t);
    }
    const next = points[segment + 1];
    const pressed = points.some((p) => (p.event === "click" || p.event === "drag") && atMs - p.at_ms >= 0 && atMs - p.at_ms <= CLICK_MS);
    const trail = points.filter((p) => p.at_ms >= atMs - trailMs && p.at_ms <= atMs).map((p) => p.xyz.slice());
    trail.push(pos);
    return { xyz: pos, gesture: next && next.event === "drag" ? "drag" : "move", pressed, trail };
  }

  const api = { animationMeshes, samplePointer };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ExcadmpleAnimation = api;
})(typeof window !== "undefined" ? window : this);
