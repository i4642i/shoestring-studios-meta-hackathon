// Probe 4: idle-clip track names + additive API presence.
// Run: node scripts/_tmpclip/tracks.mjs
import fs from "node:fs";
import path from "node:path";
import * as THREE from "./t/three.module.js";
import { GLTFLoader } from "./t/loaders/GLTFLoader.js";

console.log("makeAdditive:", typeof THREE.AnimationUtils.makeAdditive,
  "AdditiveBlendMode:", THREE.AdditiveAnimationBlendMode);
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
const gltf = await new Promise((ok, bad) => loader.parse(
  stripGlb(path.join(CDIR, "character-male-a.glb")), "", ok, bad));
const idle = THREE.AnimationClip.findByName(gltf.animations, "idle");
console.log("idle duration:", idle.duration);
for (const t of idle.tracks) console.log(" ", t.name, t.ValueTypeName,
  "times:", t.times.length);
// Head/arm value ranges (how big is the motion?).
for (const t of idle.tracks) {
  const node = t.name.split(".")[0];
  if (!["head", "arm-left", "arm-right"].includes(node)) continue;
  let mn = Infinity, mx = -Infinity;
  for (const v of t.values) { if (v < mn) mn = v; if (v > mx) mx = v; }
  console.log(`  range ${t.name}: [${mn.toFixed(4)}..${mx.toFixed(4)}]`);
}
console.log("DONE");
