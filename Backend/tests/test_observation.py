"""Real browser observation tests; local HTML only, no model or network calls."""
import json
import os
import unittest

from playwright.sync_api import sync_playwright

from Backend.explore_website import execute, observe, release


class ObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(
                channel=os.environ.get('OMNI_TEST_BROWSER_CHANNEL', 'chrome') or None,
                headless=True, timeout=15000)
        except Exception:
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 800, 'height': 600})
        self.addCleanup(self.page.close)

    def snapshot(self):
        state, handles = observe(self.page)
        self.addCleanup(release, handles)
        return state, handles

    def test_geometry_labels_styles_and_target_identity(self):
        self.page.set_content('''
            <label for="query">Search catalog</label>
            <input id="query" type="search" placeholder="Keywords" title="Catalog search"
              style="position:absolute;left:40px;top:80px;width:200px;height:40px;
                     box-sizing:border-box;font-size:18px;color:rgb(10,20,30);
                     background-color:rgb(240,241,242)">
            <button style="display:none">Hidden before target</button>
            <button id="target" aria-label="More details" onclick="this.textContent='Opened'">Details</button>
            <span id="first">Product</span><span id="second">options</span>
            <button aria-labelledby="first second">Options</button>
            <input type="password" value="secret">
            <select><option value="one">One</option></select>
        ''')
        state, handles = self.snapshot()
        query, button, labelled, password, select = state['controls']
        self.assertEqual(state['viewport'], {'width': 800, 'height': 600})
        self.assertEqual(query['bounding_box'], {'x': 40, 'y': 80, 'width': 200, 'height': 40})
        self.assertEqual(query['viewport_position'], {
            'center_x': 140 / 800, 'center_y': 100 / 600, 'visible_fraction': 1})
        self.assertEqual(query['style'], {'font_size': '18px', 'color': 'rgb(10, 20, 30)',
                                           'background_color': 'rgb(240, 241, 242)'})
        self.assertEqual(query['name'], 'Search catalog')
        self.assertEqual(query['label_metadata']['associated_labels'], 'Search catalog')
        self.assertEqual(query['label_metadata']['placeholder'], 'Keywords')
        self.assertEqual(query['label_metadata']['title'], 'Catalog search')
        self.assertEqual(labelled['name'], 'Product options')
        self.assertEqual(password['value'], '[redacted]')
        self.assertEqual(select['options'], [{'text': 'One', 'value': 'one'}])
        self.assertEqual([c['id'] for c in state['controls']], list(handles))
        self.assertEqual(button['name'], 'More details')
        self.assertEqual(handles[button['id']].get_attribute('id'), 'target')
        self.assertEqual(state, self.snapshot()[0])
        json.dumps(state, allow_nan=False)
        self.assertEqual(execute(self.page, {'action': 'click', 'target': button['id']},
                                 state, handles, self.page.url), 'executed')
        self.assertEqual(self.page.locator('#target').inner_text(), 'Opened')

    def test_hidden_disabled_and_transparent_controls(self):
        self.page.set_content('''
            <button hidden>Hidden</button><button style="visibility:hidden">Invisible</button>
            <div style="display:none"><button>Hidden ancestor</button></div>
            <input type="hidden"><button style="width:0;height:0;padding:0;border:0"></button>
            <button disabled>Disabled</button><button aria-disabled="true">ARIA disabled</button>
            <div style="opacity:0"><button>Transparent ancestor</button></div>
        ''')
        state, handles = self.snapshot()
        self.assertEqual([c['name'] for c in state['controls']],
                         ['Disabled', 'ARIA disabled', 'Transparent ancestor'])
        self.assertTrue(all(c['disabled'] for c in state['controls'][:2]))
        self.assertEqual(state['controls'][2]['visibility']['effective_opacity'], 0)
        self.assertEqual(execute(self.page, {'action': 'click', 'target': 0}, state,
                                 handles, self.page.url), 'blocked: disabled control')

    def test_scrolling_and_partial_viewport_intersection(self):
        self.page.set_content('''<style>body {margin:0;height:2000px}
            button {position:absolute;width:100px;height:40px;left:20px}</style>
            <button style="top:580px">Partial</button>
            <button style="top:900px">Below fold</button>''')
        before, _ = self.snapshot()
        self.assertEqual(len(before['controls']), 1)
        control = before['controls'][0]
        self.assertEqual(control['viewport_position']['visible_fraction'], 0.5)
        self.assertFalse(control['visibility']['fully_in_viewport'])
        self.page.evaluate('scrollTo(0, 700)')
        after, handles = self.snapshot()
        self.assertEqual(after['scroll']['y'], 700)
        self.assertEqual([c['name'] for c in after['controls']], ['Below fold'])
        self.assertEqual(after['controls'][0]['bounding_box']['y'], 200)
        self.assertEqual(handles[0].inner_text(), 'Below fold')

    def test_open_dialog_preserves_control_scope(self):
        self.page.set_content('''<button>Outside</button>
            <dialog><label for="inside">Inside label</label><input id="inside">
            <button onclick="this.closest('dialog').close()">Close</button></dialog>''')
        self.page.evaluate("document.querySelector('dialog').showModal()")
        state, handles = self.snapshot()
        self.assertEqual([c['name'] for c in state['controls']], ['Inside label', 'Close'])
        self.assertNotIn('Outside', state['visible_text'])
        self.assertEqual(handles[0].get_attribute('id'), 'inside')
        self.assertTrue(state['controls'][0]['visibility']['fully_in_viewport'])
        self.page.evaluate("document.querySelector('dialog').close()")
        self.assertEqual([c['name'] for c in self.snapshot()[0]['controls']], ['Outside'])


if __name__ == '__main__':
    unittest.main()
