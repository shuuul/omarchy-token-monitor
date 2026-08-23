QMLLINT := /usr/lib/qt6/bin/qmllint
QML_FILES := Panel.qml Service.qml

.PHONY: test test-js test-shell qml-check validate

test: test-js test-shell

test-js:
	node tests/test_providers.js
	node tests/test_model.js
	python3 tests/test_collect.py

test-shell:
	python3 tests/test_qml_names.py
	bash tests/test_panel_source.sh

qml-check:
	$(QMLLINT) -I /usr/share/omarchy/shell $(QML_FILES)

validate: test qml-check
	omarchy plugin validate .
