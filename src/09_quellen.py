# ---------------------------------------------------------------- Quellen: woher die Waggons kommen
# Ein Waggon ist ein Vergleich Quelle → Ziel in einem lokalen Klon. Quellen sind die lokalen Branches (BIS gegen VON in
# jedem Repo unter „projekte“) und GitLab-MRs; eine GitHub-Quelle wäre eine weitere Klasse. Der Zug mischt die Waggons
# aller eingeschalteten Quellen. Was ein Waggon kann, sagt seine Quelle (kann):
#   review    – Review-Kommentare und Agent-Hinweise, „Review abschließen“ überträgt sie nach außen
#   fertig    – „fertig ✓“ setzt den Ziel-Branch auf den gesehenen Stand
#   committen – der Agent darf Wünsche umsetzen und committen (sonst nur antworten)
# Das Gespräch mit Agenten gibt es überall. Schlüssel eines Waggons (g): {"lokal": projekt} bzw. {host, projekt, iid}.

class Lokal:
    name = "lokal"
    kann = {"review": False, "fertig": True, "committen": True}

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
        wurzel = g_wurzel(g["lokal"])
        if not wurzel:
            raise GitLabFehler(f'Projekt {g["lokal"]} nicht gefunden')
        head = (git(wurzel, "rev-parse", "--verify", "-q", BIS, check=False) or "").strip()
        if not head:
            raise GitLabFehler(f"Branch {BIS} fehlt in {wurzel}")
        return wurzel, head

    def seite(self, g, ansicht=None):
        wurzel = g_wurzel(g["lokal"])
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
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {g['lokal']} (Diff {BIS} gegen {VON}). "
                f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche auf {BIS} umsetzen und "
                f"committen; zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")

class GitLab:
    name = "gitlab"
    kann = {"review": True, "fertig": False, "committen": False}

    def an(self):
        return bool(KONF["gitlab"])

    def passt(self, x):
        return not Lokal.passt(None, x)

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

def wagen_daten(g, ansicht=None):
    """Alles, was die Seite über ihren Waggon braucht: Gespräch immer, Review (Kommentare, Hinweise) je nach Quelle."""
    q = quelle(g)
    gs = g_daten(g, ansicht)
    if not gs.get("ok"):
        return gs
    rv = review_daten(g, ansicht) if q.kann["review"] else \
        {"ok": True, "kommentare": [], "hinweise": [], "quellen": [], "ausstehend": 0, "ausserhalb": 0, "web_url": ""}
    with SPERRE:
        st = review_laden(g)
    return dict(rv, faeden=gs["kommentare"], g_ausstehend=gs["ausstehend"], horcht=gs["horcht"], todo=gs["todo"],
                agenten=gs["agenten"], kann=q.kann, stand=stand(g, st), ausserhalb=rv["ausserhalb"] + gs["ausserhalb"])
