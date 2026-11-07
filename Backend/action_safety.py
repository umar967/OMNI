"""Conservative execution-time checks. Never resolve an old numeric ID anew."""
import re
from urllib.parse import unquote, urlsplit

RESTRICTED = re.compile(r'\b(check\s*out|checkout|place order|pay|payment|buy now|purchase|subscribe|send|'
                        r'delete|remove account|sign\s*up|register|create account|log\s*in|sign\s*in|submit)\b', re.I)
ACCOUNT = re.compile(r'\b(log\s*in|sign\s*in|sign\s*up|register|create account)\b', re.I)
SNAPSHOT = r'''el => {
    const key = Symbol.for('omni.target.identities');
    const store = window[key] ||= {ids: new WeakMap(), forms: new WeakMap(), next: 0,
        document: [...crypto.getRandomValues(new Uint32Array(4))].join('-')};
    if (!store.ids.has(el)) store.ids.set(el, ++store.next);
    const labels = [...(el.labels || [])].map(x => x.innerText).join(' ');
    const labelled = (el.getAttribute('aria-labelledby') || '').split(' ')
        .map(id => document.getElementById(id)?.innerText || '').join(' ').trim();
    const tag = el.tagName.toLowerCase(), type = el.type || '';
    const form = el.form || el.closest('form');
    const link = el.closest('a[href]');
    let hiddenState = '';
    if (form) {
        // Detect changed hidden product IDs/tokens without writing their values
        // to the journal or sending them to the model.
        const values = JSON.stringify([...form.elements].filter(e => e.type === 'hidden').map(e => [e.name, e.value]));
        if (store.forms.get(form)?.values !== values) store.forms.set(form, {values, revision: ++store.next});
        hiddenState = store.document + ':' + store.forms.get(form).revision;
    }
    const role = el.getAttribute('role') || ({button:'button',a:'link',select:'combobox',textarea:'textbox'}[tag]) ||
        (tag === 'input' ? ({checkbox:'checkbox',radio:'radio',submit:'button',button:'button',search:'searchbox'}[type] || 'textbox') : '');
    let visible = true;
    for (let node = el; node; node = node.parentElement) {
        const s = getComputedStyle(node);
        if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0 || node.hidden || node.inert) visible = false;
    }
    const r = el.getBoundingClientRect();
    const dialog = document.querySelector('dialog[open]');
    return {identity: store.document + ':' + store.ids.get(el), url: location.href, connected: el.isConnected,
        visible: visible && !!r.width && !!r.height && (!dialog || dialog.contains(el)),
        enabled: !el.matches(':disabled') && !el.closest('[aria-disabled="true"]'),
        semantic: {tag, type, role,
            name: el.getAttribute('aria-label') || labelled || labels || el.innerText?.trim() ||
                (['button','submit','reset'].includes(type) ? el.value : '') || el.getAttribute('placeholder') || '',
            dom_id: el.id || '', title: el.getAttribute('title') || '',
            control_name: el.getAttribute('name') || '',
            action_value: ['button','submit','reset','image','checkbox','radio'].includes(type) ? el.value : '',
            data: {...el.dataset},
            href: link ? link.href : '', target: link?.getAttribute('target') || '', download: !!link?.hasAttribute('download'),
            editable: el.isContentEditable, readonly: !!el.readOnly,
            form: form ? {identity: (() => {if (!store.ids.has(form)) store.ids.set(form, ++store.next); return store.document + ':' + store.ids.get(form);})(),
                action: el.hasAttribute('formaction') ? el.formAction : form.action,
                method: el.hasAttribute('formmethod') ? el.formMethod : form.method,
                target: el.getAttribute('formtarget') || form.target,
                hidden_state: hiddenState,
                credentials: !!form.querySelector('input[type=password],input[type=file],input[autocomplete^="cc-"],input[autocomplete="new-password"]'),
                fields: [...form.elements].map(e => [e.tagName, e.type, e.name, e.getAttribute('autocomplete') || '',
                    e.getAttribute('aria-label') || e.innerText || (['button','submit','reset'].includes(e.type) ? e.value : ''),
                    e.getAttribute('formaction') || '', e.getAttribute('formmethod') || ''])} : null,
            options: tag === 'select' ? [...el.options].map(o => [o.value, o.text, o.disabled]) : []}};
}'''


