PREFIX ?= /usr/local

install:
	install -Dm755 bin/czix $(PREFIX)/bin/czix
	mkdir -p $(PREFIX)/share/czix
	cp -r src $(PREFIX)/share/czix/src
install-flatpak-data:
	install -Dm644 data/org.czix.Czix.desktop $(PREFIX)/share/applications/org.czix.Czix.desktop
uninstall:
	rm -f $(PREFIX)/bin/czix $(PREFIX)/share/applications/org.czix.Czix.desktop
	rm -rf $(PREFIX)/share/czix

.PHONY: install install-flatpak-data uninstall
