# ---------------------------------------------------------------- git

def git(ordner, *a, check=True):
    r = subprocess.run(["git", "-C", ordner, *a], capture_output=True,
                       text=True, errors="replace")
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, a, r.stdout, r.stderr)
    return r.stdout if r.returncode == 0 else None

def zerlegen(diff):
    """Unified-Diff in Dateien → Hunks → Zeilen zerlegen."""
    dateien, d, h = [], None, None
    for z in diff.splitlines():
        if z.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)", z)
            d = {"alt": m.group(1), "neu": m.group(2), "hunks": [], "binaer": False,
                 "status": "geändert", "plus": 0, "minus": 0}
            dateien.append(d); h = None
        elif d is None:
            continue
        elif h is None and z.startswith("new file"): d["status"] = "neu"
        elif h is None and z.startswith("deleted file"): d["status"] = "gelöscht"
        elif h is None and z.startswith("rename from"): d["status"] = "umbenannt"
        elif h is None and z.startswith("Binary files"): d["binaer"] = True
        elif z.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", z)
            h = {"a": int(m.group(1)), "b": int(m.group(2)), "kopf": m.group(3).strip(), "z": []}
            d["hunks"].append(h)
        elif h is not None and z[:1] in (" ", "+", "-"):
            h["z"].append((z[0], z[1:]))
            if z[0] == "+": d["plus"] += 1
            if z[0] == "-": d["minus"] += 1
    return dateien

