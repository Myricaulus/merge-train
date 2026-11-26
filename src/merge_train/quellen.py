"""Die Quellen der Waggons – Lokal (Branches im Klon), Myrling (Läufe, die auf eine Prüfung warten) und GitLab
(Merge-Requests) – und was sie können."""
import glob, json, os, re, subprocess
from datetime import datetime
from .einstellungen import ARBEITSSTAND, DATEN, KONF, RUNDE, SPERRE, dateiname, melden, projektname
from .waggon import LOKAL_ART, MR_ART, MYRLING_ART, Fehler, Waggon, fertig_moeglich, von_bis, zweige_gewaehlt, zweige_standard
from .git import (STAND_TEXT, arbeitsstand, branch_pushen, branch_von, fehlende_zweige, finde_repos, git, git_oder_fehler, ohne_basis,
                  kurzpfad, projekt_wurzel, stand_zu_gitlab, statistik, wip_name, wip_sha)
from .akte import (akte_bearbeiten, akte_lesen, ausstehend, diskussionen_stand, faeden_archivieren, faeden_zaehlen, in_gitlab,
                   review_kommentare, struktur_laden)
from .gitlab import ausgecheckt, eigener_mr, gitlab_klon, mr_anlegen, mr_liste, mr_ref, mr_uebernehmen, mrs_zum_branch
from .abhaken import abhaken, haken_weg, teil_abgeben
from .seite import LAUF_STAND, mr_seite, myrling_seite, projekt_seite
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
    """Lokale Waggons: offene Projekte (heute teilweise abgegebene mit „abgegeben“) + heute fertig gewordene (sofern seitdem
    nichts Neues kam), absteigend nach Umfang.
    wurzeln: {projekt: Klon} für den Branch der Fäden."""
    wurzeln = wurzeln or {}
    fertig = runde_laden()
    wagen = [w for w in stats if w["dateien"] or w["status"] == "fehlt"]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    for w in wagen:  # Gespräch: offene Fäden / neue Antworten des Agenten
        if w["status"] == "offen" and fertig.get(w["p"], {}).get("status") == "abgegeben":
            w["abgegeben"] = True  # heute ein Teil abgegeben: zählt für die Abfahrt, der Rest bleibt offen
        wurzel = wurzeln.get(w["p"])
        w["gs"], w["gs_neu"] = faeden_zaehlen(Waggon(lokal=w["p"]), branch_von(wurzel) if wurzel else None)
        w["datei"] = "/" + dateiname(w["p"])
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
    waggon = Waggon(lokal=projekt)
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
    with akte_bearbeiten(Waggon(lokal=projekt)) as a:
        haken_weg(a)
    faeden_archivieren(Waggon(lokal=projekt), branch_von(wurzel))
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
    with akte_bearbeiten(Waggon(lokal=projekt)) as akte:
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


def mr_wagen(akt=None):
    items, _ = mr_liste()
    wagen, gesehen = [], set()
    ausgecheckte = [mr for (wurzel, branch), mr in eigene_mrs().items() if ausgecheckt(wurzel) == branch]  # ein Waggon
    eigen = {mr.id for mr in ausgecheckte}
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
        marke = faeden_marke(gs_neu, f"● {ds['dran']} dran" if ds["dran"] else (
            "✓ in GitLab" if akte.get("abgeschlossen") else "✓ erledigt") if fertig else f"● {n} Komm." if n else "● offen")
        stand = " · ".join(t for t in (
            ", ".join({"reviewer": "Reviewer", "author": "Autor", "assignee": "zugewiesen"}.get(r, r) for r in rollen),
            "eigener MR, Quell-Branch ausgecheckt: lokaler Waggon und MR in einem" if mr.id in eigen else "",
            f"{ds['dran']} Diskussion(en): du bist dran" if ds["dran"] else "",
            f"{ds['wartet']} wartet auf andere" if ds["wartet"] else "",
            f"{ds['erledigt']} erledigt" if ds["erledigt"] else "",
            f"{gesendet} Entwurf/Entwürfe in GitLab" if gesendet else "",
            f"{n} eigene Kommentare" if n else "", faeden_text(gs, gs_neu)) if t)
        return wagen_eintrag(mr.id, f'!{mr.iid} {kurz}', f'{mr.projekt}!{mr.iid}: {titel}' + (f"\n{stand}" if stand else ""),
                             mr.url, marke, zeile2=titel, dateien=aenderungen or 0,
                             status="fertig" if fertig and not gs_neu else "offen")
    for it in items:
        try:
            mr = mr_ref(it.get("web_url", ""))
        except Fehler:
            continue
        gesehen.add(mr.id)
        wagen.append(wagen_fuer(mr, it.get("title", ""), it.get("changes_count"), it.get("rollen") or ()))
    for mr in ausgecheckte:  # eigener MR, ausgecheckt: steht auch ohne „author“ in mr_liste im Zug
        if mr.id not in gesehen:
            gesehen.add(mr.id)
            wagen.append(wagen_fuer(mr, akte_lesen(mr)["mr"].get("titel", ""), 0))
    if akt and akt not in gesehen:
        try:
            mr = Waggon.aus_id(akt)
            if mr.ist_mr:
                wagen.insert(0, wagen_fuer(mr, akte_lesen(mr)["mr"].get("titel", ""), 0))
        except Fehler:
            pass
    return wagen


