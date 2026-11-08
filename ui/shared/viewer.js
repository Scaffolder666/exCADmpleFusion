/* Version A (HiM style) — the interactive 3D reference viewport.
   The example plays here; the user's own model stays in the Fusion canvas.
   As in History in Motion, geometry the current step did not change is drawn
   transparent, the final model is kept as a faint ghost, and clicking the
   model picks a point for filtering the history (see history_filter.js).
   Orbit (left drag), pan (right drag), zoom (wheel). Coordinates are the
   package's centimeters, Z up as in Fusion. Requires vendor/three.min.js,
   vendor/OrbitControls.js and shared/animation.js. */
(function (root) {
  "use strict";
  const COLORS = { body: 0x5f8fc7, edge: 0x2f4f78, pointer: 0xf58c14, trail: 0xfabe5a, grid: 0xd6dde6 };

  // Same mesh up to rounding (animation data and stored results may differ
  // in the last digits).
  function meshKey(m) {
    return m.vertices.map((v) => v.map((c) => Math.round(c * 1000)).join(",")).join(";") + "#" + m.triangles.length;
  }

  class ReferenceViewer {
    constructor(container) {
      const THREE = root.THREE;
      this.THREE = THREE;
      this.container = container;
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      this.renderer.setPixelRatio(Math.min(2, root.devicePixelRatio || 1));
      this.renderer.setClearColor(0xf4f6f9);
      container.appendChild(this.renderer.domElement);
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
      this.camera.up.set(0, 0, 1);
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a96a3, 0.85));
      const sun = new THREE.DirectionalLight(0xffffff, 0.65);
      sun.position.set(30, -40, 60);
      this.scene.add(sun);
      this.material = new THREE.MeshStandardMaterial({ color: COLORS.body, roughness: 0.55, metalness: 0.05,
        side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
      this.edgeMaterial = new THREE.LineBasicMaterial({ color: COLORS.edge, transparent: true, opacity: 0.35 });
      this.contextMaterial = new THREE.MeshStandardMaterial({ color: 0x9aa7b5, roughness: 0.7, transparent: true,
        opacity: 0.28, depthWrite: false, side: THREE.DoubleSide });
      this.ghostMaterial = new THREE.MeshBasicMaterial({ color: 0x9aa7b5, transparent: true, opacity: 0.07,
        depthWrite: false, side: THREE.DoubleSide });
      this.ghost = new THREE.Group();
      this.scene.add(this.ghost);
      this.marker = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 12),
        new THREE.MeshBasicMaterial({ color: 0xd61f69, depthTest: false }));
      this.marker.renderOrder = 11;
      this.marker.visible = false;
      this.scene.add(this.marker);
      this.onPick = null;
      this._listenForPicks();
      this.model = new THREE.Group();
      this.scene.add(this.model);
      this.pointer = this._makePointer();
      this.scene.add(this.pointer.group);
      this.steps = [];
      this.signature = "";
      new ResizeObserver(() => this.resize()).observe(container);
      this.resize();
      const loop = () => { this.controls.update(); this.renderer.render(this.scene, this.camera); requestAnimationFrame(loop); };
      loop();
    }

    _makePointer() {
      const THREE = this.THREE;
      const group = new THREE.Group();
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12),
        new THREE.MeshBasicMaterial({ color: COLORS.pointer, depthTest: false }));
      dot.renderOrder = 10;
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.4, 0.55, 32),
        new THREE.MeshBasicMaterial({ color: COLORS.pointer, side: THREE.DoubleSide, depthTest: false }));
      ring.renderOrder = 10;
      const trail = new THREE.Line(new THREE.BufferGeometry(),
        new THREE.LineBasicMaterial({ color: COLORS.trail, depthTest: false }));
      trail.renderOrder = 9;
      group.add(dot, ring, trail);
      group.visible = false;
      return { group, dot, ring, trail };
    }

    resize() {
      const w = Math.max(10, this.container.clientWidth), h = Math.max(10, this.container.clientHeight);
      this.renderer.setSize(w, h, false);
      this.renderer.domElement.style.width = "100%";
      this.renderer.domElement.style.height = "100%";
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
    }

    /* steps: [{animation, geometry:{meshes}, pointer, duration_ms}] */
    setExample(steps) {
      this.steps = steps || [];
      this.signature = "";
      this.marker.visible = false;
      const last = this.steps.length ? this.steps[this.steps.length - 1].geometry.meshes : [];
      this._fit(last);
      this._fill(this.ghost, last, this.ghostMaterial, false);
    }

    _listenForPicks() {
      const el = this.renderer.domElement;
      let down = null;
      el.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY, e.button]; });
      el.addEventListener("pointerup", (e) => {
        if (!down || down[2] !== 0 || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) { down = null; return; }
        down = null;
        const rect = el.getBoundingClientRect();
        const ndc = new this.THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1,
                                           -((e.clientY - rect.top) / rect.height) * 2 + 1);
        const ray = new this.THREE.Raycaster();
        ray.setFromCamera(ndc, this.camera);
        const hits = ray.intersectObjects(this.model.children.filter((o) => o.isMesh), false);
        const point = hits.length ? hits[0].point : null;
        this.marker.visible = !!point;
        if (point) {
          this.marker.position.copy(point);
          this.marker.scale.setScalar(this.pointerScale || 1);
        }
        if (this.onPick) this.onPick(point ? [point.x, point.y, point.z] : null);
      });
    }

    clearPick() { this.marker.visible = false; }

    setGhost(visible) { this.ghost.visible = !!visible; }

    _fit(meshes) {
      const THREE = this.THREE;
      const box = new THREE.Box3();
      for (const m of meshes) for (const v of m.vertices) box.expandByPoint(new THREE.Vector3(v[0], v[1], v[2]));
      if (box.isEmpty()) box.set(new THREE.Vector3(-5, -5, 0), new THREE.Vector3(5, 5, 5));
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3()).length();
      this.controls.target.copy(center);
      this.camera.position.copy(center).add(new THREE.Vector3(0.9, -1.3, 0.8).multiplyScalar(size));
      this.camera.near = size / 100;
      this.camera.far = size * 50;
      this.camera.updateProjectionMatrix();
      if (this.grid) this.scene.remove(this.grid);
      this.grid = new THREE.GridHelper(Math.ceil(size * 1.6), 16, COLORS.grid, COLORS.grid);
      this.grid.rotation.x = Math.PI / 2;
      this.grid.position.set(center.x, center.y, box.min.z - 0.01);
      this.scene.add(this.grid);
      this.pointerScale = Math.max(0.6, size / 25);
    }

    resetView() {
      if (this.steps.length) this._fit(this.steps[this.steps.length - 1].geometry.meshes);
    }

    show(index, progress, elapsedMs) {
      const step = this.steps[index];
      if (!step) return;
      const meshes = step.animation ? root.ExcadmpleAnimation.animationMeshes(step.animation, progress)
        : step.geometry.meshes;
      const signature = index + ":" + (step.animation ? Math.round(progress * 400) : "final");
      if (signature !== this.signature) {
        this.signature = signature;
        // Geometry identical to the previous step's result is context: HiM
        // renders it transparent so the step's own change stands out.
        const before = new Set(index > 0 ? this.steps[index - 1].geometry.meshes.map(meshKey) : []);
        this._setMeshes(meshes.filter((m) => !before.has(meshKey(m))),
                        meshes.filter((m) => before.has(meshKey(m))));
      }
      this._showPointer(step, elapsedMs);
    }

    _setMeshes(changed, context) {
      for (const child of this.model.children.slice()) {
        child.geometry.dispose();
        this.model.remove(child);
      }
      this._fill(this.model, context, this.contextMaterial, false, true);
      this._fill(this.model, changed, this.material, true, true);
    }

    _fill(group, meshes, material, edges, keep) {
      const THREE = this.THREE;
      if (!keep) for (const child of group.children.slice()) { child.geometry.dispose(); group.remove(child); }
      for (const m of meshes) {
        if (!m.triangles.length) continue;
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(m.vertices.flat(), 3));
        geometry.setIndex(m.triangles.flat());
        geometry.computeVertexNormals();
        group.add(new THREE.Mesh(geometry, material));
        if (edges) group.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 30), this.edgeMaterial));
      }
    }

    _showPointer(step, elapsedMs) {
      const p = this.pointer;
      const state = elapsedMs === null || elapsedMs === undefined ? null :
        root.ExcadmpleAnimation.samplePointer(step.pointer, elapsedMs);
      p.group.visible = !!state;
      if (!state) return;
      const s = this.pointerScale || 1;
      p.dot.position.set(...state.xyz);
      p.dot.scale.setScalar(s * (state.pressed ? 1.4 : 1));
      p.ring.position.set(...state.xyz);
      p.ring.scale.setScalar(s);
      p.ring.visible = state.pressed;
      p.ring.quaternion.copy(this.camera.quaternion);
      p.trail.geometry.dispose();
      p.trail.geometry = new this.THREE.BufferGeometry().setFromPoints(
        state.trail.map((v) => new this.THREE.Vector3(v[0], v[1], v[2])));
    }
  }

  root.ReferenceViewer = ReferenceViewer;
})(window);
