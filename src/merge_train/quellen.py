"""Die beiden Quellen der Waggons – Lokal (Branches im Klon) und GitLab (Merge-Requests) – und was sie können."""
import html, json, re, shlex, shutil, subprocess
from datetime import datetime
from .einstellungen import ARBEITSSTAND, BIS, KONF, RUNDE, SPERRE, VON, dateiname, melden, projektname
from .git import arbeitsstand, finde_repos, git, statistik
from .zustand import ausstehend, faeden_archivieren, faeden_zaehlen, review_laden, review_kommentare, struktur_laden
from .gitlab import GitLabFehler, mr_aus_id, mr_id, mr_liste, mr_ref
from .seite import mr_seite, projekt_seite

def runde_laden():
    try:
        r = json.load(open(RUNDE))
    except (FileNotFoundError, ValueError):
        r = {}
    heute = datetime.now().strftime("%Y-%m-%d")
    return {p: w for p, w in r.items() if w.get("tag") == heute}


def lokal_wagen(stats):
    """Lokale Waggons: offene Projekte + heute fertig gewordene (sofern seitdem nichts Neues kam), absteigend nach Umfang."""
    fertig = runde_laden()
    wagen = [w for w in stats if w["dateien"]]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    for w in wagen:  # Gespräch: offene Fäden / neue Antworten des Agenten
        w["gs"], w["gs_neu"] = faeden_zaehlen({"lokal": w["p"]})
        w["datei"] = "/" + dateiname(w["p"])
    return wagen


