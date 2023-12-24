# imports - standard imports
import getpass
import os

# imports - third partyimports
import click

# imports - module imports
import ocean
from ocean.app import use_rq
from ocean.ocean import Ocean
from ocean.config.common_site_config import (
	get_gunicorn_workers,
	update_config,
	get_default_max_requests,
	compute_max_requests_jitter,
)
from ocean.utils import exec_cmd, which, get_ocean_name


def generate_systemd_config(
	ocean_path,
	user=None,
	yes=False,
	stop=False,
	create_symlinks=False,
	delete_symlinks=False,
):

	if not user:
		user = getpass.getuser()

	config = Ocean(ocean_path).conf

	ocean_dir = os.path.abspath(ocean_path)
	ocean_name = get_ocean_name(ocean_path)

	if stop:
		exec_cmd(
			f"sudo systemctl stop -- $(systemctl show -p Requires {ocean_name}.target | cut -d= -f2)"
		)
		return

	if create_symlinks:
		_create_symlinks(ocean_path)
		return

	if delete_symlinks:
		_delete_symlinks(ocean_path)
		return

	number_of_workers = config.get("background_workers") or 1
	background_workers = []
	for i in range(number_of_workers):
		background_workers.append(
			get_ocean_name(ocean_path) + "-frappe-default-worker@" + str(i + 1) + ".service"
		)

	for i in range(number_of_workers):
		background_workers.append(
			get_ocean_name(ocean_path) + "-frappe-short-worker@" + str(i + 1) + ".service"
		)

	for i in range(number_of_workers):
		background_workers.append(
			get_ocean_name(ocean_path) + "-frappe-long-worker@" + str(i + 1) + ".service"
		)

	web_worker_count = config.get(
		"gunicorn_workers", get_gunicorn_workers()["gunicorn_workers"]
	)
	max_requests = config.get(
		"gunicorn_max_requests", get_default_max_requests(web_worker_count)
	)

	ocean_info = {
		"ocean_dir": ocean_dir,
		"sites_dir": os.path.join(ocean_dir, "sites"),
		"user": user,
		"use_rq": use_rq(ocean_path),
		"http_timeout": config.get("http_timeout", 120),
		"redis_server": which("redis-server"),
		"node": which("node") or which("nodejs"),
		"redis_cache_config": os.path.join(ocean_dir, "config", "redis_cache.conf"),
		"redis_queue_config": os.path.join(ocean_dir, "config", "redis_queue.conf"),
		"webserver_port": config.get("webserver_port", 8000),
		"gunicorn_workers": web_worker_count,
		"gunicorn_max_requests": max_requests,
		"gunicorn_max_requests_jitter": compute_max_requests_jitter(max_requests),
		"ocean_name": get_ocean_name(ocean_path),
		"worker_target_wants": " ".join(background_workers),
		"ocean_cmd": which("ocean"),
	}

	if not yes:
		click.confirm(
			"current systemd configuration will be overwritten. Do you want to continue?",
			abort=True,
		)

	setup_systemd_directory(ocean_path)
	setup_main_config(ocean_info, ocean_path)
	setup_workers_config(ocean_info, ocean_path)
	setup_web_config(ocean_info, ocean_path)
	setup_redis_config(ocean_info, ocean_path)

	update_config({"restart_systemd_on_update": False}, ocean_path=ocean_path)
	update_config({"restart_supervisor_on_update": False}, ocean_path=ocean_path)


def setup_systemd_directory(ocean_path):
	if not os.path.exists(os.path.join(ocean_path, "config", "systemd")):
		os.makedirs(os.path.join(ocean_path, "config", "systemd"))


def setup_main_config(ocean_info, ocean_path):
	# Main config
	ocean_template = ocean.config.env().get_template("systemd/frappe-ocean.target")
	ocean_config = ocean_template.render(**ocean_info)
	ocean_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + ".target"
	)

	with open(ocean_config_path, "w") as f:
		f.write(ocean_config)


def setup_workers_config(ocean_info, ocean_path):
	# Worker Group
	ocean_workers_target_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-workers.target"
	)
	ocean_default_worker_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-frappe-default-worker.service"
	)
	ocean_short_worker_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-frappe-short-worker.service"
	)
	ocean_long_worker_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-frappe-long-worker.service"
	)
	ocean_schedule_worker_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-frappe-schedule.service"
	)

	ocean_workers_target_config = ocean_workers_target_template.render(**ocean_info)
	ocean_default_worker_config = ocean_default_worker_template.render(**ocean_info)
	ocean_short_worker_config = ocean_short_worker_template.render(**ocean_info)
	ocean_long_worker_config = ocean_long_worker_template.render(**ocean_info)
	ocean_schedule_worker_config = ocean_schedule_worker_template.render(**ocean_info)

	ocean_workers_target_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + "-workers.target"
	)
	ocean_default_worker_config_path = os.path.join(
		ocean_path,
		"config",
		"systemd",
		ocean_info.get("ocean_name") + "-frappe-default-worker@.service",
	)
	ocean_short_worker_config_path = os.path.join(
		ocean_path,
		"config",
		"systemd",
		ocean_info.get("ocean_name") + "-frappe-short-worker@.service",
	)
	ocean_long_worker_config_path = os.path.join(
		ocean_path,
		"config",
		"systemd",
		ocean_info.get("ocean_name") + "-frappe-long-worker@.service",
	)
	ocean_schedule_worker_config_path = os.path.join(
		ocean_path,
		"config",
		"systemd",
		ocean_info.get("ocean_name") + "-frappe-schedule.service",
	)

	with open(ocean_workers_target_config_path, "w") as f:
		f.write(ocean_workers_target_config)

	with open(ocean_default_worker_config_path, "w") as f:
		f.write(ocean_default_worker_config)

	with open(ocean_short_worker_config_path, "w") as f:
		f.write(ocean_short_worker_config)

	with open(ocean_long_worker_config_path, "w") as f:
		f.write(ocean_long_worker_config)

	with open(ocean_schedule_worker_config_path, "w") as f:
		f.write(ocean_schedule_worker_config)


