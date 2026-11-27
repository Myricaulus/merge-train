"""Die Quellen der Waggons – Branches (in den Klonen, mit GitLab als Schicht: docs/branch-waggon.md) und Myrling (Läufe,
die auf eine Prüfung warten) – und was sie können."""
import json, os, re, subprocess
from datetime import datetime
from .einstellungen import ARBEITSSTAND, KONF, RUNDE, SPERRE, dateiname, melden, projektname
from .waggon import BRANCH_ART, MYRLING_ART, Fehler, Waggon, fertig_moeglich, von_bis, zweige_gewaehlt, zweige_standard
from .git import (STAND_TEXT, branch_pushen, branch_von, fehlende_zweige, finde_repos, git, git_oder_fehler, haupt_klon,
                  kurzpfad, ohne_basis, projekt_wurzel, repo_kennung, stand_zu_gitlab, statistik, wip_name, wip_sha,
                  worktrees)
from .akte import (akte_bearbeiten, akte_lesen, akten_sperre, ausstehend, diskussionen_stand, faeden_archivieren,
                   faeden_zaehlen, in_gitlab, projekt_akte_bearbeiten, review_kommentare, struktur_laden, zweig_ordner)
from .gitlab import (ausgecheckt, eigener_mr, gitlab_klon, mr_anlegen, mr_index, mr_liste, mr_ref, mr_uebernehmen,
                     mr_von, mr_waggon, mrs_zum_branch)
from .zweig import gemerkte_klone, projekt_von, projekt_waggon
from .abhaken import abhaken, haken_weg, teil_abgeben
from .seite import LAUF_STAND, branch_seite, myrling_seite
from . import myrling

def runde_laden():
    try:
        with open(RUNDE) as f:
            r = json.load(f)
    except (FileNotFoundError, ValueError):
        r = {}
    heute = datetime.now().strftime("%Y-%m-%d")
    return {p: w for p, w in r.items() if w.get("tag") == heute}


def lokal_wagen(stats, wurzeln=None):
    """Wagen der Projekt-Ordner: offene (heute teilweise abgegebene mit „abgegeben“) + heute fertig gewordene (sofern
    seitdem nichts Neues kam), absteigend nach Umfang. Je Wagen der Branch, den das Projekt zeigt (p = seine Kennung,
    projekt = der Ordner). wurzeln: {projekt: Klon}, Standard alle unter projekte."""
    wurzeln = wurzeln or {projektname(r): r for r in finde_repos(alle=True)}
    fertig = runde_laden()
    wagen = [w for w in stats if w["dateien"] or w["status"] == "fehlt"]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen and p in wurzeln]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    for w in wagen:  # Gespräch: offene Fäden / neue Antworten des Agenten
        if w["status"] == "offen" and fertig.get(w["p"], {}).get("status") == "abgegeben":
            w["abgegeben"] = True  # heute ein Teil abgegeben: zählt für die Abfahrt, der Rest bleibt offen
        waggon = projekt_waggon(wurzeln[w["p"]])
        w["projekt"], w["p"], w["datei"], w["quelle"] = w["p"], waggon.id, waggon.url, "lokal"
        w["gs"], w["gs_neu"] = faeden_zaehlen(waggon, waggon.branch)
    return wagen


def abgabe_pruefen(projekt, sha):
    """Für „fertig“ und „abgeben“: (Klon, von, bis), sonst Fehler mit dem Grund."""
    repos = {projektname(r): r for r in finde_repos()}
    if projekt not in repos:
        raise Fehler(f"Unbekanntes Projekt: {projekt}")
    wurzel = repos[projekt]
    if not re.fullmatch(r"[0-9a-f]{40}", sha or "") or git(wurzel, "cat-file", "-t", sha, check=False) != "commit\n":
        raise Fehler("Abgelehnt: unbekannter Stand.")
    von, bis = von_bis(projekt)
    if not fertig_moeglich(projekt):
        raise Fehler(f"„fertig“ geht nur mit lokalen Branches (von = {von}, bis = {bis}).")
    if git(wurzel, "merge-base", "--is-ancestor", von, sha, check=False) is None:
        raise Fehler(f"{projekt}: {von} ist nicht Vorgänger des gesehenen Stands – nichts geändert.")
    return wurzel, von, bis


def runde_eintragen(projekt, eintrag, status):
    """Waggon für heute in RUNDE vermerken (fertig bzw. abgegeben: zählt für die Abfahrt)."""
    with SPERRE:
        r = runde_laden()
        r[projekt] = dict(eintrag, p=projekt, datei=dateiname(projekt), status=status, tag=datetime.now().strftime("%Y-%m-%d"))
        with open(RUNDE, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)


