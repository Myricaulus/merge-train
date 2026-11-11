"""Die beiden Quellen der Waggons – Lokal (Branches im Klon) und GitLab (Merge-Requests) – und was sie können."""
import json, re, subprocess
from datetime import datetime
from .einstellungen import ARBEITSSTAND, BIS, KONF, RUNDE, SPERRE, VON, dateiname, melden, projektname
from .waggon import Fehler, Waggon, fertig_moeglich
from .git import arbeitsstand, branch_von, finde_repos, git, projekt_wurzel, statistik
from .akte import akte_lesen, ausstehend, faeden_archivieren, faeden_zaehlen, review_kommentare, struktur_laden
from .gitlab import mr_liste, mr_ref
from .seite import mr_seite, projekt_seite

def runde_laden():
    try:
        r = json.load(open(RUNDE))
    except (FileNotFoundError, ValueError):
        r = {}
    heute = datetime.now().strftime("%Y-%m-%d")
    return {p: w for p, w in r.items() if w.get("tag") == heute}


def lokal_wagen(stats, wurzeln=None):
    """Lokale Waggons: offene Projekte + heute fertig gewordene (sofern seitdem nichts Neues kam), absteigend nach Umfang.
    wurzeln: {projekt: Klon} für den Branch der Fäden."""
    wurzeln = wurzeln or {}
    fertig = runde_laden()
    wagen = [w for w in stats if w["dateien"]]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    for w in wagen:  # Gespräch: offene Fäden / neue Antworten des Agenten
        wurzel = wurzeln.get(w["p"])
        w["gs"], w["gs_neu"] = faeden_zaehlen(Waggon(lokal=w["p"]), branch_von(wurzel) if wurzel else None)
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
    if not fertig_moeglich():
        return False, f"„fertig“ geht nur mit lokalen Branches (von = {VON}, bis = {BIS})."
    if git(wurzel, "merge-base", "--is-ancestor", VON, sha, check=False) is None:
        return False, f"{projekt}: {VON} ist nicht Vorgänger des gesehenen Stands – nichts geändert."
    akte = statistik(wurzel, VON, sha)
    log = git(wurzel, "log", "--format=%B", f"{VON}..{sha}")
    schliesst = sorted(set(re.findall(r"closes\s+todo:([\w.-]+)", log, flags=re.I)))
    git(wurzel, "branch", "-f", VON, sha)
    faeden_archivieren(Waggon(lokal=projekt), branch_von(wurzel))
    with SPERRE:
        r = runde_laden()
        r[projekt] = dict(akte, p=projekt, datei=dateiname(projekt), status="fertig", tag=datetime.now().strftime("%Y-%m-%d"))
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
        akte = akte_lesen(mr)
        n = sum(1 for k in review_kommentare(akte) if not k.get("geloescht"))
        fertig = bool(akte.get("abgeschlossen")) and not ausstehend(akte)
        kurz = mr.projekt.rsplit("/", 1)[-1]
        return {"p": mr.id, "name": f'!{mr.iid} {kurz}', "titel": f'{mr.projekt}!{mr.iid}: {titel}',
                "zeile2": titel, "datei": mr.url, "plus": 0, "minus": 0, "dateien": aenderungen or 0,
                "commits": 0, "todos": [], "status": "fertig" if fertig else "offen",
                "marke": "✓ in GitLab" if fertig else (f"● {n} Komm." if n else "● offen")}
    for it in items:
        try:
            mr = mr_ref(it.get("web_url", ""))
        except Fehler:
            continue
        gesehen.add(mr.id)
        wagen.append(wagen_fuer(mr, it.get("title", ""), it.get("changes_count")))
    if akt and akt not in gesehen:
        try:
            mr = Waggon.aus_id(akt)
            if not mr.lokal:
                wagen.insert(0, wagen_fuer(mr, akte_lesen(mr)["mr"].get("titel", ""), 0))
        except Fehler:
            pass
    return wagen


