"""Review pages: one self-contained HTML file per gate, to read on a phone and answer in the chat.

Usage:
  ./pal board paper  <ep>    the paper edit: what is cut, in the transcript, with the A-cut audio
  ./pal board story  <ep>    the storyboard: lanes, one card per beat, music, captions, shots to collect
  ./pal board draft  <ep>    the draft: where it is, the checks in plain words, beats with times
  ./pal board shorts <ep>    candidate Shorts moments (build/review/shorts.json)
  ./pal board thumbs <ep>    thumbnail options at feed size (build/out/thumbs/*.jpg)
  ./pal board all    <ep>    every page whose inputs exist

Writes build/review/<kind>.html. Images and audio are inside the file (no network, works offline,
works with JavaScript off). Missing inputs are named on the page together with the command that
makes them. Exit code 0 even then; 2 for wrong usage.
"""
import base64
import bisect
import glob
import html
import io
import json
import os
import re
import sys

import common

LIMIT_WARN = 14e6
LANG_NAMES = {"en": "English", "fa": "Persian", "de": "German", "fr": "French", "es": "Spanish", "ar": "Arabic"}
LAYOUTS = ["full", "pip", "split", "lower-third", "over"]

CSS = """
:root{--bg:#fafaf7;--fg:#1c1c1e;--mut:#6b6b73;--card:#fff;--line:#dcdcd4;--acc:#2457d6;--on:#ffe9a8;--bad:#b3261e;--ok:#1b7a3d;--rm:#fde4e1}
@media(prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececf0;--mut:#9a9aa6;--card:#1e1e22;--line:#34343b;--acc:#8fb0ff;--on:#5a4a10;--bad:#ff8f87;--ok:#7bd89a;--rm:#4a2220}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans","Noto Naskh Arabic",sans-serif;padding:0 16px 150px;max-width:760px;margin:auto}
h1{font-size:1.5rem;margin:1.2rem 0 .2rem}h2{font-size:1.2rem;margin:2rem 0 .5rem;border-top:1px solid var(--line);padding-top:1rem}
.sub{color:var(--mut);margin:0 0 1rem}.box{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:12px 0}
.how{border-left:4px solid var(--acc)}.how b{display:block;margin-bottom:4px}.how code{white-space:normal}
code,.id{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em;background:var(--line);padding:1px 6px;border-radius:5px}
.miss{border:1px dashed var(--bad);color:var(--bad);border-radius:12px;padding:10px 14px;margin:12px 0}
.warn{background:var(--on);border-radius:10px;padding:8px 12px;margin:10px 0}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:6px 12px}
.stat b{display:block;font-size:1.15rem}
audio{width:100%;margin:6px 0}
p.tx{margin:.5rem 0}.ts{color:var(--mut);font-size:.8rem;margin-right:6px;font-family:ui-monospace,monospace}
.w{cursor:pointer}.w.now{background:var(--on);border-radius:3px}
.rm{text-decoration:line-through;background:var(--rm);color:var(--mut);border-radius:3px}
.rm.flip{text-decoration:none;background:none;color:inherit}
.sg{border-bottom:2px dashed var(--mut);color:var(--mut)}.sg.flip{text-decoration:line-through;background:var(--rm)}
.prot{border-bottom:2px solid var(--ok)}
.chip{display:inline-block;font-size:.78rem;border:1px solid var(--line);background:var(--card);border-radius:999px;padding:3px 10px;margin:2px 4px;font-family:inherit;color:var(--fg);vertical-align:baseline}
button.chip{cursor:pointer;min-height:34px}.chip.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.chip.sugg{border-style:dashed}.chip.prot{border-color:var(--ok);color:var(--ok);background:var(--card)}
.why{display:inline-block;font-size:.85rem;color:var(--mut);margin:0 4px}.js .why{display:none}.js .why.open{display:inline-block}
.ctl{display:none}.js .ctl{display:inline-block}.js .ctl.row{display:flex;flex-wrap:wrap;gap:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:14px 0;scroll-margin-top:12px}
.card h3{margin:0 0 6px;font-size:1.05rem;display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.card img.still{width:100%;border-radius:8px;display:block;margin:6px 0}
.row2{display:flex;gap:12px;align-items:flex-start}.row2 svg{flex:0 0 76px}
.said{color:var(--mut);font-size:.92rem;margin:6px 0}.kv{font-size:.92rem;margin:4px 0}
svg text{fill:var(--fg);font-family:system-ui,sans-serif}.lane{fill:var(--line);opacity:.35}
.dia rect,.dia path,.dia line{stroke:var(--fg);fill:none;stroke-width:1.2}.dia .f{fill:var(--acc);opacity:.5}
table{border-collapse:collapse;width:100%;font-size:.92rem}td,th{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left;vertical-align:top}
.grid{display:grid;grid-template-columns:1fr;gap:12px}
.thumb{background-size:cover;background-position:center;border-radius:6px;border:1px solid var(--line)}
.t320{width:320px;max-width:100%;aspect-ratio:16/9}.t168{width:168px;aspect-ratio:16/9}
.feed{display:flex;gap:10px;align-items:flex-start;margin:6px 0}.feed .ttl{font-size:.85rem;line-height:1.25;max-width:150px}
#bar{display:none;position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);padding:8px 12px;display:flex;gap:8px;justify-content:center;align-items:center;z-index:9}
body.js #bar,.js #bar{display:flex}#bar button{font:inherit;font-weight:600;min-height:48px;border-radius:12px;border:1px solid var(--acc);background:var(--acc);color:#fff;padding:0 16px}
#bar button.sec{background:none;color:var(--acc)}#nowt{font-size:.85rem;color:var(--mut)}
textarea,input[type=text]{width:100%;font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:8px}
textarea{min-height:64px}.addrow{display:flex;gap:6px}.addrow input:first-child{width:90px}
@media(min-width:900px){body{max-width:860px}.grid{grid-template-columns:1fr 1fr}}
"""

