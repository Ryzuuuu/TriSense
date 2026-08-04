# Redirects RPi.GPIO to our mock_gpio module
import sys
import os

# Ensure the parent directory (blind_mode) is in sys.path so we can import mock_gpio
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from mock_gpio import *
