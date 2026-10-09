"""Shared, conservative reply boundaries and folded-header handling."""
import re


def unquote(line):
    return re.sub(r'^\s*(?:>\s*)*', '', line).strip()


def reply_marker(lines, index):
    value = unquote(lines[index])
    if not value.startswith('On '):
        return None
    for end in range(index, min(index + 5, len(lines))):
        if end > index:
            value += ' ' + unquote(lines[end])
        if value.endswith('wrote:'):
            return value, end + 1
    return None


def message_boundary(lines, index):
    value = unquote(lines[index])
    if re.match(r'^-{2,}\s*(?:Forwarded message|Original Message)\s*-*$', value, re.I):
        return True
    if reply_marker(lines, index):
        return True
    if value.startswith('From:'):
        following = [unquote(line) for line in lines[index + 1:index + 12]]
        return (any(re.match(r'^(Sent|Date):', line) for line in following)
                and any(line.startswith('Subject:') for line in following))
    return False


def quoted_headers(text):
    lines = text.splitlines(keepends=True)
    fields, wrappers = {}, []
    i, last = 0, None
    while i < len(lines):
        plain = unquote(lines[i])
        if not plain:
            last = None
            i += 1
        elif re.match(r'^-{2,}\s*(?:Forwarded message|Original Message)', plain, re.I):
            last = None
            i += 1
        elif (marker := reply_marker(lines, i)):
            wrappers.append(marker[0])
            i, last = marker[1], None
        elif (match := re.match(r'^(From|Date|Sent|Subject|To|Cc):\s*(.*)', plain)):
            last = match.group(1)
            fields[last] = match.group(2)
            i += 1
        elif last is not None:
            # Folding requires indentation after removing quote glyphs. Bare
            # wrapped addresses are also unambiguous recipient continuations.
            raw = re.sub(r'^(?:[ \t]*>[ ]?)+', '', lines[i]).rstrip('\r\n')
            address = re.fullmatch(r'<?[^\s<>]+@[^\s<>]+>?,?', plain)
            if raw.startswith((' ', '\t')) or (last in ('To', 'Cc') and address):
                fields[last] += ' ' + plain
                i += 1
            else:
                break
        else:
            break
    return fields, wrappers, ''.join(lines[:i]), ''.join(lines[i:])


def normalized_passage(text):
    """Only transport quoting/whitespace change; numbers and signs survive."""
    return ' '.join(' '.join(unquote(line) for line in text.splitlines()).split())
