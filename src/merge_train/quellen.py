"""Die beiden Quellen der Waggons – Lokal (Branches im Klon) und GitLab (Merge-Requests) – und was sie können."""
import json, re, subprocess
from datetime import datetime
from .einstellungen import ARBEITSSTAND, KONF, RUNDE, SPERRE, dateiname, melden, projektname
from .waggon import Fehler, Waggon, fertig_moeglich, von_bis, zweige_gewaehlt, zweige_standard
from .git import arbeitsstand, branch_von, fehlende_zweige, finde_repos, git, kurzpfad, projekt_wurzel, statistik
from .akte import (akte_bearbeiten, akte_lesen, ausstehend, diskussionen_stand, faeden_archivieren, faeden_zaehlen, in_gitlab,
                   review_kommentare, struktur_laden)
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
    wagen = [w for w in stats if w["dateien"] or w["status"] == "fehlt"]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    for w in wagen:  # Gespräch: offene Fäden / neue Antworten des Agenten
        wurzel = wurzeln.get(w["p"])
        w["gs"], w["gs_neu"] = faeden_zaehlen(Waggon(lokal=w["p"]), branch_von(wurzel) if wurzel else None)
        w["datei"] = "/" + dateiname(w["p"])
    return wagen


def fertig(projekt, sha):
    """von des Projekts auf den gesehenen Stand setzen (den Schlüssel prüft der Server). Rückgabe (ok, text)."""
    repos = {projektname(r): r for r in finde_repos()}
    if projekt not in repos:
        return False, f"Unbekanntes Projekt: {projekt}"
    wurzel = repos[projekt]
    if not re.fullmatch(r"[0-9a-f]{40}", sha or "") or git(wurzel, "cat-file", "-t", sha, check=False) != "commit\n":
        return False, "Abgelehnt: unbekannter Stand."
    von, bis = von_bis(projekt)
    if not fertig_moeglich(projekt):
        return False, f"„fertig“ geht nur mit lokalen Branches (von = {von}, bis = {bis})."
    if git(wurzel, "merge-base", "--is-ancestor", von, sha, check=False) is None:
        return False, f"{projekt}: {von} ist nicht Vorgänger des gesehenen Stands – nichts geändert."
    akte = statistik(wurzel, von, sha)
    log = git(wurzel, "log", "--format=%B", f"{von}..{sha}")
    schliesst = sorted(set(re.findall(r"closes\s+todo:([\w.-]+)", log, flags=re.I)))
    git(wurzel, "branch", "-f", von, sha)
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
    rest = git(wurzel, "rev-list", "--count", f"{sha}..{bis}").strip()
    text = (f"{projekt}: {von} → {sha[:8]}" + (f"\ntodos erledigt: {', '.join(erledigt)}" if erledigt else "")
            + (f"\nAchtung: {bis} hat {rest} neuere Commit(s)" if rest != "0" else ""))
    melden(text)
    return True, text


def stand_oder_fehlt(wurzel):
    """statistik; fehlt von oder bis im Klon, ein Waggon „⚠ fehlt“ – aufklappen und andere Zweige wählen."""
    fehlt = fehlende_zweige(wurzel)
    if not fehlt:
        return statistik(wurzel)
    p = projektname(wurzel)
    von, bis = von_bis(p)
    return {"p": p, "datei": dateiname(p), "plus": 0, "minus": 0, "dateien": 0, "commits": 0, "todos": [],
            "status": "fehlt", "sha": "", "zeile2": f"{bis} → {von}", "marke": "⚠ fehlt",
            "titel": f"{p}: {', '.join(fehlt)} fehlt im Klon – ▾ zum Einstellen"}


