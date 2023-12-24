# imports - standard imports
import subprocess
from functools import lru_cache
import os
import shutil
import json
import sys
import logging
from typing import List, MutableSequence, TYPE_CHECKING, Union

# imports - module imports
import ocean
from ocean.exceptions import AppNotInstalledError, InvalidRemoteException
from ocean.config.common_site_config import setup_config
from ocean.utils import (
	UNSET_ARG,
	paths_in_ocean,
	exec_cmd,
	is_ocean_directory,
	is_frappe_app,
	get_cmd_output,
	get_git_version,
	log,
	run_frappe_cmd,
)
from ocean.utils.ocean import (
	validate_app_installed_on_sites,
	restart_supervisor_processes,
	restart_systemd_processes,
	restart_process_manager,
	remove_backups_crontab,
	get_venv_path,
	get_env_cmd,
)
from ocean.utils.render import job, step
from ocean.utils.app import get_current_version
from ocean.app import is_git_repo


if TYPE_CHECKING:
	from ocean.app import App

logger = logging.getLogger(ocean.PROJECT_NAME)


class Base:
	def run(self, cmd, cwd=None, _raise=True):
		return exec_cmd(cmd, cwd=cwd or self.cwd, _raise=_raise)


class Validator:
	def validate_app_uninstall(self, app):
		if app not in self.apps:
			raise AppNotInstalledError(f"No app named {app}")
		validate_app_installed_on_sites(app, ocean_path=self.name)


@lru_cache(maxsize=None)
class ocean(Base, Validator):
	def __init__(self, path):
		self.name = path
		self.cwd = os.path.abspath(path)
		self.exists = is_ocean_directory(self.name)

		self.setup = oceanSetup(self)
		self.teardown = oceanTearDown(self)
		self.apps = oceanApps(self)

		self.apps_txt = os.path.join(self.name, "sites", "apps.txt")
		self.excluded_apps_txt = os.path.join(self.name, "sites", "excluded_apps.txt")

	@property
	def python(self) -> str:
		return get_env_cmd("python", ocean_path=self.name)

	@property
	def shallow_clone(self) -> bool:
		config = self.conf

		if config:
			if config.get("release_ocean") or not config.get("shallow_clone"):
				return False

		return get_git_version() > 1.9

	@property
	def excluded_apps(self) -> List:
		try:
			with open(self.excluded_apps_txt) as f:
				return f.read().strip().split("\n")
		except Exception:
			return []

	@property
	def sites(self) -> List:
		return [
			path
			for path in os.listdir(os.path.join(self.name, "sites"))
			if os.path.exists(os.path.join("sites", path, "site_config.json"))
		]

	@property
	def conf(self):
		from ocean.config.common_site_config import get_config

		return get_config(self.name)

	def init(self):
		self.setup.dirs()
		self.setup.env()
		self.setup.backups()

	def drop(self):
		self.teardown.backups()
		self.teardown.dirs()

	def install(self, app, branch=None):
		from ocean.app import App

		app = App(app, branch=branch)
		self.apps.append(app)
		self.apps.sync()

	def uninstall(self, app, no_backup=False, force=False):
		from ocean.app import App

		if not force:
			self.validate_app_uninstall(app)
		try:
			self.apps.remove(App(app, ocean=self, to_clone=False), no_backup=no_backup)
		except InvalidRemoteException:
			if not force:
				raise

		self.apps.sync()
		# self.build() - removed because it seems unnecessary
		self.reload(_raise=False)

	@step(title="Building ocean Assets", success="ocean Assets Built")
	def build(self):
		# build assets & stuff
		run_frappe_cmd("build", ocean_path=self.name)

	@step(title="Reloading ocean Processes", success="ocean Processes Reloaded")
	def reload(self, web=False, supervisor=True, systemd=True, _raise=True):
		"""If web is True, only web workers are restarted"""
		conf = self.conf

		if conf.get("developer_mode"):
			restart_process_manager(ocean_path=self.name, web_workers=web)
		if supervisor or conf.get("restart_supervisor_on_update"):
			restart_supervisor_processes(ocean_path=self.name, web_workers=web, _raise=_raise)
		if systemd and conf.get("restart_systemd_on_update"):
			restart_systemd_processes(ocean_path=self.name, web_workers=web, _raise=_raise)

	def get_installed_apps(self) -> List:
		"""Returns list of installed apps on ocean, not in excluded_apps.txt"""
		try:
			installed_packages = get_cmd_output(f"{self.python} -m pip freeze", cwd=self.name)
		except Exception:
			installed_packages = []

		return [
			app
			for app in self.apps
			if app not in self.excluded_apps and app in installed_packages
		]