# Quellen der Waggons: die lokalen Branches (bis gegen von in jedem Repo unter „projekte“, je Projekt: von_bis) und GitLab-MRs; eine
# GitHub-Quelle wäre eine weitere Klasse. Der Zug mischt die Waggons aller eingeschalteten Quellen. Eine Quelle weiß,
# wo der Klon und Stand eines Waggons liegt (ort), baut seine Seite (seite), zählt ihre Waggons auf (wagen) und sagt
# dem Agenten, was zu tun ist (prompt). Bringt sie Einträge von außen (Diskussionen), dann mit titel und logo: das
# Symbol für „zuletzt von extern“ in den Listen (Stände: docs/funktionen.md). Kennung, Seite, Dateiname und was ein
# Waggon kann, stehen an seiner Art (art, waggon.py).

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

    def waggon_von(self, p):
        """Waggon zum Feld „p“ eines Wagens im Zug (wagen)."""
        return Waggon.aus_id(p)

    def ein_waggon(self, waggon):
        """Ist der Waggon zugleich der lokale (eigener MR mit ausgechecktem Quell-Branch, docs/ein-waggon.md)?"""
        return False


class Lokal(Quelle):
    name, titel, art = "lokal", "lokal", LOKAL_ART

    def waggon_von(self, p):
        return Waggon(lokal=p)  # p ist hier der Projektname, nicht die Kennung

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

    def ziel(self, waggon):
        """Ref des Zielbranchs (see_also "ref": "ziel"): von."""
        return von_bis(waggon.lokal)[0]

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
        mrs = eigene_mrs() if GITLAB.an() else {}
        repos = [r for r in finde_repos(alle=True) if not (mrs and zusammengelegt(r, mrs))]  # steckt im MR-Waggon
        with ThreadPoolExecutor(8) as ex:
            return lokal_wagen(list(ex.map(stand_oder_fehlt, repos)), {projektname(r): r for r in repos})

    def stand_kurz(self, waggon, branch, head, wurzel):
        """Für den Kopf von feedback: worauf sich die Fäden beziehen."""
        return f"{branch}{' · Arbeitsstand' if von_bis(waggon.lokal)[1] == ARBEITSSTAND else ''} {head[:8]}"

    def zeilen_stand(self, waggon, head):
        """Für feedback: „Code-Zeilen beziehen sich auf …“ und was der Agent dort tun darf."""
        bis = von_bis(waggon.lokal)[1]
        return ("den Arbeitsstand (auch nicht Committetes); Wünsche dort umsetzen, nicht committen." if bis == ARBEITSSTAND
                else f"den aktuellen Stand von {bis}.")

    def prompt(self, waggon, wurzel):
        von, bis = von_bis(waggon.lokal)
        wo = ("im Arbeitsverzeichnis umsetzen (nicht committen)" if bis == ARBEITSSTAND else f"auf {bis} umsetzen und committen")
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {waggon.lokal} (Diff {bis} gegen {von}). "
                f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche {wo}; "
                f"zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")


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


