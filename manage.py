#!/usr/bin/env python
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, 'tagger'))


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "camper.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
