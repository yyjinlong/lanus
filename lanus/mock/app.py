# -*- coding:utf-8 -*-
#
# Copyright @ 2020 OPS, YY Inc.
#
# Author: Jinlong Yang
#

import logging

from osmo.wsgi import WSGIApplication

LOG = logging.getLogger(__name__)


class MockApi(WSGIApplication):
    name = 'mock lanus need api'
    version = '1.0'

    def init_flask(self):
        super(MockApi, self).init_flask()

        app = self.flask_app
        self.register(app)

    def register(self, app):
        import lanus.mock.v1 as v1
        app.register_blueprint(v1.bp, url_prefix='')


mock_api = MockApi().entry_point()