# ---- Eigener MR = ein Waggon (docs/ein-waggon.md, Schritt 1): ist der Quell-Branch eines eigenen, offenen MR im Klon
# ausgecheckt, geht der lokale Waggon darin auf. Der MR zeigt dann den Arbeitsstand (gitlab.eigener_arbeitsstand).

def eigene_mrs():
    """Offene eigene MRs mit Akte und Klon: {(Klon real, Quell-Branch): MR-Waggon}."""
    out = {}
    for p in glob.glob(os.path.join(DATEN, MR_ART.ordner, "*.json")):
        try:
            akte = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m, meta = akte.get("mr") or {}, akte.get("meta") or {}
        ordner = (struktur_laden(akte) or {}).get("ordner") or akte.get("klon")
        if not (m.get("iid") and m.get("source_branch") and ordner) or meta.get("state") not in (None, "opened"):
            continue
        mr = Waggon.aus_dict(m)
        if eigener_mr(mr):
            out[(os.path.realpath(ordner), m["source_branch"])] = mr
    return out


def zusammengelegt(wurzel, mrs=None):
    """Der eigene MR, dessen Quell-Branch im Klon wurzel ausgecheckt ist, sonst None. Zieht dabei die Fäden des lokalen
    Waggons zu diesem Branch in den MR um (einmal; danach gibt es nur noch einen Ort). mrs: eigene_mrs(), schon geholt."""
    branch = ausgecheckt(wurzel)
    mr = branch and (eigene_mrs() if mrs is None else mrs).get((os.path.realpath(wurzel), branch))
    if mr:
        faeden_umziehen(Waggon(lokal=projektname(wurzel)), mr, branch)
    return mr or None


def faeden_umziehen(lokal, mr, branch):
    """Fäden des lokalen Waggons zu branch in die Akte des MR (ids bleiben; erst dort eintragen, dann hier löschen).
    Rückgabe: Anzahl."""
    weg = [k for k in akte_lesen(lokal).get("kommentare") or [] if k.get("nachrichten") is not None and k.get("branch") == branch]
    if not weg:
        return 0
    with akte_bearbeiten(mr) as akte:
        da = {k.get("id") for k in akte.setdefault("kommentare", [])}
        akte["kommentare"] += [k for k in weg if k.get("id") not in da]
    ids = {k["id"] for k in weg}
    with akte_bearbeiten(lokal) as akte:
        akte["kommentare"] = [k for k in akte.get("kommentare") or [] if k.get("id") not in ids]
    melden(f"{mr.name}: {len(weg)} Faden/Fäden aus dem lokalen Waggon übernommen (eigener MR, ein Waggon)")
    return len(weg)


# ---- Branch ohne MR (docs/ein-waggon.md, Schritt 2): der lokale Waggon, ohne Kommentare der Quelle, mit Knopf
# „MR erstellen“. Erst fragen (mr_planen: gibt es schon einen MR, sonst mr_vorschlag in einen Dialog), dann pushen und
# anlegen (mr_erstellen). Danach ist es ein eigener MR, und Schritt 1 legt die Waggons zusammen.

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
    if ausgecheckt(wurzel) != branch:
        warnungen.append(f"{branch} ist nicht ausgecheckt: MR und lokaler Waggon bleiben getrennt, bis du ihn auscheckst.")
    return {"projekt": projekt, "quelle": branch, "ziel": ziel, "ziele": ziele, "titel": titel,
            "beschreibung": beschreibung, "commits": len(commits), "push": push, "push_text": push_text or "",
            "origin": origin, "warnungen": warnungen, "hindernisse": hindernisse, "host": gl[0], "gl_projekt": gl[1]}


def mr_planen(projekt):
    """Erster Klick auf „MR erstellen“: Gibt es in GitLab schon einen offenen MR zu diesem Branch, wird er übernommen
    (url: dorthin). Sonst der Vorschlag für den Dialog."""
    v = mr_vorschlag(projekt)
    da = mrs_zum_branch(v["host"], v["gl_projekt"], v["quelle"])
    if da:
        wurzel = projekt_wurzel(projekt)
        mr = mr_uebernehmen(da[0], wurzel)
        zusammengelegt(wurzel)
        return {"ok": True, "text": f"{mr.name} gibt es schon für {v['quelle']} – übernommen", "url": mr.url}
    return {"ok": True, "vorschlag": v}


