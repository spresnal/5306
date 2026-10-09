"""Remove only recognizable signature/footer blocks from individual passages."""
import re


def strip_signature(text):
    lines = text.splitlines(keepends=True)
    plain = [re.sub(r'^\s*(?:>\s*)*', '', line).strip() for line in lines]
    remove = set()
    for i, value in enumerate(plain):
        start = None
        if value == 'Jessica M. Eye' and any('Account Executive, Private Client | Gregory & Appel' in s for s in plain[i + 1:i + 4]):
            start = i
            # Include the adjacent routine signoff, not preceding substantive text.
            for j in range(i - 1, max(-1, i - 6), -1):
                if plain[j] in ('', 'Thank you,', 'Thank you!', 'Have a great day!'):
                    start = j
                else:
                    break
        elif value == 'Robyn Hammitt' and 'Branch Manager/Escrow Officer' in plain[i + 1:i + 4]:
            start = i
            for j in range(i - 1, max(-1, i - 5), -1):
                if not plain[j] or plain[j].startswith('https://www.adobe.com/products/acrobat/readstep2.html') or plain[j].startswith('You can download Acrobat Reader at'):
                    start = j
                else:
                    break
        elif value == 'Customer Service' and 'Hope Plumbing, Heating and Cooling' in plain[i + 1:i + 3]:
            start = i
            for j in range(i - 1, max(-1, i - 4), -1):
                if plain[j] in ('', 'Sincerely,'):
                    start = j
                else:
                    break
        elif value.startswith('This message contains confidential information intended only for'):
            start = i
        elif value == '*Kevin Paulin* | Health Department, Environmental Health Specialist' and '*Johnson County Government*' in plain[i + 1:i + 4]:
            start = i
            for j in range(i - 1, max(-1, i - 4), -1):
                if plain[j] in ('', '<https://www.my-company.com/>'):
                    start = j
                else:
                    break
        elif value == "Your Friends at Carter's My Plumber" and i and plain[i - 1] == 'Sincerely,':
            remove.update((i - 1, i))
        elif re.fullmatch(r'Sent from my (?:iPhone|iPad|Android)(?: device)?', value, re.I):
            remove.add(i)
        if start is not None:
            end = next((j for j in range(i + 1, len(lines)) if 'Beware of cyber-crime!' in plain[j]), len(lines))
            remove.update(range(start, end))
    return ''.join(line for i, line in enumerate(lines) if i not in remove).rstrip()