def snapshot(element):
    return element.evaluate(SNAPSHOT)


def same_origin(url, home):
    a, b = urlsplit(url), urlsplit(home)
    return a.scheme in {'http', 'https'} and (a.scheme, a.netloc) == (b.scheme, b.netloc)


def restricted(text, allow_account=False):
    # An account-navigation exception must not also exempt "delete" or "pay".
    return any(not (allow_account and ACCOUNT.fullmatch(match.group()))
               for match in RESTRICTED.finditer(text))


def install_navigation_guard(context, home):
    def guard(route):
        target = urlsplit(route.request.url)
        workspace = target.hostname in ('localhost', '127.0.0.1') and target.port == 8000
        if workspace or (route.request.is_navigation_request() and not same_origin(route.request.url, home)):
            route.abort()
        else:
            route.continue_()
    context.route('**/*', guard)


def validate(current, expected, action, value, home):
    if not expected or not current.get('connected') or current.get('identity') != expected.get('identity'):
        return 'refresh_required: original element is detached, replaced or unidentified'
    if current.get('url') != expected.get('url'):
        return 'refresh_required: page URL changed after observation'
    if current.get('semantic') != expected.get('semantic'):
        return 'refresh_required: target meaning or destination changed'
    if not current.get('enabled') and not expected.get('enabled'):
        return 'blocked: disabled control'
    if not current.get('visible') or not current.get('enabled'):
        return 'refresh_required: target is hidden, inert or disabled'
    s = current['semantic']
    tag, kind, name = s['tag'], s['type'], s['name']
    form = s.get('form')
    if kind in {'password', 'file', 'hidden'}:
        return 'blocked: credential/file/hidden input outside exploration'
    if action in {'click', 'press', 'check', 'select', 'fill'}:
        account_link = tag == 'a' and ACCOUNT.search(name)
        if restricted(name, allow_account=bool(account_link)):
            return 'blocked: account/submission/checkout boundary'
        if s.get('href'):
            if not same_origin(s['href'], home) or s['target'] not in ('', '_self') or s['download']:
                return 'blocked: external navigation, download or new browsing context'
            path = unquote(urlsplit(s['href']).path + '?' + urlsplit(s['href']).query).replace('-', ' ').replace('_', ' ')
            if restricted(path, allow_account=True):
                return 'blocked: restricted destination'
        if form:
            path = unquote(urlsplit(form['action']).path + '?' + urlsplit(form['action']).query).replace('-', ' ').replace('_', ' ')
            if (not same_origin(form['action'], home) or form['target'] not in ('', '_self') or
                    form['credentials'] or RESTRICTED.search(path)):
                return 'blocked: restricted form destination or credential semantics'
            submit = action == 'press' or (action == 'click' and kind in {'submit', 'image'})
            reversible = re.search(r'\b(search|add\s+to\s+(?:cart|bag|basket))\b', name, re.I)
            if submit and not reversible:
                return 'blocked: form submission requires a dedicated test setup'
            if action == 'press':
                # Enter may activate another submitter, including its URL override.
                for field in form.get('fields', []):
                    if field[1] in {'submit', 'image'} and (RESTRICTED.search(field[4]) or field[5] or field[6]):
                        return 'blocked: ambiguous implicit form submitter'
    if action == 'fill' and (not (tag in {'input', 'textarea'} or s['editable']) or s['readonly'] or
                            not isinstance(value, str) or len(value) > 500):
        return 'blocked: invalid fill target or value'
    if action == 'select' and (tag != 'select' or value not in [o[0] for o in s['options'] if not o[2]]):
        return 'blocked: invalid select option'
    if action == 'check' and (kind not in {'checkbox', 'radio'} or value not in {'true', 'false'}):
        return 'blocked: invalid checked state or target'
    if action == 'press' and (value != 'Enter' or tag != 'input' or not (kind == 'search' or re.search(r'\bsearch\b', name, re.I))):
        return 'blocked: Enter is only enabled on identified search inputs'
    return None