def abgeben(projekt, sha, struktur):
    """Teilabgabe: die abgehakten Dateien auf <von>-wip (abhaken.teil_abgeben). Sind damit alle gesehen (gleicher Baum
    wie der gesehene Stand), wie „fertig“. Rückgabe (ok, text)."""
    try:
        wurzel, von, bis = abgabe_pruefen(projekt, sha)
    except Fehler as e:
        return False, str(e)
    if struktur["refs"]["head_sha"] != sha:
        return False, f"{projekt}: Die Seite zeigt einen älteren Stand – neu laden."
    waggon = projekt_waggon(wurzel)
    pfade = abhaken(waggon, struktur)["abgehakt"]
    if not pfade:
        return False, "Noch keine Datei abgehakt – nichts abzugeben."
    _, gleich = teil_abgeben(struktur, von, set(pfade))
    if gleich:
        return fertig(projekt, sha)
    with akte_bearbeiten(waggon) as a:
        haken_weg(a)
    runde_eintragen(projekt, statistik(wurzel, von, sha), "abgegeben")
    text = f"{projekt}: {len(pfade)} von {len(struktur['dateien'])} Datei(en) abgegeben → {wip_name(von)}"
    melden(text)
    return True, text


def fertig(projekt, sha):
    """von des Projekts auf den gesehenen Stand setzen (den Schlüssel prüft der Server), den Teilstand <von>-wip
    löschen. Rückgabe (ok, text)."""
    try:
        wurzel, von, bis = abgabe_pruefen(projekt, sha)
    except Fehler as e:
        return False, str(e)
    alt = git(wurzel, "rev-parse", von).strip()
    log = git(wurzel, "log", "--format=%B", f"{von}..{sha}")
    schliesst = sorted(set(re.findall(r"closes\s+todo:([\w.-]+)", log, flags=re.I)))
    # git push . statt branch -f: nur Fast-Forward, und der pre-push-Hook des Repos läuft (merge-train: ./testen,
    # bis ~20 s). Zuerst, damit ein Fehlschlag nichts verändert hat.
    try:
        git_oder_fehler(wurzel, "push", "-q", ".", f"{sha}:refs/heads/{von}", rest=1500)  # Hook-Ausgabe mitnehmen
    except Fehler as e:
        return False, f"{projekt}: {von} nicht gesetzt – {e}"
    if wip_sha(wurzel, von):  # vor statistik: die zählt sonst nur den Rest nach dem Teilstand
        git(wurzel, "branch", "-D", wip_name(von))
    akte = statistik(wurzel, alt, sha)
    waggon = projekt_waggon(wurzel)
    with akte_bearbeiten(waggon) as a:
        haken_weg(a)
    faeden_archivieren(waggon, waggon.branch)
    runde_eintragen(projekt, akte, "fertig")
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
    """statistik; fehlt von oder bis im Klon oder haben sie keinen gemeinsamen Vorgänger (ohne_basis), ein Waggon
    „⚠ fehlt“ bzw. „⚠ keine Basis“ – aufklappen und andere Zweige wählen."""
    fehlt = fehlende_zweige(wurzel)
    if not fehlt and not ohne_basis(wurzel):
        return statistik(wurzel)
    p = projektname(wurzel)
    von, bis = von_bis(p)
    marke, titel = (("⚠ fehlt", f"{', '.join(fehlt)} fehlt im Klon") if fehlt else
                    ("⚠ keine Basis", f"{bis} und {von} haben keinen gemeinsamen Vorgänger (Rebase?)"))
    return {"p": p, "datei": dateiname(p), "plus": 0, "minus": 0, "dateien": 0, "commits": 0, "todos": [],
            "status": "fehlt", "sha": "", "zeile2": f"{bis} → {von}", "marke": marke,
            "titel": f"{p}: {titel} – ▾ zum Einstellen"}


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
    basislos = not fehlt and ohne_basis(wurzel)
    info = {"p": projekt, "ordner": kurzpfad(wurzel), "von": von, "bis": bis, "standard": {"von": std_von, "bis": std_bis},
            "gewaehlt": bool(zweige_gewaehlt(projekt)), "lokal": lokal, "remote": remote, "fehlt": fehlt,
            "ohne_basis": basislos, "ausgecheckt": (git(wurzel, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "").strip() or "(losgelöst)",
            "origin": (git(wurzel, "remote", "get-url", "origin", check=False) or "").strip(),
            "fertig": fertig_moeglich(projekt), "arbeitsstand": ARBEITSSTAND}
    if not fehlt and not basislos:
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
    with projekt_akte_bearbeiten(projekt) as akte:
        if (von, bis) == std:
            akte.pop("zweige", None)
        else:
            akte["zweige"] = {"von": von, "bis": bis}
    return True, f"{projekt}: {bis} → {von}" + (" (Standard)" if (von, bis) == std else "")


def wagen_eintrag(p, name, titel, datei, marke, *, zeile2=None, plus=0, minus=0, dateien=0, status="offen", **mehr):
    """Ein Wagen im Zug für MR und Myrling (lokale kommen fertig aus statistik)."""
    return {"p": p, "name": name, "titel": titel, "zeile2": zeile2, "datei": datei, "plus": plus, "minus": minus,
            "dateien": dateien, "commits": 0, "todos": [], "status": status, "marke": marke, **mehr}


def faeden_marke(gs_neu, sonst):
    """Marke am Wagen: neue Antworten des Agenten gehen vor."""
    return f"💬 {gs_neu} neu" if gs_neu else sonst


def faeden_text(gs, gs_neu):
    """Zeile im Titel des Wagens: Fäden, davon neu."""
    return f"{gs} Faden/Fäden" + (f" ({gs_neu} neu)" if gs_neu else "") if gs else ""


def mr_wagen_fuer(w, akte, titel, aenderungen, rollen=(), basis=None):
    """Wagen eines Branches mit MR-Schicht: Marke und Titel aus Diskussionen, Kommentaren und Fäden. basis: der Wagen
    seines Projekts (Statistik gegen von, Ordner), sonst zählt changes_count aus der MR-Liste. Ein im Haupt-Klon
    ausgecheckter MR ist erkennbar (⎇, „ausgecheckt“)."""
    mr = mr_von(akte)
    n = sum(1 for k in review_kommentare(akte) if not k.get("geloescht"))
    gs, gs_neu = faeden_zaehlen(w, w.branch)
    ds = diskussionen_stand(akte)
    gesendet = in_gitlab(akte)
    # fertig: abgeschlossen oder Diskussionen da und nichts mehr bei mir – kein Entwurf (lokal oder in GitLab),
    # keine Diskussion, in der ich dran bin (Stände: docs/funktionen.md)
    fertig = (bool(akte.get("abgeschlossen") or akte.get("diskussionen")) and not ausstehend(akte) and not gesendet
              and not (ds["dran"] or ds["entwurf"] or ds["gitlab_entwurf"]))
    haupt = haupt_klon(w.repo, gemerkte_klone(akte))
    aus = bool(haupt and ausgecheckt(haupt) == w.branch)
    kurz = mr.projekt.rsplit("/", 1)[-1]
    marke = faeden_marke(gs_neu, f"● {ds['dran']} dran" if ds["dran"] else (
        "✓ in GitLab" if akte.get("abgeschlossen") else "✓ erledigt") if fertig else f"● {n} Komm." if n else "● offen")
    stand = " · ".join(t for t in (
        ", ".join({"reviewer": "Reviewer", "author": "Autor", "assignee": "zugewiesen"}.get(r, r) for r in rollen),
        ("eigener MR" if eigener_mr(w, akte) else "") + (", " if eigener_mr(w, akte) and aus else "")
        + (f"{w.branch} im Haupt-Klon ausgecheckt" if aus else ""),
        f"{ds['dran']} Diskussion(en): du bist dran" if ds["dran"] else "",
        f"{ds['wartet']} wartet auf andere" if ds["wartet"] else "",
        f"{ds['erledigt']} erledigt" if ds["erledigt"] else "",
        f"{gesendet} Entwurf/Entwürfe in GitLab" if gesendet else "",
        f"{n} eigene Kommentare" if n else "", faeden_text(gs, gs_neu)) if t)
    zahlen = {k: basis[k] for k in ("plus", "minus", "dateien", "commits", "todos")} if basis else {"dateien": aenderungen or 0}
    mehr = {k: basis[k] for k in ("projekt", "sha", "abgegeben") if k in basis} if basis else {}
    return dict(wagen_eintrag(w.id, f'!{mr.iid} {kurz}' + (" ⎇" if aus else ""),
                              f'{mr.name}: {titel}' + (f"\n{stand}" if stand else ""), w.url, marke, zeile2=titel,
                              status="fertig" if fertig and not gs_neu else "offen", ausgecheckt=aus, quelle="gitlab",
                              **mehr), **zahlen)


def branch_wagen(akt=None):
    """Der Zug der Branches: je Projekt-Ordner der Branch, den es zeigt; je MR aus der MR-Liste sein Branch – ein Wagen je
    Kennung, mit MR-Schicht als MR-Wagen. Branches mit MR-Schicht, die ein Projekt zeigt oder die im Haupt-Klon
    ausgecheckt sind, stehen auch ohne Eintrag in der MR-Liste da. MRs der Liste ohne MR-Daten: ein Wagen, der die Seite
    zum Holen öffnet (ohne_daten)."""
    from concurrent.futures import ThreadPoolExecutor
    try:  # akt auch als Abkürzung (MR-Kennung, projekt:<name>)
        akt = Waggon.aus_id(akt).id if akt else None
    except Fehler:
        akt = None
    basis = {}
    if KONF["lokal"]:
        repos = finde_repos(alle=True)
        for r in repos:
            zweige_aufraeumen(r)
        with ThreadPoolExecutor(8) as ex:
            stats = list(ex.map(stand_oder_fehlt, repos))
        basis = {x["p"]: x for x in lokal_wagen(stats, {projektname(r): r for r in repos})}
    mrs, ohne = {}, []
    if KONF["gitlab"]:
        index = mr_index()
        for it in mr_liste()[0]:
            try:
                ref = mr_ref(it.get("web_url", ""))
            except Fehler:
                continue
            w = mr_waggon(ref, index)
            if w:
                mrs[w.id] = (w, it.get("title", ""), it.get("changes_count"), it.get("rollen") or ())
            else:
                ohne.append(wagen_eintrag(ref.id, f"!{ref.iid} {ref.projekt.rsplit('/', 1)[-1]}",
                                          f"{ref.name}: {it.get('title', '')}\nnoch keine MR-Daten – öffnen holt sie",
                                          ref.url, "● neu", zeile2=it.get("title", ""), dateien=it.get("changes_count") or 0,
                                          ohne_daten=True, quelle="gitlab"))
        haupt_branch = {}
        for _, w in index.values():
            if w.id in mrs:
                continue
            if w.repo not in haupt_branch:
                h = haupt_klon(w.repo)
                haupt_branch[w.repo] = h and ausgecheckt(h)
            akte = akte_lesen(w)
            if (w.id in basis or haupt_branch[w.repo] == w.branch or w.id == akt) \
               and (akte.get("meta") or {}).get("state") in (None, "opened"):
                mrs[w.id] = (w, (akte.get("gitlab") or {}).get("titel", ""), 0, ())
    wagen = [mr_wagen_fuer(Waggon.aus_id(wid), akte_lesen(Waggon.aus_id(wid)), *mrs.pop(wid)[1:], basis=x)
             if wid in mrs else x for wid, x in basis.items()]
    wagen += [mr_wagen_fuer(w, akte_lesen(w), titel, n, rollen) for w, titel, n, rollen in mrs.values()] + ohne
    if akt and not any(x["p"] == akt for x in wagen):
        w = Waggon.aus_id(akt)
        akte = akte_lesen(w) if w.branch else {}
        if mr_von(akte):
            wagen.insert(0, mr_wagen_fuer(w, akte, (akte.get("gitlab") or {}).get("titel", ""), 0))
    return wagen


# Quellen der Waggons: Branches (in den Klonen, mit GitLab als Schicht) und der Myrling. Der Zug mischt die Waggons
# aller eingeschalteten Quellen. Eine Quelle weiß, wo der Klon und Stand eines Waggons liegt (ort), baut seine Seite
# (seite), zählt ihre Waggons auf (wagen), sagt, was ein Waggon kann (kann), und dem Agenten, was zu tun ist (prompt).

class Quelle:
    name = titel = art = None
    logo = None  # Logo (Datei in web/) für Einträge von außen („wer“ = extern); ohne: kein außen

    def an(self):
        return bool(KONF[self.name])

    def ort(self, waggon):
        """(Klon, Stand), wie ihn die Seite zuletzt gebaut hat (sonst neu)."""
        struktur = struktur_laden(akte_lesen(waggon))
        if struktur is None:
            _, struktur = self.seite(waggon)
        return struktur["ordner"], struktur["refs"]["head_sha"]

    def kann(self, waggon):
        """Was der Waggon kann (Waggon.kann)."""
        return {"review": False, "fertig": False, "committen": True}


class Branch(Quelle):
    """Branches in den Klonen; GitLab ist eine Schicht darauf (Feld „gitlab“ der Akte, sobald MR-Daten geholt sind)."""
    name, titel, art = "branch", "Branch", BRANCH_ART

    def an(self):
        return bool(KONF["lokal"] or KONF["gitlab"])

    def kann(self, w):
        akte = akte_lesen(w)
        if KONF["gitlab"] and mr_von(akte):
            return {"review": True, "fertig": False, "committen": eigener_mr(w, akte)}
        p = projekt_von(w, akte)
        return {"review": False, "fertig": bool(p) and fertig_moeglich(p) and von_bis(p)[1] == w.branch, "committen": True}

    def ziel(self, w):
        """Ref des Zielbranchs (see_also "ref": "ziel"): mit MR origin/<target_branch>, sonst von des Projekts."""
        akte = akte_lesen(w)
        return ((struktur_laden(akte) or {}).get("refs") or {}).get("ziel") or (akte.get("gitlab") or {}).get("target_branch") \
            or (von_bis(projekt_von(w, akte) or "")[0])

    def seite(self, w, ansicht=None):
        return branch_seite(w, ansicht=ansicht)

    def branch(self, w):
        return w.branch

    def wagen(self, akt=None):
        return branch_wagen(akt)

    def arbeitsstand(self, w):
        """Zeigt die zuletzt gebaute Seite den Arbeitsstand (im Haupt-Klon ausgecheckt)?"""
        return bool(((struktur_laden(akte_lesen(w)) or {}).get("refs") or {}).get("arbeitsstand"))

    def stand_kurz(self, w, branch, head, wurzel):
        """Für den Kopf von feedback: worauf sich die Fäden beziehen (mit MR: dessen Name)."""
        mr = mr_von(akte_lesen(w)) if KONF["gitlab"] else None
        return (f"{f'MR {mr.name} · ' if mr else ''}Branch {branch}{' · Arbeitsstand' if self.arbeitsstand(w) else ''} · "
                f"Stand {head[:8]} · Klon {wurzel}")

    def zeilen_stand(self, w, head):
        """Für feedback: „Code-Zeilen beziehen sich auf …“ und was der Agent dort tun darf."""
        arbeit, kann = self.arbeitsstand(w), w.kann
        if kann["review"] and not kann["committen"]:
            return f"den Stand {head[:8]} im Klon (nichts ändern, nur antworten)."
        if kann["review"]:
            return (f"den Arbeitsstand von {w.branch} (auch nicht Committetes) – dein eigener MR: Wünsche dort umsetzen und "
                    "committen (pushen nur auf Bitte)." if arbeit else
                    f"den Stand {head[:8]} im Klon – dein eigener MR: Wünsche auf {w.branch} umsetzen und committen "
                    "(pushen nur auf Bitte).")
        return ("den Arbeitsstand (auch nicht Committetes); Wünsche dort umsetzen, nicht committen." if arbeit
                else f"den aktuellen Stand von {w.branch}.")

    def prompt(self, w, wurzel):
        z, kann = w.id, w.kann
        if kann["review"]:
            tun = (f"Fragen beantworten, Änderungswünsche auf {w.branch} umsetzen und committen (es ist der eigene MR des "
                   "Nutzers; pushen nur auf Bitte)" if kann["committen"] else
                   "Beantworte sie anhand des Codes im Klon; den MR nicht ändern, nichts committen oder pushen")
            was = f"zum Merge-Request {mr_von(akte_lesen(w)).name} (Branch {w.branch}, lokaler Klon: {wurzel})"
        else:
            tun = "Fragen beantworten, Änderungswünsche " + (
                "im Arbeitsverzeichnis umsetzen (nicht committen)" if self.arbeitsstand(w) else f"auf {w.branch} umsetzen und committen")
            was = f"zum Code von {w.name} (Diff {w.branch} gegen {self.ziel(w)}, Klon: {wurzel})"
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers {was}. Hol sie mit "
                f"`merge-train agent feedback {z}` ab. {tun}; zu jedem Faden mit `merge-train agent antworten <id> \"…\"` "
                f"antworten (umgesetzt: --erledigt). Danach mit `merge-train agent horchen {z}` (im Hintergrund, nach "
                "jeder Ausgabe neu) auf weitere Nachrichten warten.")


