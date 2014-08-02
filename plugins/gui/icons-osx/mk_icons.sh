#!/bin/bash
cd ../icons-dark
for a in *.png; do
    convert $a -resize 19x19 ../icons-osx/$a
done
