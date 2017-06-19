#!/bin/bash
set -e
pylint -E main.py
mypy main.py
