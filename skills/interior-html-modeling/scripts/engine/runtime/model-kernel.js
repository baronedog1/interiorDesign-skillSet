/* Shared model semantics. Runs unchanged in the browser and Node compiler adapter.
 * Coordinates are source facts. Only explicitly linked endpoints are normalized;
 * neighbouring but distinct source endpoints are never welded by a distance guess. */
(function (global) {
  "use strict";
  const EPS = 1e-7,
    copy = (x) => JSON.parse(JSON.stringify(x)),
    sub = (a, b) => a.map((v, i) => v - b[i]),
    add = (a, b) => a.map((v, i) => v + b[i]),
    mul = (a, k) => a.map((v) => v * k),
    cross = (a, b) => a[0] * b[1] - a[1] * b[0],
    length = (a) => Math.hypot(...a),
    near = (a, b) => length(sub(a, b)) < EPS;
  function line(a, u, b, v) {
    const d = cross(u, v);
    return Math.abs(d) < EPS ? null : add(a, mul(u, cross(sub(b, a), v) / d));
  }
  function normalize(input) {
    const p = (global.InteriorJoinery || (typeof require==='function'?require('./joinery-kernel.js'):null))?.solve(input) || copy(input);
    for (const join of p.wallJoins || []) {
      if (join.source === "gap") continue;
      const ends = join.ends.map((e) => {
        const w = p.walls.find((w) => w.id === e.wallId);
        if (!w || !["a", "b"].includes(e.end)) throw Error("墙连接引用无效");
        return { w, key: e.end };
      });
      if (
        !join.point ||
        join.point.length !== 2 ||
        !join.point.every(Number.isFinite)
      )
        throw Error("墙连接必须提供来源连接点");
      for (const e of ends) {
        const old = [...e.w[e.key]];
        e.w[e.key] = [...join.point];
        for (const r of p.rooms)
          r.polygon = r.polygon.map((v) =>
            near(v, old) ? [...join.point] : v,
          );
      }
    }
    for (const o of p.structuralItems || []) {
      if (!o.position) {
        o.position = [o.x, 0, o.z];
        o.size = [o.width, o.height, o.depth];
        o.rotationY = o.angle || 0;
        for (const k of ["x", "z", "width", "height", "depth", "angle", "form"])
          delete o[k];
      }
      o.name ||= o.kind === "flue" ? "烟道" : "柱子";
      if (!o.roomId) {
        const rooms = p.rooms.filter((r) => {
          let inside = false;
          for (
            let i = 0, j = r.polygon.length - 1;
            i < r.polygon.length;
            j = i++
          ) {
            const a = r.polygon[i],
              b = r.polygon[j];
            if (
              a[1] > o.position[2] !== b[1] > o.position[2] &&
              o.position[0] <
                ((b[0] - a[0]) * (o.position[2] - a[1])) / (b[1] - a[1]) + a[0]
            )
              inside = !inside;
          }
          return inside;
        });
        if (rooms.length !== 1) throw Error("旧结构体房间归属不明确 " + o.id);
        o.roomId = rooms[0].id;
      }
    }
    return p;
  }
  function wallFootprints(p) {
    const result = {};
    for (const w of p.walls) {
      const u = mul(sub(w.b, w.a), 1 / length(sub(w.b, w.a))),
        n = [-u[1], u[0]],
        half = w.thickness / 2;
      const poly = [
        add(w.a, mul(n, half)),
        add(w.b, mul(n, half)),
        add(w.b, mul(n, -half)),
        add(w.a, mul(n, -half)),
      ];
      if (w.kind !== "railing")
        for (const end of ["a", "b"]) {
          if (w.joinMode === "source-gap") continue;
          const point = w[end],
            indices = end === "a" ? [0, 3] : [1, 2];
          const peers = p.walls.filter(
            (q) =>
              q.id !== w.id &&
              q.kind !== "railing" &&
              q.joinMode !== "source-gap" &&
              (near(q.a, point) || near(q.b, point)),
          );
          if (peers.length === 1) {
            const q = peers[0],
              other = near(q.a, point) ? q.b : q.a,
              v = mul(sub(other, point), 1 / length(sub(other, point))),
              qn = [-v[1], v[0]],
              away = end === "a" ? u : mul(u, -1);
            if (Math.abs(cross(away, v)) > EPS) {
              for (const [i, side] of indices.map((i, j) => [
                i,
                j === 0 ? 1 : -1,
              ])) {
                const offset = mul(n, half * side),
                  sign =
                    Math.sign(qn[0] * away[0] + qn[1] * away[1]) *
                    Math.sign(offset[0] * v[0] + offset[1] * v[1]);
                const meet = line(
                  add(point, offset),
                  u,
                  add(point, mul(qn, (sign * q.thickness) / 2)),
                  v,
                );
                if (
                  meet &&
                  length(sub(meet, point)) <=
                    Math.max(w.thickness, q.thickness) * 8
                )
                  poly[i] = meet;
              }
            }
          } else if (!peers.length) {
            for (const q of p.walls) {
              if (
                q.id === w.id ||
                q.kind === "railing" ||
                q.joinMode === "source-gap"
              )
                continue;
              const d = sub(q.b, q.a),
                l = length(d),
                v = mul(d, 1 / l),
                t = sub(point, q.a).reduce((s, x, i) => s + x * v[i], 0);
              if (
                t <= EPS ||
                t >= l - EPS ||
                Math.abs(cross(sub(point, q.a), v)) > EPS
              )
                continue;
              const qn = [-v[1], v[0]],
                away = end === "a" ? u : mul(u, -1),
                sign = Math.sign(away[0] * qn[0] + away[1] * qn[1]);
              if (!sign) continue;
              for (const [i, side] of indices.map((i, j) => [
                i,
                j === 0 ? 1 : -1,
              ])) {
                const meet = line(
                  add(point, mul(n, half * side)),
                  u,
                  add(point, mul(qn, (sign * q.thickness) / 2)),
                  v,
                );
                if (meet) poly[i] = meet;
              }
              break;
            }
          }
        }
      result[w.id] = poly;
    }
    return result;
  }
  function openings(p) {
    const out = {};
    for (const o of p.openings) {
      const kind = o.type,
        moving = ["door", "sliding-door"].includes(kind),
        f = moving ? o.openFraction || 0 : 0,
        infill = o.infill || (kind === "door" ? "solid" : "clear-glass"),
        c = o.offset + o.width / 2,
        w = o.width,
        h = o.height,
        panels = [];
      const panel = (x, width, yaw = 0, z = 0) =>
        panels.push({
          center: [x, o.sill + h / 2, z],
          size: [width, h - 0.035, infill === "solid" ? 0.044 : 0.014],
          yaw,
          infill,
        });
      if (kind === "door") {
        const side = o.hingeSide === "right" ? -1 : 1,
          angle = (((o.swingSign || 1) * side * Math.PI) / 2) * f,
          hinge = c - (side * w) / 2;
        panel(
          hinge + (side * Math.cos(angle) * w) / 2,
          w - 0.035,
          angle,
          (-side * Math.sin(angle) * w) / 2,
        );
      } else if (kind === "sliding-door") {
        const toward = o.slideTo === "right" ? 1 : -1;
        panel(c + (toward * w) / 4, w / 2, 0, -0.022);
        panel(c - (toward * w) / 4 + ((toward * w) / 2) * f, w / 2, 0, 0.022);
      } else if (["window", "fixed-glazing"].includes(kind)) {
        const count = Math.max(2, Math.floor(w / 0.95 + 0.5));
        for (let i = 0; i < count; i++)
          panel(c - w / 2 + ((i + 0.5) * w) / count, w / count - 0.025);
      }
      out[o.id] = {
        ...o,
        openFraction: f,
        infill,
        state:
          kind === "passage"
            ? "open"
            : f === 0
              ? "closed"
              : f === 1
                ? "maximum-open"
                : "part-open",
        panels,
        seeThrough: kind === "passage" || infill === "clear-glass" || f > 0,
        sourceStatus:
          !moving || o.openFraction !== undefined
            ? "explicit"
            : "preview-default-closed-not-confirmed",
        clearOpeningFraction:
          kind === "passage" ? 1 : kind === "sliding-door" ? f / 2 : null,
        exteriorView: o.exteriorView || {
          kind: "unknown",
          description: "外部目标未确认，不能擅自当作户外实景或另一间房",
        },
      };
    }
    return out;
  }
  function updateWall(p, id, patch) {
    const w = p.walls.find((w) => w.id === id);
    if (!w) throw Error("墙体不存在");
    const oldWalls = copy(p.walls),
      oldRooms = copy(p.rooms),
      oldOutline = p.floor ? copy(p.floor.outline) : null;
    const old = copy(w);
    Object.assign(w, copy(patch));
    if (length(sub(w.b, w.a)) < 0.05 || !(w.thickness > 0) || !(w.height > 0))
      throw Error("墙长、厚度和高度必须有效");
    for (const key of ["a", "b"])
      if (!near(old[key], w[key])) {
        for (const q of p.walls)
          if (
            q.id !== id &&
            q.joinMode !== "source-gap" &&
            old.joinMode !== "source-gap"
          )
            for (const k of ["a", "b"])
              if (near(q[k], old[key])) q[k] = [...w[key]];
        for (const r of p.rooms)
          r.polygon = r.polygon.map((v) =>
            near(v, old[key]) ? [...w[key]] : v,
          );
        for (const j of p.wallJoins || [])
          if (
            j.source !== "gap" &&
            j.ends.some((e) => e.wallId === id && e.end === key)
          )
            j.point = [...w[key]];
      }
    // Existing axis-aligned joins retain their shared X/Z constraints. Deliberately
    // supplying conflicting coordinates breaks that constraint rather than inventing an angle.
    const nodes = oldWalls.flatMap((q) =>
      ["a", "b"].map((end) => ({ wallId: q.id, end, point: q[end] })),
    );
    for (let axis = 0; axis < 2; axis++) {
      const parents = nodes.map((_, i) => i),
        find = (i) => (parents[i] === i ? i : (parents[i] = find(parents[i]))),
        union = (a, b) => (parents[find(a)] = find(b));
      for (let i = 0; i < nodes.length; i++)
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i],
            b = nodes[j],
            wa = oldWalls.find((w) => w.id === a.wallId),
            wb = oldWalls.find((w) => w.id === b.wallId);
          if (wa.joinMode === "source-gap" || wb.joinMode === "source-gap")
            continue;
          if (
            near(a.point, b.point) ||
            (a.wallId === b.wallId &&
              Math.abs(a.point[axis] - b.point[axis]) < EPS)
          )
            union(i, j);
        }
      const changes = new Map();
      nodes.forEach((n, i) => {
        const now = p.walls.find((w) => w.id === n.wallId)[n.end][axis];
        if (Math.abs(now - n.point[axis]) > EPS) {
          const key = find(i);
          if (!changes.has(key)) changes.set(key, []);
          changes.get(key).push(now);
        }
      });
      nodes.forEach((n, i) => {
        const values = changes.get(find(i));
        if (values && Math.max(...values) - Math.min(...values) < EPS)
          p.walls.find((w) => w.id === n.wallId)[n.end][axis] = values[0];
      });
    }
    for (const j of p.wallJoins || [])
      if (j.source !== "gap") {
        const e = j.ends[0];
        j.point = [...p.walls.find((w) => w.id === e.wallId)[e.end]];
      }
    // Preserve signed wall-face offsets, not only centre-line coincident vertices.
    const mapped = (point) => {
      const refs = [];
      for (const a of oldWalls) {
        const d = sub(a.b, a.a),
          L = length(d),
          u = mul(d, 1 / L),
          n = [-u[1], u[0]],
          v = sub(point, a.a),
          along = v[0] * u[0] + v[1] * u[1],
          offset = v[0] * n[0] + v[1] * n[1];
        if (
          Math.abs(offset) <= a.thickness / 2 + 0.001 &&
          along >= -a.thickness / 2 - 0.001 &&
          along <= L + a.thickness / 2 + 0.001
        ) {
          const b = p.walls.find((w) => w.id === a.id),
            nu = mul(sub(b.b, b.a), 1 / length(sub(b.b, b.a))),
            nn = [-nu[1], nu[0]];
          refs.push({
            a: add(b.a, mul(nn, offset)),
            u: nu,
            t: along / L,
            L: length(sub(b.b, b.a)),
            changed: !near(a.a, b.a) || !near(a.b, b.b),
          });
        }
      }
      if (!refs.some((r) => r.changed)) return point;
      for (let i = 0; i < refs.length; i++)
        for (let j = i + 1; j < refs.length; j++) {
          const hit = line(refs[i].a, refs[i].u, refs[j].a, refs[j].u);
          if (hit) return hit;
        }
      const r = refs.find((r) => r.changed);
      return add(r.a, mul(r.u, r.t * r.L));
    };
    for (const r of p.rooms) {
      const before = oldRooms.find((x) => x.id === r.id);
      r.polygon = before.polygon.map(mapped);
    }
    if (oldOutline) p.floor.outline = oldOutline.map(mapped);
    for (const q of p.walls)
      for (const o of p.openings.filter((o) => o.wallId === q.id))
        if (
          o.offset < 0 ||
          o.offset + o.width > length(sub(q.b, q.a)) + EPS ||
          o.sill + o.height > q.height + EPS
        )
          throw Error("修改后门窗超出宿主墙，请调整墙长或开口尺寸");
  }
  function command(input, cmd) {
    const p = copy(input),
      { id, patch = {} } = cmd;
    switch (cmd.type) {
      case "wall.update":
        updateWall(p, id, patch);
        break;
      case "wall.add":
        p.walls.push(copy(cmd.value));
        break;
      case "wall.remove":
        p.walls = p.walls.filter((w) => w.id !== id);
        p.openings = p.openings.filter((o) => o.wallId !== id);
        p.wallJoins = (p.wallJoins || []).filter(
          (j) => !j.ends.some((e) => e.wallId === id),
        );
        for (const r of p.rooms) if (r.frontWallId === id) delete r.frontWallId;
        break;
      case "opening.update": {
        const o = p.openings.find((o) => o.id === id);
        if (!o) throw Error("门窗不存在");
        Object.assign(o, copy(patch));
        break;
      }
      case "opening.add":
        p.openings.push(copy(cmd.value));
        break;
      case "opening.remove":
        p.openings = p.openings.filter((o) => o.id !== id);
        break;
      case "structure.add":
        (p.structuralItems ||= []).push(copy(cmd.value));
        break;
      case "structure.update": {
        const o = (p.structuralItems || []).find((o) => o.id === id);
        if (!o) throw Error("结构体不存在");
        if (o.locked && Object.keys(patch).some((k) => k !== "locked"))
          throw Error("结构体已锁定");
        Object.assign(o, copy(patch));
        break;
      }
      case "structure.remove":
        p.structuralItems = (p.structuralItems || []).filter(
          (o) => o.id !== id,
        );
        break;
      case "placement.update": {
        const o = p.placements.find((o) => o.id === id);
        if (!o) throw Error("家具不存在");
        Object.assign(o, copy(patch));
        break;
      }
      default:
        throw Error("未知模型操作 " + cmd.type);
    }
    return normalize(p);
  }
  const api = { normalize, wallFootprints, openings, command };
  if (typeof module !== "undefined") module.exports = api;
  global.InteriorModel = api;
  if (typeof require !== "undefined" && require.main === module) {
    let s = "";
    process.stdin.on("data", (c) => (s += c));
    process.stdin.on("end", () => {
      try {
        const { action, layout, command: cmd } = JSON.parse(s);
        const p = normalize(layout);
        console.log(
          JSON.stringify(
            action === "command"
              ? command(p, cmd)
              : action === "openings"
                ? openings(p)
                : {
                    layout: p,
                    wallFootprints: wallFootprints(p),
                    openingStates: openings(p),
                  },
          ),
        );
      } catch (e) {
        process.stderr.write(e.message);
        process.exitCode = 1;
      }
    });
  }
})(typeof window === "undefined" ? globalThis : window);
