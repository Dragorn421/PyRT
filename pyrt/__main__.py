# Run PyRT with `python3 -m pyrt` in the directory where the pyrt directory is

# Calling pyrt's main function from outside the pyrt module
# allows cyclic imports to play nice instead of loading pyrt
# several times.
# If main() was called inside pyrt, the pyrt module wouldn't
# be fully loaded until main() returns, and pyrt module imports
# (for example in pyrt_modules.object_table) would initialize
# the module again. This leads to breaking events since event
# objects (of the PyRTEvent class) are assumed to be singleton
# for proper usage in dictionaries.
# Events could also just "key" by event id but it sounds better
# to only initialize the module once anyway.

import pyrt

pyrt.main()