class oceanApps(MutableSequence):
	def __init__(self, ocean: ocean):
		self.ocean = ocean
		self.states_path = os.path.join(self.ocean.name, "sites", "apps.json")
		self.apps_path = os.path.join(self.ocean.name, "apps")
		self.initialize_apps()
		self.set_states()

	def set_states(self):
		try:
			with open(self.states_path) as f:
				self.states = json.loads(f.read() or "{}")
		except FileNotFoundError:
			self.states = {}

	def update_apps_states(
		self,
		app_dir: str = None,
		app_name: Union[str, None] = None,
		branch: Union[str, None] = None,
		required: List = UNSET_ARG,
	):
		if required == UNSET_ARG:
			required = []
		if self.apps and not os.path.exists(self.states_path):
			# idx according to apps listed in apps.txt (backwards compatibility)
			# Keeping frappe as the first app.
			if "frappe" in self.apps:
				self.apps.remove("frappe")
				self.apps.insert(0, "frappe")
				with open(self.ocean.apps_txt, "w") as f:
					f.write("\n".join(self.apps))

			print("Found existing apps updating states...")
			for idx, app in enumerate(self.apps, start=1):
				self.states[app] = {
					"resolution": {"commit_hash": None, "branch": None},
					"required": required,
					"idx": idx,
					"version": get_current_version(app, self.ocean.name),
				}

		apps_to_remove = []
		for app in self.states:
			if app not in self.apps:
				apps_to_remove.append(app)

		for app in apps_to_remove:
			del self.states[app]

		if app_name and not app_dir:
			app_dir = app_name

		if app_name and app_name not in self.states:
			version = get_current_version(app_name, self.ocean.name)

			app_dir = os.path.join(self.apps_path, app_dir)
			is_repo = is_git_repo(app_dir)
			if is_repo:
				if not branch:
					branch = (
						subprocess.check_output(
							"git rev-parse --abbrev-ref HEAD", shell=True, cwd=app_dir
						)
						.decode("utf-8")
						.rstrip()
					)

				commit_hash = (
					subprocess.check_output(f"git rev-parse {branch}", shell=True, cwd=app_dir)
					.decode("utf-8")
					.rstrip()
				)

			self.states[app_name] = {
				"is_repo": is_repo,
				"resolution": "not a repo"
				if not is_repo
				else {"commit_hash": commit_hash, "branch": branch},
				"required": required,
				"idx": len(self.states) + 1,
				"version": version,
			}

		with open(self.states_path, "w") as f:
			f.write(json.dumps(self.states, indent=4))

	def sync(
		self,
		app_name: Union[str, None] = None,
		app_dir: Union[str, None] = None,
		branch: Union[str, None] = None,
		required: List = UNSET_ARG,
	):
		if required == UNSET_ARG:
			required = []
		self.initialize_apps()

		with open(self.ocean.apps_txt, "w") as f:
			f.write("\n".join(self.apps))

		self.update_apps_states(
			app_name=app_name, app_dir=app_dir, branch=branch, required=required
		)

	def initialize_apps(self):
		try:
			self.apps = [
				x
				for x in os.listdir(os.path.join(self.ocean.name, "apps"))
				if is_frappe_app(os.path.join(self.ocean.name, "apps", x))
			]
			self.apps.remove("frappe")
			self.apps.insert(0, "frappe")
		except FileNotFoundError:
			self.apps = []

	def __getitem__(self, key):
		"""retrieves an item by its index, key"""
		return self.apps[key]

	def __setitem__(self, key, value):
		"""set the item at index, key, to value"""
		# should probably not be allowed
		# self.apps[key] = value
		raise NotImplementedError

	def __delitem__(self, key):
		"""removes the item at index, key"""
		# TODO: uninstall and delete app from ocean
		del self.apps[key]

	def __len__(self):
		return len(self.apps)

	def insert(self, key, value):
		"""add an item, value, at index, key."""
		# TODO: fetch and install app to ocean
		self.apps.insert(key, value)

	def add(self, app: "App"):
		app.get()
		app.install()
		super().append(app.app_name)
		self.apps.sort()

	def remove(self, app: "App", no_backup: bool = False):
		app.uninstall()
		app.remove(no_backup=no_backup)
		super().remove(app.app_name)

	def append(self, app: "App"):
		return self.add(app)

	def __repr__(self):
		return self.__str__()

	def __str__(self):
		return str([x for x in self.apps])


