# -*- coding: utf-8 -*-

import unittest
from os import remove
from os.path import join, isfile, dirname, abspath
from libs.hook import HookManager
from utils._compat import PY2


class HookTest(unittest.TestCase):

    def setUp(self):
        self.tf = join(
            dirname(dirname(abspath(__file__))), "tests", "forTestHook.py"
        )
        self.hm = HookManager(hooks_dir="tests")
        if isfile(self.tf):
            remove(self.tf)

    def tearDown(self):
        if isfile(self.tf):
            remove(self.tf)
            try:
                remove(self.tf + "c")
            except:
                pass

    def write_testmodule(self):
        content = "\n".join([
            "# -*- coding: utf-8 -*-",
            "__version__ = '0.1.0'",
            "__author__ = 'staugur'",
            "__hookname__ = 'test'",
            "def test_func(*args, **kwargs):",
            "    return dict(args=args, kwargs=kwargs)"
        ])
        with open(self.tf, "w") as fd:
            fd.write(content)

    def callback(self, res):
        self.assertIsInstance(res, dict)
        self.assertIn("code", res)
        self.assertIn("sender", res)
        self.assertIn("args", res)
        self.assertIn("kwargs", res)
        self.assertIsInstance(res['args'], (list, tuple))
        self.assertIsInstance(res['kwargs'], dict)

    @unittest.skipIf(PY2, "Damn py2 anomaly.")
    def test_initload(self):
        hooks = self.hm.get_all_hooks
        self.assertIsInstance(hooks, list)
        self.assertEqual(len(hooks), 0)

    @unittest.skipIf(PY2, "Damn py2 anomaly.")
    def test_reload(self):
        self.write_testmodule()
        self.hm.enable('test')
        self.hm.reload()
        hooks = self.hm.get_all_hooks
        self.assertIsInstance(hooks, list)
        self.assertEqual(len(hooks), 1)
        self.assertEqual(len(self.hm.get_enabled_hooks), 1)
        self.assertTrue("test" in self.hm.get_map_hooks)
        test = self.hm.proxy("test")
        self.assertEqual(test.__version__, '0.1.0')
        self.hm.call("test_func", self.callback)

    @unittest.skipIf(PY2, "Damn py2 anomaly.")
    def test_disable_enable(self):
        self.write_testmodule()
        self.hm.disable('test')
        self.hm.reload()
        hooks = self.hm.get_all_hooks
        self.assertEqual(len(hooks), 1)
        self.assertEqual(len(self.hm.get_enabled_hooks), 0)
        self.hm.enable('test')
        self.hm.reload()
        self.assertEqual(len(self.hm.get_enabled_hooks), 1)


if __name__ == '__main__':
    unittest.main()
