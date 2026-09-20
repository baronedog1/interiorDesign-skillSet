/* Workspace tools use editor facade transactions, never duplicate furniture/camera state. */
(function (C, T) {
  "use strict";
  C.Workspace = class {
    constructor(api) {
      this.api = api;
      this.measuring = false;
      this.first = null;
      this.endpoint = null;
      this.mode = null;
      this.drag = null;
      this.library = [];
      this.unit = window.PROJECT.measurementUnit || "m";
      this.lines = new T.Group();
      this.lines.name = "编辑尺规（不导出）";
      this.lines.userData.noExport = true;
      C.scene.add(this.lines);
      this.install();
      this.refresh();
    }
    install() {
      const $ = (s) => document.querySelector(s);
      this.$ = $;
      const footer = $(".studio-footer");
      footer.insertAdjacentHTML(
        "afterbegin",
        '<div class="pro-actions"><button id="save-html" class="primary">保存完整 HTML</button><button id="import-html">打开已编辑 HTML</button></div><input id="html-input" type="file" accept=".html" hidden>',
      );
      const walls = $('[data-panel="walls"]');
      walls.insertAdjacentHTML(
        "beforeend",
        `<details id="structure-tools" open><summary>墙体与门窗</summary><p class="pro-hint">解锁后选择或拖动；数值与鼠标修改同一模型。相连墙端、门窗与已关联房间顶点一同更新。</p><label>墙体<select id="edit-wall"></select></label><div class="number-grid"><label>长度 m<input id="wall-length" type="number" min=".05" step=".01"></label><label>厚度 m<input id="wall-thickness" type="number" step=".01"></label><label>高度 m<input id="wall-height" type="number" step=".01"></label></div><details><summary>高级：端点坐标</summary><div class="number-grid"><label>A · X<input id="wall-ax" type="number" step=".01"></label><label>A · Z<input id="wall-az" type="number" step=".01"></label><label>B · X<input id="wall-bx" type="number" step=".01"></label><label>B · Z<input id="wall-bz" type="number" step=".01"></label></div></details><div class="pro-actions"><button id="wall-apply">应用墙体</button><button id="wall-add">连续画墙</button><button id="wall-delete">删除墙体</button><button id="wall-drag">移动 / 拖端点</button><button id="wall-stop">结束绘制</button></div><p id="structure-note" class="pro-hint"></p><label>门窗<select id="edit-opening"></select></label><div class="number-grid"><label>墙上偏移 m<input id="opening-offset" type="number" step=".05"></label><label>宽度 m<input id="opening-width" type="number" step=".05"></label><label>窗台 m<input id="opening-sill" type="number" step=".05"></label><label>高度 m<input id="opening-height" type="number" step=".05"></label><label>类型<select id="opening-type"><option value="door">平开门</option><option value="sliding-door">移门</option><option value="passage">通道</option><option value="window">窗</option><option value="fixed-glazing">固定玻璃</option></select></label></div><div class="pro-actions"><button id="opening-apply">应用门窗</button><button id="opening-add">新增开口</button><button id="opening-delete">删除开口</button></div></details>`,
      );
      $('[data-panel="camera"]').insertAdjacentHTML(
        "beforeend",
        `<details open><summary>比例尺 / 面积 / 拉尺</summary><p id="area-summary" class="pro-hint"></p><div class="pro-actions"><button id="measure-start">两点拉尺</button><button id="measure-cancel">取消</button></div><div class="pro-row">单位<select id="measure-unit"><option value="m">米</option><option value="mm">毫米</option></select></div><p class="pro-hint">二维/三维都投影到世界地板平面 Y=0。吸附墙端/家具包络边，不把屏幕像素当距离。边界面积不扣墙柱，不是产权面积。</p><div id="measurement-list" class="object-list"></div><button id="measure-clear">清除量尺</button></details>`,
      );
      $("#stage").insertAdjacentHTML(
        "beforeend",
        '<div id="scale-hud"><span id="scale-label"></span><i id="scale-bar"></i><small id="scale-note"></small></div><div id="measure-overlay"></div>',
      );
      document.body.insertAdjacentHTML(
        "beforeend",
        `<section id="furniture-library" hidden><div class="library-head"><b>本地家具库</b><input id="library-search" placeholder="名称 / 类别 / 风格"><label>宽度上限 m <input id="library-max-width" type="number" min="0" step=".1" placeholder="不限"></label><select id="library-room"></select><button id="load-library">选择模型目录</button><button id="close-library">收起</button><input id="library-folder" type="file" webkitdirectory directory multiple hidden></div><p class="pro-hint" id="library-message">授权选择含 library.json 与 GLB 的目录。只将本项目使用的资产嵌入交付 HTML，不读取任意磁盘路径。</p><div id="library-items"></div></section>`,
      );
      $('[data-panel="furniture"]').insertAdjacentHTML(
        "afterbegin",
        '<button id="show-library" class="primary" style="width:100%;margin-bottom:10px">打开底部家具库 / 替换款式</button>',
      );
      $("#object-editor").insertAdjacentHTML(
        "beforeend",
        '<details><summary>材质槽 / 原生尺寸 / 删除</summary><select id="native-slot"></select><div class="number-grid"><label>颜色<input id="slot-color" type="color" value="#c2ad94"></label><label>粗糙度<input id="slot-roughness" type="number" min="0" max="1" step=".05" value=".7"></label><label>金属度<input id="slot-metalness" type="number" min="0" max="1" step=".05" value="0"></label></div><div class="pro-actions"><button id="apply-slot">应用材质槽</button><button id="remove-placement">删除家具</button></div><p class="pro-hint">原生家具按资产标注决定等比/分轴变形；更换款式默认使用真实尺寸，不自动压扁。</p></details>',
      );
      const style = $('[data-panel="style"]');
      style.insertAdjacentHTML(
        "beforeend",
        '<details><summary>其它风格（联网研究入口）</summary><input id="style-query" class="search" placeholder="例如：地中海 × 当代简约 70/30"><button id="style-research">导出风格研究任务</button><p class="pro-hint">浏览器不会代用账号联网。Agent 根据任务真实检索，再导入完整配方；失败明确记录，不能退回奶油风。</p></details>',
      );
      $("#save-html").onclick = () => this.saveHTML();
      $("#import-html").onclick = () => $("#html-input").click();
      $("#html-input").onchange = (e) =>
        this.safe(async () => {
          const file = e.target.files[0];
          if (file) {
            const parser = new DOMParser(),
              d = parser.parseFromString(await file.text(), "text/html"),
              node = d.querySelector("#saved-project");
            if (!node)
              throw Error("此HTML没有可恢复的完整编辑快照；不能执行陌生脚本");
            await this.api.importSnapshot(JSON.parse(node.textContent));
            this.refresh();
          }
          e.target.value = "";
        });
      $("#show-library").onclick = () => {
        $("#furniture-library").hidden = false;
        document.body.classList.add("library-open");
        C.layout();
        this.renderLibrary();
      };
      $("#close-library").onclick = () => {
        $("#furniture-library").hidden = true;
        document.body.classList.remove("library-open");
        C.layout();
      };
      $("#load-library").onclick = () => $("#library-folder").click();
      $("#library-folder").onchange = (e) =>
        this.safe(() => this.loadLibrary([...e.target.files]));
      $("#library-search").oninput = () => this.renderLibrary();
      $("#library-max-width").oninput = () => this.renderLibrary();
      $("#edit-wall").onchange = () => {
        this.fillWall();
        this.focusKind = "wall";
        this.drawHandles();
      };
      $("#edit-opening").onchange = () => {
        this.fillOpening();
        this.focusKind = "opening";
        this.drawHandles();
      };
      $("#wall-length").onchange = () => {
        const a = [+$("#wall-ax").value, +$("#wall-az").value],
          b = [+$("#wall-bx").value, +$("#wall-bz").value],
          d = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1,
          n = +$("#wall-length").value;
        $("#wall-bx").value = a[0] + ((b[0] - a[0]) / d) * n;
        $("#wall-bz").value = a[1] + ((b[1] - a[1]) / d) * n;
      };
      $("#wall-stop").onclick = () => {
        this.cancel();
        this.api.toast("已结束绘制");
      };
      $("#wall-apply").onclick = () => this.safe(() => this.editWall());
      $("#wall-add").onclick = () => this.safe(() => this.addWall());
      $("#wall-delete").onclick = () => this.safe(() => this.deleteWall());
      $("#wall-drag").onclick = () =>
        this.safe(() => {
          this.unlock();
          this.mode = "wall";
          this.focusKind = "wall";
          this.drawHandles();
          this.api.toast("拖动端点改墙长，拖动墙身移动整墙；数值栏同步。");
        });
      $("#opening-apply").onclick = () => this.safe(() => this.editOpening());
      $("#opening-add").onclick = () => this.safe(() => this.addOpening());
      $("#opening-delete").onclick = () =>
        this.safe(() => this.deleteOpening());
      $("#measure-start").onclick = () => {
        this.api.cancel();
        this.measuring = true;
        this.first = null;
        this.api.toast("点击地板平面上的两个点，吸附墙端与家具边");
      };
      $("#measure-cancel").onclick = () => this.cancel();
      $("#measure-clear").onclick = () =>
        this.safe(async () => {
          const p = C.exportLayout(false);
          p.measurements = [];
          await this.api.apply(p);
          this.refresh();
        });
      $("#measure-unit").value = this.unit;
      $("#measure-unit").onchange = (e) => {
        this.unit = e.target.value;
        window.PROJECT.measurementUnit = this.unit;
        this.refreshMeasurements();
      };
      $("#apply-slot").onclick = () => this.safe(() => this.material());
      $("#remove-placement").onclick = () => this.safe(() => this.remove());
      $("#style-research").onclick = () => {
        const query = $("#style-query").value.trim();
        if (!query) return;
        this.downloadJSON(
          {
            schema: "interior.style-research/1",
            query,
            status: "research-required",
            sources: [],
            extract: [
              "palette",
              "materials",
              "forms",
              "details",
              "lighting",
              "componentBindings",
            ],
            note: "由当前Agent真实联网检索；不自动申请付费资产。",
          },
          "style-research.json",
        );
      };
      this.installTools();
    }

    safe(fn) {
      return Promise.resolve()
        .then(fn)
        .catch((e) => this.api.toast(e.message));
    }
    cancel() {
      this.measuring = false;
      this.first = null;
      this.mode = null;
      this.finishPreview();
      this.drag = null;
      this.drawHandles();
    }
    groundPoint(x, y) {
      const camera = C.getActiveCamera(),
        r = this.$("#webgl").getBoundingClientRect(),
        ray = new T.Raycaster();
      ray.setFromCamera(
        new T.Vector2(
          ((x - r.left) / r.width) * 2 - 1,
          (-(y - r.top) / r.height) * 2 + 1,
        ),
        camera,
      );
      return ray.ray.intersectPlane(
        new T.Plane(new T.Vector3(0, 1, 0), 0),
        new T.Vector3(),
      );
    }
    snap(v) {
      const P = C.exportLayout(false),
        points = P.walls.flatMap((w) => [w.a, w.b]);
      for (const p of P.placements) {
        const poly = Spatial.polygon(p);
        for (let i = 0; i < poly.length; i++) {
          points.push(poly[i]);
          points.push(
            Spatial.segment([v.x, v.z], poly[i], poly[(i + 1) % poly.length]),
          );
        }
      }
      let best = v.clone(),
        d = 0.12;
      for (const p of points) {
        const delta = Math.hypot(v.x - p[0], v.z - p[1]);
        if (delta < d) {
          best.set(p[0], 0, p[1]);
          d = delta;
        }
      }
      return best;
    }
    refresh() {
      const $ = this.$,
        p = window.PROJECT,
        wallId = $("#edit-wall").value,
        openingId = $("#edit-opening").value;
      $("#edit-wall").replaceChildren(
        ...p.walls.map((w) => new Option(w.name, w.id)),
      );
      if (p.walls.some((w) => w.id === wallId)) $("#edit-wall").value = wallId;
      $("#edit-opening").replaceChildren(
        ...p.openings.map((o) => new Option(o.id + " · " + o.type, o.id)),
      );
      if (p.openings.some((o) => o.id === openingId))
        $("#edit-opening").value = openingId;
      $("#library-room").replaceChildren(
        ...p.rooms.map((r) => new Option(r.name, r.id)),
      );
      this.fillWall();
      this.fillOpening();
      this.refreshStructures?.();
      $("#area-summary").textContent =
        "楼面边界面积 " +
        Spatial.area(p.floor.outline).toFixed(2) +
        " m²。" +
        p.rooms
          .map((r) => r.name + " " + Spatial.area(r.polygon).toFixed(2) + " m²")
          .join("；");
      this.refreshMeasurements();
      this.renderLibrary();
      this.drawHandles();
    }
    selectedChanged() {
      const id = C.editor.selected,
        w = window.PROJECT.walls.find((w) => w.id === id);
      if (w) {
        this.$("#edit-wall").value = id;
        this.fillWall();
        this.focusKind = "wall";
      }
      this.drawHandles();
      const e = C.entities.find((e) => e.id === C.editor.selected),
        select = this.$("#native-slot");
      select.replaceChildren();
      if (e) {
        const names = new Set();
        e.object.traverse((o) => {
          for (const m of o.material
            ? Array.isArray(o.material)
              ? o.material
              : [o.material]
            : [])
            names.add(m.name || "unnamed");
        });
        for (const name of names) select.add(new Option(name, name));
      }
    }
    fillWall() {
      const w = window.PROJECT.walls.find(
        (w) => w.id === this.$("#edit-wall").value,
      );
      if (!w) return;
      for (const [k, v] of Object.entries({
        "wall-ax": w.a[0],
        "wall-az": w.a[1],
        "wall-bx": w.b[0],
        "wall-bz": w.b[1],
        "wall-length": Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]),
        "wall-thickness": w.thickness,
        "wall-height": w.height,
      }))
        this.$("#" + k).value =
          typeof v === "number" ? Number(v.toFixed(3)) : v;
    }
    fillOpening() {
      const o = window.PROJECT.openings.find(
        (o) => o.id === this.$("#edit-opening").value,
      );
      if (!o) return;
      for (const k of [
        "offset",
        "width",
        "sill",
        "height",
        "type",
        "passageShape",
        "archRise",
        "cornerLeft",
        "cornerRight",
        "openFraction",
        "hingeSide",
        "slideTo",
      ]) {
        const el = this.$("#opening-" + k);
        if (el)
          el.value =
            o[k] ??
            {
              passageShape: "rect",
              archRise: 0.5,
              cornerLeft: 0.2,
              cornerRight: 0.2,
              openFraction: 0,
              hingeSide: "left",
              slideTo: "left",
            }[k] ??
            "";
      }
    }
    unlock() {
      if (C.state.wallLocked) throw Error("结构层已锁定，请先解锁");
    }
    async dispatch(cmd) {
      this.finishPreview();
      if (cmd.type === "placement.update") {
        const e = C.entities.find((e) => e.id === cmd.id),
          base = window.PROJECT.placements.find((p) => p.id === cmd.id);
        if (!e || !base) throw Error("家具不存在");
        const before = C.editor.capture(e),
          n = structuredClone(before),
          p = cmd.patch;
        if (p.position) n.position = p.position;
        if (p.size)
          n.scale = p.size.map(
            (v, i) => (e.original.scale[i] * v) / base.size[i],
          );
        for (const [i, k] of ["rotationX", "rotationY", "rotationZ"].entries())
          if (p[k] !== undefined) n.rotation[i] = (p[k] * Math.PI) / 180;
        C.editor.applySnapshot(e, n);
        C.editor.record(e, before);
        this.drawHandles();
        return;
      }
      const next = InteriorModel.command(C.exportLayout(false), cmd);
      await this.api.apply(next);
      this.refresh();
    }
    async editWall() {
      this.unlock();
      const $ = this.$;
      await this.dispatch({
        type: "wall.update",
        id: $("#edit-wall").value,
        patch: {
          a: ["ax", "az"].map((k) => +$("#wall-" + k).value),
          b: ["bx", "bz"].map((k) => +$("#wall-" + k).value),
          thickness: +$("#wall-thickness").value,
          height: +$("#wall-height").value,
        },
      });
    }
    async addWall() {
      this.unlock();
      this.api.cancel();
      this.mode = "draw";
      this.first = null;
      C.setView("plan");
      this.api.toast("点击起点，再点击终点。可连续绘制；Esc 结束。");
    }
    async deleteWall() {
      this.unlock();
      await this.dispatch({
        type: "wall.remove",
        id: this.$("#edit-wall").value,
      });
      this.api.toast("墙及其宿主门窗已删除，可撤销恢复。");
    }
    async editOpening() {
      this.unlock();
      const patch = {};
      for (const k of [
        "offset",
        "width",
        "sill",
        "height",
        "archRise",
        "cornerLeft",
        "cornerRight",
        "openFraction",
      ]) {
        const el = this.$("#opening-" + k);
        if (el) patch[k] = +el.value;
      }
      for (const k of ["type", "passageShape", "hingeSide", "slideTo"])
        patch[k] = this.$("#opening-" + k).value;
      await this.dispatch({
        type: "opening.update",
        id: this.$("#edit-opening").value,
        patch,
      });
    }
    async addOpening() {
      this.unlock();
      const w = window.PROJECT.walls.find(
        (w) => w.id === this.$("#edit-wall").value,
      );
      if (!w) throw Error("先选宿主墙");
      const id = this.id("opening"),
        width = Math.min(
          0.8,
          Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]) * 0.7,
        ),
        type = this.$("#opening-type").value;
      await this.dispatch({
        type: "opening.add",
        value: {
          id,
          wallId: w.id,
          type,
          offset: 0.05,
          width,
          height: Math.min(2.1, w.height - (type === "window" ? 0.8 : 0)),
          sill: type === "window" ? 0.8 : 0,
          openFraction: 0,
          passageShape: "rect",
        },
      });
      this.$("#edit-opening").value = id;
      this.fillOpening();
      this.focusKind = "opening";
      this.drawHandles();
    }
    async deleteOpening() {
      this.unlock();
      await this.dispatch({
        type: "opening.remove",
        id: this.$("#edit-opening").value,
      });
    }
    format(m) {
      return this.unit === "mm"
        ? (m * 1000).toFixed(0) + " mm"
        : m.toFixed(3) + " m";
    }
    refreshMeasurements() {
      const $ = this.$;
      this.lines.children.forEach((o) => {
        o.geometry?.dispose();
        o.material?.dispose();
      });
      this.lines.clear();
      $("#measurement-list").replaceChildren();
      for (const m of window.PROJECT.measurements || []) {
        const a = new T.Vector3(...m.a),
          b = new T.Vector3(...m.b),
          line = new T.Line(
            new T.BufferGeometry().setFromPoints([
              a.clone().setY(0.03),
              b.clone().setY(0.03),
            ]),
            new T.LineBasicMaterial({ color: 0xf3b45c, depthTest: false }),
          );
        line.userData.noExport = true;
        line.renderOrder = 100;
        this.lines.add(line);
        const row = document.createElement("div");
        row.className = "object-row";
        const span = document.createElement("span");
        span.textContent = this.format(a.distanceTo(b)) + " · 地板Y=0";
        const btn = document.createElement("button");
        btn.textContent = "×";
        btn.onclick = () =>
          this.safe(async () => {
            const p = C.exportLayout(false);
            p.measurements = p.measurements.filter((x) => x.id !== m.id);
            await this.api.apply(p);
            this.refresh();
          });
        row.append(span, btn);
        $("#measurement-list").append(row);
      }
    }
    onFrame() {
      const $ = this.$,
        camera = C.getActiveCamera(),
        h = $("#stage").clientHeight,
        pixelWorld = camera.isOrthographicCamera
          ? (camera.top - camera.bottom) / camera.zoom / h
          : (2 *
              camera.position.distanceTo(C.controls.target) *
              Math.tan((camera.fov * Math.PI) / 360)) /
            h;
      const target = pixelWorld * 110,
        pow = 10 ** Math.floor(Math.log10(Math.max(0.001, target))),
        m =
          [1, 2, 5, 10].map((x) => x * pow).find((x) => x >= target) ||
          pow * 10;
      $("#scale-bar").style.width = m / pixelWorld + "px";
      $("#scale-label").textContent = this.format(m);
      $("#scale-note").textContent = camera.isOrthographicCamera
        ? "正交米制比例尺"
        : "视图中心参考比例；拉尺在Y=0地板上";
      this.lines.visible = !C.state.busy;
      this.updateDimensions();
      $("#scale-hud").style.display = C.state.busy ? "none" : "block";
    }
    async loadLibrary(files) {
      const paths = new Map(
          files.map((f) => [f.webkitRelativePath || f.name, f]),
        ),
        index = files.find((f) => f.name === "library.json");
      if (!index) throw Error("目录中缺少 library.json");
      const info = JSON.parse(await index.text());
      if (
        info.schema !== "interior.asset-library/1" ||
        !Array.isArray(info.items)
      )
        throw Error("家具目录格式无效");
      const prefix = (index.webkitRelativePath || index.name).slice(
          0,
          -index.name.length,
        ),
        loaded = [];
      for (const item of info.items) {
        if (
          item.modelPath?.includes("..") ||
          /^([a-z]:|\/|https?:)/i.test(item.modelPath || "")
        )
          throw Error("模型只能引用授权目录内的相对路径");
        const f = paths.get(prefix + item.modelPath);
        if (!f) throw Error("缺少模型文件 " + item.modelPath);
        const asset = {
          ...item,
          modelBase64: C.nativeAssets.encode64(await f.arrayBuffer()),
        };
        delete asset.modelPath;
        delete asset.thumbnail;
        C.nativeAssets.validateRecord(asset);
        if (item.thumbnail) {
          const pic = paths.get(prefix + item.thumbnail);
          if (pic && pic.type.startsWith("image/"))
            asset.thumbnail =
              "data:" +
              pic.type +
              ";base64," +
              C.nativeAssets.encode64(await pic.arrayBuffer());
        }
        loaded.push(asset);
      }
      await C.nativeAssets.prepare(loaded);
      this.library = loaded;
      this.$("#library-message").textContent =
        `已获授权加载 ${loaded.length} 件本地模型。选择家具再点款式可替换；未选择则放入下拉房间。`;
      this.renderLibrary();
    }
    renderLibrary() {
      const $ = this.$,
        list = $("#library-items");
      if (!list) return;
      list.replaceChildren();
      const query = $("#library-search").value.toLowerCase(),
        max = +$("#library-max-width").value || Infinity;
      for (const r of this.library.filter(
        (r) =>
          (r.name + " " + r.category + " " + (r.styles || []).join(" "))
            .toLowerCase()
            .includes(query) && r.size[0] <= max,
      )) {
        const b = document.createElement("button");
        b.className = "library-item";
        if (r.thumbnail) {
          const img = document.createElement("img");
          img.src = r.thumbnail;
          b.append(img);
        }
        const name = document.createElement("b");
        name.textContent = r.name;
        const dims = document.createElement("small");
        dims.textContent =
          r.size.map((x) => x.toFixed(2)).join(" × ") +
          " m · " +
          (r.deform || "uniform");
        b.append(name, dims);
        b.onclick = () => this.safe(() => this.place(r));
        list.append(b);
      }
    }
    async place(r) {
      const p = C.exportLayout(false),
        e = C.entities.find(
          (e) => e.id === C.editor.selected && e.type === "furniture",
        ),
        old = e && p.placements.find((x) => x.id === e.id);
      let placement;
      if (old) {
        if (old.componentId !== r.componentId)
          throw Error("只允许同类替换；先取消选择可作为新家具放置");
        placement = old;
        placement.size = [...r.size];
        delete placement.materialOverrides;
      } else {
        const room = p.rooms.find(
          (r) => r.id === this.$("#library-room").value,
        );
        if (!room) throw Error("先选放置房间");
        const point = C.rooms.find((x) => x.id === room.id).point;
        placement = {
          id: "asset-" + T.MathUtils.generateUUID().slice(0, 8),
          name: r.name,
          roomId: room.id,
          componentId: r.componentId,
          position: [point[0], 0, point[2]],
          size: [...r.size],
          rotationY: 0,
        };
        p.placements.push(placement);
      }
      placement.nativeAssetId = r.id;
      placement.name = r.name;
      p.nativeAssets ||= [];
      if (!p.nativeAssets.some((a) => a.id === r.id))
        p.nativeAssets.push(structuredClone(r));
      const check = Spatial.audit(p, placement.id);
      if (check.errors.length || check.warnings.length) {
        this.api.toast(
          "保留待调整草稿：" + [...check.errors, ...check.warnings].join(", "),
        );
        p.source.assumptions.push(
          "家具 " +
            placement.id +
            " 的放置观察：" +
            [...check.errors, ...check.warnings].join(", ") +
            "；回源调整布局/选型，不自动隐藏或缩放。",
        );
      }
      await this.api.apply(p);
      C.editor.setTab("furniture");
      C.editor.select(placement.id);
      this.refresh();
      this.selectedChanged();
    }
    async material() {
      const id = C.editor.selected,
        p = C.exportLayout(false),
        x = p.placements.find((x) => x.id === id);
      if (!x) throw Error("先选家具");
      const name = this.$("#native-slot").value,
        roughness = +this.$("#slot-roughness").value,
        metalness = +this.$("#slot-metalness").value;
      if (!name || ![roughness, metalness].every((v) => v >= 0 && v <= 1))
        throw Error("无效材质槽参数");
      (x.materialOverrides ||= {})[name] = {
        color: this.$("#slot-color").value,
        roughness,
        metalness,
      };
      await this.api.apply(p);
      C.editor.select(id);
      this.selectedChanged();
    }
    async remove() {
      const p = C.exportLayout(false),
        id = C.editor.selected;
      if (!p.placements.some((x) => x.id === id)) throw Error("先选家具");
      p.placements = p.placements.filter((x) => x.id !== id);
      p.rooms.forEach(
        (r) => (r.subjectIds = r.subjectIds.filter((x) => x !== id)),
      );
      p.lighting?.lights.forEach((l) => {
        if (l.anchorId === id) l.anchorId = null;
      });
      await this.api.apply(p);
      this.refresh();
    }
    id(prefix) {
      return prefix + "-" + T.MathUtils.generateUUID().slice(0, 8);
    }
    installTools() {
      const $ = this.$;
      $("#structure-tools").insertAdjacentHTML(
        "beforeend",
        `<div class="number-grid"><label>门洞轮廓<select id="opening-passageShape"><option value="rect">矩形</option><option value="arch">拱形</option><option value="rounded">圆角</option></select></label><label>拱高 m<input id="opening-archRise" type="number" value=".5" step=".01"></label><label>左圆角 m<input id="opening-cornerLeft" type="number" value=".2" step=".01"></label><label>右圆角 m<input id="opening-cornerRight" type="number" value=".2" step=".01"></label><label>开启比例<input id="opening-openFraction" type="number" min="0" max="1" step=".1" value="0"></label><label>铰链<select id="opening-hingeSide"><option value="left">左</option><option value="right">右</option></select></label><label>移门滑向<select id="opening-slideTo"><option value="left">左</option><option value="right">右</option></select></label></div><p class="pro-hint">选中开口后拖中心点沿墙移动，三维中可调离地；拖左右端点调宽。开合与轮廓保存在同一模型。</p><h3>柱子 / 烟道</h3><select id="structure-item"></select><div class="number-grid"><label>类型<select id="structure-kind"><option value="column">柱子</option><option value="flue">烟道</option></select></label><label>房间<select id="structure-room"></select></label>${["x", "y", "z", "width", "height", "depth", "yaw"].map((k) => `<label>${{ x: "X m", y: "离地 m", z: "Z m", width: "宽 m", height: "高 m", depth: "深 m", yaw: "旋转 °" }[k]}<input id="structure-${k}" type="number" step=".01"></label>`).join("")}</div><div class="pro-actions"><button id="structure-add">新增</button><button id="structure-apply">应用</button><button id="structure-delete">删除</button></div>`,
      );
      $("#structure-item").onchange = () => {
        this.fillStructure();
        this.focusKind = "structure";
        this.drawHandles();
      };
      $("#structure-add").onclick = () =>
        this.safe(async () => {
          this.unlock();
          const room =
              window.PROJECT.rooms.find(
                (r) => r.id === $("#structure-room").value,
              ) || window.PROJECT.rooms[0],
            point = C.rooms.find((r) => r.id === room.id).point,
            id = this.id("structure");
          await this.dispatch({
            type: "structure.add",
            value: {
              id,
              name: $("#structure-kind").value === "flue" ? "烟道" : "柱子",
              kind: $("#structure-kind").value,
              roomId: room.id,
              position: [point[0], 0, point[2]],
              size: [0.4, window.PROJECT.floor.height, 0.4],
              rotationY: 0,
            },
          });
          $("#structure-item").value = id;
          this.fillStructure();
          this.focusKind = "structure";
          this.drawHandles();
        });
      $("#structure-apply").onclick = () =>
        this.safe(async () => {
          this.unlock();
          await this.dispatch({
            type: "structure.update",
            id: $("#structure-item").value,
            patch: {
              kind: $("#structure-kind").value,
              roomId: $("#structure-room").value,
              position: ["x", "y", "z"].map((k) => +$("#structure-" + k).value),
              size: ["width", "height", "depth"].map(
                (k) => +$("#structure-" + k).value,
              ),
              rotationY: +$("#structure-yaw").value,
            },
          });
        });
      $("#structure-delete").onclick = () =>
        this.safe(async () => {
          this.unlock();
          await this.dispatch({
            type: "structure.remove",
            id: $("#structure-item").value,
          });
        });
      $("#object-editor .number-grid").insertAdjacentHTML(
        "beforeend",
        ["width", "height", "depth"]
          .map(
            (k) =>
              `<label>${{ width: "宽 m", height: "高 m", depth: "深 m" }[k]}<input id="obj-${k}" type="number" step=".01" min=".01"></label>`,
          )
          .join(""),
      );

      $("#object-editor .number-grid").insertAdjacentHTML(
        "beforeend",
        '<label>X 旋转 °<input id="obj-pitch" type="number" step="1"></label><label>Z 旋转 °<input id="obj-roll" type="number" step="1"></label>',
      );
      $("#object-editor").insertAdjacentHTML(
        "beforeend",
        '<div class="pro-actions"><button id="copy-placement">复制家具</button></div>',
      );
      $("#copy-placement").onclick = () =>
        this.safe(async () => {
          const p = C.exportLayout(false),
            old = p.placements.find((p) => p.id === C.editor.selected);
          if (!old) throw Error("先选家具");
          const n = structuredClone(old);
          n.id = this.id("copy");
          n.name += " 副本";
          n.position[0] += 0.3;
          n.position[2] += 0.3;
          p.placements.push(n);
          await this.api.apply(p);
          C.editor.select(n.id);
          this.refresh();
        });
      $("#structure-tools").insertAdjacentHTML(
        "beforeend",
        '<div class="pro-actions"><select id="structure-transform-mode"><option value="move">三轴移动</option><option value="scale">三轴缩放</option><option value="rotate">水平旋转</option></select><button id="structure-copy">复制结构体</button><button id="structure-hide">显示 / 隐藏</button><button id="structure-lock">锁定 / 解锁</button></div>',
      );
      $("#structure-transform-mode").onchange = () => this.drawHandles();
      for (const act of ["copy", "hide", "lock"])
        $("#structure-" + act).onclick = () =>
          this.safe(async () => {
            this.unlock();
            const old = (window.PROJECT.structuralItems || []).find(
              (p) => p.id === $("#structure-item").value,
            );
            if (!old) throw Error("先选柱子或烟道");
            if (act === "copy") {
              const n = structuredClone(old);
              n.id = this.id("structure");
              n.position[0] += n.size[0] + 0.1;
              n.locked = false;
              await this.dispatch({ type: "structure.add", value: n });
              $("#structure-item").value = n.id;
            } else
              await this.dispatch({
                type: "structure.update",
                id: old.id,
                patch:
                  act === "lock"
                    ? { locked: !old.locked }
                    : { visible: old.visible === false },
              });
            this.fillStructure();
            this.drawHandles();
          });

      $('[data-panel="camera"]').insertAdjacentHTML(
        "afterbegin",
        '<div class="pro-actions"><button id="view-single">只看当前空间</button><button id="view-all">显示全屋</button></div><select id="view-room"></select><p class="pro-hint">W/S 前后、A/D 左右、Q/E 上下；Shift 加速。鼠标滚轮缩放，右键平移。查看范围不改变模型。</p>',
      );
      $("#view-room").replaceChildren(
        ...window.PROJECT.rooms.map((r) => new Option(r.name, r.id)),
      );
      $("#view-single").onclick = () =>
        C.editor.setRoomScope($("#view-room").value);
      $("#view-all").onclick = () => C.editor.setRoomScope(null);
      $("#stage").insertAdjacentHTML(
        "beforeend",
        '<div id="dimension-labels" style="pointer-events:none;position:absolute;inset:0;overflow:hidden"></div>',
      );
      $('[data-panel="camera"]').insertAdjacentHTML(
        "beforeend",
        '<label><input id="dimension-show" type="checkbox" checked> 显示墙体 / 选中物品尺寸</label>',
      );
      $("#dimension-show").onchange = () => C.editor.renderNow();
      this.handles = new T.Group();
      this.handles.userData.noExport = true;
      this.handles.name = "统一编辑控制点";
      C.scene.add(this.handles);
    }
    refreshStructures() {
      const $ = this.$;
      if (!$("#structure-item")) return;
      const id = $("#structure-item").value,
        rid = $("#structure-room").value;
      $("#structure-item").replaceChildren(
        ...(window.PROJECT.structuralItems || []).map(
          (p) => new Option(p.name, p.id),
        ),
      );
      if ((window.PROJECT.structuralItems || []).some((p) => p.id === id))
        $("#structure-item").value = id;
      $("#structure-room").replaceChildren(
        ...window.PROJECT.rooms.map((r) => new Option(r.name, r.id)),
      );
      if (window.PROJECT.rooms.some((r) => r.id === rid))
        $("#structure-room").value = rid;
      this.fillStructure();
    }
    fillStructure() {
      const p = (window.PROJECT.structuralItems || []).find(
        (p) => p.id === this.$("#structure-item").value,
      );
      if (!p) return;
      for (const [k, v] of Object.entries({
        x: p.position[0],
        y: p.position[1],
        z: p.position[2],
        width: p.size[0],
        height: p.size[1],
        depth: p.size[2],
        yaw: p.rotationY,
        kind: p.kind,
        room: p.roomId,
      }))
        this.$("#structure-" + k).value = v;
    }
    drawHandles() {
      if (!this.handles) return;
      this.handles.children.forEach((o) => {
        o.geometry?.dispose();
        o.material?.dispose();
      });
      this.handles.clear();
      if (C.state.busy || this.drag) return;
      const P = window.PROJECT,
        add = (pos, meta, color = 0x2399bb) => {
          const m = new T.Mesh(
            new T.SphereGeometry(0.065, 12, 8),
            new T.MeshBasicMaterial({ color, depthTest: false }),
          );
          m.position.set(...pos);
          m.userData = { noExport: true, ...meta };
          m.renderOrder = 1500;
          this.handles.add(m);
        };
      if (C.state.tab === "walls" && !C.state.wallLocked) {
        if (this.focusKind === "opening") {
          const o = P.openings.find(
              (o) => o.id === this.$("#edit-opening").value,
            ),
            w = o && P.walls.find((w) => w.id === o.wallId);
          if (w) {
            const L = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]);
            for (const [part, d] of [
              ["a", o.offset],
              ["center", o.offset + o.width / 2],
              ["b", o.offset + o.width],
            ])
              add(
                [
                  w.a[0] + ((w.b[0] - w.a[0]) * d) / L,
                  o.sill + o.height / 2,
                  w.a[1] + ((w.b[1] - w.a[1]) * d) / L,
                ],
                { kind: "opening", id: o.id, part },
              );
          }
        } else if (this.focusKind === "structure") {
          const p = (P.structuralItems || []).find(
            (p) => p.id === this.$("#structure-item").value,
          );
          if (p && !p.locked && p.visible !== false) {
            add([p.position[0], p.position[1] + p.size[1] / 2, p.position[2]], {
              kind: "structure",
              id: p.id,
              part: "center",
            });
            this.transformHandles(p, "structure", add);
          }
        } else {
          const w = P.walls.find((w) => w.id === this.$("#edit-wall").value);
          if (w) {
            for (const k of ["a", "b"])
              add([w[k][0], w.height / 2, w[k][1]], {
                kind: "wall",
                id: w.id,
                part: k,
              });
            add(
              [(w.a[0] + w.b[0]) / 2, w.height / 2, (w.a[1] + w.b[1]) / 2],
              { kind: "wall", id: w.id, part: "center" },
              0x63b669,
            );
          }
        }
      }
      if (C.state.tab === "furniture") {
        const p = C.exportLayout(false).placements.find(
          (p) => p.id === C.editor.selected,
        );
        if (p) {
          this.transformHandles(p, "placement", add);
          const poly = Spatial.polygon(p);
          for (const [i, v] of poly.entries())
            add(
              [v[0], p.position[1] + p.size[1] / 2, v[1]],
              { kind: "placement", id: p.id, part: "scale", corner: i },
              0xe5ae49,
            );
        }
      }
    }
    transformHandles(p, kind, add) {
      const mode =
          kind === "structure"
            ? this.$("#structure-transform-mode").value
            : C.state.tool,
        center = new T.Vector3(
          p.position[0],
          p.position[1] + p.size[1] / 2,
          p.position[2],
        ),
        len = Math.max(0.5, Math.min(1.5, Math.max(...p.size) * 0.65));
      for (let i = 0; i < 3; i++) {
        if (kind === "structure" && mode === "rotate" && i !== 1) continue;
        const axis = new T.Vector3().setComponent(i, 1),
          tip = center.clone().addScaledVector(axis, len);
        add(
          tip.toArray(),
          {
            kind,
            id: p.id,
            part: "axis-" + mode,
            axis: i,
            center: center.toArray(),
            tip: tip.toArray(),
            handleLength: len,
          },
          [0xe45e53, 0x63b669, 0x389ddd][i],
        );
        const line = new T.Line(
          new T.BufferGeometry().setFromPoints([center, tip]),
          new T.LineBasicMaterial({
            color: [0xe45e53, 0x63b669, 0x389ddd][i],
            depthTest: false,
          }),
        );
        line.userData.noExport = true;
        line.renderOrder = 1400;
        this.handles.add(line);
      }
    }
    pointerRay(e) {
      const camera = C.getActiveCamera(),
        box = this.$("#webgl").getBoundingClientRect(),
        ray = new T.Raycaster();
      camera.updateMatrixWorld(true);
      ray.setFromCamera(
        new T.Vector2(
          ((e.clientX - box.left) / box.width) * 2 - 1,
          1 - ((e.clientY - box.top) / box.height) * 2,
        ),
        camera,
      );
      return ray;
    }
    pointerPoint(e, plane) {
      return this.pointerRay(e).ray.intersectPlane(plane, new T.Vector3());
    }
    pointerDown(e) {
      if (C.state.busy || e.button !== 0) return false;
      if (this.drag) return true;
      if (this.measuring) {
        const p = this.groundPoint(e.clientX, e.clientY);
        if (!p) return false;
        const q = this.snap(p);
        if (!this.first) {
          this.first = q;
          this.api.toast("已选起点");
        } else {
          const a = this.first.toArray(),
            b = q.toArray();
          this.first = null;
          this.measuring = false;
          this.safe(async () => {
            const p = C.exportLayout(false);
            (p.measurements ||= []).push({
              id: this.id("measure"),
              a,
              b,
              plane: "Y=0",
            });
            await this.api.apply(p);
            this.refresh();
          });
        }
        return true;
      }
      if (
        this.mode === "draw" &&
        C.state.tab === "walls" &&
        !C.state.wallLocked
      ) {
        const p = this.groundPoint(e.clientX, e.clientY);
        if (!p) return true;
        const q = this.snap(p);
        if (!this.first) {
          this.first = q;
          return true;
        }
        const a = this.first,
          b = q;
        if (a.distanceTo(b) < 0.05) return true;
        const id = this.id("wall");
        this.first = q;
        this.safe(async () => {
          await this.dispatch({
            type: "wall.add",
            value: {
              id,
              name: "隔墙",
              a: [a.x, a.z],
              b: [b.x, b.z],
              thickness: +this.$("#wall-thickness").value || 0.12,
              height:
                +this.$("#wall-height").value || window.PROJECT.floor.height,
              kind: "wall",
            },
          });
          this.$("#edit-wall").value = id;
          this.fillWall();
          this.drawHandles();
        });
        return true;
      }
      const hit = this.pointerRay(e)
        .intersectObject(this.handles, true)
        .find((h) => h.object.userData.kind);
      let meta = hit?.object.userData;
      if (!meta && C.state.tab === "walls" && !C.state.wallLocked) {
        const picked = C.pick(e.clientX, e.clientY);
        if (picked?.entry.type === "wall") {
          this.$("#edit-wall").value = picked.entry.id;
          this.fillWall();
          this.focusKind = "wall";
          C.editor.select(picked.entry.id);
          meta = { kind: "wall", id: picked.entry.id, part: "center" };
        }
      }
      if (!meta?.kind) return false;
      const before = C.exportLayout(false),
        obj =
          meta.kind === "wall"
            ? before.walls.find((p) => p.id === meta.id)
            : meta.kind === "opening"
              ? before.openings.find((p) => p.id === meta.id)
              : meta.kind === "structure"
                ? (before.structuralItems || []).find((p) => p.id === meta.id)
                : before.placements.find((p) => p.id === meta.id);
      if (!obj) return false;
      let plane = new T.Plane(
        new T.Vector3(0, 1, 0),
        -(hit?.point.y || obj.height / 2 || 0),
      );
      if (
        meta.kind === "opening" &&
        !C.getActiveCamera().isOrthographicCamera
      ) {
        const w = before.walls.find((w) => w.id === obj.wallId),
          normal = new T.Vector3(
            w.b[1] - w.a[1],
            0,
            -(w.b[0] - w.a[0]),
          ).normalize();
        plane = new T.Plane().setFromNormalAndCoplanarPoint(
          normal,
          new T.Vector3(w.a[0], 0, w.a[1]),
        );
      }
      const start = this.pointerPoint(e, plane);
      if (!start) return false;
      this.drag = {
        ...meta,
        pointerId: e.pointerId,
        before,
        obj: structuredClone(obj),
        plane,
        start,
        x: e.clientX,
        y: e.clientY,
        candidate: null,
      };
      this.$("#webgl").setPointerCapture(e.pointerId);
      return true;
    }
    pointerMove(e) {
      if (this.mode === "draw" && this.first && !this.drag) {
        const p = this.groundPoint(e.clientX, e.clientY);
        if (p) {
          const q = this.snap(p);
          this.$("#structure-note").textContent =
            "待绘墙长 " + q.distanceTo(this.first).toFixed(3) + " m";
        }
        return true;
      }
      const g = this.drag;
      if (!g || g.pointerId !== e.pointerId) return false;
      const q = this.pointerPoint(e, g.plane);
      if (!q) return true;
      const delta = q.clone().sub(g.start),
        patch = {},
        step = +this.$("#snap").value || 0,
        round = (v) => (step > 0 ? Math.round(v / step) * step : v);
      if (g.kind === "wall") {
        if (g.part === "center") {
          patch.a = [round(g.obj.a[0] + delta.x), round(g.obj.a[1] + delta.z)];
          patch.b = [
            patch.a[0] + g.obj.b[0] - g.obj.a[0],
            patch.a[1] + g.obj.b[1] - g.obj.a[1],
          ];
        } else {
          const wanted = new T.Vector3(
            g.obj[g.part][0] + delta.x,
            0,
            g.obj[g.part][1] + delta.z,
          );
          const p = this.snap(wanted);
          patch[g.part] = [round(p.x), round(p.z)];
        }
      } else if (g.kind === "opening") {
        const w = g.before.walls.find((w) => w.id === g.obj.wallId),
          L = Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]),
          d = (delta.x * (w.b[0] - w.a[0]) + delta.z * (w.b[1] - w.a[1])) / L;
        if (g.part === "center") {
          patch.offset = Math.max(
            0,
            Math.min(L - g.obj.width, round(g.obj.offset + d)),
          );
          patch.sill = Math.max(
            0,
            Math.min(w.height - g.obj.height, round(g.obj.sill + delta.y)),
          );
        } else if (g.part === "a") {
          patch.offset = Math.max(
            0,
            Math.min(
              g.obj.offset + g.obj.width - 0.05,
              round(g.obj.offset + d),
            ),
          );
          patch.width = g.obj.offset + g.obj.width - patch.offset;
        } else
          patch.width = Math.max(
            0.05,
            Math.min(L - g.obj.offset, round(g.obj.width + d)),
          );
      } else if (g.part.startsWith("axis-")) {
        const mode = g.part.slice(5),
          camera = C.getActiveCamera(),
          rect = this.$("#webgl").getBoundingClientRect(),
          a = new T.Vector3(...g.center).project(camera),
          b = new T.Vector3(...g.tip).project(camera),
          dx = ((b.x - a.x) * rect.width) / 2,
          dy = (-(b.y - a.y) * rect.height) / 2,
          amount =
            (((e.clientX - g.x) * dx + (e.clientY - g.y) * dy) /
              Math.max(1, dx * dx + dy * dy)) *
            g.handleLength;
        if (mode === "move") {
          patch.position = [...g.obj.position];
          patch.position[g.axis] += amount;
        } else if (mode === "rotate") {
          const key = ["rotationX", "rotationY", "rotationZ"][g.axis];
          if (g.kind === "structure" && key !== "rotationY") return true;
          patch[key] = (g.obj[key] || 0) + (e.clientX - g.x) * 0.6;
          if (e.shiftKey) patch[key] = Math.round(patch[key] / 15) * 15;
        } else {
          patch.size = [...g.obj.size];
          const factor = Math.max(
              0.05,
              (patch.size[g.axis] + amount) / patch.size[g.axis],
            ),
            asset = (g.before.nativeAssets || []).find(
              (a) => a.id === g.obj.nativeAssetId,
            );
          if (asset && (asset.deform || "uniform") === "uniform")
            patch.size = g.obj.size.map((v) => v * factor);
          else patch.size[g.axis] *= factor;
        }
      } else if (g.kind === "structure")
        patch.position = [
          round(g.obj.position[0] + delta.x),
          g.obj.position[1],
          round(g.obj.position[2] + delta.z),
        ];
      else {
        const center = new T.Vector3(
            g.obj.position[0],
            g.start.y,
            g.obj.position[2],
          ),
          scale = Math.max(
            0.05,
            q.distanceTo(center) / Math.max(0.01, g.start.distanceTo(center)),
          );
        patch.size = g.obj.size.map((v) => v * scale);
      }
      try {
        const cmd = { type: g.kind + ".update", id: g.id, patch },
          next = InteriorModel.command(g.before, cmd),
          errors = Spatial.validateStructure(next);
        if (errors.length) throw Error(errors.join("; "));
        g.candidate = cmd;
        this.preview(next, g);
        this.$("#structure-note").textContent =
          "拖动预览有效；松手应用，可撤销";
      } catch (err) {
        this.$("#structure-note").textContent = err.message;
      }
      return true;
    }
    pointerUp(e) {
      const g = this.drag;
      if (!g || g.pointerId !== e.pointerId) return false;
      this.drag = null;
      this.finishPreview();
      if (this.$("#webgl").hasPointerCapture(e.pointerId))
        this.$("#webgl").releasePointerCapture(e.pointerId);
      if (g.candidate)
        this.safe(async () => {
          await this.dispatch(g.candidate);
          this.focusKind = g.kind;
          this.drawHandles();
        });
      else this.drawHandles();
      return true;
    }
    preview(next, g) {
      this.finishPreview();
      this.previewGroup = new T.Group();
      this.previewGroup.userData.noExport = true;
      C.scene.add(this.previewGroup);
      if (g.kind === "wall" || g.kind === "opening") {
        this.oldWallsVisible = C.walls.visible;
        C.walls.visible = false;
        const polys = InteriorModel.wallFootprints(next),
          states = InteriorModel.openings(next);
        for (const w of next.walls) {
          if (w.kind === "railing") continue;
          const ops = next.openings
            .filter((o) => o.wallId === w.id)
            .map((o) => ({
              id: o.id,
              type:
                o.type === "passage"
                  ? "passage"
                  : o.type === "sliding-door"
                    ? "sliding"
                    : ["window", "fixed-glazing"].includes(o.type)
                      ? "window"
                      : "door",
              c: o.offset + o.width / 2,
              w: o.width,
              b: o.sill,
              h: o.height,
              assembly: states[o.id],
            }));
          C.buildWall(
            this.previewGroup,
            w.name,
            ...w.a,
            ...w.b,
            w.thickness,
            ops,
            0.92,
            w.height,
            polys[w.id],
          );
        }
      } else {
        const p =
            g.kind === "structure"
              ? next.structuralItems.find((p) => p.id === g.id)
              : next.placements.find((p) => p.id === g.id),
          geo = new T.BoxGeometry(...p.size),
          mesh = new T.Mesh(
            geo,
            new T.MeshBasicMaterial({
              color: 0x29a2ad,
              wireframe: true,
              depthTest: false,
            }),
          );
        mesh.position.set(
          p.position[0],
          p.position[1] + p.size[1] / 2,
          p.position[2],
        );
        mesh.rotation.y = (p.rotationY * Math.PI) / 180;
        this.previewGroup.add(mesh);
      }
      C.editor.renderNow();
    }
    finishPreview() {
      if (this.oldWallsVisible !== undefined) {
        C.walls.visible = this.oldWallsVisible;
        delete this.oldWallsVisible;
      }
      if (this.previewGroup) {
        this.previewGroup.traverse((o) => {
          o.geometry?.dispose();
          if (o.material?.isMeshBasicMaterial) o.material.dispose();
        });
        C.scene.remove(this.previewGroup);
        this.previewGroup = null;
      }
    }
    updateDimensions() {
      const el = this.$("#dimension-labels");
      if (!el) return;
      el.replaceChildren();
      this.handles.visible = !C.state.busy;
      if (C.state.busy || !this.$("#dimension-show").checked) return;
      const camera = C.getActiveCamera(),
        stage = this.$("#stage"),
        add = (text, p) => {
          const q = new T.Vector3(...p).project(camera);
          if (q.z < -1 || q.z > 1 || Math.abs(q.x) > 1 || Math.abs(q.y) > 1)
            return;
          const span = document.createElement("span");
          span.textContent = text;
          span.style.cssText = `position:absolute;left:${((q.x + 1) * stage.clientWidth) / 2}px;top:${((1 - q.y) * stage.clientHeight) / 2}px;background:#ffffffe8;color:#17485a;border-radius:3px;padding:2px 5px;font:12px sans-serif;transform:translate(-50%,-50%)`;
          el.append(span);
        };
      if (C.state.tab === "walls")
        for (const w of window.PROJECT.walls)
          add(Math.hypot(w.b[0] - w.a[0], w.b[1] - w.a[1]).toFixed(2) + " m", [
            (w.a[0] + w.b[0]) / 2,
            w.height + 0.08,
            (w.a[1] + w.b[1]) / 2,
          ]);
      if (C.state.tab === "furniture") {
        const p = C.exportLayout(false).placements.find(
          (p) => p.id === C.editor.selected,
        );
        if (p)
          add(p.size.map((v) => v.toFixed(2)).join(" × ") + " m", [
            p.position[0],
            p.position[1] + p.size[1] + 0.1,
            p.position[2],
          ]);
      }
    }

    downloadJSON(obj, name) {
      C.downloadBlob(
        new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" }),
        name,
      );
    }
    saveHTML() {
      this.safe(async () => {
        const snapshot = C.editor.exportProject(),
          layout = snapshot.layout,
          used = new Set(
            layout.placements.map((p) => p.nativeAssetId).filter(Boolean),
          );
        layout.nativeAssets = (layout.nativeAssets || []).filter((x) =>
          used.has(x.id),
        );
        layout.customStyle = structuredClone(C.activeStyle);
        const encode = (x) =>
            JSON.stringify(x)
              .replace(/</g, "\\u003c")
              .replace(/\u2028/g, "\\u2028")
              .replace(/\u2029/g, "\\u2029"),
          d = new DOMParser().parseFromString(C.templateHTML, "text/html");
        d.querySelector("#project-json").textContent = encode(layout);
        d.querySelector("#saved-project")?.remove();
        const script = d.createElement("script");
        script.id = "saved-project";
        script.type = "application/json";
        script.textContent = encode(snapshot);
        d.body.prepend(script);
        const html = "<!doctype html>\n" + d.documentElement.outerHTML;
        C.downloadBlob(
          new Blob([html], { type: "text/html" }),
          "interior-edited-complete.html",
        );
        this.api.toast(
          "已保存新版 HTML。请把下载的新文件发回设计师，作为当前版本继续设计。",
        );
      });
    }
  };
})(window.CREAM, window.THREE);
