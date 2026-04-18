"""gobstopper.html — type-safe HTML DSL (vendored htpy)
=====================================================

Every HTML element is a module-level name.  **Wildcard imports shadow Python
built-ins and common loop variable names** with no warning:

.. code-block:: python

    from gobstopper.html import *   # ← HAZARDOUS

    # Built-ins now shadowed silently:
    #   input  → VoidElement("input")   (was Python's built-in input())
    #   map    → Element("map")          (was Python's built-in map())
    #   object → Element("object")       (was Python's built-in object)
    #   id     is NOT exported (no collision, but watch for future changes)

    # Common one-letter loop variables now shadowed:
    #   p      → Element("p")   — clashes with  for p in partners: …
    #   a      → Element("a")   — clashes with  for a in articles: …
    #   b      → Element("b")   — clashes with  for b in batches:  …
    #   s      → Element("s")   — clashes with  for s in strings:  …
    #   i      → Element("i")   — clashes with  for i in range(n): …
    #   q      → Element("q")   — clashes with  q = request.get_str("q")

**Recommended import patterns** (safest → least safe):

1. **Namespace import** — zero collision risk::

       from gobstopper import html
       html.div(class_="card")[html.p["Hello"]]

2. **Named imports** — explicit, no surprises::

       from gobstopper.html import div, span, ul, li, a, p

3. **Wildcard import** — only safe in dedicated rendering modules that contain
   no other logic and no loop variables named after HTML elements.

Hazardous names reference
-------------------------
The following names exported by this module conflict with Python built-ins:

==========  ================  =======================================
Name        html type         Python built-in it shadows
==========  ================  =======================================
``input``   VoidElement       ``builtins.input()``
``map``     Element           ``builtins.map()``
``object``  Element           ``builtins.object``
``data``    Element           no built-in, but very common variable
``output``  Element           no built-in, but common variable name
``time``    Element           shadows ``import time`` if in scope
``title``   Element           common variable name
``var``     Element           shadows ``var`` as short for "variable"
==========  ================  =======================================

One-letter element names that shadow loop variables: ``a``, ``b``, ``i``,
``p``, ``q``, ``s``, ``u``.

Full element reference
----------------------
Void elements (no closing tag): area, base, br, col, embed, hr, img,
**input**, link, meta, source, track, wbr.

Normal elements: a, abbr, address, article, aside, audio, b, bdi, bdo,
blockquote, body, button, canvas, caption, cite, code, colgroup, **data**,
datalist, dd, del\\_, details, dfn, dialog, div, dl, dt, em, fieldset,
figcaption, figure, footer, form, h1–h6, head, header, hgroup, html, i,
iframe, ins, kbd, label, legend, li, main, **map**, mark, math, menu, meter,
nav, noscript, **object**, ol, optgroup, option, **output**, p, picture, pre,
progress, q, rp, rt, ruby, s, samp, script, search, section, select, slot,
small, span, strong, style, sub, summary, sup, svg, table, tbody, td,
template, textarea, tfoot, th, thead, **time**, **title**, tr, u, ul, **var**,
video.
"""

from __future__ import annotations

from ._contexts import Context as Context
from ._contexts import ContextConsumer as ContextConsumer
from ._contexts import ContextProvider as ContextProvider
from ._elements import BaseElement as BaseElement
from ._elements import Element as Element
from ._elements import HTMLElement as HTMLElement
from ._elements import VoidElement as VoidElement
from ._fragments import Fragment as Fragment
from ._fragments import comment as comment
from ._fragments import fragment as fragment
from ._fragments import raw_html as raw_html
from ._fragments import raw_js as raw_js
from ._fragments import raw_css as raw_css
from ._legacy_rendering import iter_node as iter_node  # pyright: ignore[reportDeprecated]
from ._legacy_rendering import render_node as render_node  # pyright: ignore[reportDeprecated]
from ._types import Attribute as Attribute
from ._types import Node as Node
from ._types import Renderable as Renderable
from ._with_children import with_children as with_children
from . import datastar as datastar

__all__: list[str] = ["datastar"]


def __getattr__(name: str) -> Element:
    from ._elements import get_element

    return get_element(name)


# The list of HTML elements is mostly collected from
# https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements
html = HTMLElement("html")

area = VoidElement("area")
base = VoidElement("base")
br = VoidElement("br")
col = VoidElement("col")
embed = VoidElement("embed")
hr = VoidElement("hr")
img = VoidElement("img")
input = VoidElement("input")
link = VoidElement("link")
meta = VoidElement("meta")
source = VoidElement("source")
track = VoidElement("track")
wbr = VoidElement("wbr")

a = Element("a")
abbr = Element("abbr")
address = Element("address")
article = Element("article")
aside = Element("aside")
audio = Element("audio")
b = Element("b")
bdi = Element("bdi")
bdo = Element("bdo")
blockquote = Element("blockquote")
body = Element("body")
button = Element("button")
canvas = Element("canvas")
caption = Element("caption")
cite = Element("cite")
code = Element("code")
colgroup = Element("colgroup")
data = Element("data")
datalist = Element("datalist")
dd = Element("dd")
del_ = Element("del")
details = Element("details")
dfn = Element("dfn")
dialog = Element("dialog")
div = Element("div")
dl = Element("dl")
dt = Element("dt")
em = Element("em")
fieldset = Element("fieldset")
figcaption = Element("figcaption")
figure = Element("figure")
footer = Element("footer")
form = Element("form")
h1 = Element("h1")
h2 = Element("h2")
h3 = Element("h3")
h4 = Element("h4")
h5 = Element("h5")
h6 = Element("h6")
head = Element("head")
header = Element("header")
hgroup = Element("hgroup")
i = Element("i")
iframe = Element("iframe")
ins = Element("ins")
kbd = Element("kbd")
label = Element("label")
legend = Element("legend")
li = Element("li")
main = Element("main")
map = Element("map")
mark = Element("mark")
math = Element("math")
menu = Element("menu")
meter = Element("meter")
nav = Element("nav")
noscript = Element("noscript")
object = Element("object")
ol = Element("ol")
optgroup = Element("optgroup")
option = Element("option")
output = Element("output")
p = Element("p")
picture = Element("picture")
pre = Element("pre")
progress = Element("progress")
q = Element("q")
rp = Element("rp")
rt = Element("rt")
ruby = Element("ruby")
s = Element("s")
samp = Element("samp")
script = Element("script")
search = Element("search")
section = Element("section")
select = Element("select")
slot = Element("slot")
small = Element("small")
span = Element("span")
strong = Element("strong")
style = Element("style")
sub = Element("sub")
summary = Element("summary")
sup = Element("sup")
svg = Element("svg")
table = Element("table")
tbody = Element("tbody")
td = Element("td")
template = Element("template")
textarea = Element("textarea")
tfoot = Element("tfoot")
th = Element("th")
thead = Element("thead")
time = Element("time")
title = Element("title")
tr = Element("tr")
u = Element("u")
ul = Element("ul")
var = Element("var")
video = Element("video")
