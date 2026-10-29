// Regression test for vendor/seating.js (measured seat pose + sit check).
// Mock furniture only, no GLB files needed. Run: node scripts/seating_check.mjs
// Fixture geometry mirrors the probed Kenney sit pose (scripts/_tmpclip/sit.mjs):
// sit-pose hip joint ~0.042m above the origin, buttocks on the seat, feet dangle.
import * as THREE from "../vendor/three/build/three.module.js";
import { SEAT_DEFS, seatPose, sitYForSeat, hipDropOf, posedBox, seatDebug,
  checkSeated, measureSeat } from "../vendor/seating.js";

let fails = 0;
function ok(cond, msg) {
  console.log((cond ? "PASS " : "FAIL ") + msg);
  if (!cond) fails++;
}

// Mock loungeChair at scale 1.9: cushion top local y=0.25, backrest behind z<0.
const chair = new THREE.Group();
const cush = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.25, 0.45),
  new THREE.MeshBasicMaterial());
cush.position.set(0, 0.125, 0.05);
chair.add(cush);
const back = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.6, 0.12),
  new THREE.MeshBasicMaterial());
back.position.set(0, 0.4, -0.2);
chair.add(back);
chair.position.set(1.2, 0, 2.4);
chair.rotation.y = 1.6;
chair.scale.setScalar(1.9);
chair.updateWorldMatrix(true, true);

for (const f of ["chairDesk.glb", "chair.glb", "loungeChair.glb", "loungeSofa.glb"])
  ok(f in SEAT_DEFS, "SEAT_DEFS has " + f);

const pose = seatPose(chair, "loungeChair.glb", 0, 1.15, 0.042);
ok(!!pose, "seatPose returns a pose");
ok(pose && Math.abs(pose.seatY - 0.475) < 0.002,
  "seatY raycasts the cushion top (0.25*1.9=0.475)");
ok(Math.abs(sitYForSeat(0.475, 0.042) - 0.483) < 0.001,
  "sitYForSeat rests buttocks on the seat (0.475-0.042+0.05)");
ok(pose && Math.abs(pose.sitY - 0.483) < 0.001,
  "seatPose honors the measured hipDrop");
const formula = seatPose(chair, "loungeChair.glb", 0, 1.15);
ok(formula && Math.abs(formula.sitY - (formula.seatY - 0.23)) < 0.003,
  "seatPose without hipDrop keeps the bind-pose formula fallback");
// Hip offset is in model units, so it scales with the furniture:
// 0.10 * 1.9 = 0.19m ahead of center along yaw 1.6.
ok(pose && Math.abs(pose.x - (1.2 + Math.sin(1.6) * 0.19)) < 0.01 &&
  Math.abs(pose.z - (2.4 + Math.cos(1.6) * 0.19)) < 0.01,
  "hip point is ahead of the chair center, not at it");

function charBox(cx, cz, bottomY, w = 0.3, h = 0.95, d = 0.35) {
  return new THREE.Box3(
    new THREE.Vector3(cx - w / 2, bottomY, cz - d / 2),
    new THREE.Vector3(cx + w / 2, bottomY + h, cz + d / 2));
}
const furnBox = new THREE.Box3().setFromObject(chair);
ok(checkSeated(charBox(pose.x, pose.z, 0.475), furnBox,
  pose.seatY, "T/good", pose.yaw) === null, "correct sit passes silently");
ok(/sinks/.test(checkSeated(
  charBox(pose.x, pose.z, 0.475 - 0.25), furnBox,
  pose.seatY, "T/sunk", pose.yaw) || ""), "0.25m-sunk sit warns");
ok(/backrest/.test(checkSeated(charBox(
  pose.x - Math.sin(1.6) * 0.35, pose.z - Math.cos(1.6) * 0.35,
  0.475, 0.3, 1.0, 0.4), furnBox,
  pose.seatY, "T/back", pose.yaw) || ""), "torso in backrest warns");
ok(/floats/.test(checkSeated(
  charBox(pose.x, pose.z, pose.seatY + 0.2), furnBox,
  pose.seatY, "T/float", pose.yaw) || ""), "floating sit warns");
ok(/no contact/.test(checkSeated(
  charBox(pose.x + 2.0, pose.z, 0.475), furnBox,
  pose.seatY, "T/beside", pose.yaw) || ""), "disjoint sit warns no-contact");
ok(checkSeated(charBox(pose.x, pose.z, 0.483 - 0.16, 0.2, 1.05, 0.25), furnBox,
  pose.seatY, "T/feet", pose.yaw) === null, "dangling feet pass silently");
ok(seatPose(chair, "table.glb", 0, 1.15) === null, "unknown file -> null pose");
ok(measureSeat(new THREE.Group(), "chair.glb") === null, "meshless group -> null");

// hipDropOf: torso bone height above the origin, null without a hip bone.
{
  const g = new THREE.Group();
  const torso = new THREE.Bone();
  torso.name = "torso";
  torso.position.y = 0.3;
  g.add(torso);
  g.position.y = 1.0;
  ok(Math.abs(hipDropOf(g) - 0.3) < 1e-9, "hipDropOf measures the torso bone");
  ok(hipDropOf(new THREE.Group()) === null, "hipDropOf null without hip bone");
}

// posedBox matches setFromObject for rigid meshes; seatDebug builds 3 helpers.
{
  const g = new THREE.Group();
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.4, 0.3),
    new THREE.MeshBasicMaterial());
  m.position.set(1, 0.2, 3);
  g.add(m);
  const pb = posedBox(g), sb = new THREE.Box3().setFromObject(g);
  ok(pb.min.distanceTo(sb.min) < 1e-9 && pb.max.distanceTo(sb.max) < 1e-9,
    "posedBox matches for rigid meshes");
  const sc = new THREE.Scene();
  const dbg = seatDebug(sc, { x: 1, z: 2, yaw: 0.5, seatY: 0.4 }, g);
  ok(dbg.children.length === 3 && sc.children.includes(dbg),
    "seatDebug adds sphere + arrow + box");
}

const s0 = seatPose(chair, "loungeSofa.glb", 0, 1.15, 0.042);
const s1 = seatPose(chair, "loungeSofa.glb", 1, 1.15, 0.042);
ok(!!s0 && !!s1 && Math.hypot(s0.x - s1.x, s0.z - s1.z) > 0.5,
  "sofa seatIndex splits left/right");

if (fails) { console.log(fails + " FAILURES"); process.exit(1); }
console.log("ALL PASS");
