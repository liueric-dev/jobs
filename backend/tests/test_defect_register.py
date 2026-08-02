"""`docs/ingest/DEFECTS.md`'s own index links resolve to something.

Run:  python3 -m unittest tests.test_defect_register

WHY THIS FILE EXISTS

Defect D74. The register opens with an index table whose rows link into the
bodies below -- `[D01](#d01)` -- and twenty-two of those links resolved to
nothing, because a heading that gained a ` -- fixed` suffix slugs to
`#d01-fixed` and the bare `#d01` then exists nowhere. The link lands at the top
of a 2,000-line file instead of at the entry, silently.

WHY `audit-doc-links.py` DOES NOT COVER IT, AND SHOULD NOT

That checker strips `#fragment` before resolving, on the stated reasoning that a
wrong anchor still lands the reader on the right document. That is correct for
links BETWEEN documents and wrong for an index INSIDE one, where the jump is the
whole value of the link. D74 considered widening the checker to resolve
intra-document fragments and ruled it out of scope. This test is the narrow
version: one file, one rule, no change to how any other link is checked.

WHY A TEST AND NOT JUST THE FIX

The count went stale inside the session that filed it. D74's body named nineteen
broken anchors; by the time it was fixed the answer was twenty-two, because
`e79448c` gave D18, D19 and D21 a ` -- fixed` suffix hours later. Every heading
edit in this file is a chance to break a link, and nothing was watching. That is
the register's own documented failure mode -- "the index is the part anyone
scans" -- arriving one level down.

The slug rule below is the one D74's own reproduction script uses, kept
deliberately identical so the test and the defect entry cannot disagree.
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTER = os.path.join(REPO_ROOT, "docs", "ingest", "DEFECTS.md")

#: `<a id="d69"></a>` -- the explicit form, which D69-D74 already use.
_EXPLICIT = re.compile(r'<a id="(d\d+)"></a>')
#: Any heading naming a defect, at any level the file uses.
_HEADING = re.compile(r"^#{2,4}\s+(D\d+.*)$", re.M)
#: `](#d01)` -- an index row's link into a body.
_LINK = re.compile(r"\]\(#(d\d+)\)")


def slug(heading):
    """GitHub's heading-anchor rule, as D74's reproduction script states it."""
    return re.sub(r"\s+", "-",
                  re.sub(r"[^\w\s-]", "", heading.strip().lower())).strip("-")


class TestEveryIndexLinkResolves(unittest.TestCase):

    def setUp(self):
        with open(REGISTER, encoding="utf-8") as fh:
            self.text = fh.read()

    def targets(self):
        """Every anchor a `#dNN` link could land on."""
        return (set(_EXPLICIT.findall(self.text))
                | {slug(h) for h in _HEADING.findall(self.text)})

    def test_no_index_link_dangles(self):
        missing = sorted({l for l in _LINK.findall(self.text)} - self.targets(),
                         key=lambda s: int(s[1:]))
        self.assertEqual([], missing,
                         "DEFECTS.md index links resolve to no anchor: "
                         + ", ".join(missing) + ". A heading that gained a "
                         "' -- fixed' suffix no longer slugs to its bare id; add "
                         '<a id="dNN"></a> under it, as D69-D74 do. Defect D74.')

    def test_the_file_actually_has_links_to_check(self):
        """A regex that stops matching would make the test above vacuously green."""
        self.assertGreater(len(_LINK.findall(self.text)), 40)
        self.assertGreater(len(_HEADING.findall(self.text)), 40)