JS = r"""
(function(){var D=document;D.documentElement.classList.add('js');var extra=[];
function q(s){return D.querySelectorAll(s)}
function upd(){var t=[];q('[data-tok].on').forEach(function(e){t.push(e.dataset.tok)});t=t.concat(extra);
 var f=D.getElementById('free');if(f&&f.value.trim())t.push(f.value.trim());
 D.getElementById('out').value=t.join(', ');D.getElementById('cnt').textContent=t.length;return t.join(', ')}
D.addEventListener('click',function(e){var el=e.target.closest('[data-tok]');
 if(el){var g=el.dataset.grp,was=el.classList.contains('on');
  if(g)q('[data-grp="'+g+'"]').forEach(function(x){x.classList.remove('on')});
  if(!was)el.classList.add('on');else el.classList.remove('on');
  var c=el.dataset.c;if(c)q('[data-c="'+c+'"]').forEach(function(x){x.classList.toggle('flip',el.classList.contains('on'))});
  upd();return}
 var ch=e.target.closest('.chip[data-why]');if(ch){var w=D.getElementById(ch.dataset.why);if(w)w.classList.toggle('open');return}
 var wd=e.target.closest('[data-t]');var a=D.getElementById('acut');
 if(wd&&a){a.currentTime=parseFloat(wd.dataset.t);a.play();return}
 if(e.target.id==='copy'){var s=upd();var o=D.getElementById('out');
  try{navigator.clipboard.writeText(s).then(function(){e.target.textContent='Copied'},function(){o.select();D.execCommand('copy');e.target.textContent='Copied'})}
  catch(x){o.select();try{D.execCommand('copy')}catch(y){}e.target.textContent='Copied'}
  setTimeout(function(){e.target.innerHTML='Copy my notes (<span id=cnt>'+q('[data-tok].on').length+'</span>)';upd()},1500);return}
 if(e.target.id==='clr'){q('[data-tok].on').forEach(function(x){x.click()});extra=[];rl();upd();return}
 if(e.target.id==='nadd'){var tt=D.getElementById('nt').value.trim(),nn=D.getElementById('nn').value.trim();
  if(tt||nn){extra.push((tt+' '+nn).trim());D.getElementById('nt').value='';D.getElementById('nn').value='';rl();upd()}return}
 if(e.target.dataset.rm){extra.splice(+e.target.dataset.rm,1);rl();upd()}});
function rl(){var l=D.getElementById('nlist');if(!l)return;l.innerHTML='';
 extra.forEach(function(x,i){var s=D.createElement('div');s.textContent=x+' ';var b=D.createElement('button');b.className='chip';b.textContent='remove';b.dataset.rm=i;s.appendChild(b);l.appendChild(s)})}
var f=D.getElementById('free');if(f)f.addEventListener('input',upd);upd();
var a=D.getElementById('acut');if(a){var ws=[].slice.call(q('.w[data-t]')).sort(function(x,y){return x.dataset.t-y.dataset.t});
 var ts=ws.map(function(x){return +x.dataset.t}),cur=null,nt=D.getElementById('nowt');
 a.addEventListener('timeupdate',function(){var i=bs(ts,a.currentTime);if(cur)cur.classList.remove('now');cur=ws[i]||null;if(cur)cur.classList.add('now');
  if(nt){var m=Math.floor(a.currentTime/60),s=Math.floor(a.currentTime%60);nt.textContent='A-cut '+m+':'+(s<10?'0':'')+s}})}
function bs(arr,v){var lo=0,hi=arr.length-1,r=-1;while(lo<=hi){var m=(lo+hi)>>1;if(arr[m]<=v){r=m;lo=m+1}else hi=m-1}return r}
})();
"""


# ---------------------------------------------------------------- small helpers

def esc(s):
    """HTML-escape any value."""
    return html.escape(str(s), quote=True)


def mmss(t):
    """Seconds as m:ss (h:mm:ss over an hour)."""
    t = int(round(max(0.0, float(t))))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def parse_tc(s):
    """'3:41' or '1:02:03' or '95' -> seconds, or None."""
    try:
        p = [float(x) for x in str(s).strip().split(":")]
    except ValueError:
        return None
    return sum(v * 60 ** i for i, v in enumerate(reversed(p)))


class Page:
    """Collects the body of one page and its media; final HTML is built by render()."""

    def __init__(self, kind, ep, title, how):
        self.kind, self.ep, self.title, self.how = kind, ep, title, how
        self.parts, self.assets, self.warnings, self.missing = [], [], [], []

    def add(self, s):
        self.parts.append(s)

    def asset(self, mime, data, label, droppable=False):
        """Register media; returns a placeholder that render() swaps for a data: URI."""
        self.assets.append({"mime": mime, "data": data, "label": label, "drop": droppable})
        return f"@@A{len(self.assets) - 1}@@"

    def need(self, what, cmd):
        """Say on the page that an input is missing and which command makes it."""
        self.missing.append((what, cmd))
        self.add(f'<div class="miss">Missing: {esc(what)}. Make it with <code>{esc(cmd)}</code>.</div>')

    def render(self):
        total = sum(len(a["data"]) * 4 // 3 for a in self.assets)
        drop = set()
        for i in sorted((i for i, a in enumerate(self.assets) if a["drop"]), key=lambda i: -len(self.assets[i]["data"])):
            if total <= LIMIT_WARN:
                break
            total -= len(self.assets[i]["data"]) * 4 // 3
            drop.add(i)
            self.warnings.append(f"Left out the audio “{self.assets[i]['label']}” to keep this page small; it is in build/.")
        body = "\n".join(self.parts)
        for i, a in enumerate(self.assets):
            ph = f"@@A{i}@@"
            if i in drop:
                body = re.sub(r'<audio[^>]*src="' + ph + r'"[^>]*></audio>', f'<div class="miss">Audio left out (page too big): {esc(a["label"])}</div>', body)
            else:
                body = body.replace(ph, f"data:{a['mime']};base64,{base64.b64encode(a['data']).decode()}")
        warn = "".join(f'<div class="warn">{esc(w)}</div>' for w in self.warnings)
        howbox = f'<div class="box how"><b>How to reply</b>{self.how}</div>'
        notes = ('<h2>Your reply</h2><p class="sub">Tap items above (with JavaScript on), or just type here. '
                 'Then paste into the chat.</p><textarea id="free" placeholder="anything else, in your own words" dir="auto"></textarea>'
                 '<textarea id="out" readonly aria-label="reply text"></textarea>')
        bar = ('<div id="bar"><span id="nowt"></span><button id="copy" class="ctl">Copy my notes (<span id="cnt">0</span>)</button>'
               '<button id="clr" class="sec ctl">Clear</button></div>')
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<meta name="color-scheme" content="light dark"><title>{esc(self.title)}</title><style>{CSS}</style></head><body>'
                f'<h1>{esc(self.title)}</h1>{howbox}{warn}{body}{notes}{bar}<script>{JS}</script></body></html>')


# ---------------------------------------------------------------- media encoding (cached)

