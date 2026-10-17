# Render test

Starts a real server with the built Dynmap jar, places a grid of blocks and biomes in a flat world, renders it
and stitches the tiles into one picture per map. A person looks at the pictures. The job fails only if the
server, the web server or the renderer is broken.

```
python3 .github/render-test/render_test.py --version 1.21.11 --mode delta --jar target/Dynmap-<ver>-spigot.jar --out out
```

Output: `<platform>-<version>[-full]-<flat|world>.png`, `console.log` and `summary.json`.
You need Python 3 with Pillow, and a JDK that matches the Minecraft version (`--java`).

## What is rendered

- `canary.txt` and the biome strip: always.
- `--mode delta`: blocks that are new or got different properties since the previous snapshot, plus the blocks
  listed for the version in `changed.txt`. The oldest snapshot has no previous one, so it is rendered in full.
- `--mode full`: every state of every block in the version.

Some properties do not change how a block looks (note block instrument and note, redstone power). Only a few of
their values are rendered, see `RENDERED_VALUES` in `layout.py`. A change in these values does not count as a
change between versions.

Each block state gets a 2x2 area, so states never touch each other. States with water or lava go to a separate
section where every cell is walled in with stone, so the fluid cannot spread.

## Adding a Minecraft version

1. Run `python3 .github/render-test/snapshot.py <version>` and commit the new files in `snapshots/`.
2. If a block looks different in this version but its properties are the same (new texture or model), add a
   line `<version> <block id>` to `changed.txt`.

Snapshots come from the vanilla server's own data generator. Biome lists exist from 1.19.3. Older versions skip the
biome strip.
