PREFIX   ?= /usr/local
DESTDIR  ?=
BINDIR    = $(PREFIX)/bin
LIBDIR    = $(PREFIX)/lib/pinlock
DATADIR   = $(PREFIX)/share
# systemd and polkit only look in these places, whatever the prefix.
UNITDIR  ?= $(if $(filter /usr,$(PREFIX)),/usr/lib/systemd/system,/etc/systemd/system)
POLKITDIR ?= /usr/share/polkit-1/actions

SUBST = sed -e 's|@LIBDIR@|$(LIBDIR)|g' -e 's|@BINDIR@|$(BINDIR)|g'

.PHONY: all install uninstall test

all:

install:
	install -d $(DESTDIR)$(LIBDIR)/pinlock
	install -m644 src/pinlock/*.py $(DESTDIR)$(LIBDIR)/pinlock/
	install -d $(DESTDIR)$(BINDIR)
	for b in pinlock pinlockd pinlock-setup; do \
		$(SUBST) bin/$$b > $(DESTDIR)$(BINDIR)/$$b && chmod 755 $(DESTDIR)$(BINDIR)/$$b; \
	done
	install -d $(DESTDIR)$(UNITDIR) $(DESTDIR)$(POLKITDIR)
	$(SUBST) data/pinlockd.service.in > $(DESTDIR)$(UNITDIR)/pinlockd.service
	$(SUBST) data/io.github.v6bv.pinlock.policy.in > $(DESTDIR)$(POLKITDIR)/io.github.v6bv.pinlock.policy
	install -Dm644 data/pinlock-setup.desktop $(DESTDIR)$(DATADIR)/applications/pinlock-setup.desktop
	install -Dm644 data/pinlock.svg $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/pinlock.svg

uninstall:
	rm -rf $(DESTDIR)$(LIBDIR)
	rm -f $(addprefix $(DESTDIR)$(BINDIR)/,pinlock pinlockd pinlock-setup)
	rm -f $(DESTDIR)$(UNITDIR)/pinlockd.service
	rm -f $(DESTDIR)$(POLKITDIR)/io.github.v6bv.pinlock.policy
	rm -f $(DESTDIR)$(DATADIR)/applications/pinlock-setup.desktop
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/pinlock.svg

test:
	python3 -m unittest discover -s tests -v
