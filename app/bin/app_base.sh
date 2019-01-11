#!/bin/bash

# paths
app='/srv/app'
src='/srv/src'
manage=$app'/manage.py'
wsgi=$app'/wsgi.py'
static='/srv/static/'
media='/srv/media/'
log='/var/log/uwsgi/app.log'

# uwsgi params
port=8000
processes=8
threads=8
autoreload=3
uid='www-data'
gid='www-data'

# uwsgi params
port=8000
processes=8
threads=8
autoreload=3
uid='www-data'
gid='www-data'

# staging apps
# pip install -U django-cors-headers
# pip install django-debug-toolbar
# pip install jsonfield
pip install django==1.10.8
# Install (staging) libs
# /srv/bin/build/local/setup_lib.sh

# wait for other services
bash $app/bin/wait.sh
