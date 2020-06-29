#!/usr/bin/env bash

# TODO: do this in salt?
# Kill all apps we modified
for app in "Activity Monitor" \
	"Calendar" \
	"cfprefsd" \
	"ControlStrip" \
	"Dock" \
	"Finder" \
	"Mail" \
	"Messages" \
	"Safari" \
	"SystemUIServer"; do
	killall "${app}" || true &> /dev/null
done