# Quellen der Waggons: die lokalen Branches (BIS gegen VON in jedem Repo unter „projekte“) und GitLab-MRs; eine
# GitHub-Quelle wäre eine weitere Klasse. Der Zug mischt die Waggons aller eingeschalteten Quellen. Eine Quelle weiß,
# wo der Klon und Stand eines Waggons liegt (ort), baut seine Seite (seite), zählt ihre Waggons auf (wagen) und sagt
# dem Agenten, was zu tun ist (prompt). Was ein Waggon kann, steht am Waggon selbst (waggon.py).

class Lokal:
    name = "lokal"

    def an(self):
        return bool(KONF["lokal"])

    def ort(self, waggon):
        """(Klon, Stand), auf den sich Zeilen beziehen: der Branch BIS."""
        wurzel = projekt_wurzel(waggon.lokal)
        if BIS == ARBEITSSTAND:
            return wurzel, arbeitsstand(wurzel)
        head = (git(wurzel, "rev-parse", "--verify", "-q", BIS, check=False) or "").strip()
        if not head:
            raise Fehler(f"Branch {BIS} fehlt in {wurzel}")
        return wurzel, head

    def seite(self, waggon, ansicht=None):
        return projekt_seite(projekt_wurzel(waggon.lokal), ansicht=ansicht)

    def branch(self, waggon):
        """Branch der Fäden (branch_von); None, wenn es das Projekt nicht (mehr) gibt."""
        try:
            return branch_von(projekt_wurzel(waggon.lokal))
        except Fehler:
            return None

    def wagen(self, akt=None):
        from concurrent.futures import ThreadPoolExecutor
        repos = finde_repos()
        with ThreadPoolExecutor(8) as ex:
            return lokal_wagen(list(ex.map(statistik, repos)), {projektname(r): r for r in repos})

    def prompt(self, waggon, wurzel):
        wo = ("im Arbeitsverzeichnis umsetzen (nicht committen)" if BIS == ARBEITSSTAND else f"auf {BIS} umsetzen und committen")
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {waggon.lokal} (Diff {BIS} gegen {VON}). "
                f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche {wo}; "
                f"zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")


class GitLab:
    name = "gitlab"
    def an(self):
        return bool(KONF["gitlab"])

    def ort(self, waggon):
        """(Klon, Stand) des MR, wie ihn die Seite zuletzt gebaut hat."""
        struktur = struktur_laden(akte_lesen(waggon))
        if struktur is None:
            _, struktur = self.seite(waggon)
        return struktur["ordner"], struktur["refs"]["head_sha"]

    def seite(self, waggon, ansicht=None):
        pfad, struktur, _ = mr_seite(waggon, ansicht=ansicht)
        return pfad, struktur

    def branch(self, waggon):
        """Branch der Fäden: der Quell-Branch des MR."""
        return akte_lesen(waggon)["mr"].get("source_branch") or None

    def wagen(self, akt=None):
        return mr_wagen(akt)

    def prompt(self, waggon, wurzel):
        z = waggon.id
        return (f"In merge-train liegen Fragen des Nutzers zum Merge-Request {waggon.name} (lokaler Klon: {wurzel}). "
                f"Hol sie mit `merge-train agent feedback {z}` ab. Beantworte sie anhand des Codes im Klon; den MR nicht "
                f"ändern, nichts committen oder pushen. Zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten. "
                f"Danach mit `merge-train agent horchen {z}` (im Hintergrund, nach jeder Ausgabe neu) auf weitere Fragen warten.")


LOKAL, GITLAB = Lokal(), GitLab()


QUELLEN = (LOKAL, GITLAB)


def quelle(waggon):
    return LOKAL if waggon.lokal else GITLAB


def schluessel_von(sid):
    """Seiten-Kennung → Schlüssel des Waggons (prüft, ob die Quelle eingeschaltet ist)."""
    waggon = Waggon.aus_id(sid)
    if not quelle(waggon).an():
        raise Fehler(f"Quelle {quelle(waggon).name} ist abgeschaltet")
    return waggon


def alle_wagen(akt=None):
    """Der gemischte Zug: Waggons aller eingeschalteten Quellen, lokale zuerst."""
    wagen = []
    for q in QUELLEN:
        if q.an():
            for w in q.wagen(akt):
                wagen.append(dict(w, quelle=q.name))
    return wagen
