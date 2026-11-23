// Camera and group geometry in the editor (mirrors sciview.engine.camera and render.Xform).
// Used to turn a mouse drag in the preview into a change of 3D coordinates.
import { S, valueAt, ancestors, objById, isGroup, schemaOf } from './state.js';

const sub = (a, b) => a.map((x, i) => x - b[i]);
const add = (a, b) => a.map((x, i) => x + b[i]);
const mul = (a, k) => a.map((x) => x * k);
const dot = (a, b) => a.reduce((s, x, i) => s + x * b[i], 0);
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const n = Math.hypot(...a); return n > 1e-12 ? a.map((x) => x / n) : a; };
const mat = (M, v) => M.map((row) => dot(row, v));
const matmul = (A, B) => A.map((row) => [0, 1, 2].map((j) => row[0] * B[0][j] + row[1] * B[1][j] + row[2] * B[2][j]));
const I3 = () => [[1, 0, 0], [0, 1, 0], [0, 0, 1]];

export function inv3(M) {
  const [a, b, c] = M[0], [d, e, f] = M[1], [g, h, i] = M[2];
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-12) return I3();
  return [[A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
    [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
    [C / det, -(a * h - b * g) / det, (a * e - b * d) / det]];
}

/** Rotation from Euler angles in degrees, applied x, then y, then z (R = Rz Ry Rx). */
export function rotation(rx, ry, rz) {
  const [ax, ay, az] = [rx, ry, rz].map((d) => (d * Math.PI) / 180);
  const [cx, sx, cy, sy, cz, sz] = [Math.cos(ax), Math.sin(ax), Math.cos(ay), Math.sin(ay), Math.cos(az), Math.sin(az)];
  const Rx = [[1, 0, 0], [0, cx, -sx], [0, sx, cx]];
  const Ry = [[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]];
  const Rz = [[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]];
  return matmul(Rz, matmul(Ry, Rx));
}

/** The scene camera at time t, in design pixels. */
export function camera(t = S.time) {
  const c = objById('camera');
  const target = valueAt(c, 'target', t).map(Number);
  const dist = Math.max(Number(valueAt(c, 'distance', t)), 1e-6);
  const az = (Number(valueAt(c, 'azimuth', t)) * Math.PI) / 180;
  const el = (Number(valueAt(c, 'elevation', t)) * Math.PI) / 180;
  const fov = Number(valueAt(c, 'fov', t));
  const off = valueAt(c, 'offset', t).map(Number);
  const eye = add(target, mul([Math.cos(el) * Math.cos(az), Math.cos(el) * Math.sin(az), Math.sin(el)], dist));
  const fwd = norm(sub(target, eye));
  let up = [0, 0, 1];
  if (Math.abs(dot(fwd, up)) > 0.999) up = [0, 1, 0];
  const right = norm(cross(fwd, up));
  const upv = cross(right, fwd);
  const W = S.project.settings.width || 1920, H = S.project.settings.height || 1080;
  const focal = (H / 2) / Math.tan(((Math.max(fov, 1e-3) * Math.PI) / 180) / 2);
  return { eye, fwd, right, up: upv, focal, cx: W / 2 + off[0], cy: H / 2 + off[1] };
}

export function project(cam, p) {
  const r = sub(p, cam.eye);
  const z = Math.max(dot(r, cam.fwd), 1e-3);
  return [cam.cx + (cam.focal * dot(r, cam.right)) / z, cam.cy - (cam.focal * dot(r, cam.up)) / z, z];
}

/** 3D transform of the groups around an object: world = A @ local + c. ``fromGroup`` = the group whose space we want. */
export function xform3(groupId, t = S.time) {
  const g = groupId ? objById(groupId) : null;
  if (!g || !isGroup(g)) return { A: I3(), c: [0, 0, 0] };
  const chain = [g, ...ancestors(g)];                 // nearest first
  let A = I3(), c = [0, 0, 0];
  for (const grp of chain.reverse()) {                 // outermost first, like the renderer
    const sig = Number(valueAt(grp, 'scale', t));
    const R = rotation(...valueAt(grp, 'rotation', t).map(Number)).map((row) => row.map((x) => x * sig));
    const p3 = valueAt(grp, 'pivot3d', t).map(Number);
    const cg = add(sub(p3, mat(R, p3)), valueAt(grp, 'position', t).map(Number));
    c = add(mat(A, cg), c);
    A = matmul(A, R);
  }
  return { A, c };
}

/** 2D scale of the groups around an object (a design-pixel drag moves it by drag / a). */
export function scale2(groupId, t = S.time) {
  let a = 1;
  let g = groupId ? objById(groupId) : null;
  const seen = new Set();
  while (g && isGroup(g) && !seen.has(g.id)) {
    seen.add(g.id);
    a *= Number(valueAt(g, 'scale', t)) || 1;
    g = g.parent ? objById(g.parent) : null;
  }
  return a;
}

/** Which properties a 3D drag moves, and the local point to drag by. */
export function drag3dProps(obj) {
  const t = S.time;
  if (obj.type === 'beam') return { props: ['source', 'target'], anchor: mul(add(valueAt(obj, 'source', t), valueAt(obj, 'target', t)), 0.5) };
  if (obj.type === 'arrow3d') return { props: ['tail', 'tip'], anchor: mul(add(valueAt(obj, 'tail', t), valueAt(obj, 'tip', t)), 0.5) };
  if (obj.type === 'label3d') return { props: ['point'], anchor: valueAt(obj, 'point', t) };
  if (obj.type === 'group') return { props: ['position'], anchor: add(valueAt(obj, 'pivot3d', t), valueAt(obj, 'position', t)) };
  if (obj.type === 'grid3d') return null;                // the floor: dragging it orbits instead
  if (obj.type === 'scalebar3d') return { props: ['origin'], anchor: valueAt(obj, 'origin', t) };
  const sc = schemaOf(obj);
  const hasCenter = sc && sc.props.some((p) => p.name === 'center' && p.kind === 'vec3');
  return hasCenter ? { props: ['center'], anchor: valueAt(obj, 'center', t) } : null;
}

/**
 * Local-space change for a screen drag (dx, dy design px) of a point given in the space of
 * group ``spaceId``. With ``lockAxis`` the change follows the local axis closest to the drag.
 */
export function dragDelta(anchorLocal, spaceId, dx, dy, lockAxis = false) {
  const cam = camera();
  const { A, c } = xform3(spaceId);
  const world = add(mat(A, anchorLocal.map(Number)), c);
  const z = Math.max(dot(sub(world, cam.eye), cam.fwd), 1e-3);
  const Ainv = inv3(A);
  if (!lockAxis) {
    const dw = mul(add(mul(cam.right, dx), mul(cam.up, -dy)), z / cam.focal);
    return mat(Ainv, dw);
  }
  let best = null;
  for (let k = 0; k < 3; k++) {
    const e = [0, 0, 0];
    e[k] = 1;
    const dir = mat(A, e);
    const sd = [(dot(dir, cam.right) * cam.focal) / z, (-dot(dir, cam.up) * cam.focal) / z];
    const len2 = sd[0] * sd[0] + sd[1] * sd[1];
    if (len2 < 1e-9) continue;
    const score = Math.abs(sd[0] * dx + sd[1] * dy) / Math.sqrt(len2);
    if (!best || score > best.score) best = { k, s: (sd[0] * dx + sd[1] * dy) / len2, score };
  }
  const d = [0, 0, 0];
  if (best) d[best.k] = best.s;
  return d;
}