def execute_validated(page, decision, observation, handles, home, on_dispatch=lambda: None):
    action, value = decision.get('action'), decision.get('value', '')
    if page.url != observation.get('url'):
        return 'refresh_required: page URL changed after observation'
    if action in {'scroll', 'back', 'home', 'wait'} or (action == 'press' and value == 'Escape'):
        if action == 'scroll' and value not in {'up', 'down'}:
            return 'blocked: invalid scroll direction'
        on_dispatch()
        if action == 'scroll':
            page.mouse.wheel(0, (1 if value == 'down' else -1) * 550)
        elif action == 'back':
            page.go_back(wait_until='domcontentloaded')
        elif action == 'home':
            page.goto(home, wait_until='domcontentloaded')
        elif action == 'wait':
            page.wait_for_timeout(1500)
        else:
            page.keyboard.press('Escape')
        return 'executed'
    if action not in {'click', 'fill', 'select', 'check', 'hover', 'press'}:
        return 'blocked: unsupported action'
    index = decision.get('target')
    control = next((c for c in observation.get('controls', []) if c['id'] == index), {})
    if type(index) is not int or index not in handles or not control:
        return 'refresh_required: target not in the original observation'
    element = handles[index]  # Never use a selector or numeric ID to reacquire this node.
    expected = control.get('target_snapshot')
    try:
        problem = validate(snapshot(element), expected, action, value, home)
        if problem:
            return problem
        element.scroll_into_view_if_needed(timeout=1500)
        # Scrolling may trigger application handlers; check again after it.
        problem = validate(snapshot(element), expected, action, value, home)
        if problem:
            return problem
    except Exception:
        return 'refresh_required: target could not be inspected before dispatch'
    # Capture-phase guard closes the common hover/pointerdown -> changed click race.
    # It cannot sandbox arbitrary application JavaScript or guarantee server effects.
    element.evaluate('''(el, expected) => {
        const inspect = ''' + SNAPSHOT + ''';
        const types = ['pointerover','mouseover','pointerdown','mousedown','mouseup','click',
            'keydown','beforeinput','input','change','submit'];
        const key = Symbol.for('omni.dispatch.guard');
        window[key]?.remove();
        const state = {blocked: false};
        const guard = event => {
            if (!event.composedPath().includes(el) && !(event.type === 'submit' && event.target === (el.form || el.closest('form')))) return;
            const current = inspect(el);
            if (state.blocked || !current.connected || !current.visible || !current.enabled ||
                current.identity !== expected.identity || current.url !== expected.url ||
                JSON.stringify(current.semantic) !== JSON.stringify(expected.semantic)) {
                state.blocked = true; event.preventDefault(); event.stopImmediatePropagation();
            }
        };
        state.remove = () => types.forEach(t => window.removeEventListener(t, guard, true));
        types.forEach(t => window.addEventListener(t, guard, true));
        window[key] = state;
    }''', expected)
    on_dispatch()
    # ElementHandle actions do not retarget replacements. A timeout after dispatch
    # is uncertain, even when Playwright's error text suggests a navigation error.
    if action == 'click':
        element.click(timeout=1500)
    elif action == 'hover':
        element.hover(timeout=1500)
    elif action == 'fill':
        element.fill(value, timeout=1500)
    elif action == 'select':
        element.select_option(value=value, timeout=1500)
    elif action == 'check':
        element.set_checked(value == 'true', timeout=1500)
    else:
        element.press('Enter', timeout=1500)
    # If navigation closed the page, failure here conservatively stays unknown.
    guarded = page.evaluate('''() => {
        const key = Symbol.for('omni.dispatch.guard'), state = window[key];
        state?.remove(); delete window[key]; return !!state?.blocked;
    }''')
    if guarded:
        raise RuntimeError('Target changed during dispatch; some input events may have occurred')
    return 'executed'
