"""Reversible literal body framing; source text can never introduce records."""
import re

MARKER = '<!-- property-timeline-archive:1 -->'
OPEN = re.compile(r'^(`{3,})property-timeline-body$')


def frame_body(body):
    longest = max((len(m.group()) for m in re.finditer(r'`+', body)), default=0)
    fence = '`' * max(3, longest + 1)
    return fence + 'property-timeline-body\n' + body + '\n' + fence


def outside_body(lines):
    """Return raw line positions outside explicitly framed bodies."""
    fence = None
    positions = []
    for position, line in enumerate(lines):
        if fence is not None:
            if line == fence:
                fence = None
            continue
        match = OPEN.fullmatch(line)
        if match:
            fence = match[1]
        else:
            positions.append(position)
    if fence is not None:
        raise ValueError('Unclosed literal message body; repair archive framing')
    return positions


def decode_record(lines):
    """Remove only format framing, preserving literal body lines and whitespace."""
    result, fence = [], None
    for line in lines:
        if fence is None and (match := OPEN.fullmatch(line)):
            fence = match[1]
        elif fence is not None and line == fence:
            fence = None
        else:
            result.append(line)
    if fence is not None:
        raise ValueError('Unclosed literal message body')
    return '\n'.join(result)
