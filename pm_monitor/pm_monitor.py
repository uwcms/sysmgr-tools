#!/usr/bin/env python3
import csv
import datetime
import email.mime.text
import json
import os
import pprint
import smtplib
import sys
import sysmgr
import time
import traceback

class LoadShareReading(object):
	PM_LOAD_SUM_THRESHOLD  = int(os.environ.get('PM_MON_LOAD_SUM_THRESHOLD','16'))
	PM_LOAD_SHARE_WARNING  = float(os.environ.get('PM_MON_LOAD_SHARE_WARNING_LEVEL','0.6'))
	PM_LOAD_SHARE_CRITICAL = float(os.environ.get('PM_MON_LOAD_SHARE_WARNING_LEVEL','0.7'))

	def __init__(self, pm1_amps, pm2_amps, timestamp):
		self.pm1_amps = pm1_amps
		self.pm2_amps = pm2_amps
		self.timestamp = timestamp
		self.total_amps = pm1_amps + pm2_amps
		self.pm1_percent = (pm1_amps / self.total_amps) if self.total_amps else None
		self.pm2_percent = (pm2_amps / self.total_amps) if self.total_amps else None

	def any_zero(self):
		return self.pm1_amps == 0 or self.pm2_amps == 0

	def get_level(self):
		if self.total_amps < self.PM_LOAD_SUM_THRESHOLD:
			return ('OK', 'Power total below monitoring threshold')

		if self.pm1_percent >= self.PM_LOAD_SHARE_CRITICAL:
			return ('CRITICAL', 'PM1 Load Share is {loadP:.0f}%  ({loadA:.2f} A)'.format(loadA=self.pm1_amps, loadP=self.pm1_percent*100))
		if self.pm2_percent >= self.PM_LOAD_SHARE_CRITICAL:
			return ('CRITICAL', 'PM2 Load Share is {loadP:.0f}%  ({loadA:.2f} A)'.format(loadA=self.pm2_amps, loadP=self.pm2_percent*100))

		if self.pm1_percent >= self.PM_LOAD_SHARE_WARNING:
			return ('WARNING', 'PM1 Load Share is {loadP:.0f}%  ({loadA:.2f} A)'.format(loadA=self.pm1_amps, loadP=self.pm1_percent*100))
		if self.pm2_percent >= self.PM_LOAD_SHARE_WARNING:
			return ('WARNING', 'PM2 Load Share is {loadP:.0f}%  ({loadA:.2f} A)'.format(loadA=self.pm2_amps, loadP=self.pm2_percent*100))

		return ('OK', 'Power modules in balance')

	def get_detail(self):
		return [
				'PM1 Load: {loadA:6.2f} A ({loadP:.0f}%)'.format(loadA=self.pm1_amps, loadP=(self.pm1_percent*100) if self.pm1_percent is not None else 0),
				'PM2 Load: {loadA:6.2f} A ({loadP:.0f}%)'.format(loadA=self.pm2_amps, loadP=(self.pm2_percent*100) if self.pm2_percent is not None else 0),
				]

