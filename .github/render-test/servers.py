"""Download and run the Minecraft servers (Paper, Fabric, Forge) used by the test."""
import json, os, re, shutil, subprocess, sys, time, urllib.parse, urllib.request


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "dynmap-render-test"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_paper(v, cache):
    dest = f"{cache}/paper-{v}.jar"
    if os.path.exists(dest):
        return dest
    os.makedirs(cache, exist_ok=True)
    try:
        builds = json.loads(http_get(f"https://fill.papermc.io/v3/projects/paper/versions/{v}/builds"))
        builds = [b for b in builds if b.get("channel") in ("STABLE", "RECOMMENDED")] or builds
        url = builds[0]["downloads"]["server:default"]["url"]
    except Exception:
        b = json.loads(http_get(f"https://api.papermc.io/v2/projects/paper/versions/{v}/builds"))["builds"][-1]["build"]
        url = f"https://api.papermc.io/v2/projects/paper/versions/{v}/builds/{b}/downloads/paper-{v}-{b}.jar"
    with open(dest + ".part", "wb") as f:
        f.write(http_get(url, 300))
    os.rename(dest + ".part", dest)
    return dest


def download(url, dest, timeout=600):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest + ".part", "wb") as f:
        f.write(http_get(url, timeout))
    os.rename(dest + ".part", dest)
    return dest


def get_fabric(v, loader, api, cache):
    """Fabric server launcher and the Fabric API jar that the Dynmap mod needs.
    loader / api: versions to use (the ones the module is built with). Empty means the latest."""
    meta = "https://meta.fabricmc.net/v2/versions"
    if not loader:
        loaders = json.loads(http_get(f"{meta}/loader/{v}"))
        loader = next(x for x in loaders if x["loader"]["stable"])["loader"]["version"]
    installer = next(x for x in json.loads(http_get(f"{meta}/installer")) if x["stable"])["version"]
    launcher = f"{cache}/fabric-{v}-{loader}-{installer}.jar"
    if not os.path.exists(launcher):
        download(f"{meta}/loader/{v}/{loader}/{installer}/server/jar", launcher)
    # Maven only has a stub (a few KB) for the Fabric API of old versions, so the real jar comes from Modrinth
    # a pinned API version may not list this Minecraft version (a 1.21.9 build used on 1.21.10), so no game filter then
    q = urllib.parse.urlencode({"loaders": '["fabric"]', **({} if api else {"game_versions": json.dumps([v])})})
    vers = json.loads(http_get(f"https://api.modrinth.com/v2/project/fabric-api/version?{q}"))
    ver = next((x for x in vers if x["version_number"] == api), None) if api else vers[0]
    if ver is None:
        sys.exit(f"Fabric API {api} not found on Modrinth for {v}")
    apijar = f"{cache}/fabric-api-{ver['version_number']}.jar"
    if not os.path.exists(apijar) or os.path.getsize(apijar) < 100_000:
        f = next((x for x in ver["files"] if x["primary"]), ver["files"][0])
        download(f["url"], apijar)
    return launcher, apijar


def get_forge(v, java, cache):
    """Installed Forge server directory (cached). Returns the directory and the launch command without java."""
    promos = json.loads(http_get("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"))
    fv = promos["promos"].get(f"{v}-latest") or promos["promos"][f"{v}-recommended"]
    full = f"{v}-{fv}"
    inst = f"{cache}/forge-{full}-server"
    if not os.path.isdir(inst):
        jar = f"{cache}/forge-{full}-installer.jar"
        if not os.path.exists(jar):
            download(f"https://maven.minecraftforge.net/net/minecraftforge/forge/{full}/forge-{full}-installer.jar", jar)
        tmp = inst + ".part"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        r = subprocess.run([java, "-jar", jar, "--installServer"], cwd=tmp, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(tmp + "/run.sh"):
            sys.exit(f"forge installer failed for {full}:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
        os.rename(tmp, inst)
    line = next(l for l in open(inst + "/run.sh") if l.lstrip().startswith("java ") and "unix_args.txt" in l)
    args = [a for a in line.split()[1:] if a != '"$@"']
    return inst, args


# the log says Dynmap did not start: the server would sit there until the timeout otherwise
BROKEN = re.compile(r"Error occurred while enabling dynmap[^\n]*|Cannot execute command 'dynmap'[^\n]*"
                    r"|\[PluginRemapper\] Encountered exception[^\n]*|Unknown or incomplete command[^\n]*\n[^\n]*dynmap[^\n]*")


class Server:
    def __init__(self, rdir, cmd):
        self.log = rdir + "/console.log"
        self.proc = subprocess.Popen(cmd, cwd=rdir,
                                     stdin=subprocess.PIPE, stdout=open(self.log, "w"),
                                     stderr=subprocess.STDOUT, text=True)

    def text(self, since=0):
        try:
            return open(self.log, errors="replace").read()[since:]
        except FileNotFoundError:
            return ""

    def mark(self):
        return len(self.text())

    def cmd(self, c):
        self.proc.stdin.write(c + "\n")

    def flush(self):
        self.proc.stdin.flush()

    def problem(self, since=0):
        """The first line of the log that says Dynmap is not running, or None."""
        m = BROKEN.search(self.text(since))
        return m.group(0).strip() if m else None

    def wait(self, pattern, timeout, since=0, stall=0):
        """True when the pattern shows up in the log. False on timeout, when the server exits, when the log says
        Dynmap is broken (see self.why) or when the log does not grow for `stall` seconds (0: no check)."""
        rx, end = re.compile(pattern), time.time() + timeout
        size, moved = -1, time.time()
        self.why = ""
        while time.time() < end:
            text = self.text(since)
            if rx.search(text):
                return True
            m = BROKEN.search(text)
            if m:
                self.why = "Dynmap is not running: " + m.group(0).strip()
                return False
            if self.proc.poll() is not None:
                self.why = "server exited"
                return False
            if len(text) != size:
                size, moved = len(text), time.time()
            elif stall and time.time() - moved > stall:
                self.why = f"nothing in the log for {stall} seconds"
                return False
            time.sleep(1)
        self.why = "timeout"
        return False

    def stop(self):
        if self.proc.poll() is None:
            try:
                self.cmd("stop")
                self.flush()
                self.proc.wait(timeout=120)
            except Exception:
                self.proc.kill()
