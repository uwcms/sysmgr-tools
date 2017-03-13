%define commit %(git describe --match 'pm_monitor_*' | sed -e 's/pm_monitor_//')

Summary: University of Wisconsin Power Module Monitor
Name: pm_monitor
Version: %(git describe --match 'pm_monitor_*' | sed -e 's/pm_monitor_v//;s/-/./g')
Release: 1%{?dist}
#Release: 1%{?dist}.%(git rev-parse --abbrev-ref HEAD | sed s/-/_/g)
#BuildArch: %{_buildarch}
License: Reserved
Group: Applications/XDAQ
#Source: http://github.com/uwcms/sysmgr-tools/archive/%{commit}/sysmgr-tools-%{commit}.tar.gz
URL: https://github.com/uwcms/sysmgr-tools
BuildRoot: %{PWD}/rpm/buildroot
Requires: procps
#Prefix: /usr

%description
The University of Wisconsin Power Module Monitor tracks power module current
balance through the University of Wisconsin System Manager.

#
# Devel RPM specified attributes (extension to binary rpm with include files)
#
#%package -n pm_monitor-devel
#Summary: University of Wisconsin IPMI Multitool
#Group:    Applications/XDAQ
#
#%description -n %{_project}-%{_packagename}-devel
#The University of Wisconsin Power Module Monitor tracks power module current
#balance through the University of Wisconsin System Manager.
#Manager.

#%prep

#%setup 

#%build

#
# Prepare the list of files that are the input to the binary and devel RPMs
#
%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/etc/init.d
mkdir -p %{buildroot}/etc/sysconfig
#mkdir -p %{buildroot}/usr/share/doc/%{name}-%{version}/

install -m 755 $PM_MON_ROOT/pm_monitor.py %{buildroot}/usr/bin/pm_monitor
install -m 755 $PM_MON_ROOT/init.d_pm_monitor.sh %{buildroot}/etc/init.d/pm_monitor
install -m 755 $PM_MON_ROOT/pm_monitor.sysconfig %{buildroot}/etc/sysconfig/pm_monitor
#install -m 655 %{_packagedir}/MAINTAINER %{_packagedir}/rpm/RPMBUILD/BUILD/MAINTAINER

%clean
rm -rf %{buildroot}

#
# Files that go in the binary RPM
#
%files
%defattr(-,root,root,-)
#%doc /usr/share/doc/%{name}-%{version}/
/usr/bin/pm_monitor
/etc/init.d/pm_monitor
%config(noreplace) /etc/sysconfig/pm_monitor

#
# Files that go in the devel RPM
#
#%files -n pm_monitor-devel
#%defattr(-,root,root,-)

#%changelog

%debug_package
