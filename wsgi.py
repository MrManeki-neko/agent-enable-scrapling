# wsgi.py — gunicorn entry point
#
# Python module names cannot contain hyphens, so gunicorn cannot import
# "scrapling-service" directly. This shim loads the file by path and
# re-exports its Flask `app` object under a valid module name.

import importlib.util
import os

_service_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scrapling-service.py")
_spec = importlib.util.spec_from_file_location("scrapling_service", _service_path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

app = _module.app