class AlertManager(object):
	MAX_RECENT_READINGS      = int(os.environ.get('PM_MON_RECENT_READINGS', '12'))
	ALERT_LOCKOUT_WINDOW     = int(os.environ.get('PM_MON_ALERT_LOCKOUT_SECONDS', '3600'))
	ALERT_CONSECUTIVE_ERRORS = int(os.environ.get('PM_MON_CONSECUTIVE_ERRORS', '5'))

	ALERT_RANK = { 'OK': 0, 'WARNING': 1, 'CRITICAL': 2 }

	_last_alert       = datetime.datetime(1970,1,1,0,0,0)
	_last_alert_level = 'OK'

	def __init__(self, logcsv):
		self._logcsv_fd = logcsv
		self._logcsv = csv.writer(self._logcsv_fd)
		self._alert_history = []
		self._logcsv_fd.seek(0)
		self._recent_readings = {}
		for row in csv.reader(self._logcsv_fd):
			time = datetime.datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
			crate = int(row[1])
			reading = LoadShareReading(float(row[2]), float(row[3]), time)
			self._record_recent_reading(crate, reading)
		self._logcsv_fd.seek(0,2) # Seek to end, just in case.

	def _record_recent_reading(self, crate, reading):
		recent_readings = self._recent_readings.setdefault(crate,[])
		recent_readings.append(reading)
		if len(recent_readings) > self.MAX_RECENT_READINGS:
			recent_readings.pop(0)

	def process_reading(self, crate, reading):
		self._logcsv.writerow([reading.timestamp.strftime('%Y-%m-%d %H:%M:%S'), crate.number, reading.pm1_amps, reading.pm2_amps])
		self._logcsv_fd.flush()
		self._record_recent_reading(crate.number, reading)
		level, descriptor = reading.get_level()
		if level != 'OK':
			if os.environ.get('PM_MON_VERBOSE','0') != '0':
				print('C{crate.number}:'.format(crate=crate))
				print('\t{descriptor}'.format(descriptor=descriptor))
				print('\t--')
				print('\t'+'\n\t'.join(reading.get_detail()))
				print()
			if reading.any_zero() and not all(map(lambda x: x.any_zero(), self._recent_readings.get(crate.number, [])[:self.ALERT_CONSECUTIVE_ERRORS])):
				# We most likely have encountered a read error.  We will wait
				# until we have N straight read errors before alerting.  This
				# can be transient and will happen occasionally, at a rate of
				# about 1/day on on test crate so far.
				pass
			elif self.ALERT_RANK[level] > self.ALERT_RANK[self._last_alert_level] or (reading.timestamp - self._last_alert).seconds > self.ALERT_LOCKOUT_WINDOW:
				self._last_alert_level = level
				self._last_alert = datetime.datetime.now()
				self.email_report(crate, reading)

	def email_report(self, crate, reading):
		past_readings = reversed(list(map(lambda x: '{time}  {a:6.2f}  {b:6.2f}'.format(time=x.timestamp.strftime('%Y-%m-%d %H:%M:%S'), a=x.pm1_amps, b=x.pm2_amps), self._recent_readings.get(crate.number,[]))))
		mail = '''
Crate {crate.number} at {location}: {level[0]} alert: {level[1]}!

{details}

Recent readings:
{past}'''
		mail = mail.strip().format(location=os.uname().nodename, level=reading.get_level(), details='\n'.join(reading.get_detail()), reading=reading, crate=crate, past='\n'.join(past_readings))

		with (smtplib.SMTP_SSL if os.environ.get('PM_MON_SMTP_SSL','0') == '1' else smtplib.SMTP)(os.environ['PM_MON_SMTP_HOST']) as s:
			if os.environ.get('PM_MON_SMTP_USER', False) and os.environ('PM_MON_SMTP_PASSWORD', False):
				s.login(os.environ['PM_MON_SMTP_USER'], os.environ['PM_MON_SMTP_PASSWORD'])
			msg = email.mime.text.MIMEText(mail)
			msg['Subject'] = 'Crate {crate.number} at {host}: {level[0]} alert: {level[1]}'.format(host=os.uname().nodename, crate=crate, level=reading.get_level())
			msg['From'] = os.environ['PM_MON_SMTP_FROM']
			msg['To'] = os.environ['PM_MON_SMTP_TO']
			s.send_message(msg)


def get_current_total(s, crate, pm):
	sensors = filter(lambda sensor: ' iOut ' in sensor.name, s.list_sensors(crate, pm))
	total = 0
	for sensor in sensors:
		try:
			reading = s.sensor_read(crate, pm, sensor)
		except sysmgr.SysmgrError as e:
			if sensor.name == 'UTC010 iOut 2':
				pass # UTC010s don't have this sensor readable?  Ignore.
			else:
				raise
		total += reading.threshold
	return total

def run_monitor(alertmgr):
	s = sysmgr.Sysmgr()
	monitored_crates = os.environ.get('PM_MON_CRATES', 'ALL')
	if monitored_crates != 'ALL':
		monitored_crates = set(map(lambda x: int(x), monitored_crates.split(',')))
	while True:
		for crate in s.list_crates():
			if monitored_crates != 'ALL' and crate.number not in monitored_crates:
				continue
			if not crate.connected:
				continue
			try:
				s.list_cards(crate) # Rudamentary check that the crate is alive.
				pm1 = 0
				pm2 = 0
				try:
					pm1 = get_current_total(s, crate, 'PM1')
				except sysmgr.SysmgrError as e:
					pass # Ignore.  It will register as 0.
				try:
					pm2 = get_current_total(s, crate, 'PM2')
				except sysmgr.SysmgrError as e:
					pass # Ignore.  It will register as 0.

				alertmgr.process_reading(crate, LoadShareReading(pm1, pm2, datetime.datetime.now()))
			except Exception as e:
				print('{e} occured during scan of crate {crate.number}'.format(e=repr(e), crate=crate))
				print('\n'+''.join(traceback.format_exception(type(e), e, e.__traceback__))+'\n')
				s = sysmgr.Sysmgr() # Reconnect possibly required.
		time.sleep(30)

if __name__ == '__main__':
	log_filename = os.environ.get('PM_MON_LOGFILE', ('/var/log/pm_monitor.csv' if os.geteuid() == 0 else 'pm_monitor.csv'))
	try:
		logfile = open(log_filename,'a+')
	except Exception as e:
		print('Unable to open logfile: {}'.format(e))
		logfile = open('/dev/null','a+')

	if os.environ.get('PM_MON_DAEMON', '1') == '1':
		try:
			pid = os.fork()
			if pid > 0:
				# exit first parent
				sys.exit(0)
		except OSError as e:
			sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)

		# decouple from parent environment
		os.chdir("/")
		os.setsid()
		#os.umask(0)

		# do second fork
		try:
			pid = os.fork()
			if pid > 0:
				# exit from second parent
				sys.exit(0)
		except OSError as e:
			sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
			sys.exit(1)

	run_monitor(AlertManager(logfile))