def projekt_einstellung(projekt):
    """Für den aufgeklappten Waggon: Projektinfos, von/bis (gewählt bzw. Standard) und die Branches zur Auswahl."""
    wurzel = projekt_wurzel(projekt)
    von, bis = von_bis(projekt)
    std_von, std_bis = zweige_standard(projekt)
    refs = (git(wurzel, "for-each-ref", "--sort=-committerdate", "--format=%(refname)", "refs/heads", "refs/remotes",
                check=False) or "").split()
    lokal = [r[len("refs/heads/"):] for r in refs if r.startswith("refs/heads/")]
    remote = [r[len("refs/remotes/"):] for r in refs if r.startswith("refs/remotes/") and not r.endswith("/HEAD")]
    fehlt = fehlende_zweige(wurzel)
    info = {"p": projekt, "ordner": kurzpfad(wurzel), "von": von, "bis": bis, "standard": {"von": std_von, "bis": std_bis},
            "gewaehlt": bool(zweige_gewaehlt(projekt)), "lokal": lokal, "remote": remote, "fehlt": fehlt,
            "ausgecheckt": (git(wurzel, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "").strip() or "(losgelöst)",
            "origin": (git(wurzel, "remote", "get-url", "origin", check=False) or "").strip(),
            "fertig": fertig_moeglich(projekt), "arbeitsstand": ARBEITSSTAND}
    if not fehlt:
        st = statistik(wurzel)
        info.update({k: st[k] for k in ("plus", "minus", "dateien", "commits")})
        letzter = (git(wurzel, "log", "-1", "--format=%h%x1f%cd%x1f%s", "--date=format:%d.%m. %H:%M",
                       "HEAD" if bis == ARBEITSSTAND else bis, check=False) or "").strip()
        if letzter:
            info["letzter"] = dict(zip(("sha", "zeit", "betreff"), letzter.split("\x1f", 2)))
    return info


def projekt_einstellen(projekt, von, bis):
    """von/bis eines lokalen Projekts auf der Seite wählen (in der Akte); gleich dem Standard bzw. leer = Standard."""
    wurzel = projekt_wurzel(projekt)
    std = zweige_standard(projekt)
    von, bis = (von or std[0]).strip(), (bis or std[1]).strip()
    fehlt = fehlende_zweige(wurzel, von, bis)
    if fehlt:
        return False, f"{projekt}: {', '.join(fehlt)} gibt es im Klon nicht"
    with akte_bearbeiten(Waggon(lokal=projekt)) as akte:
        if (von, bis) == std:
            akte.pop("zweige", None)
        else:
            akte["zweige"] = {"von": von, "bis": bis}
    return True, f"{projekt}: {bis} → {von}" + (" (Standard)" if (von, bis) == std else "")


def mr_wagen(akt=None):
    items, _ = mr_liste()
    wagen, gesehen = [], set()
    def wagen_fuer(mr, titel, aenderungen, rollen=()):
        akte = akte_lesen(mr)
        n = sum(1 for k in review_kommentare(akte) if not k.get("geloescht"))
        gs, gs_neu = faeden_zaehlen(mr, akte["mr"].get("source_branch") or None)
        ds = diskussionen_stand(akte)
        gesendet = in_gitlab(akte)
        # fertig: abgeschlossen oder Diskussionen da und nichts mehr bei mir – kein Entwurf (lokal oder in GitLab),
        # keine Diskussion, in der ich dran bin (Stände: docs/funktionen.md)
        fertig = (bool(akte.get("abgeschlossen") or akte.get("diskussionen")) and not ausstehend(akte) and not gesendet
                  and not (ds["dran"] or ds["entwurf"] or ds["gitlab_entwurf"]))
        kurz = mr.projekt.rsplit("/", 1)[-1]
        marke = (f"💬 {gs_neu} neu" if gs_neu else
                 f"● {ds['dran']} dran" if ds["dran"] else ("✓ in GitLab" if akte.get("abgeschlossen") else "✓ erledigt")
                 if fertig else f"● {n} Komm." if n else "● offen")
        stand = " · ".join(t for t in (
            ", ".join({"reviewer": "Reviewer", "author": "Autor", "assignee": "zugewiesen"}.get(r, r) for r in rollen),
            f"{ds['dran']} Diskussion(en): du bist dran" if ds["dran"] else "",
            f"{ds['wartet']} wartet auf andere" if ds["wartet"] else "",
            f"{ds['erledigt']} erledigt" if ds["erledigt"] else "",
            f"{gesendet} Entwurf/Entwürfe in GitLab" if gesendet else "",
            f"{n} eigene Kommentare" if n else "",
            f"{gs} Faden/Fäden" + (f" ({gs_neu} neu)" if gs_neu else "") if gs else "") if t)
        return {"p": mr.id, "name": f'!{mr.iid} {kurz}', "titel": f'{mr.projekt}!{mr.iid}: {titel}' + (f"\n{stand}" if stand else ""),
                "zeile2": titel, "datei": mr.url, "plus": 0, "minus": 0, "dateien": aenderungen or 0,
                "commits": 0, "todos": [], "status": "fertig" if fertig and not gs_neu else "offen",
                "marke": marke}
    for it in items:
        try:
            mr = mr_ref(it.get("web_url", ""))
        except Fehler:
            continue
        gesehen.add(mr.id)
        wagen.append(wagen_fuer(mr, it.get("title", ""), it.get("changes_count"), it.get("rollen") or ()))
    if akt and akt not in gesehen:
        try:
            mr = Waggon.aus_id(akt)
            if not mr.lokal:
                wagen.insert(0, wagen_fuer(mr, akte_lesen(mr)["mr"].get("titel", ""), 0))
        except Fehler:
            pass
    return wagen


# Quellen der Waggons: die lokalen Branches (bis gegen von in jedem Repo unter „projekte“, je Projekt: von_bis) und GitLab-MRs; eine
# GitHub-Quelle wäre eine weitere Klasse. Der Zug mischt die Waggons aller eingeschalteten Quellen. Eine Quelle weiß,
# wo der Klon und Stand eines Waggons liegt (ort), baut seine Seite (seite), zählt ihre Waggons auf (wagen) und sagt
# dem Agenten, was zu tun ist (prompt). Bringt sie Einträge von außen (Diskussionen), dann mit titel und logo: das
# Symbol für „zuletzt von extern“ in den Listen (Stände: docs/funktionen.md). Was ein Waggon kann, steht am Waggon selbst (waggon.py).

class Lokal:
    name, titel = "lokal", "lokal"
    logo = None  # Logo (Datei in web/) für Einträge von außen („wer“ = extern); lokal gibt es kein außen

    def an(self):
        return bool(KONF["lokal"])

    def ort(self, waggon):
        """(Klon, Stand), auf den sich Zeilen beziehen: der Branch bis des Projekts."""
        wurzel = projekt_wurzel(waggon.lokal)
        bis = von_bis(waggon.lokal)[1]
        if bis == ARBEITSSTAND:
            return wurzel, arbeitsstand(wurzel)
        head = (git(wurzel, "rev-parse", "--verify", "-q", bis, check=False) or "").strip()
        if not head:
            raise Fehler(f"Branch {bis} fehlt in {wurzel}")
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
        repos = finde_repos(alle=True)
        with ThreadPoolExecutor(8) as ex:
            return lokal_wagen(list(ex.map(stand_oder_fehlt, repos)), {projektname(r): r for r in repos})

    def prompt(self, waggon, wurzel):
        von, bis = von_bis(waggon.lokal)
        wo = ("im Arbeitsverzeichnis umsetzen (nicht committen)" if bis == ARBEITSSTAND else f"auf {bis} umsetzen und committen")
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {waggon.lokal} (Diff {bis} gegen {von}). "
                f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche {wo}; "
                f"zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")


class GitLab:
    name, titel = "gitlab", "GitLab"
    logo = "gitlab.svg"
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


def extern_von(waggon):
    """Für die Seite: Titel und Logo-URL der Quelle (wer = extern), None ohne Logo."""
    q = quelle(waggon)
    return {"titel": q.titel, "logo": f"/logo/{q.name}.svg"} if q.logo else None


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