def fertig(projekt, sha):
    """VON auf den gesehenen Stand setzen (den Schlüssel prüft der Server). Rückgabe (ok, text)."""
    repos = {projektname(r): r for r in finde_repos()}
    if projekt not in repos:
        return False, f"Unbekanntes Projekt: {projekt}"
    wurzel = repos[projekt]
    if not re.fullmatch(r"[0-9a-f]{40}", sha or "") or git(wurzel, "cat-file", "-t", sha, check=False) != "commit\n":
        return False, "Abgelehnt: unbekannter Stand."
    if not LOKAL.kann["fertig"]:
        return False, f"„fertig“ geht nur mit lokalen Branches (von = {VON}, bis = {BIS})."
    if git(wurzel, "merge-base", "--is-ancestor", VON, sha, check=False) is None:
        return False, f"{projekt}: {VON} ist nicht Vorgänger des gesehenen Stands – nichts geändert."
    st = statistik(wurzel, VON, sha)
    log = git(wurzel, "log", "--format=%B", f"{VON}..{sha}")
    schliesst = sorted(set(re.findall(r"closes\s+todo:([\w.-]+)", log, flags=re.I)))
    git(wurzel, "branch", "-f", VON, sha)
    faeden_archivieren({"lokal": projekt})
    with SPERRE:
        r = runde_laden()
        r[projekt] = dict(st, p=projekt, datei=dateiname(projekt), status="fertig", tag=datetime.now().strftime("%Y-%m-%d"))
        with open(RUNDE, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    erledigt = []
    for t in schliesst:
        ok = subprocess.run(["todo", "erledigt", t, "-n", f"Merge-Request {projekt} angenommen ({sha[:8]})"],
                            cwd=wurzel, capture_output=True).returncode == 0
        erledigt.append(t + ("" if ok else " (Fehler)"))
    rest = git(wurzel, "rev-list", "--count", f"{sha}..{BIS}").strip()
    text = (f"{projekt}: {VON} → {sha[:8]}" + (f"\ntodos erledigt: {', '.join(erledigt)}" if erledigt else "")
            + (f"\nAchtung: {BIS} hat {rest} neuere Commit(s)" if rest != "0" else ""))
    melden(text)
    return True, text


def mr_wagen(akt=None):
    items, _ = mr_liste()
    wagen, gesehen = [], set()
    def wagen_fuer(mr, titel, aenderungen):
        st = review_laden(mr)
        n = sum(1 for k in review_kommentare(st) if not k.get("geloescht"))
        fertig = bool(st.get("abgeschlossen")) and not ausstehend(st)
        kurz = mr["projekt"].rsplit("/", 1)[-1]
        return {"p": mr_id(mr), "name": f'!{mr["iid"]} {kurz}', "titel": f'{mr["projekt"]}!{mr["iid"]}: {titel}',
                "zeile2": titel, "datei": "/mr/" + mr_id(mr), "plus": 0, "minus": 0, "dateien": aenderungen or 0,
                "commits": 0, "todos": [], "status": "fertig" if fertig else "offen",
                "marke": "✓ in GitLab" if fertig else (f"● {n} Komm." if n else "● offen")}
    for it in items:
        try:
            mr = mr_ref(it.get("web_url", ""))
        except GitLabFehler:
            continue
        gesehen.add(mr_id(mr))
        wagen.append(wagen_fuer(mr, it.get("title", ""), it.get("changes_count")))
    if akt and akt not in gesehen and not str(akt).startswith("projekt:"):
        try:
            mr = mr_aus_id(akt)
            wagen.insert(0, wagen_fuer(mr, review_laden(mr)["mr"].get("titel", ""), 0))
        except GitLabFehler:
            pass
    return wagen


# Ein Waggon ist ein Vergleich Quelle → Ziel in einem lokalen Klon. Quellen sind die lokalen Branches (BIS gegen VON in
# jedem Repo unter „projekte“) und GitLab-MRs; eine GitHub-Quelle wäre eine weitere Klasse. Der Zug mischt die Waggons
# aller eingeschalteten Quellen. Was ein Waggon kann, sagt seine Quelle (kann):
#   review    – Review-Kommentare und Agent-Hinweise, „Review abschließen“ überträgt sie nach außen
#   fertig    – „fertig ✓“ setzt den Ziel-Branch auf den gesehenen Stand
#   committen – der Agent darf Wünsche umsetzen und committen (sonst nur antworten)
# Das Gespräch mit Agenten gibt es überall. Schlüssel eines Waggons (g): {"lokal": projekt} bzw. {host, projekt, iid}.

class Lokal:
    name = "lokal"

    @property
    def kann(self):  # „fertig“ setzt den Branch von – nur bei lokalen Branches, nicht gegen origin/… oder den Arbeitsstand
        fertig = BIS != ARBEITSSTAND and not VON.startswith(("origin/", "refs/remotes/"))
        return {"review": False, "fertig": fertig, "committen": True}

    def an(self):
        return bool(KONF["lokal"])

    def passt(self, x):
        return bool(x.get("lokal")) if isinstance(x, dict) else str(x).startswith("projekt:")

    def name_von(self, g):
        return g["lokal"]

    def url(self, g):
        return "/" + dateiname(g["lokal"])

    def ort(self, g):
        """(Klon, Stand), auf den sich Zeilen beziehen: der Branch BIS."""
        wurzel = projekt_wurzel(g["lokal"])
        if not wurzel:
            raise GitLabFehler(f'Projekt {g["lokal"]} nicht gefunden')
        if BIS == ARBEITSSTAND:
            return wurzel, arbeitsstand(wurzel)
        head = (git(wurzel, "rev-parse", "--verify", "-q", BIS, check=False) or "").strip()
        if not head:
            raise GitLabFehler(f"Branch {BIS} fehlt in {wurzel}")
        return wurzel, head

    def seite(self, g, ansicht=None):
        wurzel = projekt_wurzel(g["lokal"])
        if not wurzel:
            raise GitLabFehler(f'Projekt {g["lokal"]} nicht gefunden')
        return projekt_seite(wurzel, ansicht=ansicht)

    def wagen(self, akt=None):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:
            return lokal_wagen(list(ex.map(statistik, finde_repos())))

    def leitstand(self):
        return '<button data-l="neu" title="Nach neuen lokalen Änderungen schauen">↻ Änderungen</button>'

    def prompt(self, g, wurzel):
        wo = ("im Arbeitsverzeichnis umsetzen (nicht committen)" if BIS == ARBEITSSTAND else f"auf {BIS} umsetzen und committen")
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {g['lokal']} (Diff {BIS} gegen {VON}). "
                f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche {wo}; "
                f"zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")


