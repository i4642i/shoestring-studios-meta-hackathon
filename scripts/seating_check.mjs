// Regression test for vendor/seating.js (measured seat pose + sit check).
// Mock furniture only, no GLB files needed. Run: node scripts/seating_check.mjs
import * as THREE from "../vendor/three/build/three.module.js";
import { SEAT_DEFS, seatPose, checkSeated, measureSeat } from "../vendor/seating.js";

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

const pose = seatPose(chair, "loungeChair.glb", 0, 1.15);
ok(!!pose, "seatPose returns a pose");
ok(pose && Math.abs(pose.seatY - 0.475) < 0.002,
  "seatY raycasts the cushion top (0.25*1.9=0.475)");
ok(pose && Math.abs(pose.sitY - (pose.seatY - 0.23)) < 0.003,
  "sitY sits the 1.15m rig hips on the seat");
// Hip offset is in model units, so it scales with the furniture:
// 0.10 * 1.9 = 0.19m ahead of center along yaw 1.6.
ok(pose && Math.abs(pose.x - (1.2 + Math.sin(1.6) * 0.19)) < 0.01 &&
  Math.abs(pose.z - (2.4 + Math.cos(1.6) * 0.19)) < 0.01,
  "hip point is ahead of the chair center, not at it");

function charBox(cx, cz, bottomY, w = 0.3, h = 0.75, d = 0.35) {
  return new THREE.Box3(
    new THREE.Vector3(cx - w / 2, bottomY, cz - d / 2),
    new THREE.Vector3(cx + w / 2, bottomY + h, cz + d / 2));
}
const furnBox = new THREE.Box3().setFromObject(chair);
ok(checkSeated(charBox(pose.x, pose.z, pose.sitY), furnBox,
  pose.seatY, "T/good", pose.yaw) === null, "correct sit passes silently");
ok(/sinks/.test(checkSeated(
  charBox(pose.x, pose.z, pose.sitY - 0.25), furnBox,
  pose.seatY, "T/sunk", pose.yaw) || ""), "0.25m-sunk sit warns");
ok(/backrest/.test(checkSeated(charBox(
  pose.x - Math.sin(1.6) * 0.35, pose.z - Math.cos(1.6) * 0.35,
  pose.sitY, 0.3, 1.0, 0.4), furnBox,
  pose.seatY, "T/back", pose.yaw) || ""), "torso in backrest warns");
ok(/floats/.test(checkSeated(
  charBox(pose.x, pose.z, pose.seatY + 0.2), furnBox,
  pose.seatY, "T/float", pose.yaw) || ""), "floating sit warns");
ok(/no contact/.test(checkSeated(
  charBox(pose.x + 2.0, pose.z, pose.sitY), furnBox,
  pose.seatY, "T/beside", pose.yaw) || ""), "disjoint sit warns no-contact");
ok(seatPose(chair, "table.glb", 0, 1.15) === null, "unknown file -> null pose");
ok(measureSeat(new THREE.Group(), "chair.glb") === null, "meshless group -> null");

const s0 = seatPose(chair, "loungeSofa.glb", 0, 1.15);
const s1 = seatPose(chair, "loungeSofa.glb", 1, 1.15);
ok(!!s0 && !!s1 && Math.hypot(s0.x - s1.x, s0.z - s1.z) > 0.5,
  "sofa seatIndex splits left/right");

if (fails) { console.log(fails + " FAILURES"); process.exit(1); }
console.log("ALL PASS");
