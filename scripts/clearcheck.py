#!/usr/bin/env python3
"""
clearcheck.py - the CLEAR-100 checker.

Scores text on four axes: Plain, Human, Structured, Dense.
Reads every rule from rules/clear-100.json. Stdlib only, no install step.

Usage:
  python3 scripts/clearcheck.py FILE [FILE...]
  python3 scripts/clearcheck.py FILE --profile social
  python3 scripts/clearcheck.py FILE --json
  python3 scripts/clearcheck.py FILE --gate 85 --strict
  cat draft.md | python3 scripts/clearcheck.py --stdin
  python3 scripts/clearcheck.py --explain H6
  python3 scripts/clearcheck.py --list-rules

Profiles: general (default), technical, social, agent.

Inline suppression, on the same line:
  clear: ignore            skips the whole line
  clear: ignore H1,P5      skips those rules on that line
  voice-lint: ignore       honored too, for personal-brand-os compatibility

Exit codes:
  0  passed the gate
  1  failed (an error-severity finding, or score below the gate)
  2  usage problem
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
RULES_PATH = HERE.parent / "rules" / "clear-100.json"

EM_DASH = "—"
EN_DASH = "–"
CURLY = ["“", "”", "‘", "’"]

SEV_ORDER = {"error": 0, "warn": 1, "review": 2}

# Terms that are jargon in a technical sentence and ordinary words elsewhere.
# Flagged as review so they never block a gate on a false positive.
LOW_CONFIDENCE_JARGON = {
    "agent", "token", "schema", "migration", "container", "canary", "funnel",
    "conversion", "churn", "runway", "burn", "cohort", "attribution", "inference",
    "attention", "surface", "regression", "immutable", "polling", "rollback",
}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_pack(path: pathlib.Path = RULES_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        pack = json.load(fh)
    pack["_rules_by_id"] = {r["id"]: r for r in pack["rules"]}
    pack["_rules_by_detector"] = {}
    for r in pack["rules"]:
        pack["_rules_by_detector"].setdefault(r["detector"], []).append(r)
    pack["_anchor_res"] = [re.compile(p) for p in pack["content_anchors"]["patterns"]]
    return pack


# --------------------------------------------------------------------------
# text model
# --------------------------------------------------------------------------

class Doc:
    """A markdown document split into what each rule needs to see."""

    FENCE = re.compile(r"^\s*(?:```|~~~)")
    FRONTMATTER = re.compile(r"^---\s*$")
    HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
    BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
    ORDERED = re.compile(r"^\s*\d+[.)]\s+")
    TABLE = re.compile(r"^\s*\|")

    def __init__(self, text: str, label: str = "<stdin>"):
        self.label = label
        self.raw = text
        self.lines = text.splitlines()
        self.prose_lines: list[tuple[int, str]] = []   # (lineno, text) prose only
        self.headings: list[tuple[int, int, str]] = []  # (lineno, level, text)
        self.blocks: list[dict] = []                    # paragraphs and list groups
        self.skip_lines: set[int] = set()               # code, tables, frontmatter
        self._parse()

    def _parse(self) -> None:
        in_fence = False
        in_front = False
        buf: list[tuple[int, str]] = []
        buf_kind = "para"

        def flush() -> None:
            nonlocal buf, buf_kind
            if buf:
                self.blocks.append({
                    "kind": buf_kind,
                    "start": buf[0][0],
                    "lines": list(buf),
                    "text": " ".join(t.strip() for _, t in buf).strip(),
                })
            buf = []
            buf_kind = "para"

        for i, line in enumerate(self.lines, start=1):
            if i == 1 and self.FRONTMATTER.match(line):
                in_front = True
                self.skip_lines.add(i)
                continue
            if in_front:
                self.skip_lines.add(i)
                if self.FRONTMATTER.match(line):
                    in_front = False
                continue
            if self.FENCE.match(line):
                in_fence = not in_fence
                self.skip_lines.add(i)
                flush()
                continue
            if in_fence:
                self.skip_lines.add(i)
                continue
            if self.TABLE.match(line):
                self.skip_lines.add(i)
                flush()
                continue

            h = self.HEADING.match(line)
            if h:
                flush()
                self.headings.append((i, len(h.group(1)), h.group(2).strip()))
                self.prose_lines.append((i, h.group(2).strip()))
                continue

            if not line.strip():
                flush()
                continue

            self.prose_lines.append((i, line))
            kind = "list" if self.BULLET.match(line) else "para"
            if buf and kind != buf_kind:
                flush()
            buf_kind = kind
            buf.append((i, line))

        flush()

    # -- helpers ---------------------------------------------------------

    def paragraphs(self) -> list[dict]:
        return [b for b in self.blocks if b["kind"] == "para"]

    def list_lines(self) -> set[int]:
        out: set[int] = set()
        for b in self.blocks:
            if b["kind"] == "list":
                out.update(ln for ln, _ in b["lines"])
        return out

    def ordered_list_lines(self) -> set[int]:
        return {i for i, t in self.prose_lines if self.ORDERED.match(t)}

    def prose_text(self) -> str:
        return "\n".join(t for _, t in self.prose_lines)


# --------------------------------------------------------------------------
# sentence and word plumbing
# --------------------------------------------------------------------------

ABBREV = {"e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "st", "fig", "no", "approx", "al"}
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+")
WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
INLINE_CODE = re.compile(r"`[^`]*`")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BOLD = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF⬀-⯿←-⇿✀-➿]"
)


def split_sentences(text: str) -> list[str]:
    text = MD_LINK.sub(r"\1", text)
    parts = SENT_SPLIT.split(text)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if out:
            tail = WORD.findall(out[-1][-12:])
            if tail and tail[-1].lower() in ABBREV:
                out[-1] = out[-1] + " " + p
                continue
        out.append(p)
    return out


def words(text: str) -> list[str]:
    return WORD.findall(INLINE_CODE.sub(" ", text))


def syllables(word: str) -> int:
    w = word.lower().strip("'’-")
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    n = len(re.findall(r"[aeiouy]{1,2}", w))
    return max(1, n)


def flesch(text: str) -> tuple[float, float, int, int]:
    sents = split_sentences(text)
    ws = words(text)
    if not sents or not ws:
        return 0.0, 0.0, 0, 0
    syl = sum(syllables(w) for w in ws)
    wps = len(ws) / len(sents)
    spw = syl / len(ws)
    ease = 206.835 - 1.015 * wps - 84.6 * spw
    grade = 0.39 * wps + 11.8 * spw - 15.59
    return round(ease, 1), round(grade, 1), len(ws), len(sents)


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

class Finding(dict):
    pass


def make(rule: dict, line: int, match: str, note: str = "", col: int = 1,
         severity: str | None = None) -> Finding:
    return Finding({
        "rule": rule["id"],
        "axis": rule["axis"],
        "severity": severity or rule["severity"],
        "title": rule["title"],
        "line": line,
        "col": col,
        "match": match[:120],
        "note": note,
        "fix": rule.get("fix", ""),
        "weight": rule.get("weight", 1),
    })


def suppressed(line_text: str) -> tuple[bool, set[str]]:
    m = re.search(r"(?:clear|voice-lint):\s*ignore(?:\s+([A-Za-z0-9,\s]+))?", line_text)
    if not m:
        return False, set()
    if not m.group(1) or not m.group(1).strip():
        return True, set()
    ids = {x.strip().upper() for x in m.group(1).split(",") if x.strip()}
    return False, ids


# --------------------------------------------------------------------------
# the checker
# --------------------------------------------------------------------------

class Checker:
    def __init__(self, pack: dict, profile: str = "general"):
        self.pack = pack
        self.profile_name = profile
        if profile not in pack["profiles"]:
            raise SystemExit(f"clearcheck: unknown profile '{profile}'")
        self.p = pack["profiles"][profile]
        self.R = pack["_rules_by_id"]

    # -- anchors ---------------------------------------------------------

    def has_anchor(self, text: str) -> bool:
        return any(r.search(text) for r in self.pack["_anchor_res"])

    # -- main ------------------------------------------------------------

    def run(self, doc: Doc) -> dict:
        f: list[Finding] = []
        f += self._regex_rules(doc)
        f += self._lexicon_rules(doc)
        f += self._substitutions(doc)
        f += self._openers(doc)
        f += self._punctuation(doc)
        f += self._sentence_rules(doc)
        f += self._jargon(doc)
        f += self._acronyms(doc)
        f += self._noun_clusters(doc)
        f += self._stiffness(doc)
        f += self._structure(doc)
        f += self._headings(doc)
        f += self._density(doc)
        stats = self._stats(doc)
        f += self._doc_level(doc, stats)

        line_map = {i: t for i, t in doc.prose_lines}
        kept: list[Finding] = []
        for item in f:
            txt = line_map.get(item["line"], "")
            whole, ids = suppressed(txt)
            if whole or item["rule"] in ids:
                continue
            kept.append(item)

        kept.sort(key=lambda x: (SEV_ORDER[x["severity"]], x["line"]))
        return {
            "file": doc.label,
            "profile": self.profile_name,
            "stats": stats,
            "findings": kept,
            **self._score(kept, stats),
        }

    # -- rule families ---------------------------------------------------

    def _iter_prose(self, doc: Doc):
        for lineno, text in doc.prose_lines:
            yield lineno, INLINE_CODE.sub(" ", text)

    def _iter_clean(self, doc: Doc):
        """Prose with code, link targets, and bare URLs removed.

        Acronym and noun-stack checks would otherwise flag every domain name.
        """
        for lineno, text in doc.prose_lines:
            clean = INLINE_CODE.sub(" ", text)
            clean = MD_LINK.sub(r"\1", clean)
            clean = re.sub(r"https?://\S+|\b[\w.-]+\.(?:com|org|net|io|dev|gov|uk|ai)\b", " ", clean)
            yield lineno, clean

    def _regex_rules(self, doc: Doc) -> list[Finding]:
        out = []
        for rule in self.pack["_rules_by_detector"].get("regex", []):
            rx = re.compile(rule["pattern"], re.I if "i" in rule.get("flags", "") else 0)
            for lineno, text in self._iter_prose(doc):
                for m in rx.finditer(text):
                    out.append(make(rule, lineno, m.group(0), col=m.start() + 1))
        return out

    def _lexicon_rules(self, doc: Doc) -> list[Finding]:
        out = []
        specs = [
            ("H1", "slop_words", "slop_word_exceptions"),
            ("H2", "slop_phrases", None),
            ("H9", "promo_words", "promo_word_exceptions"),
            ("H12", "assistant_voice", None),
        ]
        for rid, key, exc_key in specs:
            rule = self.R[rid]
            terms = sorted(self.pack[key], key=len, reverse=True)
            exceptions = self.pack.get(exc_key or "", {}) or {}
            rx = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)
            for lineno, text in self._iter_prose(doc):
                low = text.lower()
                for m in rx.finditer(text):
                    hit = m.group(1).lower()
                    ok = exceptions.get(hit) or []
                    window = low[max(0, m.start() - 20):m.end() + 20]
                    if any(e in window for e in ok):
                        continue
                    note = ""
                    if rid == "H1":
                        swap = self.pack.get("slop_replacements", {}).get(hit)
                        if swap:
                            note = f'say "{swap}", or say the specific thing'
                    out.append(make(rule, lineno, m.group(1), note=note, col=m.start() + 1))
        return out

    def _substitutions(self, doc: Doc) -> list[Finding]:
        rule = self.R["P5"]
        subs = self.pack["substitutions"]
        rx = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(subs, key=len, reverse=True)) + r")\b", re.I)
        out = []
        for lineno, text in self._iter_clean(doc):
            for m in rx.finditer(text):
                key = m.group(1).lower()
                out.append(make(rule, lineno, m.group(1),
                                note=f"use \"{subs[key]}\"", col=m.start() + 1))
        return out

    def _openers(self, doc: Doc) -> list[Finding]:
        rule = self.R["H3"]
        openers = self.pack["banned_openers"]
        rx = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)?(" + "|".join(re.escape(o) for o in openers) + r")\b[,:]?", re.I)
        out = []
        for lineno, text in doc.prose_lines:
            stripped = text.strip()
            m = rx.match(stripped)
            if m:
                out.append(make(rule, lineno, m.group(1)))
                continue
            for s in split_sentences(stripped)[1:]:
                m2 = re.match(r"(" + "|".join(re.escape(o) for o in openers) + r")\b[,:]?", s, re.I)
                if m2:
                    out.append(make(rule, lineno, m2.group(1)))
        return out

    def _punctuation(self, doc: Doc) -> list[Finding]:
        out = []
        h4, h5 = self.R["H4"], self.R["H5"]
        for lineno, text in doc.prose_lines:
            for m in re.finditer(re.escape(EM_DASH), text):
                out.append(make(h4, lineno, EM_DASH, note="em-dash", col=m.start() + 1))
            for m in re.finditer(r" " + re.escape(EN_DASH) + r" ", text):
                out.append(make(h4, lineno, EN_DASH, note="spaced en-dash", col=m.start() + 1))
            for ch in CURLY:
                for m in re.finditer(re.escape(ch), text):
                    out.append(make(h5, lineno, ch, note="curly quote", col=m.start() + 1))
        return out

    def _sentence_rules(self, doc: Doc) -> list[Finding]:
        rule = self.R["P1"]
        warn, err = self.p["sentence_words_warn"], self.p["sentence_words_error"]
        out = []
        for block in doc.blocks:
            for lineno, text in block["lines"]:
                for s in split_sentences(INLINE_CODE.sub(" ", text)):
                    n = len(words(s))
                    if n > err:
                        out.append(make(rule, lineno, s[:80], note=f"{n} words, cap is {err}",
                                        severity="error"))
                    elif n > warn:
                        out.append(make(rule, lineno, s[:80], note=f"{n} words, target is under {warn}"))
        return out

    def _jargon(self, doc: Doc) -> list[Finding]:
        rule = self.R["P6"]
        if self.profile_name == "agent":
            return []
        jargon = self.pack["jargon"]
        text = doc.prose_text()
        low = text.lower()
        out = []
        for term, gloss in jargon.items():
            if len(term) <= 3 and term.isupper():
                continue  # acronyms are P7's job
            m = re.search(r"\b" + re.escape(term.lower()) + r"\b", low)
            if not m:
                continue
            window = low[m.end():m.end() + 160]
            glossed = (
                "(" in window[:40]
                or re.search(r"^\s*[,:]?\s*(?:which means|which is|that is|meaning|i\.e\.|in other words)", window)
                or any(w in window for w in words(gloss.lower())[:3] if len(w) > 4)
            )
            if glossed:
                continue
            lineno = low[:m.start()].count("\n") + 1
            real_line = doc.prose_lines[min(lineno - 1, len(doc.prose_lines) - 1)][0]
            sev = "review" if term in LOW_CONFIDENCE_JARGON else None
            out.append(make(rule, real_line, term, note=f'gloss it: "{gloss}"', severity=sev))
        return out

    def _acronyms(self, doc: Doc) -> list[Finding]:
        rule = self.R["P7"]
        if self.profile_name == "agent":
            return []
        common = set(self.pack["common_acronyms"])
        seen: set[str] = set()
        out = []
        for lineno, text in self._iter_clean(doc):
            for m in re.finditer(r"\b([A-Z]{2,6})(?:s)?\b", text):
                a = m.group(1)
                if a in common or a in seen or a.lower() in ("i",):
                    continue
                seen.add(a)
                after = text[m.end():m.end() + 80]
                before = text[max(0, m.start() - 90):m.start()]
                if "(" in after[:6] or ")" in before[-3:]:
                    continue
                initials = "".join(w[0].upper() for w in words(before)[-len(a):])
                if initials == a:
                    continue
                gloss = self.pack["jargon"].get(a)
                note = f'expand it{f": {gloss}" if gloss else ""}'
                out.append(make(rule, lineno, a, note=note, col=m.start() + 1))
        return out

    def _noun_clusters(self, doc: Doc) -> list[Finding]:
        rule = self.R["P9"]
        cap = self.p["noun_cluster_max"]
        stop = set("""the a an and or but if then so of to in on at by for with from as is are was were be been
        being this that these those it its he she they we you i not no all any each more most some such than
        very can will would should could may might must do does did done have has had here there when where
        which who whom whose what how why also just only over under after before while during about into out
        up down off again once because both few other own same too new now every either neither much
        less least many few enough one two three own via per else still yet ever never""".split())
        stop |= set("""carry make take give get read write run build ship need want know tell show keep
        hold find help work look come go use add cut put let say see mean matter fit feel think turn move
        stay start stop call name pick drop break fix test check count track send load save open close
        pass fail wait learn teach ask answer pay cost sell buy hire join leave meet talk speak play
        win lose try begin end grow fall rise push pull throw catch live""".split())
        verbish = re.compile(r"(?:ing|ed|s)$")
        out = []
        for lineno, text in self._iter_clean(doc):
            toks = re.findall(r"\b[a-z][a-z-]{2,}\b", text)
            run: list[str] = []
            for t in toks + ["."]:
                if t != "." and t not in stop and not verbish.search(t):
                    run.append(t)
                    continue
                if len(run) > cap:
                    out.append(make(rule, lineno, " ".join(run), note=f"{len(run)} nouns in a row"))
                run = []
        return out

    def _stiffness(self, doc: Doc) -> list[Finding]:
        rule = self.R["P11"]
        if self.profile_name == "agent":
            return []
        text = doc.prose_text()
        expanded = len(re.findall(
            r"\b(?:do not|does not|did not|cannot|can not|will not|is not|are not|it is|that is|you are|we are|"
            r"there is|they are|you will|we will|i am)\b", text, re.I))
        contracted = len(re.findall(r"\b\w+(?:'|’)(?:t|s|re|ve|ll|d|m)\b", text))
        if expanded >= 4 and contracted == 0:
            return [make(rule, doc.prose_lines[0][0] if doc.prose_lines else 1,
                         f"{expanded} expanded forms, 0 contractions",
                         note="reads formal, which reads synthetic")]
        return out_empty()

    def _structure(self, doc: Doc) -> list[Finding]:
        out = []
        s1, s2, s3, s4, s5, s8, s9 = (self.R[k] for k in ("S1", "S2", "S3", "S4", "S5", "S8", "S9"))
        h7 = self.R["H7"]
        list_lines = doc.list_lines()
        ordered = doc.ordered_list_lines()

        # S1 / H7: comma series
        series = re.compile(r"([A-Za-z][\w'’-]*(?:\s+[\w'’-]+){0,3}(?:,\s+[\w'’-]+(?:\s+[\w'’-]+){0,3}){1,},?\s+(?:and|or)\s+[\w'’-]+(?:\s+[\w'’-]+){0,3})")
        for lineno, text in self._iter_prose(doc):
            if lineno in list_lines:
                continue
            for m in series.finditer(text):
                chunk = m.group(1)
                items = [x.strip() for x in re.split(r",\s*|\s+(?:and|or)\s+", chunk) if x.strip()]
                if len(items) < 3:
                    continue
                short = all(len(words(x)) <= 2 for x in items)
                if len(items) >= 4:
                    out.append(make(s1, lineno, chunk[:90], note=f"{len(items)} parallel items"))
                elif len(items) == 3 and short:
                    out.append(make(h7, lineno, chunk[:90], note="three-item cadence"))
        # S2: step sequences in prose
        step = re.compile(r"\b(?:first|then|next|after that|finally|lastly)\b", re.I)
        for b in doc.paragraphs():
            hits = len(step.findall(b["text"]))
            if hits >= 2 and not (set(ln for ln, _ in b["lines"]) & ordered):
                out.append(make(s2, b["start"], b["text"][:90], note=f"{hits} sequence markers, no numbered list"))
        # S3: comparison prose
        comp = re.compile(r"\b(?:whereas|while|compared to|versus|vs\.?|on the other hand|by contrast)\b", re.I)
        for b in doc.paragraphs():
            if len(comp.findall(b["text"])) >= 2 and len(split_sentences(b["text"])) >= 2:
                out.append(make(s3, b["start"], b["text"][:90], note="two or more comparisons in prose"))
        # S4 / S5: paragraph size and topic count
        for b in doc.paragraphs():
            sents = split_sentences(b["text"])
            if len(sents) > self.p["paragraph_sentences_warn"]:
                out.append(make(s4, b["start"], b["text"][:70],
                                note=f"{len(sents)} sentences, cap is {self.p['paragraph_sentences_warn']}"))
            if len(b["text"]) > self.p["paragraph_chars_warn"]:
                out.append(make(s4, b["start"], b["text"][:70],
                                note=f"{len(b['text'])} chars in one block"))
            props = set(re.findall(r"\b[A-Z][a-z]{2,}(?:[A-Z][a-z]+)?\b", b["text"][1:]))
            if len(sents) >= 4 and len(props) >= 3:
                out.append(make(s5, b["start"], ", ".join(sorted(props)[:4]),
                                note="several topics in one paragraph"))
        # S8: bold density
        all_words = len(words(doc.prose_text()))
        bold_words = sum(len(words(m.group(1) or m.group(2) or "")) for m in BOLD.finditer(doc.prose_text()))
        if all_words >= 60:
            ratio = bold_words / all_words
            if ratio > self.p["bold_ratio_warn"]:
                out.append(make(s8, 1, f"{bold_words}/{all_words} words bold",
                                note=f"{ratio:.1%} bold, cap is {self.p['bold_ratio_warn']:.0%}"))
        # S9: emoji as structure
        for lineno, text in doc.prose_lines:
            t = text.strip()
            if EMOJI.match(t) or (t.startswith(("-", "*", "+")) and EMOJI.match(t[1:].strip() or " ")):
                out.append(make(s9, lineno, t[:40], note="emoji leading a line"))
            elif t.startswith("#") and EMOJI.search(t):
                out.append(make(s9, lineno, t[:40], note="emoji in a heading"))
        return out

    def _headings(self, doc: Doc) -> list[Finding]:
        out = []
        s6, s7 = self.R["S6"], self.R["S7"]
        prev_level = 0
        prev_line = -2
        for lineno, level, text in doc.headings:
            if prev_level and level > prev_level + 1:
                out.append(make(s6, lineno, "#" * level + " " + text[:40],
                                note=f"h{prev_level} jumped to h{level}"))
            if prev_line == lineno - 1:
                out.append(make(s6, lineno, text[:40], note="heading directly under a heading"))
            ws = [w for w in words(text) if w]
            if len(ws) >= 3:
                caps = [w for w in ws[1:] if w[0].isupper() and not w.isupper()]
                if len(caps) >= 2 and len(caps) / max(1, len(ws) - 1) > 0.5:
                    out.append(make(s7, lineno, text[:60], note="Title Case heading"))
            prev_level, prev_line = level, lineno
        return out

    def _density(self, doc: Doc) -> list[Finding]:
        out = []
        d1, d2, d3, d4, d5 = (self.R[k] for k in ("D1", "D2", "D3", "D4", "D5"))

        # D3: the first real sentence
        first = None
        for lineno, text in doc.prose_lines:
            if text.strip().startswith("#"):
                continue
            sents = split_sentences(text)
            if sents and len(words(sents[0])) >= 4:
                first = (lineno, sents[0])
                break
        if first and not self.has_anchor(first[1]):
            out.append(make(d3, first[0], first[1][:90], note="no number, name, or claim in line one"))

        # D1: sentence-level delete test.
        # Density is a paragraph property. A short sentence inside an anchored
        # paragraph is rhythm, not filler, so only long orphans get flagged.
        flagged = 0
        list_lines = doc.list_lines()
        for b in doc.paragraphs():
            para_anchored = self.has_anchor(b["text"])
            for lineno, raw in b["lines"]:
                if raw.strip().startswith("#") or lineno in list_lines:
                    continue
                for s in split_sentences(raw):
                    n = len(words(s))
                    if n < 10 or s.rstrip().endswith(":"):
                        continue
                    if self.has_anchor(s):
                        continue
                    if para_anchored and n < 16:
                        continue
                    flagged += 1
                    if flagged <= 8:
                        out.append(make(d1, lineno, s[:90],
                                        note="nothing here a reader could not guess"))
        if flagged > 8:
            out.append(make(d1, 1, f"{flagged} sentences with no anchor",
                            note="showing the first 8"))

        # D2: restatement
        for b in doc.blocks:
            sents = split_sentences(b["text"])
            for a, bb in zip(sents, sents[1:]):
                wa = {w.lower() for w in words(a) if len(w) > 3}
                wb = {w.lower() for w in words(bb) if len(w) > 3}
                if len(wa) >= 4 and len(wb) >= 4:
                    j = len(wa & wb) / len(wa | wb)
                    if j > 0.55:
                        out.append(make(d2, b["start"], bb[:90], note=f"{j:.0%} overlap with the sentence before"))

        # D4: horoscope paragraphs
        for b in doc.paragraphs():
            sents = split_sentences(b["text"])
            if len(sents) >= 3 and len(words(b["text"])) >= 40 and not self.has_anchor(b["text"]):
                out.append(make(d4, b["start"], b["text"][:90], note="could be about anything"))

        # D5: filler
        fillers = sorted(self.pack["filler_words"], key=len, reverse=True)
        rx = re.compile(r"\b(" + "|".join(re.escape(f) for f in fillers) + r")\b", re.I)
        total = max(1, len(words(doc.prose_text())))
        hits = 0
        for lineno, text in self._iter_prose(doc):
            for m in rx.finditer(text):
                hits += 1
                if hits <= 15:
                    out.append(make(d5, lineno, m.group(1), col=m.start() + 1))
        if total >= 80 and hits / total > self.p["filler_ratio_warn"]:
            out.append(make(d5, 1, f"{hits}/{total} filler words",
                            note=f"{hits/total:.1%}, cap is {self.p['filler_ratio_warn']:.1%}"))
        return out

    def _stats(self, doc: Doc) -> dict:
        prose = doc.prose_text()
        ease, grade, nwords, nsents = flesch(prose)
        lens = [len(words(s)) for b in doc.blocks for s in split_sentences(b["text"])]
        lens = [n for n in lens if n]
        return {
            "words": nwords,
            "sentences": nsents,
            "paragraphs": len(doc.paragraphs()),
            "headings": len(doc.headings),
            "reading_ease": ease,
            "grade_level": grade,
            "avg_sentence_words": round(statistics.mean(lens), 1) if lens else 0,
            "sentence_stdev": round(statistics.pstdev(lens), 2) if len(lens) > 1 else 0.0,
        }

    def _doc_level(self, doc: Doc, stats: dict) -> list[Finding]:
        out = []
        p8, h13, s10 = self.R["P8"], self.R["H13"], self.R["S10"]
        g = stats["grade_level"]
        if stats["words"] >= 60:
            if g > self.p["grade_error"]:
                out.append(make(p8, 1, f"grade {g}", severity="error",
                                note=f"target is {self.p['grade_target']}, hard cap {self.p['grade_error']}"))
            elif g > self.p["grade_target"]:
                out.append(make(p8, 1, f"grade {g}", note=f"target is {self.p['grade_target']}"))
        if stats["sentences"] >= 8 and self.p["sentence_length_stdev_min"] > 0:
            if stats["sentence_stdev"] < self.p["sentence_length_stdev_min"]:
                out.append(make(h13, 1, f"stdev {stats['sentence_stdev']}",
                                note=f"needs {self.p['sentence_length_stdev_min']}+, sentences are too even"))
        if stats["words"] >= self.p["tldr_required_words"]:
            head = doc.prose_text()[:600].lower()
            if not re.search(r"\b(tl;dr|tldr|in one line|the short version|short answer|bottom line)\b", head):
                first_para = doc.paragraphs()[0]["text"] if doc.paragraphs() else ""
                if not self.has_anchor(first_para):
                    out.append(make(s10, 1, f"{stats['words']} words, no lead answer",
                                    note="open with the conclusion in 1 to 3 lines"))
        return out

    # -- scoring ---------------------------------------------------------

    def _score(self, findings: list[Finding], stats: dict) -> dict:
        mult = self.pack["scoring"]["severity_multiplier"]
        axis_pen: dict[str, float] = {a: 0.0 for a in self.pack["axes"]}
        for f in findings:
            axis_pen[f["axis"]] += f["weight"] * mult[f["severity"]]
        # Longer pieces get proportional slack: the same five warnings mean
        # less in a 2000-word article than in a tweet.
        size = max(1.0, stats["words"] / 250.0)
        axis_scores = {}
        for name in self.pack["axes"]:
            pen = axis_pen[name] / size
            axis_scores[name] = max(0, round(100 - pen * 2.5, 1))
        total = round(sum(axis_scores[a] * self.pack["axes"][a]["weight"] for a in axis_scores) / 100.0, 1)
        band = next(b for b in self.pack["scoring"]["grade_bands"] if total >= b["min"])
        return {
            "axis_scores": axis_scores,
            "score": total,
            "band": band["label"],
            "verdict": band["verdict"],
            "counts": {
                s: sum(1 for f in findings if f["severity"] == s) for s in ("error", "warn", "review")
            },
        }


def out_empty() -> list[Finding]:
    return []


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

COLORS = {"error": "\033[31m", "warn": "\033[33m", "review": "\033[36m", "off": "\033[0m",
          "bold": "\033[1m", "dim": "\033[2m", "green": "\033[32m"}


def render(result: dict, color: bool = True, max_findings: int = 40, quiet: bool = False) -> str:
    def c(key: str, s: str) -> str:
        return f"{COLORS[key]}{s}{COLORS['off']}" if color else s

    st, ax = result["stats"], result["axis_scores"]
    lines = [
        "",
        c("bold", f"{result['file']}") + c("dim", f"  profile={result['profile']}"),
        f"  CLEAR {c('bold', str(result['score']))}/100  band {result['band']}  {result['verdict']}",
        "  " + "  ".join(f"{k[:5].capitalize()} {v}" for k, v in ax.items()),
        c("dim", f"  {st['words']} words, {st['sentences']} sentences, grade {st['grade_level']}, "
                 f"ease {st['reading_ease']}, avg {st['avg_sentence_words']}w, stdev {st['sentence_stdev']}"),
        c("dim", f"  {result['counts']['error']} error, {result['counts']['warn']} warn, "
                 f"{result['counts']['review']} review"),
    ]
    if not quiet:
        lines.append("")
        for f in result["findings"][:max_findings]:
            head = f"  {result['file']}:{f['line']}:{f['col']}"
            tag = c(f["severity"], f"{f['severity']:<6}")
            note = f"  {c('dim', f['note'])}" if f["note"] else ""
            lines.append(f"{head}  {tag} {f['rule']:<3} {f['title']}{note}")
            if f["match"]:
                lines.append(c("dim", f"        > {f['match']}"))
        extra = len(result["findings"]) - max_findings
        if extra > 0:
            lines.append(c("dim", f"  ... {extra} more, use --max-findings 0 for all"))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="clearcheck", description="CLEAR-100 checker")
    ap.add_argument("paths", nargs="*", help="files to check")
    ap.add_argument("--profile", default="general", help="general | technical | social | agent")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--gate", type=float, default=None, help="minimum score to pass")
    ap.add_argument("--strict", action="store_true", help="any finding fails, not just errors")
    ap.add_argument("--stdin", action="store_true", help="read the document from stdin")
    ap.add_argument("--only", default=None, help="limit to one axis: plain|human|structured|dense")
    ap.add_argument("--ignore", default="", help="comma-separated rule ids to skip")
    ap.add_argument("--explain", default=None, help="print one rule in full and exit")
    ap.add_argument("--list-rules", action="store_true")
    ap.add_argument("--max-findings", type=int, default=40, help="0 for all")
    ap.add_argument("--quiet", action="store_true", help="scores only")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--rules", default=str(RULES_PATH), help="path to the rule pack")
    a = ap.parse_args(argv)

    pack = load_pack(pathlib.Path(a.rules))

    if a.list_rules:
        for r in pack["rules"]:
            print(f"{r['id']:<4} {r['severity']:<6} {r['axis']:<10} {r['title']}")
        return 0

    if a.explain:
        r = pack["_rules_by_id"].get(a.explain.upper())
        if not r:
            print(f"no rule {a.explain}", file=sys.stderr)
            return 2
        print(f"{r['id']}  {r['title']}  [{r['axis']}, {r['severity']}, weight {r['weight']}]\n")
        print(f"Why:  {r['why']}\nFix:  {r['fix']}")
        if r.get("bad"):
            print(f"\nBad:  {r['bad']}")
        if r.get("good"):
            print(f"Good: {r['good']}")
        return 0

    docs: list[Doc] = []
    if a.stdin:
        docs.append(Doc(sys.stdin.read(), "<stdin>"))
    for p in a.paths:
        path = pathlib.Path(p)
        if not path.is_file():
            print(f"clearcheck: not a file: {p}", file=sys.stderr)
            return 2
        docs.append(Doc(path.read_text(encoding="utf-8"), p))
    if not docs:
        ap.print_usage()
        return 2

    checker = Checker(pack, a.profile)
    ignore = {x.strip().upper() for x in a.ignore.split(",") if x.strip()}
    gate = a.gate if a.gate is not None else pack["scoring"]["gate_default"]

    results = []
    for d in docs:
        r = checker.run(d)
        if ignore:
            r["findings"] = [f for f in r["findings"] if f["rule"] not in ignore]
        if a.only:
            r["findings"] = [f for f in r["findings"] if f["axis"] == a.only]
        r["counts"] = {s: sum(1 for f in r["findings"] if f["severity"] == s)
                       for s in ("error", "warn", "review")}
        r["gate"] = gate
        r["passed"] = r["score"] >= gate and r["counts"]["error"] == 0 and not (
            a.strict and r["findings"])
        results.append(r)

    if a.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    else:
        mf = a.max_findings if a.max_findings > 0 else 10 ** 6
        for r in results:
            print(render(r, color=not a.no_color and sys.stdout.isatty(),
                         max_findings=mf, quiet=a.quiet))
        print("")

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
