#!/bin/bash

cd "$(this_dir)" || exit

. ~/bash_ci

ci_run pylint -E *.py
ci_run mypy *.py

ci_report_errors
