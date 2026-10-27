"""Render a run as a single self-contained page.

One file, no network, no CDN, no fonts to fetch. That is a constraint from the
architecture rather than a preference: this system is not allowed a hosted
control plane, and a demo that quietly phones out to a CDN while the document
argues for data residency is an own goal in front of exactly the audience that
will notice.

The page has two views, and the toggle between them is the whole argument.
The clinician view is what a doctor sees mid-consultation, which on a green
visit is nothing at all. The audit view is everything the system checked to
decide it could stay quiet.
"""

from __future__ import annotations

import html
import json
from typing import Any

from tools.demo.templates import fill

BAND_ORDER = {"red": 0, "amber": 1, "green": 2}

TEMPLATE = "report.html"


def render(data: dict[str, Any], *, title: str = "AI clinician, demo") -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=None)
    # `</` inside a <script> block ends the block, whatever it is inside.
    return fill(TEMPLATE, title=html.escape(title), data=payload.replace("</", "<\\/"))
