#!/bin/sh
# Fixture for DFS-015's hung-observer case: reads the triggering fact off
# stdin like a well-behaved observer, then sleeps far longer than the
# config's timeout_seconds so the supervisor process is the one that has to
# kill it. Writes past the sleep only if the supervisor failed to enforce
# the timeout (it never should).
read -r fact
sleep 300
echo "should never reach here" >> "${DFS015_LOG:-hang.log}"