def mr_erstellen(projekt, ziel, titel, beschreibung, entwurf=False):
    """Nach der Rückfrage: Quell-Branch pushen (wie im Vorschlag), MR anlegen, die Waggons zusammenlegen (ist der Branch
    ausgecheckt). Rückgabe für die Seite: ok, text, url des MR."""
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
    mr = mr_anlegen(v["host"], v["gl_projekt"], branch, ziel, titel, str(beschreibung or ""), wurzel)
    texte.append(f"{mr.name} erstellt ({branch} → {ziel})" + (" – ein Waggon mit dem lokalen" if zusammengelegt(wurzel) else ""))
    melden(" · ".join(texte))
    return {"ok": True, "text": " · ".join(texte), "url": mr.url}


class GitLab(Quelle):
    name, titel, art = "gitlab", "GitLab", MR_ART
    logo = "gitlab.svg"

    def ziel(self, waggon):
        """Ref des Zielbranchs im Klon (origin/<target_branch>, wie mr_lokal ihn nimmt)."""
        akte = akte_lesen(waggon)
        return ((struktur_laden(akte) or {}).get("refs") or {}).get("ziel") or (akte.get("mr") or {}).get("target_branch") or None

    def seite(self, waggon, ansicht=None):
        pfad, struktur, _ = mr_seite(waggon, ansicht=ansicht)
        return pfad, struktur

    def branch(self, waggon):
        """Branch der Fäden: der Quell-Branch des MR."""
        return akte_lesen(waggon)["mr"].get("source_branch") or None

    def ein_waggon(self, waggon):
        akte = akte_lesen(waggon)
        ordner, branch = (struktur_laden(akte) or {}).get("ordner") or akte.get("klon"), akte["mr"].get("source_branch")
        return bool(ordner and branch and os.path.isdir(ordner) and ausgecheckt(ordner) == branch and eigener_mr(waggon))

    def wagen(self, akt=None):
        return mr_wagen(akt)

    def stand_kurz(self, waggon, branch, head, wurzel):
        return f"MR {waggon.id} · Stand {head[:8]} · Klon {wurzel}"

    def zeilen_stand(self, waggon, head):
        if self.ein_waggon(waggon):
            return (f"den Arbeitsstand von {self.branch(waggon)} (auch nicht Committetes) – dein eigener MR: Wünsche dort "
                    "umsetzen und committen (pushen nur auf Bitte).")
        if eigener_mr(waggon):
            return (f"den Stand {head[:8]} im Klon – dein eigener MR: Wünsche auf {self.branch(waggon)} umsetzen und "
                    "committen (pushen nur auf Bitte).")
        return f"den Stand {head[:8]} im Klon (nichts ändern, nur antworten)."

    def prompt(self, waggon, wurzel):
        z = waggon.id
        tun = (f"Fragen beantworten, Änderungswünsche auf {self.branch(waggon)} umsetzen und committen (es ist der eigene "
               f"MR des Nutzers; pushen nur auf Bitte)" if eigener_mr(waggon) else
               "Beantworte sie anhand des Codes im Klon; den MR nicht ändern, nichts committen oder pushen")
        return (f"In merge-train liegen Fragen des Nutzers zum Merge-Request {waggon.name} (lokaler Klon: {wurzel}). "
                f"Hol sie mit `merge-train agent feedback {z}` ab. {tun}. Zu jedem Faden mit "
                f"`merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen {z}` (im Hintergrund, nach jeder Ausgabe neu) auf weitere Fragen warten.")


LOKAL, MYRLING, GITLAB = Lokal(), Myrling(), GitLab()


QUELLEN = (LOKAL, MYRLING, GITLAB)


QUELLE_JE_ART = {q.art: q for q in QUELLEN}


def quelle(waggon):
    return QUELLE_JE_ART[waggon.art]


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
                w = dict(w, quelle=q.name)
                if w.get("status") == "offen":  # Füllung aus den abgehakten Dateien (abhaken.py)
                    w["fuellung"] = akte_lesen(q.waggon_von(w["p"])).get("fuellung")
                wagen.append(w)
    return wagen
