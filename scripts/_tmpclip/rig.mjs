// Probe 1: character rig inventory (clips, bones, bind box).
// Run: node scripts/_tmpclip/rig.mjs
import fs from "node:fs";
import path from "node:path";
import * as THREE from "./t/three.module.js";
import { GLTFLoader } from "./t/loaders/GLTFLoader.js";

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const CDIR = path.join(ROOT, "vendor/kenney/mini-characters/Models/GLB format");
const loader = new GLTFLoader();
// Strip images/textures (node has no image decoders); rig + clips survive.
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
  out.writeUInt32LE(0x46546c67, 0);
  out.writeUInt32LE(2, 4);
  out.writeUInt32LE(out.length, 8);
  out.writeUInt32LE(jp.length, 12);
  out.writeUInt32LE(0x4e4f534a, 16);
  jp.copy(out, 20);
  bin.copy(out, 20 + jp.length);
  return out.buffer.slice(out.byteOffset, out.byteOffset + out.byteLength);
}
function parseGlb(full) {
  return new Promise((ok, bad) => loader.parse(stripGlb(full), "", ok, bad));
}

for (const f of ["character-male-a.glb", "character-female-a.glb"]) {
  const gltf = await parseGlb(path.join(CDIR, f));
  console.log("=== " + f);
  console.log("clips:", gltf.animations.map((c) =>
    `${c.name}(${c.duration.toFixed(2)}s)`).join(" "));
  const root = gltf.scene;
  root.updateMatrixWorld(true);
  const bb = new THREE.Box3().setFromObject(root);
  const sz = bb.getSize(new THREE.Vector3());
  console.log(`bind box h=${sz.y.toFixed(3)} miny=${bb.min.y.toFixed(3)}`);
  let skinned = 0;
  root.traverse((o) => { if (o.isSkinnedMesh) skinned++; });
  console.log("skinned meshes:", skinned);
  const bones = [];
  root.traverse((o) => { if (o.isBone) bones.push(o); });
  console.log("bones(" + bones.length + "):");
  const v = new THREE.Vector3();
  for (const b of bones) {
    b.getWorldPosition(v);
    console.log(`  ${b.name} pos=(${v.x.toFixed(3)},${v.y.toFixed(3)},${v.z.toFixed(3)})`);
  }
}
console.log("DONE");
