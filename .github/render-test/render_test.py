#!/usr/bin/env python3
"""Start a server with Dynmap, place a grid of blocks in a flat world, render it and stitch the tiles into pictures.

  render_test.py --platform spigot --version 1.21.11 --mode delta --jar target/Dynmap-...-spigot.jar --out out

mode full   every state of every block in the version
mode delta  blocks that are new or got different properties since the previous snapshot, plus the ones in
            changed.txt (the oldest snapshot has no previous one, so it is rendered in full)
Both modes always add canary.txt and a biome strip (tinted blocks and a water pool in every biome).

Output: <platform>-<version>[-full]-<flat|world>.png, console.log and summary.json in --out.
The exit code is not 0 if the server, the web server or the renderer is broken. A person has to look at the
pictures.
"""
import argparse, glob, json, math, os, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from layout import (BIOME_COLS, M, ORIGIN, SIZE_BIOME, block_commands, biome_commands, canary_states, feedback_rule,  # noqa: E402
                    floor_y, gamerules, level_type, load_biomes, select_states)
from servers import Server, get_fabric, get_forge, get_paper, http_get  # noqa: E402
from stitch import stitch  # noqa: E402

TEMPLATES = os.path.join(HERE, "..", "..", "DynmapCore", "src", "main", "resources", "templates")
MAPS = {"flat": "flat", "world": "surface"}   # picture variant -> Dynmap map
PREFIX = {"flat": "flat", "world": "t"}       # picture variant -> tile prefix on disk


