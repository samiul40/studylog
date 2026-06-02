#!/bin/sh
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

exec gunicorn studyflow.wsgi:application --bind 0.0.0.0:8000 --workers 2
