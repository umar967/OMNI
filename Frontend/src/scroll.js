// DOM nodes are replaced during redraws. Remember positions by their path in
// the app so nested containers, textareas and horizontal scrollers survive.
export function captureScroll(root, viewport = window) {
  const positions = [];
  function visit(element, path) {
    if (element.scrollTop || element.scrollLeft)
      positions.push({ path, top: element.scrollTop, left: element.scrollLeft });
    [...element.children].forEach((child, index) => visit(child, [...path, index]));
  }
  visit(root, []);
  const x = viewport.scrollX;
  const y = viewport.scrollY;
  return () => {
    for (const { path, top, left } of positions) {
      const element = path.reduce((node, index) => node?.children[index], root);
      if (element) {
        element.scrollTop = top;
        element.scrollLeft = left;
      }
    }
    viewport.scrollTo(x, y);
  };
}
