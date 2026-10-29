import shutil

V = "vendor/three/examples/jsm/"
T = "scripts/_tmpclip/t/"
jobs = [
    (V + "loaders/GLTFLoader.js", T + "loaders/GLTFLoader.js", "../three.module.js"),
    (V + "utils/BufferGeometryUtils.js", T + "utils/BufferGeometryUtils.js", "../three.module.js"),
    (V + "utils/SkeletonUtils.js", T + "utils/SkeletonUtils.js", "../three.module.js"),
]
for src, dst, rel in jobs:
    shutil.copyfile(src, dst)
    with open(dst, encoding="utf-8") as f:
        text = f.read()
    text = text.replace("from 'three'", "from '%s'" % rel)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("ok", dst)
