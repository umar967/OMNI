"""Bounded DOM text fragments in CSS-pixel viewport coordinates.

No OCR, iframe/shadow traversal or assertion of complete visual visibility.
Associations use DOM containment, HTML labels and ARIA references, never proximity.
"""
import hashlib
import json

TEXT_VERSION = 'geometry-text-1'

SCRIPT = r'''({controls, selector, maxNodes, maxFragments}) => {
    const scope = document.querySelector('dialog[open]') || document.body;
    const ids = new Map(controls.map((el, i) => [el, i]));
    const all = [...document.querySelectorAll(selector)];
    const normalize = x => (x || '').replace(/\s+/g, ' ').trim();
    const privateValues = [...document.querySelectorAll('input,textarea,[contenteditable="true"],[data-omni-private],[data-private]')]
        .filter(el => !['button','submit','reset','checkbox','radio','hidden'].includes(el.type))
        .map(el => normalize(el.value || el.innerText)).filter(Boolean);
    const sensitive = text => privateValues.some(v => text.includes(v)) ||
        /[\w.+-]+@[\w.-]+\.[a-z]{2,}/i.test(text) || /\b(?:\d[ -]*?){13,19}\b/.test(text);
    const rect = r => ({x:r.x, y:r.y, width:r.width, height:r.height});
    const intersect = (a,b) => {
        const x=Math.max(a.x,b.x), y=Math.max(a.y,b.y);
        return {x,y,width:Math.max(0,Math.min(a.x+a.width,b.x+b.width)-x),
            height:Math.max(0,Math.min(a.y+a.height,b.y+b.height)-y)};
    };
    const blocks=[]; let visited=0, omitted=0, truncated=false;
    const walker=document.createTreeWalker(scope,NodeFilter.SHOW_TEXT);
    let node;
    while (node=walker.nextNode()) {
        if (++visited > maxNodes || blocks.length >= maxFragments) {truncated=true; break;}
        const el=node.parentElement, text=normalize(node.textContent);
        if (!el || !text || el.closest('script,style,noscript,template,select,option')) continue;
        if (el.closest('input,textarea,[contenteditable="true"],[data-omni-private],[data-private]') || sensitive(text)) {
            omitted++; continue;
        }
        let opacity=1, hidden=false;
        for (let a=el;a;a=a.parentElement) {
            const s=getComputedStyle(a);
            opacity*=Number(s.opacity);
            if (s.display==='none' || ['hidden','collapse'].includes(s.visibility) ||
                a.hidden || a.inert || a.getAttribute('aria-hidden')==='true') hidden=true;
        }
        if (hidden || opacity<=0) continue;
        const range=document.createRange(); range.selectNodeContents(node);
        const box=rect(range.getBoundingClientRect());
        if (!box.width || !box.height) continue;
        // Range rectangles respect line wrapping. Ancestor overflow clipping is
        // applied per fragment; complex clip paths and occlusion remain unknown.
        const fragments=[...range.getClientRects()].map(rect);
        let shown=[];
        for (const f of fragments) {
            let clip=intersect(f,{x:0,y:0,width:innerWidth,height:innerHeight});
            for (let a=el;a;a=a.parentElement) {
                const s=getComputedStyle(a), r=a.getBoundingClientRect();
                if (/(hidden|clip|auto|scroll)/.test(s.overflowX))
                    clip=intersect(clip,{x:r.x,y:clip.y,width:r.width,height:clip.height});
                if (/(hidden|clip|auto|scroll)/.test(s.overflowY))
                    clip=intersect(clip,{x:clip.x,y:r.y,width:clip.width,height:r.height});
            }
            if (clip.width && clip.height) shown.push(clip);
        }
        if (!shown.length) continue;
        const area=fragments.reduce((n,r)=>n+r.width*r.height,0);
        const fraction=Math.min(1,shown.reduce((n,r)=>n+r.width*r.height,0)/area);
        const related=[], kinds=new Set();
        for (const control of all) {
            let associated=false;
            if (control.contains(node)) {associated=true;kinds.add('descendant');}
            if ([...(control.labels || [])].some(label=>label.contains(node))) {associated=true;kinds.add('html_label');}
            for (const attr of ['aria-labelledby','aria-describedby','aria-errormessage','aria-details','aria-controls']) {
                if ((control.getAttribute(attr)||'').split(/\s+/).filter(Boolean)
                    .some(id=>document.getElementById(id)?.contains(node))) {associated=true;kinds.add(attr);}
            }
            if (associated) related.push(control);
        }
        // A structural path is stable across unchanged observations, not a locator
        // or identity guarantee across DOM replacement. No element text in this path.
        let path=[];
        for (let a=el;a && a!==scope;a=a.parentElement)
            path.push([...a.parentNode.childNodes].indexOf(a));
        path.reverse(); path.push([...el.childNodes].indexOf(node));
        const flags=['occlusion_not_checked','complex_clipping_not_checked'];
        if (!related.length) flags.push('semantic_association_unknown');
        if (fraction < .9999) flags.push('partially_clipped');
        if (text.length>500) flags.push('text_truncated');
        if (fragments.length>32) flags.push('fragment_geometry_truncated');
        blocks.push({text:text.slice(0,500), bounding_box:box, fragments:fragments.slice(0,32),
            viewport_intersection:{rects:shown.slice(0,32),visible_fraction:fraction,intersects:true,fully_visible:fraction>=.9999},
            visibility:{effective_opacity:opacity,css_visible:true,occlusion:'unknown'},
            association:{control_ids:related.filter(c=>ids.has(c)).map(c=>ids.get(c)),
                complete:related.every(c=>ids.has(c)), kinds:[...kinds],
                status:related.length?'deterministic':'unassociated'},
            quality_flags:flags, privacy:'screened', _path:path});
    }
    const privateControls=controls.map((el,i)=>({el,i})).filter(({el}) => {
        const labelled=(el.getAttribute('aria-labelledby')||'').split(/\s+/).map(id=>document.getElementById(id)?.innerText||'').join(' ');
        const names=[el.innerText,el.getAttribute('aria-label'),labelled,el.getAttribute('title'),
            el.getAttribute('placeholder'),...[...(el.labels||[])].map(l=>l.innerText)].map(normalize).join(' ');
        return !!el.closest('[contenteditable="true"],[data-omni-private],[data-private]') || sensitive(names);
    }).map(({i})=>i);
    let decodedUrl=location.href;
    try {decodedUrl=decodeURI(decodedUrl);} catch (_) { /* malformed escapes stay literal */ }
    return {blocks,private_control_ids:privateControls,private_title:sensitive(normalize(document.title)),
        private_url:sensitive(normalize(decodedUrl)),
        status:truncated || blocks.some(b=>b.quality_flags.some(f=>f.endsWith('_truncated')))?'partial':'complete',nodes_visited:Math.min(visited,maxNodes),
        omitted_sensitive:omitted,limits:{max_nodes:maxNodes,max_fragments:maxFragments,max_text_chars:500},
        limitations:['Occlusion, complex clipping, generated content, canvas, frames and shadow DOM are not fully observed.',
            'Unassociated means no deterministic DOM association was found; semantic independence is not established.',
            'Privacy screening is conservative and incomplete; screenshots and legacy evidence may contain private content.']};
}'''


def observe_text(page, handles, selector, max_nodes=4000, max_fragments=256):
    try:
        result = page.evaluate(SCRIPT, {'controls':list(handles.values()), 'selector':selector,
                                       'maxNodes':max_nodes, 'maxFragments':max_fragments})
        for block in result['blocks']:
            path = block.pop('_path')
            block['id'] = 'text-' + hashlib.sha256(json.dumps(path).encode()).hexdigest()[:20]
            block['fingerprint'] = hashlib.sha256((block['id'] + block['text']).encode()).hexdigest()
        result['version'] = TEXT_VERSION
        return result
    except Exception as exc:
        return {'version':TEXT_VERSION, 'status':'unavailable', 'blocks':[],
                'limitations':['Text observation unavailable: ' + type(exc).__name__]}
