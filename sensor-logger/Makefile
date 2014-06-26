DEPOPTS = -MMD -MF .$@.dep -MP
CCOPTS = $(DEPOPTS) -ggdb -Wall

all: sensor-logger tags

sensor-logger: sensor-logger.cpp
	g++ $(CCOPTS) $(IPMILIBS) -o $@ sensor-logger.cpp -lconfuse -lsysmgr

tags: *.cpp
	ctags -R . 2>/dev/null || true

distclean: clean
	rm -f .*.dep tags
clean:
	rm -f sensor-logger

.PHONY: distclean clean all

-include $(wildcard .*.dep)
