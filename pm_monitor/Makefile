rpm: pm_monitor.py init.d_pm_monitor.sh pm_monitor.sysconfig pm_monitor.spec
	PM_MON_ROOT=$(PWD) rpmbuild --sign -ba --quiet --define "_topdir $(PWD)/rpm" pm_monitor.spec
	cp -v $(PWD)/rpm/RPMS/*/*.rpm ./
	rm -rf $(PWD)/rpm/

distclean: clean
	rm -rf tags *.rpm
clean:
	rm -rf rpm/

.PHONY: distclean clean rpm

#-include $(wildcard .dep/*)
