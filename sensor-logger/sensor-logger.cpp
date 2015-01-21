#include <limits.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <confuse.h>
#include <sysmgr.h>

#define CSV_COMMA ","

static inline std::string stdsprintf(const char *fmt, ...) {
	va_list va;
	va_list va2;
	va_start(va, fmt);
	va_copy(va2, va);
	size_t s = vsnprintf(NULL, 0, fmt, va);
	char str[s];
	vsnprintf(str, s+1, fmt, va2);
	va_end(va);
	va_end(va2);
	return std::string(str);
}

static int cfg_validate_hostname(cfg_t *cfg, cfg_opt_t *opt)
{
	const char *host = cfg_opt_getnstr(opt, cfg_opt_size(opt) - 1);

	if (strspn(host, "qwertyuiopasdfghjklzxcvbnm.-_1234567890QWERTYUIOPASDFGHJKLZXCVBNM") != strlen(host)) {
		cfg_error(cfg, "Invalid %s: %s", opt->name, host);
		return -1;
	}
	return 0;
}

static int cfg_validate_port(cfg_t *cfg, cfg_opt_t *opt)
{
	unsigned int port = cfg_opt_getnint(opt, cfg_opt_size(opt) - 1);

	if (port > USHRT_MAX) {
		cfg_error(cfg, "Invalid %s: %s", opt->name, port);
		return -1;
	}
	return 0;
}

class Sensor {
	public: 
		uint8_t crate;
		uint8_t fru;
		std::string sensor;
		std::string name;

		Sensor(uint8_t crate, uint8_t fru, std::string sensor, std::string name)
			: crate(crate), fru(fru), sensor(sensor), name(name) { };
};

