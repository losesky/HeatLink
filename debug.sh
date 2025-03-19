#!/bin/bash
python backend/start_server.py 2>&1 | tee server_debug.log