def _cache_path(ep, key, ext):
    d = os.path.join(ep, "build", "review", ".cache")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{key}.{ext}")


def _stamp(path):
    st = os.stat(path)
    return [os.path.abspath(path), st.st_size, st.st_mtime_ns]


def image_bytes(ep, path, maxw=480, quality=70):
    """A JPEG of the image at `path`, at most maxw wide (cached)."""
    cp = _cache_path(ep, common.sha("img", _stamp(path), maxw, quality), "jpg")
    if not os.path.exists(cp):
        from PIL import Image
        im = Image.open(path)
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, (30, 30, 34))
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im = im.convert("RGB")
        if im.width > maxw:
            im = im.resize((maxw, max(1, round(im.height * maxw / im.width))))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        with open(cp, "wb") as f:
            f.write(buf.getvalue())
    with open(cp, "rb") as f:
        return f.read()


def audio_bytes(ep, path, kbps=24, start=None, dur=None):
    """Small mono AAC (m4a) of the audio at `path`, optionally just a span (cached)."""
    cp = _cache_path(ep, common.sha("aud", _stamp(path), kbps, start, dur), "m4a")
    if not os.path.exists(cp):
        cmd = ["ffmpeg", "-i", path] if start is None else ["ffmpeg", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", path]
        common.run(cmd + ["-vn", "-ac", "1", "-ar", "22050", "-c:a", "aac", "-b:a", f"{kbps}k", "-movflags", "+faststart", cp + ".m4a"])
        os.replace(cp + ".m4a", cp)
    with open(cp, "rb") as f:
        return f.read()


def img_tag(page, path, maxw=480, cls="still", alt=""):
    """<img> with the image inside the page, or '' when the file is missing."""
    if not path or not os.path.exists(path):
        return ""
    return f'<img class="{cls}" alt="{esc(alt)}" src="{page.asset("image/jpeg", image_bytes(page.ep, path, maxw), alt)}">'


def audio_tag(page, path, label, kbps=24, start=None, dur=None, ident=None, droppable=True):
    """<audio controls> with the audio inside the page."""
    ref = page.asset("audio/mp4", audio_bytes(page.ep, path, kbps, start, dur), label, droppable)
    return f'<audio {"id=" + ident if ident else ""} controls preload="none" src="{ref}"></audio>'


# ---------------------------------------------------------------- reading the episode

class Ep:
    """Lazy access to the episode's files (any may be missing -> None / empty)."""

    def __init__(self, ep):
        self.ep = ep
        self.ch = common.channel()
        self.edit = self.j("edit.json")
        self.plan = self.j("plan.json")
        self.raw = self.j("transcript.raw.json")
        self.tr = self.j("transcript.json")
        self.sources = self.j("sources.json")
        self.words = {w["id"]: w for w in (self.tr or {}).get("words", [])}
        self.order = [w["id"] for w in (self.tr or {}).get("words", [])]

    def j(self, name):
        p = os.path.join(self.ep, name)
        return common.load(p) if os.path.exists(p) else None

    def p(self, *parts):
        return os.path.join(self.ep, *parts)

    def has(self, *parts):
        return os.path.exists(self.p(*parts))

    @property
    def slug(self):
        return os.path.basename(self.ep)

    def title(self, what):
        name = self.ch.get("name") or ""
        return f"{name} · {what}" if name else what

    def acut_len(self):
        """Length of the edited video in seconds (media if present, else the sum of kept ranges)."""
        for f in ("build/cut/acut.mp4", "build/cut/voice.wav"):
            if self.has(f):
                return common.duration(self.p(f))
        if self.edit and self.edit.get("keep"):
            return sum(k["out"] - k["in"] for k in self.edit["keep"])
        return (self.tr or {}).get("duration") or 0.0

    def beat_t(self, b):
        """[start, end] of a beat on the edited timeline, from `t` or from its word anchors."""
        if b.get("t"):
            return b["t"]
        a, u = self.words.get(b.get("anchor")), self.words.get(b.get("until"))
        if a:
            return [a["start"], (u or a)["end"] if u else a["start"] + 3.0]
        return None

    def beat_words(self, b, limit=40):
        """The spoken words under a beat."""
        if b.get("anchor") in self.words:
            i = self.order.index(b["anchor"])
            j = self.order.index(b["until"]) if b.get("until") in self.words else i + 12
            ids = self.order[i:j + 1]
        elif b.get("t") and self.words:
            ids = [w for w in self.order if b["t"][0] - 0.05 <= self.words[w]["start"] < b["t"][1]]
        else:
            return ""
        txt = " ".join(self.words[w]["w"] for w in ids[:limit])
        return txt + (" …" if len(ids) > limit else "")


def how_box(lines):
    """The 3-line 'how to reply' box: each line is (words, meaning)."""
    items = "".join(f"<div><code>{esc(a)}</code> {esc(b)}</div>" for a, b in lines)
    return ("<div>Tap what you want to change, then <b style='display:inline'>Copy my notes</b> and paste it in the chat. "
            "No JavaScript? Type the words yourself:</div>" + items)


# ---------------------------------------------------------------- paper

def chip_label(r):
    return f"{r['id']} {r.get('kind', '')} · {max(0.0, r['out'] - r['in']):.1f} s"


def build_paper(E):
    ch = E.ch
    pg = Page("paper", E.ep, E.title("Paper edit"), how_box([
        ("keep C012", "put a cut back"), ("cut C045", "accept a suggestion"),
        ("C007 looser / C007 tighter", "more or less air at a cut"),
        ("cut 3:41-3:55  ·  restore \"words\"  ·  lock", "cut a time span, bring words back, or approve")]))
    ed = E.edit
    if not ed:
        pg.need("the cut (edit.json)", f"./pal cut propose {E.slug}")
        return pg
    keep, rem, prot = ed.get("keep", []), ed.get("removed", []), ed.get("protect", [])
    after = sum(k["out"] - k["in"] for k in keep)
    src_len = (E.raw or {}).get("duration") or ((E.sources or {}).get("sources", {}).get((E.sources or {}).get("master"), {}).get("duration"))
    cuts = [r for r in rem if r.get("kind") != "suggest" and r.get("ok", True)]
    sugg = [r for r in rem if r.get("kind") == "suggest"]
    before = src_len or (after + sum(r["out"] - r["in"] for r in cuts))
    kinds = {}
    for r in cuts:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    stats = f'<div class="stat"><b>{mmss(before)} → {mmss(after)}</b>length, before → after</div>'
    stats += f'<div class="stat"><b>{len(cuts)}</b>cuts</div>' + "".join(f'<div class="stat"><b>{n}</b>{esc(k)}</div>' for k, n in sorted(kinds.items()))
    if sugg:
        stats += f'<div class="stat"><b>{len(sugg)}</b>ideas, not cut yet</div>'
    pg.add(f'<div class="stats">{stats}</div>')
    pg.add("<h2>Listen</h2>")
    if pg.ep and E.has("build/cut/voice.wav"):
        pg.add('<div class="box">The A-cut, voice only (tap a word below to jump there)'
               + audio_tag(pg, E.p("build/cut/voice.wav"), "A-cut voice", ident="acut") + "</div>")
        if E.has("build/cut/voice.raw.wav"):
            t0 = min(max(0.0, after * 0.25), max(0.0, after - 10))
            d = min(10.0, after)
            pg.add('<div class="box">Same 10 seconds, before and after cleaning the voice'
                   + "<div>Before (raw)</div>" + audio_tag(pg, E.p("build/cut/voice.raw.wav"), "raw 10 s", 32, t0, d, droppable=False)
                   + "<div>After (cleaned)</div>" + audio_tag(pg, E.p("build/cut/voice.wav"), "cleaned 10 s", 32, t0, d, droppable=False) + "</div>")
    else:
        pg.need("the A-cut audio (build/cut/voice.wav)", f"./pal cut render {E.slug}")
    if E.has("build/review/seam-reel.m4a"):
        pg.add('<div class="box">Seam reel: 3 seconds around every cut, one after another, numbered in order. Listen for clicks, '
               "cut-off words and odd pauses." + audio_tag(pg, E.p("build/review/seam-reel.m4a"), "seam reel", 32) + "</div>")
    else:
        pg.add(f'<div class="miss">No seam reel yet. Make it with <code>./pal sheet reel {esc(E.slug)}</code>.</div>')
    pg.add("<h2>What is cut</h2>")
    pg.add('<p class="sub">Struck through = removed. Dashed = only an idea, not cut. Tap a tag to see why; use the button to change it.</p>')
    if not E.raw:
        pg.need("the transcript (transcript.raw.json)", f"./pal transcribe {E.slug}")
        pg.add(paper_table(E, cuts + sugg))
    else:
        pg.add(paper_text(pg, E, rem, prot))
    return pg


def paper_table(E, rem):
    """Fallback list of the removals when there is no transcript."""
    rows = "".join(
        f'<tr><td><span class="id">{esc(r["id"])}</span></td><td>{mmss(r["in"])}</td><td>{esc(r.get("kind"))} · {r["out"] - r["in"]:.1f} s</td>'
        f'<td dir="auto">{esc(r.get("text", ""))} <i>{esc(r.get("why", ""))}</i></td></tr>' for r in rem)
    return f"<table>{rows}</table>"


def to_acut_fn(E):
    """Function: source time -> A-cut time (None when the time is not kept)."""
    starts, acc = [], 0.0
    for k in E.edit.get("keep", []):
        starts.append((k["in"], k["out"], acc))
        acc += k["out"] - k["in"]

    def f(t):
        for a, b, s in starts:
            if a - 1e-6 <= t < b:
                return s + t - a
        return None
    return f


def paper_text(pg, E, rem, prot):
    """The transcript on the source timeline with removals struck through."""
    raw = E.raw
    words = raw.get("words", [])
    segs = raw.get("segments") or []
    if not segs:
        segs, cur = [], []
        for i, w in enumerate(words):
            if cur and (w["start"] - words[i - 1]["end"] > 0.8 or len(cur) >= 25):
                segs.append({"first": cur[0]["id"], "last": cur[-1]["id"]})
                cur = []
            cur.append(w)
        if cur:
            segs.append({"first": cur[0]["id"], "last": cur[-1]["id"]})
    idx = {w["id"]: i for i, w in enumerate(words)}
    mids = [(w["start"] + w["end"]) / 2 for w in words]
    rs = sorted(rem, key=lambda r: r["in"])
    ins = [r["in"] for r in rs]
    to_a = to_acut_fn(E)
    pr = []
    for p in prot:
        if p.get("first") in idx and p.get("last") in idx:
            pr.append((idx[p["first"]], idx[p["last"]], p.get("kind", "")))
    # a word inside a kept range by its id is kept, whatever the transcriber's timing says
    # (word times can sit a little late, inside the following silence)
    kept_ix = set()
    for k in (E.edit or {}).get("keep", []):
        a, b = idx.get(k.get("first")), idx.get(k.get("last"))
        if a is not None and b is not None:
            kept_ix.update(range(a, b + 1))
    emitted, nxt = set(), 0
    out = []

    def chip(r):
        sug = r.get("kind") == "suggest"
        kept = r.get("ok") is False
        rid = "why-" + r["id"]
        flag = (r.get("seam") or {}).get("flag")
        lab = chip_label(r) + (" · kept" if kept else "")
        h = f'<button class="chip{" sugg" if sug else ""}" data-why="{rid}" type="button">{"⚠ " if flag else ""}{esc(lab)}</button>'
        reason = esc(r.get("why") or r.get("text") or "")
        if flag:
            reason += f' <b>⚠ seam: {esc(flag)}</b>'
        act = ""
        if sug:
            act = f'<button class="chip ctl" data-tok="cut {esc(r["id"])}" data-c="{esc(r["id"])}" type="button">cut it?</button>'
        elif not kept:
            act = f'<button class="chip ctl" data-tok="keep {esc(r["id"])}" data-c="{esc(r["id"])}" type="button">keep it</button>'
            act += (f'<button class="chip ctl" data-tok="{esc(r["id"])} looser" type="button">looser</button>'
                    f'<button class="chip ctl" data-tok="{esc(r["id"])} tighter" type="button">tighter</button>')
        img = ""
        sp = next(iter(sorted(glob.glob(E.p("build/review/seams", f"seam-*-{r['id']}.png")))), "")
        if flag and sp:
            img = f'<br>{img_tag(pg, sp, 640, "still", "seam " + r["id"])}'
        return h + f'<span class="why" id="{rid}">{reason}{act}{img}</span>'

    def flush(upto):
        nonlocal nxt
        while nxt < len(rs) and rs[nxt]["in"] <= upto:
            r = rs[nxt]
            nxt += 1
            if r["id"] not in emitted:
                emitted.add(r["id"])
                out.append(chip(r))

    for sg in segs:
        i0, i1 = idx.get(sg["first"]), idx.get(sg["last"])
        if i0 is None or i1 is None:
            continue
        out.append(f'<p class="tx" dir="auto"><a class="ts">{mmss(words[i0]["start"])}</a>')
        for i in range(i0, i1 + 1):
            w = words[i]
            flush(mids[i])
            k = bisect.bisect_right(ins, mids[i]) - 1
            r = rs[k] if k >= 0 and mids[i] < rs[k]["out"] and i not in kept_ix else None
            for a, b, kind in pr:
                if i == a:
                    out.append(f'<span class="chip prot">protected · {esc(kind)}</span>')
            cls = ["w"]
            attrs = ""
            if r:
                cls = ["rm" if r.get("kind") != "suggest" else "sg"]
                if r.get("ok") is False:
                    cls.append("flip")
                attrs = f' data-c="{esc(r["id"])}"'
            else:
                ta = E.words[w["id"]]["start"] if w["id"] in E.words else to_a(w["start"])
                if ta is not None:
                    attrs = f' data-t="{ta:.2f}"'
            if any(a <= i <= b for a, b, _ in pr):
                cls.append("prot")
            out.append(f'<span class="{" ".join(cls)}"{attrs}>{esc(w["w"])}</span> ')
        out.append("</p>")
    flush(1e12)
    return "".join(out)


# ---------------------------------------------------------------- story

def diagram(layout):
    """Tiny 64x36 drawing of a layout."""
    bodies = {
        "full": '<rect class="f" x="3" y="3" width="58" height="30"/>',
        "pip": '<rect class="f" x="3" y="3" width="58" height="30"/><rect x="42" y="21" width="16" height="10" fill="var(--card)"/>',
        "split": '<rect class="f" x="3" y="3" width="29" height="30"/><circle cx="48" cy="15" r="6"/>',
        "lower-third": '<circle cx="32" cy="14" r="7"/><rect class="f" x="6" y="24" width="30" height="6"/>',
        "over": '<circle cx="32" cy="18" r="8"/><rect class="f" x="40" y="6" width="18" height="10"/>',
        "punch": '<rect x="3" y="3" width="58" height="30" stroke-dasharray="3 2"/><rect class="f" x="14" y="8" width="36" height="20"/>',
        "b-roll": '<rect class="f" x="3" y="3" width="58" height="30"/><path d="M27 12 L27 24 L39 18 Z"/>',
        "card": '<rect x="3" y="3" width="58" height="30"/><line x1="16" y1="14" x2="48" y2="14"/><line x1="22" y1="22" x2="42" y2="22"/>',
    }
    return f'<svg class="dia" viewBox="0 0 64 36" width="76" height="43" aria-label="{esc(layout)}"><rect x="1" y="1" width="62" height="34" rx="3"/>{bodies.get(layout, "")}</svg>'


def fmt_dur(s):
    s = int(round(s))
    return f"{s // 60} min {s % 60} s" if s >= 60 else f"{s} s"


def lanes_svg(E, beats, total):
    """The whole video as lanes: one row each for A-roll, B-roll, graphics, captions, music, effects."""
    W, LW, H = 520, 56, 26
    names = ["A-roll", "B-roll", "Graphics", "Captions", "Music", "Effects"]
    sx = (W - LW - 6) / max(total, 1.0)
    X = lambda t: LW + t * sx
    out = [f'<svg viewBox="0 0 {W} {len(names) * H + 34}" width="100%" role="img" aria-label="timeline of the whole video">']
    for i, n in enumerate(names):
        y = 28 + i * H
        out.append(f'<rect class="lane" x="{LW}" y="{y}" width="{W - LW - 6}" height="{H - 4}" rx="3"/><text x="4" y="{y + 16}" font-size="12">{n}</text>')
    acc = 0.0
    for k in (E.edit or {}).get("keep", []):
        d = k["out"] - k["in"]
        out.append(f'<rect x="{X(acc):.1f}" y="32" width="{max(1.5, d * sx - 1):.1f}" height="{H - 12}" fill="var(--acc)" opacity="{0.35 if k.get("angle") else 0.7}"/>')
        acc += d
    if not (E.edit or {}).get("keep"):
        out.append(f'<rect x="{X(0):.1f}" y="32" width="{total * sx:.1f}" height="{H - 12}" fill="var(--acc)" opacity=".5"/>')
    for b in beats:
        t = E.beat_t(b)
        if not t:
            continue
        lay = b.get("layout")
        row, col = {"b-roll": (1, "#d6892b"), "punch": (5, "#8a5cd6"), "over": (2, "#2e9c6a"), "lower-third": (2, "#2e9c6a")}.get(lay, (2, "#2e9c6a"))
        y = 28 + row * H + 4
        out.append(f'<a href="#{esc(b["id"])}"><rect x="{X(t[0]):.1f}" y="{y}" width="{max(4, (t[1] - t[0]) * sx):.1f}" height="{H - 12}" rx="2" fill="{col}"><title>{esc(b["id"])} {esc(lay)}</title></rect></a>')
        for s in b.get("sfx", []) or []:
            out.append(f'<line x1="{X(t[0] + s.get("at", 0)):.1f}" x2="{X(t[0] + s.get("at", 0)):.1f}" y1="{28 + 5 * H + 4}" y2="{28 + 5 * H + H - 8}" stroke="var(--fg)" stroke-width="2"/>')
    cap = (E.plan or {}).get("captions", {})
    out.append(f'<rect x="{X(0):.1f}" y="{28 + 3 * H + 4}" width="{total * sx:.1f}" height="{H - 12}" fill="{"var(--acc)" if cap.get("burn") else "none"}" stroke="var(--mut)" stroke-dasharray="{"" if cap.get("burn") else "4 3"}" opacity=".6"/>')
    for m in (E.plan or {}).get("music", []):
        t = m.get("t") or [0, total]
        out.append(f'<rect x="{X(t[0]):.1f}" y="{28 + 4 * H + 4}" width="{max(3, (t[1] - t[0]) * sx):.1f}" height="{H - 12}" rx="2" fill="#c2569a" opacity=".7"><title>{esc(m.get("id"))}</title></rect>')
        out.append(f'<text x="{X(t[0]) + 3:.1f}" y="{28 + 4 * H + 17}" font-size="11" fill="#fff" style="fill:#fff">{esc(m.get("id", ""))}</text>')
    for r in (E.plan or {}).get("redact", []):
        out.append(f'<rect x="{X(r["t"][0]):.1f}" y="{28 + 5 * H + 4}" width="{max(3, (r["t"][1] - r["t"][0]) * sx):.1f}" height="{H - 12}" fill="var(--bad)" opacity=".7"><title>redact</title></rect>')
    for s in (E.plan or {}).get("sections", []):
        a = E.words.get(s.get("anchor"))
        if a:
            out.append(f'<line x1="{X(a["start"]):.1f}" x2="{X(a["start"]):.1f}" y1="14" y2="{28 + len(names) * H}" stroke="var(--mut)" stroke-dasharray="2 3"/>'
                       f'<text x="{X(a["start"]) + 3:.1f}" y="11" font-size="12">{esc(s.get("id", ""))}</text>')
    step = next(x for x in (30, 60, 120, 300, 600, 1200, 3600) if total / x <= 7)
    for t in range(0, int(total) + 1, step):
        out.append(f'<text x="{X(t):.1f}" y="{28 + len(names) * H + 12}" font-size="12" text-anchor="middle">{mmss(t)}</text>')
    out.append("</svg>")
    return "".join(out)


def text_lines(txt):
    """The on-screen text of a beat, one line per language."""
    rows = []
    for lang, d in (txt or {}).items():
        body = " · ".join(f"{k}: {v}" for k, v in d.items()) if isinstance(d, dict) else str(d)
        rows.append(f'<div class="kv" dir="auto"><b>{esc(lang)}</b> {esc(body)}</div>')
    return "".join(rows)


def build_story(E):
    pg = Page("story", E.ep, E.title("Storyboard"), how_box([
        ("B07 pip", "change a layout: full, pip, split, lower-third or over"),
        ("B09 drop  ·  B12 move to \"words\"  ·  B05 text: …", "remove a beat, move it, change its words"),
        ("M2  ·  no music  ·  no sfx  ·  captions on  ·  go", "pick the music, effects, captions; go = build it")]))
    plan = E.plan
    if not plan:
        pg.need("the plan (plan.json)", "ask Claude to write the plan: `/plan` (beats, music, captions)")
        return pg
    beats = plan.get("beats", [])
    total = E.acut_len() or max([(E.beat_t(b) or [0, 0])[1] for b in beats] + [60])
    kit = sum(1 for b in beats if (b.get("plate") or {}).get("type") == "kit")
    cust = sum(1 for b in beats if (b.get("plate") or {}).get("type") == "custom")
    est = sum(b.get("est_render_s", 0) for b in beats)
    stats = (f'<div class="stat"><b>{mmss(total)}</b>video length</div><div class="stat"><b>{kit + cust}</b>plates ({kit} kit, {cust} custom)</div>'
             f'<div class="stat"><b>{len(beats)}</b>beats</div><div class="stat"><b>{fmt_dur(est) if est else "?"}</b>estimated plate render time</div>')
    pg.add(f'<div class="stats">{stats}</div>')
    if not E.words:
        pg.add(f'<div class="miss">Missing: the edited transcript (transcript.json), so beat times and spoken words may be blank. Make it with <code>./pal cut remap {esc(E.slug)}</code>.</div>')
    pg.add("<h2>The whole video</h2><p class=sub>Blue = the speaker, green = graphics, orange = B-roll, purple = zooms, pink = music, red = hidden areas. Tap a block to jump to its card.</p>")
    pg.add(f'<div class="box">{lanes_svg(E, beats, total)}</div>')
    pg.add("<h2>Beat by beat</h2>")
    for b in beats:
        pg.add(beat_card(pg, E, b))
    if not beats:
        pg.add('<p class="sub">No beats yet.</p>')
    cap = plan.get("captions", {})
    pg.add("<h2>Captions</h2>")
    first = next(iter((E.tr or {}).get("segments", [])), None)
    sample = first["text"] if first else "Your words appear here, in the channel's caption style."
    on = "burned into the picture" if cap.get("burn") else "not burned in (subtitle files only)"
    pg.add(f'<div class="box">Style <b>{esc(cap.get("style", "brand"))}</b>, {on}.<div class="box" dir="auto" style="text-align:center;font-weight:700">{esc(sample)}</div>'
           '<div class="ctl row"><button class="chip" type="button" data-grp="cap" data-tok="captions on">captions on</button>'
           '<button class="chip" type="button" data-grp="cap" data-tok="captions off">captions off</button></div></div>')
    pg.add("<h2>Music and effects</h2>")
    music = plan.get("music", [])
    if not music:
        pg.add('<div class="box">No music in the plan.</div>')
    for m in music:
        mp = E.p("build/review/music", f'{m["id"]}.mp3')
        trk = m.get("track", "")
        if not os.path.exists(mp) and trk and not trk.startswith("library:") and E.has("sources.json"):
            try:        # a track from the creator's own sources: a preview is one local ffmpeg call
                import mix, music
                music.preview(mix.track_path(E.ep, trk), mp)
            except SystemExit:
                pass
        prev = audio_tag(pg, mp, f'music {m["id"]}', 32, droppable=True) if os.path.exists(mp) else \
            f'<div class="miss">No preview yet. Make it with <code>./pal music preview {esc(m.get("track", "").replace("library:", ""))} build/review/music/{esc(m["id"])}.mp3</code></div>'
        pg.add(f'<div class="box"><button class="chip ctl" type="button" data-grp="mus" data-tok="{esc(m["id"])}">{esc(m["id"])}</button> '
               f'<span class="id">{esc(m["id"])}</span> {esc(m.get("track", ""))} · {mmss(m.get("t", [0, total])[0])}-{mmss(m.get("t", [0, total])[1])} · {m.get("gain_db", "")} dB'
               f'{" · ducks under speech" if m.get("duck") else ""}{prev}</div>')
    nsfx = sum(len(b.get("sfx") or []) for b in beats)
    pg.add('<div class="box"><button class="chip ctl" type="button" data-grp="mus" data-tok="no music">no music</button> '
           f'<button class="chip ctl" type="button" data-tok="no sfx">no sfx</button> Sound effects planned: {nsfx}. '
           f'Zoom-ins: {sum(1 for b in beats if b.get("layout") == "punch")}. Hidden areas: {len(plan.get("redact", []))}.</div>')
    need = [b for b in beats if b.get("status") == "outline" and b.get("needs")]
    pg.add("<h2>Shots to collect</h2>")
    pg.add("".join(f'<div class="box"><span class="id">{esc(b["id"])}</span> <span dir="auto">{esc(b["needs"])}</span></div>' for b in need)
           or '<p class="sub">Nothing to collect: every beat can be made from what exists.</p>')
    langs = (E.ch.get("languages") or {}).get("dub", [])
    for lg in langs:
        vp = E.p("build/review", f"voice-sample.{lg}.mp3")
        pg.add(f"<h2>Dub voice: {esc(LANG_NAMES.get(lg, lg))}</h2>" + (
            f'<div class="box">{audio_tag(pg, vp, "voice sample " + lg, 32)}</div>' if os.path.exists(vp) else
            f'<div class="miss">No sample yet. Make it with <code>./pal voice say host --lang {esc(lg)} --text "…" -o build/review/voice-sample.{esc(lg)}.mp3</code></div>'))
    pg.add('<div class="ctl row" style="margin-top:20px"><button class="chip" type="button" data-tok="go" style="font-size:1.1rem;padding:8px 24px">go: build it</button></div>')
    return pg


def beat_card(pg, E, b):
    """One card of the storyboard."""
    t = E.beat_t(b)
    lay = b.get("layout", "?")
    plate = b.get("plate") or {}
    still = E.p("build/review/stills", f'{b["id"]}.jpg')
    img = img_tag(pg, still, 480, "still", b["id"])
    if not img:
        img = (f'<div class="miss">No still yet. Make it with <code>./pal plates stills {esc(E.slug)}</code></div>' if plate else "")
    said = E.beat_words(b)
    kind = {"kit": "kit template", "custom": "made for this beat"}.get(plate.get("type"), "")
    extra = []
    if b.get("punch"):
        extra.append(f'zoom ×{b["punch"].get("scale", 1.15)}')
    if b.get("broll"):
        extra.append(f'B-roll from {esc(b["broll"].get("src"))} at {b["broll"].get("in", 0)} s')
    for s in b.get("sfx") or []:
        extra.append(f'sound: {esc(s.get("id"))}')
    if plate.get("alpha"):
        extra.append("see-through background")
    ctl = "".join(f'<button class="chip" type="button" data-grp="{esc(b["id"])}" data-tok="{esc(b["id"])} {l}">{l}</button>' for l in LAYOUTS if l != lay)
    ctl += f'<button class="chip" type="button" data-tok="{esc(b["id"])} drop">drop</button>'
    return (f'<div class="card" id="{esc(b["id"])}"><h3><span class="id">{esc(b["id"])}</span> {mmss(t[0]) + "-" + mmss(t[1]) if t else "time not set yet"}'
            f'<span class="chip">{esc(lay)}</span>{f"<span class=chip>{esc(kind)}</span>" if kind else ""}'
            f'{f"<span class=chip>{esc(b.get("status"))}</span>" if b.get("status") else ""}</h3>'
            f'<div class="row2">{diagram(lay)}<div>{text_lines(b.get("text"))}'
            f'{"<div class=kv>" + " · ".join(extra) + "</div>" if extra else ""}</div></div>{img}'
            f'{f"<div class=said dir=auto>says: “{esc(said)}”</div>" if said else ""}'
            f'<div class="ctl row">{ctl}</div></div>')


# ---------------------------------------------------------------- draft

QC_WORDS = {"black": "black frames", "flash": "a flash or strobe", "frozen": "frozen picture", "loudness": "loudness",
            "clip": "clipped (too loud) sound", "clipping": "clipped (too loud) sound", "duration": "length",
            "seam": "a cut that may be audible", "caption": "captions"}


def qc_rows(q):
    """Plain-language rows (level, when, text) from a qc.json of unknown exact shape."""
    items = []
    if isinstance(q, dict):
        for key in ("findings", "issues", "problems", "checks", "results"):
            if isinstance(q.get(key), list):
                items = q[key]
                break
        else:
            items = [{"kind": k, "msg": v} for k, v in q.items() if k not in ("v", "file")]
    elif isinstance(q, list):
        items = q
    rows = []
    for it in items:
        if not isinstance(it, dict):
            rows.append(("note", "", str(it)))
            continue
        msg = next((it[k] for k in ("say", "msg", "message", "text", "detail", "what", "note") if it.get(k)), None)
        kind = next((str(it[k]) for k in ("kind", "check", "type", "name") if it.get(k)), "")
        t = next((it[k] for k in ("t", "at", "start", "time") if isinstance(it.get(k), (int, float))), None)
        lvl = str(next((it[k] for k in ("level", "severity", "status") if it.get(k) is not None), "note"))
        if msg is None:
            msg = ", ".join(f"{k} {v}" for k, v in it.items() if k not in ("kind", "check", "type", "name", "level", "severity", "status", "t", "at"))
        label = QC_WORDS.get(kind.lower(), kind)
        rows.append((lvl.lower(), mmss(t) if t is not None else "", f"{label}: {msg}" if label and str(msg) != label else str(msg)))
    return rows


def build_draft(E):
    pg = Page("draft", E.ep, E.title("Draft review"), how_box([
        ("3:12 too fast", "a time and what is wrong (use the box below to collect several)"),
        ("B14 drop  ·  music lower", "remove a beat, change the music"),
        ("final", "the draft is good: render the final")]))
    dp = E.p("build/out/draft.mp4")
    lk = E.p("build/out/draft.link")
    if os.path.exists(dp):
        link = open(lk).read().strip() if os.path.exists(lk) else ""
        size = os.path.getsize(dp) / 1e6
        pg.add(f'<div class="stats"><div class="stat"><b>{mmss(common.duration(dp))}</b>length</div><div class="stat"><b>{size:.0f} MB</b>draft file</div></div>')
        pg.add('<div class="box"><b>Watch it:</b> ' + (f'<a href="{esc(link)}">open the draft on Drive</a>' if link else
               'the file is <code>build/out/draft.mp4</code> (not uploaded yet: <code>./pal drive put ' + esc(E.slug) + ' build/out/draft.mp4</code>)') + "</div>")
    else:
        pg.need("the draft video (build/out/draft.mp4)", f"./pal composite {E.slug} --draft")
    pg.add("<h2>Checks</h2>")
    q = E.j("build/review/qc.json")
    if q is None:
        pg.need("the check results (build/review/qc.json)", f"./pal qc build/out/draft.mp4 --ep {E.slug}")
    else:
        rows = qc_rows(q)
        pg.add("".join(f'<div class="box">{"⚠ " if l in ("warn", "warning", "error", "fail", "bad") else ""}{f"<span class=id>{esc(t)}</span> " if t else ""}<span dir="auto">{esc(m)}</span></div>' for l, t, m in rows)
               or '<div class="box">No problems found.</div>')
    pg.add("<h2>Beats</h2>")
    beats = (E.plan or {}).get("beats", [])
    pg.add("<table><tr><th>id<th>time<th>what<th>words</tr>" + "".join(
        f'<tr><td><span class="id">{esc(b["id"])}</span><td>{(mmss(E.beat_t(b)[0]) + "-" + mmss(E.beat_t(b)[1])) if E.beat_t(b) else "?"}<td>{esc(b.get("layout"))}'
        f'<td dir="auto">{esc(E.beat_words(b, 8))}</tr>' for b in beats) + "</table>" if beats else '<p class="sub">No beats in plan.json.</p>')
    pg.add('<h2>Add a note</h2><p class="sub">Type the time you saw it (like 3:12) and what is wrong, then Add. Your notes collect in the reply.</p>'
           '<div class="ctl"><div class="addrow"><input type="text" id="nt" placeholder="3:12" inputmode="text"><input type="text" id="nn" placeholder="too fast" dir="auto">'
           '<button class="chip" id="nadd" type="button">Add</button></div><div id="nlist"></div></div>'
           '<div class="ctl row"><button class="chip" type="button" data-tok="music lower">music lower</button><button class="chip" type="button" data-tok="final" style="font-size:1.1rem">final</button></div>')
    return pg


# ---------------------------------------------------------------- shorts, thumbs

def find_img(E, name):
    """Locate an image named in a JSON file (absolute, or relative to the episode, review or stills folder)."""
    if not name:
        return None
    for base in ("", "build/review", "build/review/stills", "build"):
        p = name if os.path.isabs(name) else E.p(base, name)
        if os.path.exists(p):
            return p
    return None


def build_shorts(E):
    pg = Page("shorts", E.ep, E.title("Shorts candidates"), how_box([
        ("S1 S3", "make these"), ("you choose", "let Claude pick the best"), ("S2 first line: …", "change a first line")]))
    c = E.j("build/review/shorts.json")
    if c is None:
        pg.need("the candidates (build/review/shorts.json)", "ask Claude to find the Shorts moments")
        return pg
    for s in c:
        t = s.get("t", [0, 0])
        im = img_tag(pg, find_img(E, s.get("still")), 480, "still", s.get("id", ""))
        pg.add(f'<div class="card"><h3><button class="chip ctl" data-tok="{esc(s["id"])}" type="button">{esc(s["id"])}</button><span class="id">{esc(s["id"])}</span>'
               f'{mmss(t[0])}-{mmss(t[1])} · {t[1] - t[0]:.0f} s</h3>{im}<div dir="auto"><b>starts:</b> “{esc(s.get("first_line", ""))}”</div>'
               f'<div class="said" dir="auto">{esc(s.get("why", ""))}</div></div>')
    pg.add('<div class="ctl row"><button class="chip" type="button" data-tok="you choose" style="font-size:1.1rem">you choose</button></div>')
    return pg


def package_titles(E):
    """Title candidates from package.md: bullet lines under a heading that mentions 'title'."""
    if not E.has("package.md"):
        return []
    out, on = [], False
    for ln in open(E.p("package.md"), encoding="utf-8"):
        if ln.startswith("#"):
            on = "title" in ln.lower()
        elif on:
            m = re.match(r"\s*(?:[-*]|\d+[.)])\s+(.*\S)", ln)
            if m:
                out.append(re.sub(r"[*_`]", "", m.group(1)))
    return out[:6]


def build_thumbs(E):
    pg = Page("thumbs", E.ep, E.title("Thumbnail options"), how_box([
        ("T2", "use this one"), ("T2 text: THREE WORDS", "use this one with other words on it"), ("none", "try again")]))
    files = sorted(glob.glob(E.p("build/out/thumbs", "*.jpg")))
    if not files:
        pg.need("thumbnail options (build/out/thumbs/*.jpg)", f"./pal thumb {E.slug}, then ./pal thumb {E.slug} --make f3 --text \"WORDS\" -o T1.jpg")
        return pg
    titles = package_titles(E) or ["Your video title appears here"]
    if not E.has("package.md"):
        pg.add(f'<div class="miss">No package.md yet, so sample titles are shown. Titles come from the packaging step.</div>')
    css = []
    for i, f in enumerate(files):
        stem = os.path.splitext(os.path.basename(f))[0]
        tid = stem if re.match(r"T\d+$", stem) else f"T{i + 1}"
        ref = pg.asset("image/jpeg", image_bytes(E.ep, f, 480, 72), tid)
        css.append(f'.th{i}{{background-image:url("{ref}")}}')
        feed = "".join(f'<div class="feed"><div class="thumb t168 th{i}"></div><div class="ttl" dir="auto">{esc(t)}</div></div>' for t in titles[:2])
        pg.add(f'<div class="card"><h3><button class="chip ctl" data-grp="thumb" data-tok="{esc(tid)}" type="button">{esc(tid)}</button><span class="id">{esc(tid)}</span> {esc(os.path.basename(f))}</h3>'
               f'<div class="thumb t320 th{i}"></div><p class="sub">In a feed (small):</p>{feed}</div>')
    pg.parts.insert(0, "<style>" + "".join(css) + "</style>")
    if len(titles) > 1:
        pg.add("<h2>Title candidates</h2>" + "".join(f'<div class="box" dir="auto">{esc(t)}</div>' for t in titles))
    return pg


# ---------------------------------------------------------------- main

BUILDERS = {"paper": build_paper, "story": build_story, "draft": build_draft, "shorts": build_shorts, "thumbs": build_thumbs}


def write_page(E, kind):
    """Build one page and write build/review/<kind>.html."""
    pg = BUILDERS[kind](E)
    doc = pg.render()
    out = common.build(E.ep, "review", f"{kind}.html")
    with open(out + ".part", "w", encoding="utf-8") as f:
        f.write(doc)
    os.replace(out + ".part", out)
    size = os.path.getsize(out)
    common.say(f"✓ {common.rel(E.ep, out)}  {size / 1e6:.2f} MB")
    for w in pg.warnings:
        common.say("  ! " + w)
    for what, cmd in pg.missing:
        common.say(f"  ? missing {what}: {cmd}")
    return out


def main(argv):
    if len(argv) != 2 or argv[0] not in list(BUILDERS) + ["all"]:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    E = Ep(common.episode(argv[1]))
    kinds = list(BUILDERS) if argv[0] == "all" else [argv[0]]
    for k in kinds:
        write_page(E, k)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
