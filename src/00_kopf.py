#!/usr/bin/env python3
"""merge-train – Merge-Requests claude → reviewed aller Projekte, sofort im Browser.
Dazu: Review von GitLab-Merge-Requests (über glab) mit Kommentaren und Agent-Hinweisen.

Aufruf:
  merge-train [projekt] [--nur-datei]                   lokaler Zug bzw. nur dieses Projekt
  merge-train <MR-URL> | '!42' | gruppe/projekt!42      GitLab-MR reviewen
  merge-train --mrs                                     Zug der MRs, bei denen ich Reviewer bin
  merge-train agent zeigen|pruefen <hinweise.json>      Agent-Hinweise zu einem MR (siehe docs/agent-hinweise.md)

Ein kleiner Server auf 127.0.0.1 baut die Seiten beim Abruf (wie der „Changes“-Reiter in GitLab): oben Güterbahnhof
und Zug, darunter Commits, links die Dateiliste, rechts die Diffs mit Syntaxhervorhebung.
Verglichen wird wie in GitLab ab dem gemeinsamen Vorgänger (reviewed...claude).

Tasten: j/k nächste/vorige Datei, i nebeneinander/inline, z alle zu/auf,
c Commits ein-/ausklappen, Enter fertig.

Einstellungen: ~/.config/merge-train/config.toml (Vorlage: config.example.toml).
"""
import argparse, difflib, glob, hashlib, html, json, os, re, shlex, shutil, subprocess, sys, threading, time
import urllib.parse
from datetime import datetime

try:
    from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
    from pygments.util import ClassNotFound
    from pygments import token as T
    PYGMENTS = True
except ImportError:
    PYGMENTS = False

