// Shared seating: measured seat points for Kenney seat furniture.
// Imported by office_3d.html and index.html. Three comes from the same
// vendored build the pages' importmap maps, so the module instance is shared
// (and plain node can run this file for scripts/seating_check.mjs).
// Local units = recentered model space (base y=0, center x/z=0, faces +z);
// world placement goes through each furniture group's own transform, so any
// scale works. Seat height is raycast once per model and cached.
import * as THREE from "./three/build/three.module.js";

// Local-space seat geometry (measured with scripts/_tmpclip/seats.mjs):
// fwd = hip offset from model center toward the seat front; probeH = ray origin.
export const SEAT_DEFS = {
  "chairDesk.glb": { fwd: 0.10, probeH: 1.0 },
  "chair.glb": { fwd: 0.05, probeH: 1.0 },
  "loungeChair.glb": { fwd: 0.10, probeH: 1.0 },
  "loungeSofa.glb": {
    fwd: 0.10, probeH: 1.0,
    seats: [{ dx: -0.245, dz: 0.10 }, { dx: 0.245, dz: 0.10 }],
  },
};

// Character rig (measured Kenney mini rig at 1.15m: hip joint 0.28m).
export const HIP_FRAC = 0.2435;
export const BUTT_BELOW_HIP = 0.05;
export const FALLBACK_SIT_Y = 0.2;

const seatCache = {}; // filename -> seat local Y

export function measureSeat(group, filename) {
  const def = SEAT_DEFS[filename];
  if (!def) return null;
  const sc = group.scale.x;
  if (!(filename in seatCache)) {
    const probe = def.seats ? def.seats[0] : { dx: 0, dz: def.fwd };
    group.updateWorldMatrix(true, false);
    const wp = group.localToWorld(new THREE.Vector3(probe.dx || 0, 0, probe.dz));
    const ray = new THREE.Raycaster(
      new THREE.Vector3(wp.x, group.position.y + def.probeH * sc, wp.z),
      new THREE.Vector3(0, -1, 0));
    const hits = ray.intersectObject(group, true);
    if (!hits.length) return null;
    seatCache[filename] = (hits[0].point.y - group.position.y) / sc;
  }
  return group.position.y + seatCache[filename] * sc;
}

export function sitYFor(seatY, charH) {
  return seatY - (HIP_FRAC * charH - BUTT_BELOW_HIP);
}

// World-space seat pose for sitting: hip XZ on the cushion front,
// chair yaw, measured seat height and matching character lift.
export function seatPose(group, filename, seatIndex, charH) {
  const def = SEAT_DEFS[filename];
  if (!def) return null;
  const off = def.seats
    ? def.seats[(seatIndex || 0) % def.seats.length]
    : { dx: 0, dz: def.fwd };
  group.updateWorldMatrix(true, false);
  const wp = group.localToWorld(new THREE.Vector3(off.dx || 0, 0, off.dz));
  const seatY = measureSeat(group, filename);
  if (seatY === null) return null;
  return { x: wp.x, z: wp.z, yaw: group.rotation.y, seatY,
           sitY: sitYFor(seatY, charH || 1.15) };
}

// Load-time penetration check. charBox is the bind-pose box; the rules are
// XZ-aware so dangling legs (outside the chair column) and arms pass, while
// a butt through the cushion or a torso inside the backrest warns.
// Returns a warning string or null.
export function checkSeated(charBox, furnBox, seatY, label, yaw) {
  const ix0 = Math.max(charBox.min.x, furnBox.min.x);
  const ix1 = Math.min(charBox.max.x, furnBox.max.x);
  const iz0 = Math.max(charBox.min.z, furnBox.min.z);
  const iz1 = Math.min(charBox.max.z, furnBox.max.z);
  if (ix0 >= ix1 || iz0 >= iz1) return `[seating] ${label}: no contact with seat`;
  if (charBox.min.y > seatY + 0.10)
    return `[seating] ${label}: floats above seat`;
  const colA = (ix1 - ix0) * (iz1 - iz0);
  const underH = Math.min(charBox.max.y, seatY - 0.15) - charBox.min.y;
  if (underH > 0 && underH * colA > 0.02) {
    return `[seating] ${label}: sinks through cushion ` +
      `(${(underH * colA).toFixed(3)}m3 below seat)`;
  }
  // Backrest = rear 35% along the dominant facing axis (rear opposes facing).
  let rx0 = furnBox.min.x, rx1 = furnBox.max.x;
  let rz0 = furnBox.min.z, rz1 = furnBox.max.z;
  if (Math.abs(Math.sin(yaw)) >= Math.abs(Math.cos(yaw))) {
    const w = rx1 - rx0;
    if (Math.sin(yaw) >= 0) rx1 = rx0 + 0.35 * w; else rx0 = rx1 - 0.35 * w;
  } else {
    const d = rz1 - rz0;
    if (Math.cos(yaw) >= 0) rz1 = rz0 + 0.35 * d; else rz0 = rz1 - 0.35 * d;
  }
  const tx0 = Math.max(charBox.min.x, rx0), tx1 = Math.min(charBox.max.x, rx1);
  const tz0 = Math.max(charBox.min.z, rz0), tz1 = Math.min(charBox.max.z, rz1);
  const ty0 = Math.max(charBox.min.y, seatY + 0.25);
  const ty1 = Math.min(charBox.max.y, seatY + 0.7);
  if (tx1 > tx0 && tz1 > tz0 && ty1 > ty0 &&
      (tx1 - tx0) * (tz1 - tz0) * (ty1 - ty0) > 0.008) {
    return `[seating] ${label}: torso into backrest`;
  }
  return null;
}
