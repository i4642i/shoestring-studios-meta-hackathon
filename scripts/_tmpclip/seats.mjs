// Measure seat geometry per model (recentered LOCAL units, no scale).
// Raycast profile along +z (model faces +z) to find cushion front + seat top.
// Run: node scripts/_tmpclip/seats.mjs
import fs from "node:fs";
import path from "node:path";
import * as THREE from "./t/three.module.js";
import { GLTFLoader } from "./t/loaders/GLTFLoader.js";

const ROOT = path.resolve(import.meta.dirname, "..", "..");
const FDIR = path.join(ROOT, "vendor/kenney/furniture-kit/Models/GLTF format");
const loader = new GLTFLoader();
function parseGlb(full) {
  const buf = fs.readFileSync(full);
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  return new Promise((ok, bad) => loader.parse(ab, "", ok, bad));
}

const MODELS = ["chairDesk.glb", "chair.glb", "loungeChair.glb", "loungeSofa.glb"];
for (const f of MODELS) {
  const gltf = await parseGlb(path.join(FDIR, f));
  const m = gltf.scene;
  const fb = new THREE.Box3().setFromObject(m);
  const c = fb.getCenter(new THREE.Vector3());
  m.position.set(-c.x, -fb.min.y, -c.z);
  const g = new THREE.Group();
  g.add(m);
  g.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(g);
  const sz = box.getSize(new THREE.Vector3());
  console.log(`${f} local size ${sz.x.toFixed(3)}x${sz.y.toFixed(3)}x${sz.z.toFixed(3)}` +
    ` xz[${box.min.x.toFixed(3)}..${box.max.x.toFixed(3)}, ${box.min.z.toFixed(3)}..${box.max.z.toFixed(3)}]`);
  const ray = new THREE.Raycaster();
  const prof = [];
  for (const pz of [0.0, 0.05, 0.1, 0.15, 0.2, 0.25]) {
    ray.set(new THREE.Vector3(0, 2.0, pz), new THREE.Vector3(0, -1, 0));
    const hits = ray.intersectObject(g, true);
    prof.push(`${pz.toFixed(2)}:${hits.length ? hits[0].point.y.toFixed(3) : "miss"}`);
  }
  console.log(`  z-profile: ${prof.join(" ")}`);
  if (f === "loungeSofa.glb") {
    for (const px of [-0.3, -0.15, 0.15, 0.3]) {
      ray.set(new THREE.Vector3(px, 2.0, 0.1), new THREE.Vector3(0, -1, 0));
      const hits = ray.intersectObject(g, true);
      console.log(`  x=${px.toFixed(2)} z=0.10: ${hits.length ? hits[0].point.y.toFixed(3) : "miss"}`);
    }
  }
}
console.log("DONE");
