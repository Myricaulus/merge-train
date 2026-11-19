"""Der Waggon: ein Vergleich Quelle → Ziel in einem lokalen Klon – ein lokales Projekt (Branch bis gegen von), ein
GitLab-Merge-Request oder ein Lauf des Myrlings, der auf eine Prüfung wartet (Skript gegen die zuletzt angesehene Fassung). Waggon ist sein Schlüssel; daraus ergeben sich Kennung, Name, Dateiname und was er kann.
von/bis eines lokalen Projekts: von_bis."""
import re
from .einstellungen import ARBEITSSTAND, BIS, KONF, VON, dateiname
from .akte import akte_lesen
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
    """Auf der Seite (aufgeklappter Waggon) gewähltes {von, bis}, leer = Standard."""
    return akte_lesen(Waggon(lokal=projekt)).get("zweige") or {}


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
# Akten-Ordner, Fähigkeiten. Die Quelle dazu (Klon, Seite, Zug, Prompt) steht in quellen.py und nennt ihre Art
# (Quelle.art). Eine neue Quelle (GitHub) bekommt hier eine weitere Art.

class Art:
    """Art mit einem Feld des Waggons als Schlüssel; Kennung „<praefix><schlüssel>“."""
    feld = praefix = titel = None
    ordner = None  # Akten-Ordner unter DATEN

    def erkennt(self, d):
        """Gehört der Waggon (als dict: Feld „mr“ einer Akte, Waggon._asdict()) zu dieser Art?"""
        return bool(d.get(self.feld))

    def erkennt_kennung(self, kennung):
        return kennung.startswith(self.praefix)

    def gueltig(self, name):
        raise NotImplementedError

    def aus_kennung(self, kennung):
        name = kennung[len(self.praefix):]
        if not self.gueltig(name):
            raise Ungueltig(f"ungültige {self.titel}-Kennung: {kennung}")
        return Waggon(**{self.feld: name})

    def aus_dict(self, d):
        return Waggon(**{self.feld: d[self.feld]})

    def als_dict(self, w):
        return {self.feld: getattr(w, self.feld)}

    def id(self, w):
        return self.praefix + getattr(w, self.feld)

    def name(self, w):
        return getattr(w, self.feld)


class LokalArt(Art):
    feld, praefix, titel, ordner = "lokal", "projekt:", "Projekt", "lokal"

    def gueltig(self, name):
        return name and not any(t in ("", ".", "..") for t in name.split("/"))

    def url(self, w):
        return "/" + dateiname(w.lokal)

    def dateiname(self, w):
        return dateiname(w.lokal)[:-5]

    def kann(self, w):
        return {"review": False, "fertig": fertig_moeglich(w.lokal), "committen": True}


class MyrlingArt(Art):
    """Myrling: der Agent im Repo des Skripts darf es ändern; die Entscheidung über den Lauf trifft der Nutzer."""
    feld, praefix, titel, ordner = "myrling", "myrling:", "Myrling", "myrling"

    def gueltig(self, name):
        return re.fullmatch(r"[\w][\w.+-]*", name) and ".." not in name

    def url(self, w):
        return "/myrling/" + w.myrling

    def dateiname(self, w):
        return w.myrling

    def kann(self, w):
        return {"review": False, "fertig": False, "committen": True}


class MrArt(Art):
    """Merge-Request: alles, was keine andere Art erkennt; Kennung „host/gruppe/projekt/42“."""
    titel, ordner = "MR", "reviews"

    def erkennt(self, d):
        return True

    def erkennt_kennung(self, kennung):
        return True

    def aus_kennung(self, kennung):
        teile = kennung.split("/")
        if len(teile) < 3 or not teile[-1].isdigit() or not re.fullmatch(r"[\w.:-]*", teile[0]) \
           or any(t in ("", ".", "..") for t in teile[1:-1]):
            raise Ungueltig(f"ungültige MR-Kennung: {kennung}")
        return Waggon(host=teile[0], projekt="/".join(teile[1:-1]), iid=int(teile[-1]))

    def aus_dict(self, d):
        return Waggon(host=d["host"], projekt=d["projekt"], iid=d["iid"])

    def als_dict(self, w):
        return {"host": w.host, "projekt": w.projekt, "iid": w.iid}

    def id(self, w):
        return f"{w.host}/{w.projekt}/{w.iid}"

    def name(self, w):
        return f"{w.projekt}!{w.iid}"

    def url(self, w):
        return "/mr/" + self.id(w)

    def dateiname(self, w):
        return re.sub(r"[^\w.-]", "_", f"{w.host or 'gitlab'}_{w.projekt}_{w.iid}")

    def kann(self, w):
        return {"review": True, "fertig": False, "committen": False}


LOKAL_ART, MYRLING_ART, MR_ART = LokalArt(), MyrlingArt(), MrArt()
ARTEN = (LOKAL_ART, MYRLING_ART, MR_ART)  # in dieser Reihenfolge gefragt: MR_ART nimmt den Rest


class Waggon(NamedTuple):
    lokal: Optional[str] = None    # Name des lokalen Projekts – oder der MR:
    host: Optional[str] = None     # None = Standardhost von glab
    projekt: Optional[str] = None  # gruppe/projekt
    iid: Optional[int] = None
    myrling: Optional[str] = None  # oder ein Lauf des Myrlings: Name des Skripts (nas-lauf --anstehend)

    @classmethod
    def aus_id(cls, kennung):
        """Kennung (wie sie die Seite und der Agent nennen) → Waggon. „projekt:name“ = lokales Projekt, sonst
        „myrling:skript“ = Lauf des Myrlings, sonst „host/gruppe/projekt/42“."""
        kennung = str(kennung)
        return next(a for a in ARTEN if a.erkennt_kennung(kennung)).aus_kennung(kennung)

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
    def ist_mr(self):
        return self.art is MR_ART

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
        """review    – Review-Kommentare und Agent-Hinweise, „Review abschließen“ überträgt sie nach GitLab
        fertig    – „fertig ✓“ setzt den Ziel-Branch auf den gesehenen Stand
        committen – der Agent darf Wünsche umsetzen und committen (sonst nur antworten)"""
        return self.art.kann(self)
