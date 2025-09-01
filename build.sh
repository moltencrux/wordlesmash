#!/bin/sh
# compiles the UI and resource files form their definitions
pyside6-rcc -o wordlesmash/ui/wordlesmash_rc.py wordlesmash/ui/wordlesmash.qrc
pyuic6 -o wordlesmash/ui/WordLeSmash_ui.py wordlesmash/ui/WordLeSmash.ui
pyuic6 -o wordlesmash/ui/preferences_ui.py wordlesmash/ui/preferences.ui
pyuic6 -o wordlesmash/ui/NewProfile_ui.py wordlesmash/ui/NewProfile.ui
pyuic6 -o wordlesmash/ui/BatchAdd_ui.py wordlesmash/ui/BatchAdd.ui
pyuic6 -o wordlesmash/ui/ProgressDialog_ui.py wordlesmash/ui/ProgressDialog.ui
