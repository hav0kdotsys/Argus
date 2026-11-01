#!/usr/bin/env python3
"""ARGUS rebrand pass - rewrites USER-FACING text from Hermes to ARGUS, nothing else.

ARGUS is HavoK's own application (not a skin over Hermes), so what a person reads - messages, hints, prompts,
labels - says ARGUS. What a program reads stays as it is: module names (hermes_cli), env vars (HERMES_HOME),
package / toolset ids (hermes-cli, @hermes/ink), file names, URLs, Nous' Hermes MODEL names ("Hermes 4",
"Hermes-3-Llama"), code identifiers, comments and docstrings.

It edits only string literals:
  - Python: tokenize-exact (STRING tokens and f-string bodies with {expressions} masked); docstrings skipped.
  - TypeScript/TSX: a literal scanner ('..', "..", `..` with ${..} masked); comments and imports skipped.
  - YAML (the i18n catalogues in locales/): values only - keys and comments are left alone.

Blind spots (check by hand after a run): a literal nested INSIDE an f-string's {expression}
(f"{t('k', agent_name='Hermes')}"), and a command built from a list (" ".join(["hermes", ...])).

Usage:  python3 argus/tools/rebrand.py [--check] PATH...     (dirs are walked; --check only reports)
Re-run it after taking anything from upstream - it is idempotent.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

# ------------------------------------------------------------------------------------------------- the rules

_NOT_ID_BEFORE = r"(?<![\w./@~\\$-])"
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"summoning hermes…"), "opening its eyes…"),
    (re.compile(r"\bexit hermes\b"), "exit argus"),
    (re.compile(r"(?<![\w-])hermes-tui: "), "argus: "),
    (re.compile(_NOT_ID_BEFORE + r"Hermes[ -]Agent(?![-_./\w])"), "ARGUS"),
    (re.compile(_NOT_ID_BEFORE + r"Hermes agent(?![-_./\w])"), "ARGUS"),
    # ~/.hermes in prose -> ~/.argus (code builds real paths from get_hermes_home(), never from this text)
    (re.compile(r"~/\.hermes(?=[/\s'\"`),.:;]|$)"), "~/.argus"),
    # A command hint: `hermes model`, hermes -p work --tui, "run hermes doctor" ...
    (re.compile(_NOT_ID_BEFORE + r"hermes(?= (?:-{1,2}[a-zA-Z]|[a-z][a-z-]*\b|<|\[|\$\{|\{))"), "argus"),
    (re.compile(r"(?<=`)hermes(?=`)"), "argus"),
    # The product name. Not "Hermes 4" / "Hermes-3" (Nous models), not hermes-ish identifiers, and not the
    # "Hey Hermes" wake word (a trained hotword model, hey_hermes - it changes when an ARGUS model exists).
    (re.compile(_NOT_ID_BEFORE + r"(?<![Hh]ey )Hermes(?![-_./\w]|\s?\d|\s+(?:[234]|Llama|Pro|model|models)\b)"), "ARGUS"),
    (re.compile(r"\b([Aa]) ARGUS\b"), r"\1n ARGUS"),
]


def rebrand_text(s: str) -> str:
    for pat, rep in _RULES:
        s = pat.sub(rep, s)
    return s


def _masked(body: str, opener: str, closer: str, escape_double: bool) -> str:
    """Apply rebrand_text to the literal parts of a template body, leaving {expr} / ${expr} untouched.

    Each expression becomes a placeholder that starts with "{" (so a rule can see `hermes ${cmd}` as a command
    hint) and is restored afterwards."""
    held: list[str] = []
    buf, i, n = [], 0, len(body)
    while i < n:
        if escape_double and (body.startswith("{{", i) or body.startswith("}}", i)):
            buf.append(body[i:i + 2]); i += 2; continue
        if body.startswith(opener, i):
            depth, j = 1, i + len(opener)
            while j < n and depth:
                if body[j] == "{":
                    depth += 1
                elif body[j] == "}":
                    depth -= 1
                j += 1
            held.append(body[i:j])
            buf.append(f"{{\x00{len(held) - 1}\x00}}"); i = j; continue
        buf.append(body[i]); i += 1
    text = rebrand_text("".join(buf))
    return re.sub(r"\{\x00(\d+)\x00\}", lambda m: held[int(m.group(1))], text)


# ------------------------------------------------------------------------------------------------- python

_STR_PREFIX = re.compile(r"^([rRbBuUfF]{0,2})('''|\"\"\"|'|\")")


def _py_literal(tok: str) -> str:
    m = _STR_PREFIX.match(tok)
    if not m:
        return tok
    prefix, q = m.groups()
    if "b" in prefix.lower():
        return tok  # bytes are protocol, not prose
    head, body, tail = tok[:m.end()], tok[m.end():len(tok) - len(q)], tok[len(tok) - len(q):]
    if "f" in prefix.lower():
        return head + _masked(body, "{", "}", True) + tail
    return head + rebrand_text(body) + tail


def rebrand_python(src: str) -> str:
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return src
    lines = src.splitlines(keepends=True)
    offs = [0]
    for ln in lines:
        offs.append(offs[-1] + len(ln))
    pos = lambda rc: offs[rc[0] - 1] + rc[1]
    spans: list[tuple[int, int]] = []
    prev_sig = tokenize.NEWLINE
    i = 0
    skip = {tokenize.NL, tokenize.COMMENT}
    FSTART = getattr(tokenize, "FSTRING_START", None)
    FEND = getattr(tokenize, "FSTRING_END", None)
    while i < len(toks):
        t = toks[i]
        if t.type == tokenize.STRING or (FSTART is not None and t.type == FSTART):
            start = t.start
            j = i
            if t.type == FSTART:
                depth = 0
                while j < len(toks):
                    if toks[j].type == FSTART:
                        depth += 1
                    elif toks[j].type == FEND:
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
            end = toks[j].end
            # A docstring / bare string statement: first thing on its logical line and the line ends after it.
            k = j + 1
            while k < len(toks) and toks[k].type in skip:
                k += 1
            nxt = toks[k].type if k < len(toks) else tokenize.ENDMARKER
            is_doc = prev_sig in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT) and nxt in (
                tokenize.NEWLINE, tokenize.ENDMARKER)
            if not is_doc:
                spans.append((pos(start), pos(end)))
            prev_sig = toks[j].type if t.type != FSTART else tokenize.STRING
            i = j + 1
            continue
        if t.type not in skip:
            prev_sig = t.type
        i += 1
    # A line ending in "# rebrand: keep" holds strings a PROGRAM reads (a container user, a marker written by an
    # older version, a binary name): leave every literal on it alone.
    keep_lines = {i for i, ln in enumerate(lines) if "rebrand: keep" in ln}
    line_of = lambda off: next(i for i in range(len(offs) - 1) if offs[i] <= off < offs[i + 1])
    spans = [(a, b) for a, b in spans if line_of(a) not in keep_lines and line_of(max(a, b - 1)) not in keep_lines]
    if not spans:
        return src
    out, last = [], 0
    for a, b in spans:
        out.append(src[last:a])
        out.append(_py_literal(src[a:b]))  # one literal per span (adjacent literals are separate tokens)
        last = b
    out.append(src[last:])
    return "".join(out)


# ------------------------------------------------------------------------------------------------------ yaml

# `key:` (optionally a list item or a quoted key), then the value. Anything else that is not a comment is the
# continuation of a block scalar or a multi-line quoted value, so it is all value.
_YAML_KEY = re.compile(r"^(\s*(?:- )?(?:\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s#'\"-][^:#]*?):)(?=\s|$)(.*)$", re.DOTALL)


def rebrand_yaml(src: str) -> str:
    out = []
    for line in src.splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith("#") or "rebrand: keep" in line:
            out.append(line)
            continue
        m = _YAML_KEY.match(line)
        out.append(m.group(1) + rebrand_text(m.group(2)) if m else rebrand_text(line))
    return "".join(out)


# ------------------------------------------------------------------------------------------------- typescript

def rebrand_ts(src: str) -> str:
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i); j = n if j < 0 else j
            out.append(src[i:j]); i = j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2); j = n if j < 0 else j + 2
            out.append(src[i:j]); i = j; continue
        if c in "'\"`":
            j = i + 1
            depth = 0
            while j < n:
                if src[j] == "\\":
                    j += 2; continue
                if c == "`" and src.startswith("${", j):
                    depth += 1; j += 2; continue
                if c == "`" and depth and src[j] == "}":
                    depth -= 1; j += 1; continue
                if src[j] == c and not depth:
                    break
                if c != "`" and src[j] == "\n":
                    break
                j += 1
            lit = src[i:j + 1]
            line_start = src.rfind("\n", 0, i) + 1
            line = src[line_start:i]
            line_end = src.find("\n", j); line_end = n if line_end < 0 else line_end
            if (re.search(r"\b(import|from|require)\b", line) or re.search(r"\bimport\(\s*$", line)
                    or "rebrand: keep" in src[line_start:line_end]):
                out.append(lit)
            else:
                body = lit[1:-1]
                body = _masked(body, "${", "}", False) if c == "`" else rebrand_text(body)
                out.append(c + body + lit[-1])
            i = j + 1; continue
        out.append(c); i += 1
    return "".join(out)


# ------------------------------------------------------------------------------------------------- driver

_SKIP_DIRS = {"node_modules", "dist", ".git", "__pycache__", ".venv", "venv", "build"}
# Files rebranded by hand (they define the classic Hermes look on purpose).
_SKIP_FILES = {
    "hermes_cli/skin_engine.py", "hermes_cli/default_soul.py",
    # argv fixtures: a real process line always says `hermes` (the launcher execs `python <repo>/hermes`)
    "tests/gateway/test_gateway_command_line_matcher.py", "tests/gateway/test_status.py",
    # fixtures a program reads (argv, bot names and mention text, worktree lock reasons, service units, the
    # docker user, HTTP User-Agents), or upstream tooling ARGUS doesn't ship yet (installer, desktop updater, docs)
    "tests/gateway/test_bluebubbles_plugin.py",
    "tests/gateway/test_buzz_mention_resolution.py",
    "tests/gateway/test_dingtalk.py",
    "tests/gateway/test_feishu_bot_admission.py",
    "tests/gateway/test_feishu.py",
    "tests/gateway/test_matrix_mention.py",
    "tests/gateway/test_multiplex_api_server_routing.py",
    "tests/gateway/test_multiplex_lifecycle.py",
    "tests/gateway/test_multiplex_secondary_port_binding_env.py",
    "tests/gateway/test_slack_pasted_tables.py",
    "tests/hermes_cli/test_gateway_migrate_compensator_resume.py",
    "tests/hermes_cli/test_gateway_migrate_converged_host.py",
    "tests/hermes_cli/test_gateway_multiplex_mode.py",
    "tests/hermes_cli/test_gui_command.py",
    "tests/hermes_cli/test_orphan_desktop_serve_reap.py",
    "tests/hermes_cli/test_parser_help_home.py",
    "tests/hermes_cli/test_pooled_served_profile_backend_unscoped.py",
    "tests/hermes_cli/test_process_identity_canonical_matchers.py",
    "tests/hermes_cli/test_projects_db.py",
    "tests/hermes_cli/test_served_profile_mirror_platforms.py",
    "tests/hermes_cli/test_serve_runtime_inventory.py",
    "tests/hermes_cli/test_service_manager.py",
    "tests/hermes_cli/test_update_stale_dashboard.py",
    "tests/hermes_cli/test_web_server_messaging_posture.py",
    "tests/hermes_cli/test_worktree_gc.py",
    "tests/hermes_cli/test_worktree.py",
    "tests/hermes_cli/test_worktree_snapshot_prune.py",
    "tests/plugins/image_gen/test_xai_provider.py",
    "tests/plugins/platforms/photon/test_auth.py",
    "tests/plugins/platforms/photon/test_mention_gating.py",
    "tests/scripts/desktop_update/test_desktop_update_gateway_flag.py",
    "tests/scripts/desktop_update/test_desktop_update_posix_marker.py",
    "tests/scripts/desktop_update/test_handoff_delegate_publication.py",
    "tests/scripts/install/test_install_sh_existing_destination.py",
    "tests/scripts/install/test_install_sh_shell_path.py",
    "tests/scripts/test_code_health_rules.py",
    "tests/scripts/test_release_entrypoint.py",
    "tests/skills/test_google_workspace_setup_deps.py",
    "tests/test_display_hermes_home.py",
    "tests/tools/test_skill_linter.py",
    "tests/tools/test_stage2_hook_symlink_chown.py",
    "tests/website/test_extract_plugins.py",
    "tests/website/test_extract_skills.py",
    "tests/hermes_cli/test_gateway_migrate_multiplex.py",
}


def _files(paths: list[str]):
    for p in map(Path, paths):
        if p.is_file():
            yield p
            continue
        for f in p.rglob("*"):
            # YAML only in locales/ (the i18n catalogues): other YAML (plugin manifests, configs) holds identifiers.
            yaml_ok = f.suffix == ".yaml" and "locales" in f.parts
            if (f.is_file() and (f.suffix in (".py", ".ts", ".tsx") or yaml_ok) and not (_SKIP_DIRS & set(f.parts))
                    and not any(f.as_posix().endswith(x) for x in _SKIP_FILES)):
                yield f


def main(argv: list[str]) -> int:
    check = "--check" in argv
    paths = [a for a in argv if a != "--check"]
    changed = 0
    for f in _files(paths):
        try:
            src = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = {".py": rebrand_python, ".yaml": rebrand_yaml}.get(f.suffix, rebrand_ts)(src)
        if new != src:
            changed += 1
            if check:
                print(f)
            else:
                f.write_text(new, encoding="utf-8")
    print(f"rebrand: {changed} file(s) {'would change' if check else 'changed'}", file=sys.stderr)
    return 1 if check and changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