def seed_templates(dyn_dir, flat_scale, world_scale, area):
    """Dynmap uses templates that already exist, so we set the map resolution there.
    Only the test area is rendered (area is x0, z0, x1, z1): the server also generates chunks around it."""
    tdir = dyn_dir + "/templates"
    os.makedirs(tdir, exist_ok=True)
    for f in glob.glob(f"{TEMPLATES}/*.txt"):
        t = re.sub(r"iso_S_90_\w+", f"iso_S_90_{flat_scale}", open(f).read())
        t = re.sub(r"(iso_SE_\d+_)\w+", rf"\g<1>{world_scale}", t)
        t = re.sub(r"(?m)^(    extrazoomout:.*)$",
                   rf"\g<1>\n    hidestyle: air\n    visibilitylimits:\n      - x0: {area[0]}\n        z0: {area[1]}\n"
                   rf"        x1: {area[2]}\n        z1: {area[3]}", t)
        open(os.path.join(tdir, os.path.basename(f)), "w").write(t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", default="spigot", choices=["spigot", "fabric", "forge"])
    ap.add_argument("--version", required=True)
    ap.add_argument("--mode", default="delta", choices=["delta", "full"])
    ap.add_argument("--jar", required=True, help="Dynmap jar of the platform")
    ap.add_argument("--out", default="render-out")
    ap.add_argument("--java", default=os.environ.get("JAVA", "java"))
    ap.add_argument("--mem", default="3G")
    ap.add_argument("--work", default=os.path.join(HERE, ".work"))
    ap.add_argument("--flat-scale", default="hires")
    ap.add_argument("--world-scale", default="hires", help="map resolution of the world map (medres is ~4x faster)")
    ap.add_argument("--variants", default="flat,world")
    ap.add_argument("--loader", default="", help="fabric: loader version (default: latest stable)")
    ap.add_argument("--api", default="", help="fabric: Fabric API version (default: latest for the Minecraft version)")
    a = ap.parse_args()
    v = a.version
    world_scale = a.world_scale
    variants = a.variants.split(",")
    fy = floor_y(v)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    failures, notes = [], []

    selected, cur = select_states(v, a.mode)
    canary = canary_states(cur)
    in_canary = set(canary)
    states = canary + [s for s in selected if s not in in_canary]
    bcmds, width, zb = block_commands(states, fy)
    biomes = load_biomes(v)
    biocmds, zend = biome_commands(biomes, zb + 8, fy, cur) if biomes else ([], zb)
    if not biomes:
        notes.append("no biome list for this version: biome strip skipped")
    extent = M + max(width, BIOME_COLS * SIZE_BIOME[0] if biomes else 0) + M
    zend += M - ORIGIN   # from here on zend is the depth of the area, the commands use the absolute z
    extent, zend = -(-extent // 16) * 16, -(-zend // 16) * 16   # whole chunks, so the floor leaves no strip of grass
    print(f"{v} {a.mode}: {len(selected)} selected + {len(canary)} canary states, {len(biomes)} biomes, "
          f"area {extent} x {zend}", flush=True)

    rdir = os.path.join(os.path.abspath(a.work), f"{a.platform}-{v}")
    shutil.rmtree(rdir, ignore_errors=True)
    cache = os.path.join(HERE, ".cache")
    if a.platform == "forge":
        inst, fargs = get_forge(v, a.java, cache)
        shutil.copytree(inst, rdir)
        jvm = open(rdir + "/user_jvm_args.txt").read() if os.path.exists(rdir + "/user_jvm_args.txt") else ""
        open(rdir + "/user_jvm_args.txt", "w").write(re.sub(r"(?m)^\s*#.*$", "", jvm) + f"\n-Xmx{a.mem}\n")
        cmd = [a.java] + fargs + ["nogui"]
    else:
        os.makedirs(rdir)
        cmd = [a.java, f"-Xmx{a.mem}", "-jar", "server.jar", "nogui"]
    dyn = rdir + ("/plugins/dynmap" if a.platform == "spigot" else "/dynmap")
    os.makedirs(dyn, exist_ok=True)
    os.makedirs(rdir + ("/plugins" if a.platform == "spigot" else "/mods"), exist_ok=True)
    open(rdir + "/eula.txt", "w").write("eula=true\n")
    open(rdir + "/server.properties", "w").write(
        f"online-mode=false\nlevel-type={level_type(v)}\ngenerate-structures=false\nlevel-seed=93026\n"
        "spawn-monsters=false\nspawn-animals=false\nspawn-npcs=false\nallow-nether=false\n"
        "view-distance=4\nsimulation-distance=2\nmax-tick-time=-1\nspawn-protection=0\nenable-rcon=false\n"
        "pause-when-empty-seconds=-1\n")   # an empty vanilla server stops ticking and the Dynmap render stalls
    seed_templates(dyn, a.flat_scale, world_scale, (ORIGIN, ORIGIN, ORIGIN + extent - 1, ORIGIN + zend - 1))
    if a.platform == "spigot":
        shutil.copy(get_paper(v, cache), rdir + "/server.jar")
        shutil.copy(a.jar, rdir + "/plugins/")
    elif a.platform == "fabric":
        launcher, apijar = get_fabric(v, a.loader, a.api, cache)
        shutil.copy(launcher, rdir + "/server.jar")
        shutil.copy(apijar, rdir + "/mods/")
        shutil.copy(a.jar, rdir + "/mods/")
    else:
        shutil.copy(a.jar, rdir + "/mods/")

    srv = Server(rdir, cmd)
    rendered = []
    try:
        if not srv.wait(r"Done \(", 420):
            failures.append("server did not start")
            raise RuntimeError("start")
        time.sleep(3)
        for rule, val in gamerules(v):
            srv.cmd(f"gamerule {rule} {val}")
        srv.cmd("dynmap pause update")   # only the radiusrender below should render anything
        srv.cmd("time set noon")
        srv.cmd("weather clear")
        for zs in range(0, zend, 128):   # at most 256 chunks per command
            srv.cmd(f"forceload add {ORIGIN} {ORIGIN + zs} {ORIGIN + extent - 1} {ORIGIN + min(zs + 127, zend - 1)}")
        srv.flush()

        loaded = False
        corners = [(ORIGIN + x, ORIGIN + z) for x in (0, extent - 1) for z in (0, zend - 1)]
        for _ in range(120):
            m = srv.mark()
            for cx, cz in corners:
                srv.cmd(f"setblock {cx} {fy} {cz} minecraft:stone")
            srv.flush()
            time.sleep(3)
            t = srv.text(m)
            if "not loaded" not in t and len(re.findall(r"Changed the block|Could not set the block", t)) == 4:
                loaded = True
                break
        if not loaded:
            failures.append("chunks of the test area did not load")
            raise RuntimeError("load")
        time.sleep(5)
        srv.cmd(f"gamerule {feedback_rule(v)} false")

        for zs in range(0, zend, 100):
            srv.cmd(f"fill {ORIGIN} {fy} {ORIGIN + zs} {ORIGIN + extent - 1} {fy} "
                    f"{ORIGIN + min(zs + 99, zend - 1)} minecraft:stone")
        mark = srv.mark()
        for c in biocmds + bcmds:
            srv.cmd(c)
        srv.cmd("say PLACED")
        srv.flush()
        if not srv.wait(r"\[Server\] PLACED", 900, mark):
            failures.append("placing the blocks did not finish")
            raise RuntimeError("place")
        t = srv.text(mark)
        if "not loaded" in t:
            failures.append("some blocks were placed outside loaded chunks")
        # blocks from experimental feature packs are in the snapshot but a default server lacks them: a note, not a failure
        unknown = sorted(set(re.findall(r"Unknown block type '([^']+)'", t)))
        if unknown:
            notes.append(f"server does not know {len(unknown)} blocks of the snapshot (not placed): {', '.join(unknown)}")
        if re.search(r"Expected", t):
            failures.append("server rejected a block state (snapshot does not match this server?)")
        if "Unknown or incomplete command" in t and biocmds:
            notes.append("server has no /fillbiome: biome strip is not tinted per biome")
        time.sleep(5)

        r = int(math.hypot(extent // 2, zend // 2)) + 16
        cx, cz = ORIGIN + extent // 2, ORIGIN + zend // 2
        for variant in variants:
            mp = MAPS[variant]
            mark = srv.mark()
            srv.cmd(f"dynmap radiusrender world {cx} {cz} {r} {mp}")
            srv.flush()
            if srv.wait(r"render of map.*completed|Render of .* completed", 3600, mark):
                rendered.append(variant)
            else:
                failures.append(f"render of map {mp} did not complete")
        time.sleep(5)

        try:
            cfg = json.loads(http_get("http://127.0.0.1:8123/up/configuration", 10))
            if not cfg.get("worlds"):
                failures.append("dynmap web: no worlds in /up/configuration")
        except Exception as e:
            failures.append(f"dynmap web server unreachable: {e}")
    except RuntimeError:
        pass
    finally:
        srv.stop()
        shutil.copy(srv.log, out + "/console.log")

    log = open(out + "/console.log", errors="replace").read()
    if re.search(r"^\s+at org\.dynmap\.", log, re.M):
        failures.append("exception from org.dynmap in the server log")
    tiles = glob.glob(rdir + "/**/tiles/world", recursive=True)
    suffix = "-full" if a.mode == "full" else ""
    pictures = {}
    for variant in rendered:
        if not tiles:
            failures.append("no tiles directory")
            break
        name = f"{a.platform}-{v}{suffix}-{variant}.png"
        try:
            n, img = stitch(tiles[0], PREFIX[variant], f"{out}/{name}")
        except SystemExit as e:
            failures.append(str(e))
            continue
        few = img.convert("RGB").getcolors(maxcolors=64)   # None means more than 64 colours
        if few is not None and len(few) < 8:
            failures.append(f"{name} has almost no colours: nothing rendered?")
        pictures[name] = {"tiles": n, "size": list(img.size)}
        print(f"{name}: {n} tiles {img.size}", flush=True)

    summary = {"platform": a.platform, "version": v, "mode": a.mode, "states": len(states), "canary": len(canary),
               "biomes": len(biomes), "pictures": pictures, "notes": notes, "failures": failures}
    json.dump(summary, open(out + "/summary.json", "w"), indent=1)
    shutil.rmtree(rdir, ignore_errors=True)
    print("notes:", notes)
    print("FAILED:" if failures else "OK", failures if failures else "")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
