"""
Structural guard: the playlist import modal's x-data component must NOT be nested
inside the panel() component.  Alpine v3 x-teleport loses scope for child elements
when the x-data that owns the teleported element is itself a child x-data of another
component — x-if conditions and @click handlers evaluate in the wrong scope.
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

# Identifiers that are fine in any Alpine expression context
_ALLOWED = {
    # JS keywords / operators
    'true', 'false', 'null', 'undefined', 'void', 'in', 'of', 'new',
    'typeof', 'instanceof', 'return', 'let', 'const', 'var',
    # JS built-ins
    'window', 'document', 'this', 'Object', 'String', 'Number', 'Boolean',
    'Array', 'Math', 'JSON', 'CustomEvent', 'setTimeout', 'clearTimeout',
    'parseInt', 'parseFloat', 'Promise', 'console', 'fetch', 'localStorage',
    # common array/string prototype methods (appear after a dot, fine)
    'length', 'filter', 'map', 'find', 'includes', 'startsWith', 'trim',
    'toLowerCase', 'join', 'replace', 'slice', 'split', 'push', 'some', 'every',
    # Alpine magic ($el, $event, $nextTick — $-prefixed, captured as just the word)
    'el', 'event', 'refs', 'nextTick', 'watch', 'dispatch', 'store',
    # x-for loop variables used in the modal
    'p', 's', 'tip',
    # property names on loop objects (not component-level variables)
    'pk', 'title', 'channel_title', 'video_count', 'last_synced_at', 'is_mine',
    'running', 'msg', 'failed', 'detected_exam_type', 'detected_subject_name',
    'already_imported', 'detected_subject_id', 'exam_type', 'subject_display',
    'result_msg', 'display_name', 'id', 'ad',
    # misc
    'Infinity', 'NaN',
}


def _strip_string_literals(expr: str) -> str:
    """Replace quoted string content with empty quotes so only code tokens remain."""
    # Replace single-quoted strings (Alpine expressions use single quotes inside double-quoted attrs)
    return re.sub(r"'[^']*'", "''", expr)


def _extract_alpine_expressions(html: str) -> list[tuple[str, str]]:
    """Return [(directive, code_tokens), …] for all Alpine directives in the HTML.
    String literal content is stripped so identifier extraction only sees JS code."""
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


def test_modal_not_nested_in_panel():
    """
    The playlist import modal include must appear OUTSIDE the x-data="panel()" element
    in hafta.html.  Nesting breaks Alpine v3 x-teleport scope.
    """
    text = HAFTA.read_text(encoding='utf-8')

    panel_attr_pos = text.find('x-data="panel()"')
    include_pos    = text.find('_playlist_import_modal.html')
    assert panel_attr_pos != -1, "panel() x-data not found in hafta.html"
    assert include_pos    != -1, "modal include not found in hafta.html"

    # Start the segment at the <div that opens the panel() component
    panel_div_start = text.rfind('<div', 0, panel_attr_pos)
    segment = text[panel_div_start:include_pos]

    opens  = len(re.findall(r'<div\b', segment))
    closes = len(re.findall(r'</div>', segment))
    net    = opens - closes

    assert net == 0, (
        f"The modal include is still nested inside x-data=\"panel()\" "
        f"(net unclosed divs between panel() opening and include: {net}). "
        "Alpine v3 x-teleport loses its scope chain when the owning x-data is a child "
        "component — move the include to after the panel() closing </div>."
    )


def test_modal_alpine_variables_self_contained():
    """
    Every identifier referenced in Alpine directives inside the modal template
    must be either declared in playlistImporter() or be a well-known external.
    An undeclared identifier means Alpine will silently fall back to a parent scope
    (panel()) or the window — causing the exact bug: x-if never renders, @click does nothing.
    """
    html = MODAL.read_text(encoding='utf-8')
    pairs = _extract_alpine_expressions(html)

    unknown: list[str] = []
    for directive, code_tokens, raw_expr in pairs:
        # Skip the x-data declaration itself and x-teleport target
        if directive in ('x-data', 'x-teleport', 'x-cloak', 'x-ref'):
            continue
        # Extract bare word identifiers from the code (string literals already stripped)
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
