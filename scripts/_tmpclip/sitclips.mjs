// Probe 3: compare sit-like clips + sit timing variance.
// Run: node scripts/_tmpclip/sitclips.mjs
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

for (const f of ["character-male-a.glb", "character-female-a.glb"]) {
  console.log("=== " + f);
  for (const clipName of ["sit", "drive", "wheelchair-sit"]) {
    const gltf = await parseGlb(path.join(CDIR, f));
    const root = gltf.scene;
    const bindH = new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3()).y;
    root.scale.setScalar(1.15 / bindH);
    root.updateMatrixWorld(true);
    const bones = {};
    root.traverse((o) => { if (o.isBone) bones[o.name] = o; });
    const clip = THREE.AnimationClip.findByName(gltf.animations, clipName);
    const mixer = new THREE.AnimationMixer(root);
    mixer.clipAction(clip).play();
    const tv = new THREE.Vector3(), q = new THREE.Quaternion(), d = new THREE.Vector3();
    const line = [];
    for (const t of [0, clip.duration / 2, clip.duration * 0.99]) {
      mixer.setTime(t);
      root.updateMatrixWorld(true);
      root.traverse((o) => { if (o.isSkinnedMesh) o.skeleton.update(); });
      bones.torso.getWorldPosition(tv);
      bones["leg-left"].getWorldQuaternion(q);
      d.set(0, -1, 0).applyQuaternion(q);
      const pb = new THREE.Box3().setFromObject(root, true);
      line.push(`t=${t.toFixed(3)} torsoY=${tv.y.toFixed(3)} ` +
        `legL=(${d.x.toFixed(2)},${d.y.toFixed(2)},${d.z.toFixed(2)}) ` +
        `boxX=[${pb.min.x.toFixed(2)}..${pb.max.x.toFixed(2)}] ` +
        `boxY=[${pb.min.y.toFixed(2)}..${pb.max.y.toFixed(2)}] ` +
        `boxZ=[${pb.min.z.toFixed(2)}..${pb.max.z.toFixed(2)}]`);
    }
    console.log("  [" + clipName + "]");
    for (const l of line) console.log("   " + l);
  }
}
console.log("DONE");
