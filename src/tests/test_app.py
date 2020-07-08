# -*- coding: utf-8 -*-

import unittest
from jinja2 import ChoiceLoader
from utils.web import default_login_auth, get_site_config
from utils.tool import generate_random
from app import app
from utils.cli import exec_createuser


class AppTest(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        self.app = app

    def login(self, username, password):
        return self.client.post('/api/login', data=dict(
            username=username,
            password=password,
            set_state=True,
        ), follow_redirects=False)

    def logout(self):
        self.client.get("/logout", follow_redirects=True)

    def test_app(self):
        self.assertIsInstance(self.app.jinja_loader, ChoiceLoader)
        self.assertIn("hookmanager", self.app.extensions)
        self.assertIn("get_call_list", self.app.jinja_env.globals)
        self.assertIn("api", self.app.blueprints)
        self.assertIn("front.index", self.app.view_functions)

    def test_api(self):
        #: No cookie
        self.logout()

        rv = self.client.get("/api", follow_redirects=True)
        self.assertIn(b"Hello picbed", rv.data)

        rv = self.client.get("/api/login")
        self.assertEqual(405, rv.status_code)
        self.assertIn(b"Not Allowed", rv.data)

        rv = self.client.post("/api/config")
        self.assertEqual(404, rv.status_code)

    def test_comment_login_logout(self):
        user = ("test_" + generate_random()).lower()
        pwd = "pwd123"
        rv = self.login(user, pwd)
        self.assertEqual(200, rv.status_code)
        self.assertIn(b"No valid username found", rv.data)

        exec_createuser(user, pwd)
        rv = self.login(user, pwd)
        data = rv.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("sid", data)
        self.assertIn("code", data)
        self.assertIn("expire", data)
        self.assertEqual(data["code"], 0)
        with self.app.test_request_context():
            self.app.preprocess_request()
            (signin, userinfo) = default_login_auth(data["sid"])
            self.assertTrue(signin)
            self.assertIsInstance(userinfo, dict)
            self.assertEqual(user, userinfo["username"])

        rv = self.client.get("/api/config")
        self.assertEqual(405, rv.status_code)
        rv = self.client.post("/api/config")
        self.assertEqual(403, rv.status_code)

        self.logout()
        rv = self.client.post("/api/config")
        self.assertEqual(404, rv.status_code)

    def test_admin(self):
        user = "testadmin_" + generate_random()
        pwd = "pwd123"
        exec_createuser(user, pwd, is_admin=1)
        rv = self.login(user, pwd)
        self.assertIn(b"sid", rv.data)

        rv = self.client.post("/api/config", data=dict(hello='world'))
        self.assertEqual(200, rv.status_code)
        site = get_site_config()
        self.assertIn("hello", site)
        self.assertEqual(site["hello"], "world")

        hm = self.app.extensions["hookmanager"]
        self.client.post("/api/hook?Action=disable", data=dict(
            name='up2local'
        ))
        self.assertEqual(2, len(hm.get_enabled_hooks))
        self.client.post("/api/hook?Action=enable", data=dict(
            name='up2local'
        ))
        self.assertEqual(3, len(hm.get_enabled_hooks))


if __name__ == '__main__':
    unittest.main()
