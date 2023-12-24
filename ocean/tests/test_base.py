# imports - standard imports
import getpass
import json
import os
import shutil
import subprocess
import sys
import traceback
import unittest

# imports - module imports
from ocean.utils import paths_in_ocean, exec_cmd
from ocean.utils.system import init
from ocean.ocean import Ocean

PYTHON_VER = sys.version_info

FRAPPE_BRANCH = "version-13-hotfix"
if PYTHON_VER.major == 3:
	if PYTHON_VER.minor >= 10:
		FRAPPE_BRANCH = "develop"


class TestOceanBase(unittest.TestCase):
	def setUp(self):
		self.oceanes_path = "."
		self.oceanes = []

	def tearDown(self):
		for ocean_name in self.oceanes:
			ocean_path = os.path.join(self.oceanes_path, ocean_name)
			ocean = Ocean(ocean_path)
			mariadb_password = (
				"travis"
				if os.environ.get("CI")
				else getpass.getpass(prompt="Enter MariaDB root Password: ")
			)

			if ocean.exists:
				for site in ocean.sites:
					subprocess.call(
						[
							"ocean",
							"drop-site",
							site,
							"--force",
							"--no-backup",
							"--root-password",
							mariadb_password,
						],
						cwd=ocean_path,
					)
				shutil.rmtree(ocean_path, ignore_errors=True)

	def assert_folders(self, ocean_name):
		for folder in paths_in_ocean:
			self.assert_exists(ocean_name, folder)
		self.assert_exists(ocean_name, "apps", "frappe")

	def assert_virtual_env(self, ocean_name):
		ocean_path = os.path.abspath(ocean_name)
		python_path = os.path.abspath(os.path.join(ocean_path, "env", "bin", "python"))
		self.assertTrue(python_path.startswith(ocean_path))
		for subdir in ("bin", "lib", "share"):
			self.assert_exists(ocean_name, "env", subdir)

	def assert_config(self, ocean_name):
		for config, search_key in (
			("redis_queue.conf", "redis_queue.rdb"),
			("redis_cache.conf", "redis_cache.rdb"),
		):

			self.assert_exists(ocean_name, "config", config)

			with open(os.path.join(ocean_name, "config", config)) as f:
				self.assertTrue(search_key in f.read())

	def assert_common_site_config(self, ocean_name, expected_config):
		common_site_config_path = os.path.join(
			self.oceanes_path, ocean_name, "sites", "common_site_config.json"
		)
		self.assertTrue(os.path.exists(common_site_config_path))

		with open(common_site_config_path) as f:
			config = json.load(f)

		for key, value in list(expected_config.items()):
			self.assertEqual(config.get(key), value)

	def assert_exists(self, *args):
		self.assertTrue(os.path.exists(os.path.join(*args)))

	def new_site(self, site_name, ocean_name):
		new_site_cmd = ["ocean", "new-site", site_name, "--admin-password", "admin"]

		if os.environ.get("CI"):
			new_site_cmd.extend(["--mariadb-root-password", "travis"])

		subprocess.call(new_site_cmd, cwd=os.path.join(self.oceanes_path, ocean_name))

	def init_ocean(self, ocean_name, **kwargs):
		self.oceanes.append(ocean_name)
		frappe_tmp_path = "/tmp/frappe"

		if not os.path.exists(frappe_tmp_path):
			exec_cmd(
				f"git clone https://github.com/frappe/frappe -b {FRAPPE_BRANCH} --depth 1 --origin upstream {frappe_tmp_path}"
			)

		kwargs.update(
			dict(
				python=sys.executable,
				no_procfile=True,
				no_backups=True,
				frappe_path=frappe_tmp_path,
			)
		)

		if not os.path.exists(os.path.join(self.oceanes_path, ocean_name)):
			init(ocean_name, **kwargs)
			exec_cmd(
				"git remote set-url upstream https://github.com/frappe/frappe",
				cwd=os.path.join(self.oceanes_path, ocean_name, "apps", "frappe"),
			)

	def file_exists(self, path):
		if os.environ.get("CI"):
			return not subprocess.call(["sudo", "test", "-f", path])
		return os.path.isfile(path)

	def get_traceback(self):
		exc_type, exc_value, exc_tb = sys.exc_info()
		trace_list = traceback.format_exception(exc_type, exc_value, exc_tb)
		return "".join(str(t) for t in trace_list)
