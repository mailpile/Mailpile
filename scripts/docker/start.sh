#!/bin/bash

cd Mailpile
git pull
$(make dev)
./mp --set http_host=0.0.0.0
./mp
