#!/usr/bin/env python3
"""Upstream's factory presets (vst/presets/factory.toml, from idlefoundry/ca-72's crates/ca72-plugin/sounds/presets.toml)
as this port's presets: each one the whole panel, upstream's defaults where a preset names no value.

    tools/presets.py json            -> vst/presets.json (the wrapper's PRESET menu, tools/gen_vst.py "presets")
                                        and vst/presets/factory.json (every value, for the .xpl files)
    tools/presets.py xpl <skin dir>  -> <skin dir>/Presets/NNNN-<name>.xpl (MPC's own preset files, one per preset)

Upstream's POLY and UNISON become MODE, its DOUBLE switch PLAYED AS; LOCK (oscillators identical) is left out."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VST = os.path.join(HERE, "..", "vst")
IGNORED = {"lock"}


def params():
    return json.load(open(os.path.join(VST, "params.json")))["params"]


def presets():
    """[(name, {key: value})], values in this port's units (an option as its index)."""
    ps = params()
    keys = {p["key"] for p in ps}
    out = []
    import tomllib
    for pr in tomllib.load(open(os.path.join(VST, "presets", "factory.toml"), "rb"))["preset"]:
        v = {p["key"]: (p["options"].index(p["default"]) if "options" in p else p["default"]) for p in ps}
        src = dict(pr["values"])
        mode = 2 if src.pop("unison", 0) else (1 if src.pop("poly", 0) else 0)
        src.pop("poly", None)
        v["mode"] = mode
        v["played_as"] = 1 if src.pop("doubled", 0) else 0
        # (Upstream's FEEDBACK is always cabled; here PATCH plugs the cable in.)
        v["patch"] = 1 if src.get("feedback", 0) else 0
        for k, x in src.items():
            if k in IGNORED:
                continue
            if k not in keys:
                sys.exit("preset %r: unknown key %r" % (pr["name"], k))
            v[k] = x
        out.append((pr["name"], v))
    return out


def write_json():
    ps = {p["key"]: p for p in params()}
    rows = []
    for name, v in presets():
        rows.append({"name": name, "values": {k: (ps[k]["options"][int(x)] if "options" in ps[k] else x)
                                               for k, x in v.items() if k != "auto_db" and not k.startswith("dot_")}})
    json.dump({"presets": rows}, open(os.path.join(VST, "presets.json"), "w"), indent=1)
    # (The build's step that writes the .xpl files runs where Python may have no tomllib.)
    json.dump([[n, v] for n, v in presets()], open(os.path.join(VST, "presets", "factory.json"), "w"), indent=1)


def write_xpl(skin):
    sys.path.insert(0, os.environ.get("MPC_VST_TOOLS", os.path.join(HERE, "..", "..", "mpc-vst-plugins", "tools")))
    import xpl
    cfg = json.load(open(os.path.join(VST, "vst.json")))
    so_path = "%%payload-path%%/%s - VST - %s/%s" % (cfg["vendor"], cfg["name"], cfg["so"])
    uid = int.from_bytes(cfg["uid"].encode(), "big")
    os.makedirs(os.path.join(skin, "Presets"), exist_ok=True)
    for i, (name, v) in enumerate(json.load(open(os.path.join(VST, "presets", "factory.json"))), 1):
        state = ";".join("%s=%s" % (k, x) for k, x in v.items()).encode() + b"\0"
        fn = os.path.join(skin, "Presets", "%04d-%s.xpl" % (i, name))
        with open(fn, "w", encoding="utf-8") as f:
            f.write(xpl.xpl(cfg["name"], cfg["vendor"], so_path, uid, cfg.get("version", 1000), state, preset=name))


if __name__ == "__main__":
    if sys.argv[1:2] == ["json"]:
        write_json()
    elif sys.argv[1:2] == ["xpl"] and len(sys.argv) == 3:
        write_xpl(sys.argv[2])
    else:
        sys.exit(__doc__)
