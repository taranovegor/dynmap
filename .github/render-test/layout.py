"""What goes into the test world: which block states to render, and the commands that place them."""
import glob, itertools, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS = os.path.join(HERE, "snapshots")
SPACING = 2             # one block state per 2x2 cells so neighbours do not connect
M = 16                  # margin around everything, inside the loaded chunks
SIZE_BIOME = (20, 12)   # x and z size of one biome cell
BIOME_COLS = 10

# blocks that hold or spread fluid: they go to a section where every cell is walled in with stone
FLUID_BLOCKS = {"minecraft:water", "minecraft:lava", "minecraft:bubble_column", "minecraft:kelp",
                "minecraft:kelp_plant", "minecraft:seagrass", "minecraft:tall_seagrass", "minecraft:frosted_ice"}
# properties that do not change how a block looks: only these values are rendered and compared between versions,
# so a version that adds a note block instrument does not add 1350 note_block states to the delta
RENDERED_VALUES = {
    "minecraft:note_block": {"instrument": ["harp"], "note": ["0"]},
    "minecraft:redstone_wire": {"power": ["0", "8", "15"]},
}
BIOME_ITEMS = ["grass_block", "short_grass", "fern", "oak_leaves", "birch_leaves", "spruce_leaves", "jungle_leaves",
               "acacia_leaves", "dark_oak_leaves", "mangrove_leaves", "sugar_cane", "oak_sapling"]


def vtuple(v):
    return tuple(int(x) for x in v.split("."))


# ---- what differs between Minecraft versions -------------------------------------------------------------
def floor_y(v):         # top layer of the default flat world
    return -61 if vtuple(v) >= (1, 18) else 3


def level_type(v):
    return "minecraft:flat" if vtuple(v) >= (1, 19) else "flat"


def gamerules(v):
    if vtuple(v) >= (1, 21, 11):
        names = ["advance_time", "advance_weather", "block_drops", "log_admin_commands", "random_tick_speed",
                 "spawn_mobs", "mob_griefing"]
    else:
        names = ["doDaylightCycle", "doWeatherCycle", "doTileDrops", "logAdminCommands", "randomTickSpeed",
                 "doMobSpawning", "mobGriefing"]
    values = ["false", "false", "false", "false", "0", "false", "false"]
    return list(zip(names, values))


def feedback_rule(v):
    return "send_command_feedback" if vtuple(v) >= (1, 21, 11) else "sendCommandFeedback"


# ---- snapshots -------------------------------------------------------------------------------------------
def snapshot_versions():
    return sorted((os.path.basename(f)[:-4] for f in glob.glob(f"{SNAPSHOTS}/*.txt") if "biomes" not in f),
                  key=vtuple)


def load_snapshot(v):
    blocks = {}
    for line in open(f"{SNAPSHOTS}/{v}.txt"):
        parts = line.split()
        blocks[parts[0]] = [(p.split("=")[0], p.split("=")[1].split("|")) for p in parts[1:]]
    return blocks


def load_biomes(v):
    f = f"{SNAPSHOTS}/{v}.biomes.txt"
    return [l.strip() for l in open(f) if l.strip()] if os.path.exists(f) else []


def reduced(blocks):
    """Snapshot without the property values that make no difference in the picture (see RENDERED_VALUES)."""
    out = {}
    for name, props in blocks.items():
        keep = RENDERED_VALUES.get(name, {})
        out[name] = [(k, [x for x in vals if x in keep[k]] or vals[:1] if k in keep else vals) for k, vals in props]
    return out


def expand(name, props):
    if not props:
        return [name]
    keys = [k for k, _ in props]
    return [f"{name}[{','.join(f'{k}={x}' for k, x in zip(keys, combo))}]"
            for combo in itertools.product(*[vals for _, vals in props])]


def changed_blocks(v):
    out = set()
    for line in open(os.path.join(HERE, "changed.txt")):
        line = line.split("#")[0].split()
        if len(line) == 2 and line[0] == v:
            out.add(line[1])
    return out


def select_states(v, mode):
    cur = load_snapshot(v)
    red = reduced(cur)
    versions = snapshot_versions()
    idx = versions.index(v)
    if mode == "full" or idx == 0:
        names = set(red)
    else:
        prev = reduced(load_snapshot(versions[idx - 1]))
        names = {n for n in red if n not in prev or prev[n] != red[n]}
        names |= {n for n in changed_blocks(v) if n in red}
    return [s for n in sorted(names) for s in expand(n, red[n])], cur


def canary_states(cur):
    out = []
    for line in open(os.path.join(HERE, "canary.txt")):
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, _, rest = line.partition("[")
        if name not in cur:
            continue
        given = dict(p.split("=") for p in rest.rstrip("]").split(",") if p)
        schema = dict(cur[name])
        if all(k in schema and v in schema[k] for k, v in given.items()):
            out.append(line)
    return out


# ---- layout ----------------------------------------------------------------------------------------------
def is_wet(state):
    return state.split("[")[0] in FLUID_BLOCKS or "waterlogged=true" in state


def grid(states, z0, walled, fy):
    side = max(1, math.ceil(math.sqrt(len(states))))
    width, depth = side * SPACING, max(1, math.ceil(len(states) / side)) * SPACING
    cmds = []
    if walled and states:
        for zs in range(z0 - 2, z0 + depth + 2, 100):
            cmds.append(f"fill {M - 2} {fy + 1} {zs} {M + width + 1} {fy + 1} {min(zs + 99, z0 + depth + 1)} "
                        f"minecraft:stone")
    for i, s in enumerate(states):
        cmds.append(f"setblock {M + (i % side) * SPACING} {fy + 1} {z0 + (i // side) * SPACING} {s} replace")
    return cmds, (width if states else 0), z0 + (depth if states else 0)


def block_commands(states, fy):
    dry = [s for s in states if not is_wet(s)]
    wet = [s for s in states if is_wet(s)]
    c1, w1, z1 = grid(dry, M, False, fy)
    c2, w2, z2 = grid(wet, z1 + 8, True, fy)
    return c1 + c2, max(w1, w2), z2


def biome_commands(biomes, z0, fy, cur):
    items = [i for i in BIOME_ITEMS if f"minecraft:{i}" in cur]
    cmds = []
    for i, b in enumerate(biomes):
        bx, bz = M + (i % BIOME_COLS) * SIZE_BIOME[0], z0 + (i // BIOME_COLS) * SIZE_BIOME[1]
        cmds.append(f"fillbiome {bx} {fy - 3} {bz} {bx + SIZE_BIOME[0] - 1} {fy + 20} {bz + SIZE_BIOME[1] - 1} {b}")
        for j, item in enumerate(items):
            cmds.append(f"setblock {bx + (j % 10) * 2} {fy + 1} {bz + (j // 10) * 2} minecraft:{item} replace")
        cmds.append(f"fill {bx} {fy + 1} {bz + 5} {bx + 4} {fy + 1} {bz + 9} minecraft:stone")
        cmds.append(f"fill {bx + 1} {fy + 1} {bz + 6} {bx + 3} {fy + 1} {bz + 8} minecraft:water")
    return cmds, z0 + math.ceil(len(biomes) / BIOME_COLS) * SIZE_BIOME[1]