int main(int argc, char *argv[]) {
	try {
		cfg_opt_t opts_sensor[] =
		{
			CFG_INT(const_cast<char *>("crate"), 0xff, CFGF_NONE),
			CFG_INT(const_cast<char *>("fru"), 0xff, CFGF_NONE),
			CFG_STR(const_cast<char *>("card"), const_cast<char *>(""), CFGF_NONE),
			CFG_STR(const_cast<char *>("sensor"), const_cast<char *>(""), CFGF_NONE),
			CFG_END()
		};
		cfg_opt_t opts[] =
		{
			CFG_SEC(const_cast<char *>("sensor"), opts_sensor, CFGF_MULTI),
			CFG_STR(const_cast<char *>("outfile"), const_cast<char *>("data.csv"), CFGF_NONE),
			CFG_STR(const_cast<char *>("host"), const_cast<char *>("localhost"), CFGF_NONE),
			CFG_STR(const_cast<char *>("password"), const_cast<char *>(""), CFGF_NONE),
			CFG_INT(const_cast<char *>("port"), 4681, CFGF_NONE),
			CFG_INT(const_cast<char *>("interval"), 5, CFGF_NONE),
			CFG_END()
		};
		cfg_t *cfg = cfg_init(opts, CFGF_NONE);
		cfg_set_validate_func(cfg, "host", &cfg_validate_hostname);
		cfg_set_validate_func(cfg, "port", &cfg_validate_port);

		if (argc < 2) {
			printf("%s sensor-spec.conf\n", argv[0]);
			exit(1);
		}
		if (cfg_parse(cfg, argv[1]) == CFG_PARSE_ERROR)
			exit(1);

		const char *host = cfg_getstr(cfg, "host");
		const char *pass = cfg_getstr(cfg, "password");
		const char *outfile = cfg_getstr(cfg, "outfile");
		uint16_t port = cfg_getint(cfg, "port");
		uint32_t interval = cfg_getint(cfg, "interval");

		sysmgr::sysmgr sm(host, pass, port);
		try {
			sm.connect();
		}
		catch (sysmgr::sysmgr_exception &e) {
			printf("Unable to connect to system manager: %s\n", e.message.c_str());
			exit(2);
		}

		std::vector<Sensor> sensors;

		std::vector<sysmgr::crate_info> sm_crates = sm.list_crates();
		for (std::vector<sysmgr::crate_info>::iterator it = sm_crates.begin(); it != sm_crates.end(); it++) {
			if (!it->connected)
				printf("Warning: Crate %hhu is not connected at this time.  Discarding all data related to it.\n", it->crateno);
		}

		for(unsigned int i = 0; i < cfg_size(cfg, "sensor"); i++) {
			cfg_t *cfgsensor = cfg_getnsec(cfg, "sensor", i);

			uint8_t crate = cfg_getint(cfgsensor, "crate");
			uint8_t fru = cfg_getint(cfgsensor, "fru");
			const char *card = cfg_getstr(cfgsensor, "card");
			const char *sensor = cfg_getstr(cfgsensor, "sensor");

			bool found = false;

			for (std::vector<sysmgr::crate_info>::iterator c_it = sm_crates.begin(); c_it != sm_crates.end(); c_it++) {
				if (!c_it->connected)
					continue;

				if (crate != 0xff && c_it->crateno != crate)
					continue;

				std::vector<sysmgr::card_info> sm_frus = sm.list_cards(c_it->crateno);
				for (std::vector<sysmgr::card_info>::iterator f_it = sm_frus.begin(); f_it != sm_frus.end(); f_it++) {
					if (fru != 0xff && f_it->fru != fru)
						continue;

					if (card[0] != '\0' && f_it->name != card)
						continue;

					std::vector<sysmgr::sensor_info> sm_sensors = sm.list_sensors(c_it->crateno, f_it->fru);
					for (std::vector<sysmgr::sensor_info>::iterator s_it = sm_sensors.begin(); s_it != sm_sensors.end(); s_it++) {
						if (s_it->type == 'E' || s_it->type == 'O')
							continue; // We don't know how to read these.

						if (sensor[0] != '\0' && s_it->name != sensor)
							continue;

						sensors.push_back(Sensor(c_it->crateno, f_it->fru, s_it->name, stdsprintf("C%hhu %s (%s) %s", c_it->crateno, sysmgr::sysmgr::get_slotstring(f_it->fru).c_str(), f_it->name.c_str(), s_it->name.c_str())));
						found = true;
					}
				}
			}

			if (!found)
				printf("Warning: Unable to find a match for %hhu %hhu \"%s\" \"%s\"\n", crate, fru, card, sensor);
		}

		FILE *fd = fopen(outfile, "w");
		if (!fd) {
			printf("Unable to open %s for writing\n", outfile);
			exit(1);
		}
		cfg_free(cfg);

		printf("Sensors indexed.  Now polling %d sensors.\n", (int)sensors.size());

		fprintf(fd, "Time");
		for (std::vector<Sensor>::iterator it = sensors.begin(); it != sensors.end(); it++) {
			fprintf(fd, CSV_COMMA "\"%s\"", it->name.c_str());
		}
		fprintf(fd, "\n");
		fflush(fd);

		time_t now;
		char timestamp[32];

		while (1) {
			time(&now);
			strftime(timestamp, 32, "%Y-%m-%d %H:%M:%S", localtime(&now));
			fprintf(fd, "%s", timestamp);
			for (std::vector<Sensor>::iterator it = sensors.begin(); it != sensors.end(); it++) {
				fprintf(fd, CSV_COMMA);

				try {
					sysmgr::sensor_reading reading = sm.sensor_read(it->crate, it->fru, it->sensor);
					if (reading.threshold_set)
						fprintf(fd, "%f", reading.threshold);
					else
						fprintf(fd, "0x%04hx", reading.eventmask);
				}
				catch (sysmgr::sysmgr_exception &e) {
					//printf("Error reading sensor \"%s\": %s\n",  it->name.c_str(), e.message.c_str());
				}
				//usleep(100000);
			}
			fprintf(fd, "\n");
			fflush(fd);
			sleep(interval);

			if (!sm.connected())
				break;
		}
	}
	catch (sysmgr::sysmgr_exception &e) {
		printf("Caught fatal exception: %s\n", e.message.c_str());
		printf("Goodbye.\n");
	}
}