class GitLab:
    name = "gitlab"
    kann = {"review": True, "fertig": False, "committen": False}

    def an(self):
        return bool(KONF["gitlab"])

    def passt(self, x):
        return not LOKAL.passt(x)

    def name_von(self, g):
        return f'{g["projekt"]}!{g["iid"]}'

    def url(self, g):
        return "/mr/" + mr_id(g)

    def ort(self, g):
        """(Klon, Stand) des MR, wie ihn die Seite zuletzt gebaut hat."""
        with SPERRE:
            struktur = struktur_laden(review_laden(g))
        if struktur is None:
            _, struktur = self.seite(g)
        return struktur["ordner"], struktur["refs"]["head_sha"]

    def seite(self, g, ansicht=None):
        pfad, struktur, _ = mr_seite(g, ansicht=ansicht)
        return pfad, struktur

    def wagen(self, akt=None):
        return mr_wagen(akt)

    def leitstand(self):
        fehlt = not shutil.which((shlex.split(KONF["glab"]) or ["glab"])[0])
        def knopf(g, text, titel):  # ohne glab ausgegraut: der Bahnhof steht, aber es fährt nichts
            if fehlt:
                return f'<button data-g="{g}" disabled title="glab fehlt ({html.escape(KONF["glab"])}) – siehe README">{text}</button>'
            return f'<button data-g="{g}" title="{titel}">{text}</button>'
        return (knopf("mrliste", "↻ MRs", "MRs, bei denen ich Reviewer bin, aus GitLab holen")
                + knopf("mrdaten", "↻ MR-Daten", "Titel, Beschreibung, Branches und GitLab-Stand dieses MR neu holen"))

    def prompt(self, g, wurzel):
        z = mr_id(g)
        return (f"In merge-train liegen Fragen des Nutzers zum Merge-Request {self.name_von(g)} (lokaler Klon: {wurzel}). "
                f"Hol sie mit `merge-train agent feedback {z}` ab. Beantworte sie anhand des Codes im Klon; den MR nicht "
                f"ändern, nichts committen oder pushen. Zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten. "
                f"Danach mit `merge-train agent horchen {z}` (im Hintergrund, nach jeder Ausgabe neu) auf weitere Fragen warten.")


LOKAL, GITLAB = Lokal(), GitLab()


QUELLEN = (LOKAL, GITLAB)


def quelle(x):
    """Quelle zu einer Seiten-Kennung („projekt:name“, „host/gruppe/projekt/42“) oder einem Schlüssel."""
    return LOKAL if LOKAL.passt(x) else GITLAB


def schluessel_von(sid):
    """Seiten-Kennung → Schlüssel des Waggons (prüft, ob die Quelle eingeschaltet ist)."""
    g = mr_aus_id(sid)
    if not quelle(g).an():
        raise GitLabFehler(f"Quelle {quelle(g).name} ist abgeschaltet")
    return g


def alle_wagen(akt=None):
    """Der gemischte Zug: Waggons aller eingeschalteten Quellen, lokale zuerst."""
    wagen = []
    for q in QUELLEN:
        if q.an():
            for w in q.wagen(akt):
                wagen.append(dict(w, quelle=q.name))
    return wagen


def leitstand_html():
    return "".join(q.leitstand() for q in QUELLEN if q.an())


def projekt_wurzel(projekt):
    return next((r for r in finde_repos() if projektname(r) == projekt), None)