def myrling_wagen(akt=None):
    """Ein Waggon je anstehendem Lauf (myrling.anstehend; zug.js holt die Liste im Hintergrund neu). Die Statistik
    kommt aus dem Diff Basis → Stand; abgelehnte warten auf eine neue Fassung."""
    laeufe, _ = myrling.gepuffert()
    if laeufe is None:
        try:
            laeufe = myrling.anstehend()
        except Fehler as e:
            return [wagen_eintrag("myrling:", "Myrling", str(e), "", "⚠ Fehler", zeile2="Befehl scheitert", status="fehlt")]
    wagen = []
    for lauf in laeufe:
        waggon = Waggon(myrling=lauf["skript"])
        plus = minus = dateien = 0
        try:
            wurzel, basis, head, fehlen = myrling.lauf_ort(lauf)
            for z in git(wurzel, "diff", "--numstat", basis, head).splitlines():
                a, b, _ = z.split("\t", 2); dateien += 1
                if a != "-": plus += int(a); minus += int(b)
            dateien += len(fehlen)
            branch = MYRLING.branch(waggon)
        except Fehler as e:
            wurzel, fehlen, branch = None, [], None
            lauf = dict(lauf, stand="fehlt", grund=str(e))
        gs, gs_neu = faeden_zaehlen(waggon, branch)
        kurz, lang = LAUF_STAND.get(lauf["stand"], (lauf["stand"], lauf.get("grund") or lauf["stand"]))
        marke = faeden_marke(gs_neu, "✗ abgelehnt" if lauf["stand"] == "abgelehnt" else f"● {kurz}")
        titel = "\n".join(t for t in (
            f'{lauf["skript"]}: {lang}', f'braucht {lauf["braucht"]}' if lauf["braucht"] else "",
            f'abgelehnt: {(lauf["abgelehnt"] or {}).get("grund") or "?"}' if lauf["abgelehnt"] else "",
            f"{len(fehlen)} Datei(en) aus anderen Repos fehlen im Diff" if fehlen else "", faeden_text(gs, gs_neu)) if t)
        wagen.append(wagen_eintrag(waggon.id, "⛭ " + lauf["skript"], titel, waggon.url, marke,
                                   zeile2=None if plus + minus else kurz, plus=plus, minus=minus, dateien=dateien,
                                   status="fehlt" if lauf["stand"] == "fehlt" else "offen", gs=gs, gs_neu=gs_neu))
    return wagen