def setup_web_config(ocean_info, ocean_path):
	# Web Group
	ocean_web_target_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-web.target"
	)
	ocean_web_service_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-frappe-web.service"
	)
	ocean_node_socketio_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-node-socketio.service"
	)

	ocean_web_target_config = ocean_web_target_template.render(**ocean_info)
	ocean_web_service_config = ocean_web_service_template.render(**ocean_info)
	ocean_node_socketio_config = ocean_node_socketio_template.render(**ocean_info)

	ocean_web_target_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + "-web.target"
	)
	ocean_web_service_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + "-frappe-web.service"
	)
	ocean_node_socketio_config_path = os.path.join(
		ocean_path,
		"config",
		"systemd",
		ocean_info.get("ocean_name") + "-node-socketio.service",
	)

	with open(ocean_web_target_config_path, "w") as f:
		f.write(ocean_web_target_config)

	with open(ocean_web_service_config_path, "w") as f:
		f.write(ocean_web_service_config)

	with open(ocean_node_socketio_config_path, "w") as f:
		f.write(ocean_node_socketio_config)


def setup_redis_config(ocean_info, ocean_path):
	# Redis Group
	ocean_redis_target_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-redis.target"
	)
	ocean_redis_cache_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-redis-cache.service"
	)
	ocean_redis_queue_template = ocean.config.env().get_template(
		"systemd/frappe-ocean-redis-queue.service"
	)

	ocean_redis_target_config = ocean_redis_target_template.render(**ocean_info)
	ocean_redis_cache_config = ocean_redis_cache_template.render(**ocean_info)
	ocean_redis_queue_config = ocean_redis_queue_template.render(**ocean_info)

	ocean_redis_target_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + "-redis.target"
	)
	ocean_redis_cache_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + "-redis-cache.service"
	)
	ocean_redis_queue_config_path = os.path.join(
		ocean_path, "config", "systemd", ocean_info.get("ocean_name") + "-redis-queue.service"
	)

	with open(ocean_redis_target_config_path, "w") as f:
		f.write(ocean_redis_target_config)

	with open(ocean_redis_cache_config_path, "w") as f:
		f.write(ocean_redis_cache_config)

	with open(ocean_redis_queue_config_path, "w") as f:
		f.write(ocean_redis_queue_config)


def _create_symlinks(ocean_path):
	ocean_dir = os.path.abspath(ocean_path)
	etc_systemd_system = os.path.join("/", "etc", "systemd", "system")
	config_path = os.path.join(ocean_dir, "config", "systemd")
	unit_files = get_unit_files(ocean_dir)
	for unit_file in unit_files:
		filename = "".join(unit_file)
		exec_cmd(
			f'sudo ln -s {config_path}/{filename} {etc_systemd_system}/{"".join(unit_file)}'
		)
	exec_cmd("sudo systemctl daemon-reload")


def _delete_symlinks(ocean_path):
	ocean_dir = os.path.abspath(ocean_path)
	etc_systemd_system = os.path.join("/", "etc", "systemd", "system")
	unit_files = get_unit_files(ocean_dir)
	for unit_file in unit_files:
		exec_cmd(f'sudo rm {etc_systemd_system}/{"".join(unit_file)}')
	exec_cmd("sudo systemctl daemon-reload")


def get_unit_files(ocean_path):
	ocean_name = get_ocean_name(ocean_path)
	unit_files = [
		[ocean_name, ".target"],
		[ocean_name + "-workers", ".target"],
		[ocean_name + "-web", ".target"],
		[ocean_name + "-redis", ".target"],
		[ocean_name + "-frappe-default-worker@", ".service"],
		[ocean_name + "-frappe-short-worker@", ".service"],
		[ocean_name + "-frappe-long-worker@", ".service"],
		[ocean_name + "-frappe-schedule", ".service"],
		[ocean_name + "-frappe-web", ".service"],
		[ocean_name + "-node-socketio", ".service"],
		[ocean_name + "-redis-cache", ".service"],
		[ocean_name + "-redis-queue", ".service"],
	]
	return unit_files
