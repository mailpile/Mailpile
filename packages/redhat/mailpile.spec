Summary:            Mail client with a web-mail interface, fast integrated search engine, and encryption.
Name:               mailpile
Version:            0.4.1
Release:            1%{?dist}
License:            AGPLv3/Apache 2.0
Group:              Applications/Mail
Source:             %{name}-%{version}.tar.gz
URL:                https://www.mailpile.is
BuildRequires:      gettext
BuildRequires:      libtool

%description
A modern, fast email client with user-friendly encryption and privacy features.

%prep
%autosetup -n %{name}

%build
%configure
make %{?_smp_mflags}

%install
%make_install

install -m 755 -d %{buildroot}/%{_sbindir}
ln -s ../usr/bin/mailpile %{buildroot}/%{_sbindir}

%find_lang %{name}

%files -f %{name}.lang
%doc README TODO COPYING ChangeLog
%{_bindir}/*
%{_sbindir}/*
%{_mandir}/man1/*

%changelog
* Fri Oct 17 2014 Smári McCarthy <smari@mailpile.is> - 0.4.1-1
- First RPM build