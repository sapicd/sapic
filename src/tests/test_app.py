# -*- coding: utf-8 -*-

import unittest
from app import app
from jinja2 import ChoiceLoader

class AppTest(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.app = app

    def test_app(self):
        self.assertIsInstance(self.app.jinja_loader, ChoiceLoader)


if __name__ == '__main__':
    unittest.main()
