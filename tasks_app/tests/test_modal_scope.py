"""
Structural guards for the playlist import modal.

The proven working pattern (39e905a) is:
  x-data="playlistImporter()" + x-show="show" + x-cloak on ONE overlay div.
  NO x-teleport. Include inside panel().

x-teleport inside a nested child x-data component breaks Alpine scope for
all elements INSIDE the teleported tree — x-if never fires, @click does nothing.
"""
import re
from pathlib import Path

HAFTA = Path('templates/coach/tasks/hafta.html')
MODAL = Path('templates/coach/tasks/_playlist_import_modal.html')

PLAYLISTIMPORTER_MEMBERS = {
    # state
    'show', 'step', 'url', 'errorMsg', 'progressMsg', 'preview', 'subjects',
    'selectedSubjectId', 'selectedExamType', 'importResult', 'myPlaylists',
    'loadingPlaylists', 'search', 'pendingDeletePk', 'deleteError', 'deleteErrorPk',
    'refreshJobs', '_activeJobId', '_pollTimer',
    # computed getter
    'filteredPlaylists',
    # methods
    '_fmtDate', 'open', 'close', 'reset', 'loadMyPlaylists', 'deletePl',
    'doRefresh', '_pollRefresh', 'doPreview', 'doImport', '_startPoll', '_stopPoll',
    'useNow',
}

_ALLOWED = {
    # JS keywords / operators
    'true', 'false', 'null', 'undefined', 'void', 'in', 'of', 'new',
    'typeof', 'instanceof', 'return', 'let', 'const', 'var',
    # JS built-ins
    'window', 'document', 'this', 'Object', 'String', 'Number', 'Boolean',
    'Array', 'Math', 'JSON', 'CustomEvent', 'setTimeout', 'clearTimeout',
    'parseInt', 'parseFloat', 'Promise', 'console', 'fetch', 'localStorage',
    # array/string prototype methods
    'length', 'filter', 'map', 'find', 'includes', 'startsWith', 'trim',
    'toLowerCase', 'join', 'replace', 'slice', 'split', 'push', 'some', 'every',
    # Alpine magic tokens ($el etc. captured as bare words)
    'el', 'event', 'refs', 'nextTick', 'watch', 'dispatch', 'store',
    # x-for loop variables in the modal
    'p', 's', 'tip',
    # object property names on loop items (not component state)
    'pk', 'title', 'channel_title', 'video_count', 'last_synced_at', 'is_mine',
    'running', 'msg', 'failed', 'detected_exam_type', 'detected_subject_name',
    'already_imported', 'detected_subject_id', 'exam_type', 'subject_display',
    'result_msg', 'display_name', 'id', 'ad',
    'Infinity', 'NaN',
}


def _strip_string_literals(expr: str) -> str:
    return re.sub(r"'[^']*'", "''", expr)


def _extract_alpine_expressions(html: str) -> list[tuple[str, str, str]]:
    """Return [(directive, code_without_string_literals, raw_expr), …]."""
    pattern = re.compile(
        r'(?:'
        r'(?:x-(?:show|if|text|model|for|cloak|data|teleport|ref))'
        r'|(?:@[\w.:-]+)'
        r'|(?::[\w-]+)'
        r')="([^"]*)"',
    )
    results = []
    for m in pattern.finditer(html):
        directive = html[m.start():m.end()].split('=')[0]
        raw_expr = m.group(1)
        code_tokens = _strip_string_literals(raw_expr)
        results.append((directive, code_tokens, raw_expr))
    return results


def test_modal_has_no_x_teleport():
    """
    The modal must NOT use x-teleport. The proven shell (39e905a) works without it.
    x-teleport inside a nested x-data component silently breaks Alpine scope on
    the teleported subtree, making x-if never render and @click do nothing.
    """
    text = MODAL.read_text(encoding='utf-8')
    assert 'x-teleport=' not in text, (
        "Modal template contains x-teleport. Remove it: the overlay is a plain "
        "fixed-position element inside panel() and works without teleport. "
        "See 39e905a for the proven pattern."
    )


def test_modal_xdata_and_xshow_on_same_element():
    """
    x-data='playlistImporter()' and x-show='show' must be on the SAME element —
    exactly as the working 39e905a pattern. Splitting them (wrapper div + teleported
    child) is what causes the component to silently fail.
    """
    text = MODAL.read_text(encoding='utf-8')
    # Find the line that has x-data="playlistImporter()"
    for line in text.splitlines():
        if 'x-data="playlistImporter()"' in line:
            # x-show doesn't have to be on the exact same line (attributes can span lines)
            break
    else:
        raise AssertionError("x-data=\"playlistImporter()\" not found in modal template")

    # Find the opening tag that contains x-data="playlistImporter()"
    # It should be a <div that also has x-show
    xdata_pos = text.find('x-data="playlistImporter()"')
    tag_start = text.rfind('<', 0, xdata_pos)
    tag_end = text.find('>', xdata_pos)
    opening_tag = text[tag_start:tag_end + 1]
    assert 'x-show' in opening_tag, (
        "x-show is not on the same opening tag as x-data=\"playlistImporter()\". "
        "Both must be on the single overlay div (not on a wrapper + child)."
    )


def test_modal_alpine_variables_self_contained():
    """
    Every identifier referenced in Alpine directive expressions in the modal
    must be declared in playlistImporter() or be a known global/loop variable.
    """
    html = MODAL.read_text(encoding='utf-8')
    pairs = _extract_alpine_expressions(html)

    unknown: list[str] = []
    for directive, code_tokens, raw_expr in pairs:
        if directive in ('x-data', 'x-teleport', 'x-cloak', 'x-ref'):
            continue
        for ident in re.findall(r'\b([A-Za-z_]\w*)\b', code_tokens):
            if ident in PLAYLISTIMPORTER_MEMBERS:
                continue
            if ident in _ALLOWED:
                continue
            unknown.append(f"{directive}: '{ident}'  (in: {raw_expr[:80]})")

    assert not unknown, (
        "Modal Alpine expressions reference identifiers not declared in playlistImporter():\n"
        + "\n".join(unknown)
    )