class Myrling(Quelle):
    name, titel, art = "myrling", "Myrling", MYRLING_ART

    def an(self):
        return super().an() and myrling.befehl_da()

    def ziel(self, waggon):
        """Ein Lauf hat keinen Zielbranch: jede Datei steht gegen ihre zuletzt angesehene Fassung."""
        return None

    def seite(self, waggon, ansicht=None):
        return myrling_seite(waggon, ansicht=ansicht)

    def branch(self, waggon):
        """Fäden hängen am Skript, nicht an einem Branch: über neue Fassungen wandern sie mit (Zeilen vorwärts)."""
        return "myrling"

    def wagen(self, akt=None):
        return myrling_wagen(akt)

    def stand_kurz(self, waggon, branch, head, wurzel):
        return f"Lauf {waggon.myrling} · Stand {head[:8]} · Repo {wurzel}"

    def zeilen_stand(self, waggon, head):
        return (f"den Stand {head[:8]} des Skripts; Änderungen im Repo committen, der Myrling führt erst die neu geprüfte "
                "Fassung aus.")

    def prompt(self, waggon, wurzel):
        z = waggon.id
        return (f"In merge-train liegen Fragen des Nutzers zum Skript {waggon.myrling}, das der Myrling ausführen soll "
                f"(Repo {wurzel}; Diff gegen die zuletzt angesehene Fassung). Hol sie mit "
                f"`merge-train agent feedback {z}` ab. Fragen beantworten, Änderungswünsche am Skript im Repo umsetzen "
                f"und committen (das Skript läuft erst nach erneuter Prüfung); zu jedem Faden mit "
                f"`merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). Danach mit "
                f"`merge-train agent horchen {z}` (im Hintergrund, nach jeder Ausgabe neu) auf weitere Fragen warten.")


