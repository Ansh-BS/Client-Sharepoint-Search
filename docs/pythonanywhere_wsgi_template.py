# PythonAnywhere WSGI configuration for Client SharePoint Search.
#
# This is a TEMPLATE. Do NOT add it as a new file on the server.
# When you set up the web app, PythonAnywhere auto-generates a WSGI file at:
#     /var/www/<your-username>_pythonanywhere_com_wsgi.py
# Open that file (there is an "edit" link on the Web tab), delete everything
# already in it, and paste the block below in its place. Then fix the two
# placeholders and Save.

import sys

# Absolute path to the project folder on the server (the one that holds app.py).
# Example: /home/janedoe/sharepoint-search
project_home = "/home/<your-username>/<project-folder-name>"

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# app.py exposes a module-level `app`; PythonAnywhere expects `application`.
from app import app as application  # noqa: E402
