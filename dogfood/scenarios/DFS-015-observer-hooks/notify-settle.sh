#!/bin/sh
# Fixture for DFS-015: appends the triggering fact's JSON (delivered on stdin)
# to $DFS015_LOG. The scenario commands always export DFS015_LOG pointing at
# $DOGFOOD_SCRATCH so this fixture never writes inside the repo checkout.
read -r fact
echo "notified: $fact" >> "${DFS015_LOG:-notifications.log}"
