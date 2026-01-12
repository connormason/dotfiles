#!/usr/bin/env bash
# Code from: https://stackoverflow.com/questions/3466166/how-to-check-if-running-in-cygwin-mac-or-linux

unameOut="$(uname -s)"
case "${unameOut}" in
    Linux*)     machine=Linux;;
    Darwin*)    machine=Mac;;
    CYGWIN*)    machine=Cygwin;;
    MINGW*)     machine=MinGw;;
    *)          machine="UNKNOWN:${unameOut}"
esac
echo ${machine}
