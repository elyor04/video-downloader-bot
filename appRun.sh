#!/bin/bash

BASE_DIR=$(dirname "$(readlink -f "$0")")

apt-get update
apt-get install -y python3-full ffmpeg

cd "$BASE_DIR"
git pull

pip3 install -r requirements.txt
python3 main.py
