"""Der Waggon: ein Branch eines Repos (docs/branch-waggon.md) – ein GitLab-MR ist nur eine Schicht darauf – oder ein Lauf
des Myrlings, der auf eine Prüfung wartet (Skript gegen die zuletzt angesehene Fassung). Waggon ist sein Schlüssel;
daraus ergeben sich Kennung, Name, Dateiname und was er kann. von/bis eines lokalen Projekts (Ordners): von_bis."""
import re
import urllib.parse
from .einstellungen import ARBEITSSTAND, BIS, KONF, VON
from .akte import projekt_akte_lesen
from typing import NamedTuple, Optional


class Fehler(Exception):
    """Fehler mit einer Meldung für den Nutzer bzw. den Agenten (kein Programmfehler)."""


class Ungueltig(Fehler):
    """Ungültige Eingabe (Kennung, Parameter einer Anfrage): beim Server 400."""


def zweige_standard(projekt):
    """von/bis eines lokalen Projekts laut Einstellung: [zweige."<projekt>"] vor von/bis."""
    eigen = (KONF.get("zweige") or {}).get(projekt) or {}
    return eigen.get("von") or VON, eigen.get("bis") or BIS


def zweige_gewaehlt(projekt):
    """Auf der Seite (aufgeklappter Waggon) gewähltes {von, bis}, leer = Standard (in der Projekt-Akte des Ordners)."""
    return projekt_akte_lesen(projekt).get("zweige") or {}


def von_bis(projekt):
    """(von, bis) eines lokalen Projekts: auf der Seite gewählt vor der Einstellung (zweige_standard)."""
    von, bis = zweige_standard(projekt)
    g = zweige_gewaehlt(projekt)
    return g.get("von") or von, g.get("bis") or bis


def fertig_moeglich(projekt):
    """„fertig“ setzt den Branch von – nur bei lokalen Branches, nicht gegen origin/… oder den Arbeitsstand."""
    von, bis = von_bis(projekt)
    return bis != ARBEITSSTAND and not von.startswith(("origin/", "refs/remotes/"))


# ---- Arten von Waggons: was an der Art hängt und ohne Klon, Seite oder GitLab auskommt – Kennung, Seite, Dateiname,
# Akten-Ordner. Was ein Waggon kann, entscheidet seine Quelle (quellen.py). Alte Kennungen (projekt:<name>, MR-Kennung
# host/gruppe/projekt/42) lösen die Abkürzungen in ABKUERZUNGEN auf einen Branch auf.

class Art:
    """Art mit einem Feld des Waggons als Schlüssel."""
    feld = praefix = titel = None
    ordner = None  # Akten-Ordner unter DATEN

    def erkennt(self, d):
        """Gehört der Waggon (als dict: Feld „mr“ einer Akte, Waggon._asdict()) zu dieser Art?"""
        return bool(d.get(self.feld))

    def kann(self, w):
        from .quellen import quelle  # quellen braucht waggon
        return quelle(w).kann(w)


class BranchArt(Art):
    """Branch eines Repos: Kennung „<repo>@<branch>“ (repo = Projektpfad aus origin bzw. Projektname)."""
    feld, titel, ordner = "repo", "Branch", "zweige"

    def erkennt_kennung(self, kennung):
        return "@" in kennung and not kennung.startswith(("myrling:", "projekt:"))

    def aus_kennung(self, kennung):
        repo, _, branch = kennung.partition("@")
        if not repo or not branch or any(t in ("", ".", "..") for t in repo.split("/")) or ".." in branch.split("/"):
            raise Ungueltig(f"ungültige Branch-Kennung: {kennung}")
        return Waggon(repo=repo, branch=branch)

    def aus_dict(self, d):
        return Waggon(repo=d["repo"], branch=d["branch"])

    def als_dict(self, w):
        return {"repo": w.repo, "branch": w.branch}

    def id(self, w):
        return f"{w.repo}@{w.branch}"

    def name(self, w):
        return f"{w.repo.rsplit('/', 1)[-1]}@{w.branch}"

    def url(self, w):
        return "/b/" + urllib.parse.quote(self.id(w), safe="/@")

    def dateiname(self, w):
        return urllib.parse.quote(self.id(w), safe="")


class MyrlingArt(Art):
    """Myrling: der Agent im Repo des Skripts darf es ändern; die Entscheidung über den Lauf trifft der Nutzer."""
    feld, praefix, titel, ordner = "myrling", "myrling:", "Myrling", "myrling"

    def erkennt_kennung(self, kennung):
        return kennung.startswith(self.praefix)

    def aus_kennung(self, kennung):
        name = kennung[len(self.praefix):]
        if not (re.fullmatch(r"[\w][\w.+-]*", name) and ".." not in name):
            raise Ungueltig(f"ungültige Myrling-Kennung: {kennung}")
        return Waggon(myrling=name)

    def aus_dict(self, d):
        return Waggon(myrling=d["myrling"])

    def als_dict(self, w):
        return {"myrling": w.myrling}

    def id(self, w):
        return self.praefix + w.myrling

    def name(self, w):
        return w.myrling

    def url(self, w):
        return "/myrling/" + w.myrling

    def dateiname(self, w):
        return w.myrling


BRANCH_ART, MYRLING_ART = BranchArt(), MyrlingArt()
ARTEN = (MYRLING_ART, BRANCH_ART)


# Abkürzungen: kennung → Waggon oder None (nicht meine). Tragen ein: quellen.py (projekt:<name>), gitlab.py (MR).
ABKUERZUNGEN = []


class Waggon(NamedTuple):
    repo: Optional[str] = None     # Repo-Kennung (git.repo_kennung) – mit branch: ein Branch
    branch: Optional[str] = None
    myrling: Optional[str] = None  # oder ein Lauf des Myrlings: Name des Skripts (aus --anstehend)

    @classmethod
    def aus_id(cls, kennung):
        """Kennung (wie sie die Seite und der Agent nennen) → Waggon: „repo@branch“, „myrling:skript“ oder eine
        Abkürzung (projekt:<name>, MR-Kennung bzw. -URL)."""
        kennung = str(kennung)
        art = next((a for a in ARTEN if a.erkennt_kennung(kennung)), None)
        if art:
            return art.aus_kennung(kennung)
        for f in ABKUERZUNGEN:
            w = f(kennung)
            if w:
                return w
        raise Ungueltig(f"unbekannte Kennung: {kennung}")

    @classmethod
    def aus_dict(cls, d):
        """Aus dem Feld „mr“ einer Akte."""
        return next(a for a in ARTEN if a.erkennt(d)).aus_dict(d)

    @property
    def art(self):
        return next(a for a in ARTEN if a.erkennt(self._asdict()))

    def als_dict(self):
        return self.art.als_dict(self)

    @property
    def id(self):
        return self.art.id(self)

    @property
    def name(self):
        return self.art.name(self)

    @property
    def url(self):
        """Pfad der Seite auf dem Server."""
        return self.art.url(self)

    @property
    def dateiname(self):
        """Name (ohne Endung) für Dateien zu diesem Waggon."""
        return self.art.dateiname(self)

    @property
    def kann(self):
        """review    – hat eine Quellen-Schicht (MR): Review-Kommentare und Agent-Hinweise, „Review abschließen“
        fertig    – „fertig ✓“ setzt den Ziel-Branch auf den gesehenen Stand
        committen – der Agent darf Wünsche umsetzen und committen (sonst nur antworten)"""
        return self.art.kann(self)
