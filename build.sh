#!/bin/sh
# compiles the UI and resource files form their definitions
pyside6-rcc -o ui/wordlesmash_rc.py ui/wordlesmash.qrc
pyuic6 -o ui/WordLeSmash_ui.py ui/WordLeSmash.ui
pyuic6 -o ui/preferences_ui.py ui/preferences.ui
pyuic6 -o ui/NewProfile_ui.py ui/NewProfile.ui
pyuic6 -o ui/BatchAdd_ui.py ui/BatchAdd.ui
pyuic6 -o ui/ProgressDialog_ui.py ui/ProgressDialog.ui
