#!/usr/bin/env python3
"""Write the block snapshot of a Minecraft version: snapshot.py <mc version> [snapshot dir]

snapshots/<version>.txt         one line per block: `<id> <prop>=<v1>|<v2> ...`, sorted. The states of a block are
                                all combinations of its property values, so this is enough to rebuild the list.
snapshots/<version>.biomes.txt  biome ids (only if the data generator writes them as files)

The data comes from the vanilla server's own data generator, so it matches what that version knows.
"""
import glob, json, math, os, shutil, subprocess, sys, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
JAVA = os.environ.get("JAVA", "java")
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dynmap-render-test"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def server_jar(version):
    dest = os.path.join(CACHE, f"server-{version}.jar")
    if os.path.exists(dest):
        return dest
    os.makedirs(CACHE, exist_ok=True)
    entry = next(v for v in json.loads(get(MANIFEST))["versions"] if v["id"] == version)
    url = json.loads(get(entry["url"]))["downloads"]["server"]["url"]
    with open(dest + ".part", "wb") as f:
        f.write(get(url))
    os.rename(dest + ".part", dest)
    return dest


def run_generator(version):
    """Returns (blocks.json content, sorted biome ids)."""
    jar = server_jar(version)
    out = tempfile.mkdtemp(prefix="dynmap-reports-")
    try:
        # 1.18+ has a bundler jar, older versions have a plain server jar
        for cmd in ([JAVA, "-DbundlerMainClass=net.minecraft.data.Main", "-jar", jar, "--reports", "--server",
                     "--output", out],
                    [JAVA, "-cp", jar, "net.minecraft.data.Main", "--reports", "--server", "--output", out]):
            subprocess.run(cmd, cwd=out, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            f = os.path.join(out, "reports", "blocks.json")
            if os.path.exists(f):
                biomes = sorted("minecraft:" + os.path.basename(b)[:-5]
                                for b in glob.glob(f"{out}/data/minecraft/worldgen/biome/*.json"))
                return json.load(open(f)), biomes
        raise RuntimeError(f"data generator produced no blocks.json for {version}")
    finally:
        shutil.rmtree(out, ignore_errors=True)


def snapshot_lines(blocks):
    lines = []
    for name in sorted(blocks):
        props = {}
        states = blocks[name]["states"]
        for st in states:
            for k, v in (st.get("properties") or {}).items():
                props.setdefault(k, set()).add(v)
        if math.prod(len(v) for v in props.values()) != len(states):   # render_test rebuilds the states from all combinations
            print(f"warning: {name} has {len(states)} states, its properties give "
                  f"{math.prod(len(v) for v in props.values())}", file=sys.stderr)
        lines.append(" ".join([name] + [f"{k}={'|'.join(sorted(props[k]))}" for k in sorted(props)]))
    return lines


if __name__ == "__main__":
    version = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "snapshots")
    os.makedirs(outdir, exist_ok=True)
    blocks, biomes = run_generator(version)
    lines = snapshot_lines(blocks)
    with open(os.path.join(outdir, f"{version}.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    bpath = os.path.join(outdir, f"{version}.biomes.txt")
    if biomes:
        with open(bpath, "w") as f:
            f.write("\n".join(biomes) + "\n")
    elif os.path.exists(bpath):
        os.remove(bpath)
    print(f"{version}: {len(lines)} blocks, {len(biomes)} biomes")
