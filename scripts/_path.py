"""Lets scripts import the traffix package when run as  python scripts/<name>.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