# Aufräumen der Branch-Akten (docs/branch-akte.md): Fäden gelöschter oder in von gemergter Branches verschwinden aus
# „fremde Fäden“. Höchstens alle AUFRAEUMEN_S je Repo (beim Zug).
AUFRAEUMEN_S = 600
_AUFGERAEUMT = {}


def zweige_aufraeumen(wurzel, jetzt_s=None):
    """Akten von Branches des Repos, die weder der aktuelle des Projekts, von, bis noch in einem Worktree ausgecheckt
    sind, keinen offenen MR haben und weg sind (weder lokal noch auf origin) oder in von gemergt: nach archiv/<name>-<zeit>.json.
    Rückgabe: aufgeräumte Branches."""
    import time
    from .akte import zweig_akten
    repo, p = repo_kennung(wurzel), projektname(wurzel)
    jetzt_s = time.time() if jetzt_s is None else jetzt_s
    if jetzt_s - _AUFGERAEUMT.get(repo, 0) < AUFRAEUMEN_S or not os.path.isdir(zweig_ordner(repo)):
        return []
    _AUFGERAEUMT[repo] = jetzt_s
    von, bis = von_bis(p)
    behalten = {branch_von(wurzel), von, bis} | {ausgecheckt(b) for b in worktrees(wurzel)}
    ref = lambda r: (git(wurzel, "rev-parse", "--verify", "-q", r, check=False) or "").strip()
    weg = []
    for b, pfad in zweig_akten(repo):
        if b in behalten:
            continue
        try:
            akte = json.load(open(pfad, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if akte.get("gitlab") and (akte.get("meta") or {}).get("state") in (None, "opened"):
            continue
        da = ref(f"refs/heads/{b}") or ref(f"refs/remotes/origin/{b}")
        if da and not (ref(von) and git(wurzel, "merge-base", "--is-ancestor", da, von, check=False) is not None):
            continue
        with akten_sperre():
            if os.path.exists(pfad):
                os.makedirs(os.path.join(zweig_ordner(repo), "archiv"), exist_ok=True)
                os.replace(pfad, os.path.join(zweig_ordner(repo), "archiv",
                                              f"{os.path.basename(pfad)[:-5]}-{datetime.now():%Y%m%d-%H%M%S}.json"))
        weg.append(b)
    return weg


# ---- Branch ohne MR (docs/ein-waggon.md, Schritt 2): Knopf „MR erstellen“. Erst fragen (mr_planen: gibt es schon einen
# MR, sonst mr_vorschlag in einen Dialog), dann pushen und anlegen (mr_erstellen). Danach hat der Branch seine
# MR-Schicht.

def mr_quellbranch(projekt):
    """(Klon, Quell-Branch) für „MR erstellen“: bis des Projekts, beim Arbeitsstand der ausgecheckte Branch."""
    wurzel = projekt_wurzel(projekt)
    bis = von_bis(projekt)[1]
    branch = ausgecheckt(wurzel) if bis == ARBEITSSTAND else bis
    if not branch or git(wurzel, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False) is None:
        raise Fehler(f"{projekt}: {branch or 'losgelöster HEAD'} ist kein lokaler Branch – ein MR braucht einen")
    return wurzel, branch


def mr_vorschlag(projekt):
    """Was „MR erstellen“ fragt, ohne GitLab: Quell-Branch, Ziel-Branches auf origin (vorgeschlagen: von des Projekts,
    sonst der Standard-Branch von origin), Titel und Beschreibung aus den Commits, ob und wie gepusht wird, Warnungen
    und Hindernisse (dann kein Erstellen)."""
    wurzel, branch = mr_quellbranch(projekt)
    gl = gitlab_klon(wurzel)
    if not gl:
        raise Fehler(f"{projekt}: origin ist kein GitLab-Projekt")
    ziele = [z for z in (git(wurzel, "for-each-ref", "--format=%(refname:strip=3)", "refs/remotes/origin",
                             check=False) or "").split() if z not in ("HEAD", branch)]
    von = re.sub(r"^(refs/remotes/)?origin/", "", von_bis(projekt)[0])
    std = (git(wurzel, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD", check=False) or "").strip()
    ziel = next((z for z in (von, std.split("/", 1)[-1], "main", "master") if z in ziele), ziele[0] if ziele else "")
    hindernisse, warnungen = [], []
    if not ziel:
        hindernisse.append("Im Klon ist kein Branch von origin bekannt (git fetch).")
    commits = [c.strip("\n").split("\x1f", 1) for c in (git(wurzel, "log", "--reverse", "--format=%s%x1f%b%x1e",
               f"refs/remotes/origin/{ziel}..refs/heads/{branch}", check=False) or "").split("\x1e") if c.strip()] if ziel else []
    if ziel and not commits:
        warnungen.append(f"{branch} hat keine Commits gegenüber {ziel}.")
    if len(commits) == 1:
        titel, beschreibung = commits[0][0], commits[0][1].strip()
    else:
        titel = re.sub(r"[-_/]+", " ", branch).strip().capitalize()
        beschreibung = "\n".join(f"- {c[0]}" for c in commits)
    lokal = git(wurzel, "rev-parse", f"refs/heads/{branch}").strip()
    origin = (git(wurzel, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}", check=False) or "").strip()
    push = "neu" if not origin else stand_zu_gitlab(wurzel, branch, lokal, origin)
    push_text = {"neu": f"{branch} wird neu nach origin gepusht (als Upstream).", None: f"{branch} ist schon auf origin.",
                 "lokal_voraus": f"Die neuen Commits von {branch} werden nach origin gepusht.",
                 "umgeschrieben": f"{branch} ist umgeschrieben: Force-Push mit Lease nach origin."}.get(push)
    if push_text is None:
        hindernisse.append(f"{branch}: {STAND_TEXT.get(push, push)}.")
    offen = len((git(wurzel, "status", "--porcelain", "--untracked-files=no", check=False) or "").splitlines())
    if offen:
        warnungen.append(f"{offen} Datei(en) nicht committet: Sie kommen nicht in den MR.")
    return {"projekt": projekt, "quelle": branch, "ziel": ziel, "ziele": ziele, "titel": titel,
            "beschreibung": beschreibung, "commits": len(commits), "push": push, "push_text": push_text or "",
            "origin": origin, "warnungen": warnungen, "hindernisse": hindernisse, "host": gl[0], "gl_projekt": gl[1]}


def mr_planen(projekt):
    """Erster Klick auf „MR erstellen“: Gibt es in GitLab schon einen offenen MR zu diesem Branch, wird er übernommen
    (url: dorthin). Sonst der Vorschlag für den Dialog."""
    v = mr_vorschlag(projekt)
    da = mrs_zum_branch(v["host"], v["gl_projekt"], v["quelle"])
    if da:
        w = mr_uebernehmen(da[0], projekt_wurzel(projekt))
        return {"ok": True, "text": f"{da[0].name} gibt es schon für {v['quelle']} – übernommen", "url": w.url}
    return {"ok": True, "vorschlag": v}


def mr_erstellen(projekt, ziel, titel, beschreibung, entwurf=False):
    """Nach der Rückfrage: Quell-Branch pushen (wie im Vorschlag), MR anlegen. Rückgabe für die Seite: ok, text, url des
    Branches (mit MR-Schicht)."""
    v = mr_vorschlag(projekt)
    branch, wurzel = v["quelle"], projekt_wurzel(projekt)
    titel = " ".join(str(titel).split())
    if v["hindernisse"]:
        raise Fehler(" ".join(v["hindernisse"]))
    if ziel not in v["ziele"]:
        raise Fehler(f"Ziel-Branch {ziel} gibt es auf origin nicht")
    if not titel:
        raise Fehler("Der MR braucht einen Titel")
    if git(wurzel, "rev-list", "--count", f"refs/remotes/origin/{ziel}..refs/heads/{branch}").strip() == "0":
        raise Fehler(f"{branch} hat keine Commits gegenüber {ziel} – nichts für einen MR")
    if entwurf and not re.match(r"(?i)(draft|wip)\b", titel):
        titel = "Draft: " + titel
    texte = [branch_pushen(wurzel, branch, v["origin"], neu=v["push"] == "neu")] if v["push"] else []
    w = mr_anlegen(v["host"], v["gl_projekt"], branch, ziel, titel, str(beschreibung or ""), wurzel)
    texte.append(f"{mr_von(akte_lesen(w)).name} erstellt ({branch} → {ziel})")
    melden(" · ".join(texte))
    return {"ok": True, "text": " · ".join(texte), "url": w.url}


class Schalter:
    """Eine Quelle, die nur an- und abschaltet (Einstellung lokal bzw. gitlab): Routen der Projekt-Ordner und des
    Güterbahnhofs. GitLab bringt dazu Titel und Logo der Schicht mit („wer“ = extern in den Listen)."""
    def __init__(self, name, titel, logo=None):
        self.name, self.titel, self.logo = name, titel, logo

    def an(self):
        return bool(KONF[self.name])


BRANCH, MYRLING = Branch(), Myrling()
LOKAL, GITLAB = Schalter("lokal", "lokal"), Schalter("gitlab", "GitLab", "gitlab.svg")


QUELLEN = (BRANCH, MYRLING)
SCHICHTEN = (GITLAB,)


QUELLE_JE_ART = {q.art: q for q in QUELLEN}


def quelle(waggon):
    return QUELLE_JE_ART[waggon.art]


def extern_von(waggon):
    """Für die Seite: Titel und Logo-URL der Schicht (wer = extern), None ohne (kein MR, Myrling)."""
    if not (waggon.branch and KONF["gitlab"] and mr_von(akte_lesen(waggon))):
        return None
    return {"titel": GITLAB.titel, "logo": f"/logo/{GITLAB.name}.svg"}


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
                w = dict({"quelle": q.name}, **w)
                if w.get("status") == "offen" and not w.get("ohne_daten"):  # Füllung aus den abgehakten Dateien (abhaken.py)
                    w["fuellung"] = akte_lesen(Waggon.aus_id(w["p"])).get("fuellung")
                wagen.append(w)
    return wagen
