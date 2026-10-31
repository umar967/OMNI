"""Capture actual browser viewports with the current interaction highlighted."""
import hashlib
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


READINESS = """() => {
    const visible = el => {
        const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight &&
            r.right > 0 && r.left < innerWidth && s.visibility !== 'hidden' && s.display !== 'none';
    };
    const images = [...document.images].filter(visible);
    return {content: !!document.body && (document.body.innerText.trim().length > 0 || images.length > 0),
        images_ready: images.every(img => img.complete && img.naturalWidth > 0),
        pending_images: images.filter(img => !img.complete || !img.naturalWidth).length,
        fonts_ready: !document.fonts || document.fonts.status === 'loaded',
        busy: [...document.querySelectorAll('[aria-busy="true"], [data-loading="true"], .skeleton, .loading-skeleton')].some(visible)};
}"""


def wait_for_capture(page, timeout=8000):
    """Bounded viewport readiness; timeout is a capture limitation, not a defect."""
    timed_out = False
    try:
        page.wait_for_function('() => { const s = (' + READINESS + ')(); return s.content && s.images_ready && s.fonts_ready && !s.busy; }', timeout=timeout)
    except PlaywrightTimeoutError:
        timed_out = True
    status = page.evaluate(READINESS)
    return dict(status, timed_out=timed_out,
                ready=not timed_out and status['content'] and status['images_ready'] and status['fonts_ready'] and not status['busy'],
                scope='Viewport images, fonts and common loading indicators; CSS backgrounds and offscreen content are not verified.')


def capture_step(page, folder, step, phase, target=None, metadata=None):
    filename = f'step-{step}-{phase}.png'
    directory = folder / 'evidence'
    directory.mkdir(exist_ok=True)
    readiness = wait_for_capture(page)
    if metadata is not None:
        metadata.update(readiness)
        metadata.update(title=page.title(), url=page.url)
    marked = False
    original = None
    try:
        if target is not None:
            try:
                original = target.evaluate("el => el.getAttribute('style')")
                target.evaluate("el => { el.style.outline = '4px solid #f59e0b'; el.style.outlineOffset = '4px'; }")
                marked = True
            except Exception:
                pass  # A navigation can detach the previous target.
        image = page.screenshot(path=str(directory / filename), animations='disabled', full_page=False,
                        mask=[page.locator('input[type="password"], input[type="file"]')])
        if metadata is not None:
            metadata['sha256'] = hashlib.sha256(image).hexdigest()
        return filename
    finally:
        if marked:
            try:
                target.evaluate("(el, value) => value === null ? el.removeAttribute('style') : el.setAttribute('style', value)", original)
            except Exception:
                pass
