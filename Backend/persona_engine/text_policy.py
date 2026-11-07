"""Conservative text exposure. Structural associations are not semantic proof."""
from copy import deepcopy
import re


def normalized(value):
    return ' '.join(str(value).casefold().split())


def forbidden_strings(observation, selected):
    denied = set()
    for c in observation.get('controls', []):
        if c['id'] not in selected:
            denied.update(normalized(v) for v in [c.get('name', ''),
                *(c.get('label_metadata') or {}).values(),
                *(o.get('text', '') for o in c.get('options', []))] if isinstance(v, str) and v.strip())
        if c.get('tag') in ('input', 'textarea') and c.get('type') not in ('button','submit','reset','radio','checkbox'):
            if c.get('value') and c['value'] != '[redacted]':
                denied.add(normalized(c['value']))
    return denied


def sensitive(value, denied):
    text = normalized(value)
    return any(v in text for v in denied) or bool(re.search(
        r'[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b(?:\d[ -]*?){13,19}\b', text))


def scrub_strings(value, denied):
    if isinstance(value, str):
        return '' if sensitive(value, denied) else value
    if isinstance(value, list):
        return [scrub_strings(v, denied) for v in value]
    if isinstance(value, dict):
        return {k:scrub_strings(v, denied) for k,v in value.items()}
    return value


def safe_blocks(blocks):
    # Model/replay boundary: no arbitrary attributes or DOM paths.
    fields = ('id','fingerprint','text','bounding_box','fragments','viewport_intersection',
              'visibility','association','quality_flags','privacy')
    shapes = {'bounding_box':('x','y','width','height'),
              'visibility':('effective_opacity','css_visible','occlusion'),
              'association':('control_ids','complete','kinds','status'),
              'viewport_intersection':('rects','visible_fraction','intersects','fully_visible')}
    out = []
    for block in blocks:
        safe = {k:deepcopy(block[k]) for k in fields if k in block}
        for key, keys in shapes.items():
            safe[key] = {k:deepcopy(block.get(key, {}).get(k)) for k in keys if k in block.get(key, {})}
        for rects in (safe.get('fragments', []), safe.get('viewport_intersection', {}).get('rects', [])):
            for r in rects:
                for key in list(r):
                    if key not in ('x','y','width','height'):
                        del r[key]
        out.append(safe)
    return out


def project_text(observation, selected, budget, denied):
    source = observation.get('text_observation') or {}
    blocks = source.get('blocks', []) if source.get('version') == 'geometry-text-1' else []
    # Detect copied labels split over adjacent nodes as well as whole-node labels.
    joined, offsets = '', []
    for block in blocks:
        start = len(joined)
        joined += normalized(block.get('text', '')) + ' '
        offsets.append((start, len(joined)))
    tainted = set()
    for term in denied:
        offset = joined.find(term)
        while offset >= 0:
            tainted.update(i for i,(a,b) in enumerate(offsets) if a < offset+len(term) and b > offset)
            offset = joined.find(term, offset+1)
    permitted = []
    for i, block in enumerate(blocks):
        association = block.get('association', {})
        intersection = block.get('viewport_intersection', {})
        if (i in tainted or sensitive(block.get('text', ''), denied) or block.get('privacy') != 'screened'
                or not association.get('complete') or not set(association.get('control_ids', [])).issubset(selected)
                or not intersection.get('fully_visible') or 'text_truncated' in block.get('quality_flags', [])
                or not block.get('visibility', {}).get('css_visible')):
            continue
        permitted.append(block)
    # DOM reading order; this engineering budget is not a human fixation model.
    shown = safe_blocks(permitted[:budget])
    return shown, {'source_status':source.get('status', 'legacy_unavailable'),
        'observed_fragments':len(blocks), 'eligible_fragments':len(permitted),
        'exposed_fragments':len(shown), 'withheld_fragments':len(blocks)-len(shown),
        'partial':source.get('status') != 'complete' or len(shown)<len(blocks)}