class oceanSetup(Base):
	def __init__(self, ocean: ocean):
		self.ocean = ocean
		self.cwd = self.ocean.cwd

	@step(title="Setting Up Directories", success="Directories Set Up")
	def dirs(self):
		os.makedirs(self.ocean.name, exist_ok=True)

		for dirname in paths_in_ocean:
			os.makedirs(os.path.join(self.ocean.name, dirname), exist_ok=True)

	@step(title="Setting Up Environment", success="Environment Set Up")
	def env(self, python="python3"):
		"""Setup env folder
		- create env if not exists
		- upgrade env pip
		- install frappe python dependencies
		"""
		import ocean.cli
		import click

		verbose = ocean.cli.verbose

		click.secho("Setting Up Environment", fg="yellow")

		frappe = os.path.join(self.ocean.name, "apps", "frappe")
		quiet_flag = "" if verbose else "--quiet"

		if not os.path.exists(self.ocean.python):
			venv = get_venv_path(verbose=verbose, python=python)
			self.run(f"{venv} env", cwd=self.ocean.name)

		self.pip()
		self.wheel()

		if os.path.exists(frappe):
			self.run(
				f"{self.ocean.python} -m pip install {quiet_flag} --upgrade -e {frappe}",
				cwd=self.ocean.name,
			)

	@step(title="Setting Up ocean Config", success="ocean Config Set Up")
	def config(self, redis=True, procfile=True, additional_config=None):
		"""Setup config folder
		- create pids folder
		- generate sites/common_site_config.json
		"""
		setup_config(self.ocean.name, additional_config=additional_config)

		if redis:
			from ocean.config.redis import generate_config

			generate_config(self.ocean.name)

		if procfile:
			from ocean.config.procfile import setup_procfile

			setup_procfile(self.ocean.name, skip_redis=not redis)

	@step(title="Updating pip", success="Updated pip")
	def pip(self, verbose=False):
		"""Updates env pip; assumes that env is setup"""
		import ocean.cli

		verbose = ocean.cli.verbose or verbose
		quiet_flag = "" if verbose else "--quiet"

		return self.run(
			f"{self.ocean.python} -m pip install {quiet_flag} --upgrade pip", cwd=self.ocean.name
		)

	@step(title="Installing wheel", success="Installed wheel")
	def wheel(self, verbose=False):
		"""Wheel is required for building old setup.py packages.
		ref: https://github.com/pypa/pip/issues/8559"""
		import ocean.cli

		verbose = ocean.cli.verbose or verbose
		quiet_flag = "" if verbose else "--quiet"

		return self.run(
			f"{self.ocean.python} -m pip install {quiet_flag} wheel", cwd=self.ocean.name
		)

	def logging(self):
		from ocean.utils import setup_logging

		return setup_logging(ocean_path=self.ocean.name)

	@step(title="Setting Up ocean Patches", success="ocean Patches Set Up")
	def patches(self):
		shutil.copy(
			os.path.join(os.path.dirname(os.path.abspath(__file__)), "patches", "patches.txt"),
			os.path.join(self.ocean.name, "patches.txt"),
		)

	@step(title="Setting Up Backups Cronjob", success="Backups Cronjob Set Up")
	def backups(self):
		# TODO: to something better for logging data? - maybe a wrapper that auto-logs with more context
		logger.log("setting up backups")

		from crontab import CronTab

		ocean_dir = os.path.abspath(self.ocean.name)
		user = self.ocean.conf.get("frappe_user")
		logfile = os.path.join(ocean_dir, "logs", "backup.log")
		system_crontab = CronTab(user=user)
		backup_command = f"cd {ocean_dir} && {sys.argv[0]} --verbose --site all backup"
		job_command = f"{backup_command} >> {logfile} 2>&1"

		if job_command not in str(system_crontab):
			job = system_crontab.new(
				command=job_command, comment="ocean auto backups set for every 6 hours"
			)
			job.every(6).hours()
			system_crontab.write()

		logger.log("backups were set up")

	@job(title="Setting Up ocean Dependencies", success="ocean Dependencies Set Up")
	def requirements(self, apps=None):
		"""Install and upgrade specified / all installed apps on given ocean"""
		from ocean.app import App

		apps = apps or self.ocean.apps

		self.pip()

		print(f"Installing {len(apps)} applications...")

		for app in apps:
			path_to_app = os.path.join(self.ocean.name, "apps", app)
			app = App(path_to_app, ocean=self.ocean, to_clone=False).install(
				skip_assets=True, restart_ocean=False, ignore_resolution=True
			)

	def python(self, apps=None):
		"""Install and upgrade Python dependencies for specified / all installed apps on given ocean"""
		import ocean.cli

		apps = apps or self.ocean.apps

		quiet_flag = "" if ocean.cli.verbose else "--quiet"

		self.pip()

		for app in apps:
			app_path = os.path.join(self.ocean.name, "apps", app)
			log(f"\nInstalling python dependencies for {app}", level=3, no_log=True)
			self.run(f"{self.ocean.python} -m pip install {quiet_flag} --upgrade -e {app_path}")

	def node(self, apps=None):
		"""Install and upgrade Node dependencies for specified / all apps on given ocean"""
		from ocean.utils.ocean import update_node_packages

		return update_node_packages(ocean_path=self.ocean.name, apps=apps)


class oceanTearDown:
	def __init__(self, ocean):
		self.ocean = ocean

	def backups(self):
		remove_backups_crontab(self.ocean.name)

	def dirs(self):
		shutil.rmtree(self.ocean.name)
