// Probe 2: sit-pose measurements at 1.15m normalize (like the pages).
// Run: node scripts/_tmpclip/sit.mjs
import fs from "node:fs";
import path from "node:path";
import * as THREE from "./t/three.module.js";
import { GLTFLoader } from "./t/loaders/GLTFLoader.js";

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const CDIR = path.join(ROOT, "vendor/kenney/mini-characters/Models/GLB format");
const loader = new GLTFLoader();
function stripGlb(full) {
  const buf = Buffer.from(fs.readFileSync(full));
  const jLen = buf.readUInt32LE(12);
  const json = JSON.parse(buf.subarray(20, 20 + jLen).toString("utf-8"));
  delete json.images; delete json.textures; delete json.samplers;
  json.materials = (json.materials || []).map(() => ({}));
  const js = Buffer.from(JSON.stringify(json));
  const pad = (4 - (js.length % 4)) % 4;
  const jp = Buffer.concat([js, Buffer.alloc(pad, 0x20)]);
  const bin = buf.subarray(20 + jLen);
  const out = Buffer.alloc(20 + jp.length + bin.length);
  out.writeUInt32LE(0x46546c67, 0); out.writeUInt32LE(2, 4);
  out.writeUInt32LE(out.length, 8); out.writeUInt32LE(jp.length, 12);
  out.writeUInt32LE(0x4e4f534a, 16);
  jp.copy(out, 20); bin.copy(out, 20 + jp.length);
  return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength);
}
function parseGlb(full) {
  return new Promise((ok, bad) => loader.parse(stripGlb(full), "", ok, bad));
}
const f3 = (v) => v.toArray().map((x) => +x.toFixed(3)).join(",");

for (const f of ["character-male-a.glb", "character-female-a.glb"]) {
  const gltf = await parseGlb(path.join(CDIR, f));
  const root = gltf.scene;
  // Normalize like the pages: bind-pose Box3 height -> 1.15m.
  const bindH = new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3()).y;
  root.scale.setScalar(1.15 / bindH);
  root.position.set(0, 0, 0);
  root.rotation.y = 0;
  root.updateMatrixWorld(true);
  const bones = {};
  root.traverse((o) => { if (o.isBone) bones[o.name] = o; });
  const sit = THREE.AnimationClip.findByName(gltf.animations, "sit");
  const mixer = new THREE.AnimationMixer(root);
  const action = mixer.clipAction(sit);
  action.play();
  mixer.update(sit.duration / 2);
  root.updateMatrixWorld(true);
  root.traverse((o) => { if (o.isSkinnedMesh) o.skeleton.update(); });
  console.log(`=== ${f} (scale ${(1.15 / bindH).toFixed(3)})`);
  const tv = new THREE.Vector3();
  bones.torso.getWorldPosition(tv);
  console.log("sit torso world y =", tv.y.toFixed(3), " (bind hip ~=0.28)");
  const q = new THREE.Quaternion(), down = new THREE.Vector3();
  for (const ln of ["leg-left", "leg-right"]) {
    bones[ln].getWorldQuaternion(q);
    down.set(0, -1, 0).applyQuaternion(q);
    console.log(`${ln} down-axis world =`, f3(down));
  }
  const pb = new THREE.Box3().setFromObject(root, true);
  console.log("precise posed box min", f3(pb.min), "max", f3(pb.max));
  const nb = new THREE.Box3().setFromObject(root, false);
  console.log("plain box        min", f3(nb.min), "max", f3(nb.max));
}
console.log("DONE");
