"""Capture actual browser viewports with the current interaction highlighted."""


def capture_step(page, folder, step, phase, target=None):
    filename = f'step-{step}-{phase}.png'
    directory = folder / 'evidence'
    directory.mkdir(exist_ok=True)
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
        page.screenshot(path=str(directory / filename), animations='disabled',
                        mask=[page.locator('input[type="password"], input[type="file"]')])
        return filename
    finally:
        if marked:
            try:
                target.evaluate("(el, value) => value === null ? el.removeAttribute('style') : el.setAttribute('style', value)", original)
            except Exception:
                pass
