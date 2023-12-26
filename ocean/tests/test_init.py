# imports - standard imports
import json
import os
import subprocess
import unittest

# imports - third paty imports
import git

# imports - module imports
from ocean.utils import exec_cmd
from ocean.app import App
from ocean.tests.test_base import FRAPPE_BRANCH, TestOceanBase
from ocean.ocean import Ocean


# changed from frappe_theme because it wasn't maintained and incompatible,
# chat app & wiki was breaking too. hopefully frappe_docs will be maintained
# for longer since docs.erpnext.com is powered by it ;)
TEST_FRAPPE_APP = "frappe_docs"


class TestOceanInit(TestOceanBase):
	def test_utils(self):
		self.assertEqual(subprocess.call("ocean"), 0)

	def test_init(self, ocean_name="test-ocean", **kwargs):
		self.init_ocean(ocean_name, **kwargs)
		app = App("file:///tmp/frappe")
		self.assertTupleEqual(
			(app.mount_path, app.url, app.repo, app.app_name, app.org),
			("/tmp/frappe", "file:///tmp/frappe", "frappe", "frappe", "frappe"),
		)
		self.assert_folders(ocean_name)
		self.assert_virtual_env(ocean_name)
		self.assert_config(ocean_name)
		test_ocean = Ocean(ocean_name)
		app = App("frappe", ocean=test_ocean)
		self.assertEqual(app.from_apps, True)

	def basic(self):
		try:
			self.test_init()
		except Exception:
			print(self.get_traceback())

	def test_multiple_oceanes(self):
		for ocean_name in ("test-ocean-1", "test-ocean-2"):
			self.init_ocean(ocean_name, skip_assets=True)

		self.assert_common_site_config(
			"test-ocean-1",
			{
				"webserver_port": 8000,
				"socketio_port": 9000,
				"file_watcher_port": 6787,
				"redis_queue": "redis://127.0.0.1:11000",
				"redis_socketio": "redis://127.0.0.1:13000",
				"redis_cache": "redis://127.0.0.1:13000",
			},
		)

		self.assert_common_site_config(
			"test-ocean-2",
			{
				"webserver_port": 8001,
				"socketio_port": 9001,
				"file_watcher_port": 6788,
				"redis_queue": "redis://127.0.0.1:11001",
				"redis_socketio": "redis://127.0.0.1:13001",
				"redis_cache": "redis://127.0.0.1:13001",
			},
		)

	def test_new_site(self):
		ocean_name = "test-ocean"
		site_name = "test-site.local"
		ocean_path = os.path.join(self.oceanes_path, ocean_name)
		site_path = os.path.join(ocean_path, "sites", site_name)
		site_config_path = os.path.join(site_path, "site_config.json")

		self.init_ocean(ocean_name)
		self.new_site(site_name, ocean_name)

		self.assertTrue(os.path.exists(site_path))
		self.assertTrue(os.path.exists(os.path.join(site_path, "private", "backups")))
		self.assertTrue(os.path.exists(os.path.join(site_path, "private", "files")))
		self.assertTrue(os.path.exists(os.path.join(site_path, "public", "files")))
		self.assertTrue(os.path.exists(site_config_path))

		with open(site_config_path) as f:
			site_config = json.loads(f.read())

			for key in ("db_name", "db_password"):
				self.assertTrue(key in site_config)
				self.assertTrue(site_config[key])

	def test_get_app(self):
		self.init_ocean("test-ocean", skip_assets=True)
		ocean_path = os.path.join(self.oceanes_path, "test-ocean")
		exec_cmd(f"ocean get-app {TEST_FRAPPE_APP} --skip-assets", cwd=ocean_path)
		self.assertTrue(os.path.exists(os.path.join(ocean_path, "apps", TEST_FRAPPE_APP)))
		app_installed_in_env = TEST_FRAPPE_APP in subprocess.check_output(
			["ocean", "pip", "freeze"], cwd=ocean_path
		).decode("utf8")
		self.assertTrue(app_installed_in_env)

	@unittest.skipIf(FRAPPE_BRANCH != "develop", "only for develop branch")
	def test_get_app_resolve_deps(self):
		FRAPPE_APP = "healthcare"
		self.init_ocean("test-ocean", skip_assets=True)
		ocean_path = os.path.join(self.oceanes_path, "test-ocean")
		exec_cmd(f"ocean get-app {FRAPPE_APP} --resolve-deps --skip-assets", cwd=ocean_path)
		self.assertTrue(os.path.exists(os.path.join(ocean_path, "apps", FRAPPE_APP)))

		states_path = os.path.join(ocean_path, "sites", "apps.json")
		self.assertTrue(os.path.exists(states_path))

		with open(states_path) as f:
			states = json.load(f)

		self.assertTrue(FRAPPE_APP in states)

	def test_install_app(self):
		ocean_name = "test-ocean"
		site_name = "install-app.test"
		ocean_path = os.path.join(self.oceanes_path, "test-ocean")

		self.init_ocean(ocean_name, skip_assets=True)
		exec_cmd(
			f"ocean get-app {TEST_FRAPPE_APP} --branch master --skip-assets", cwd=ocean_path
		)

		self.assertTrue(os.path.exists(os.path.join(ocean_path, "apps", TEST_FRAPPE_APP)))

		# check if app is installed
		app_installed_in_env = TEST_FRAPPE_APP in subprocess.check_output(
			["ocean", "pip", "freeze"], cwd=ocean_path
		).decode("utf8")
		self.assertTrue(app_installed_in_env)

		# create and install app on site
		self.new_site(site_name, ocean_name)
		installed_app = not exec_cmd(
			f"ocean --site {site_name} install-app {TEST_FRAPPE_APP}",
			cwd=ocean_path,
			_raise=False,
		)

		if installed_app:
			app_installed_on_site = subprocess.check_output(
				["ocean", "--site", site_name, "list-apps"], cwd=ocean_path
			).decode("utf8")
			self.assertTrue(TEST_FRAPPE_APP in app_installed_on_site)

	def test_remove_app(self):
		self.init_ocean("test-ocean", skip_assets=True)
		ocean_path = os.path.join(self.oceanes_path, "test-ocean")

		exec_cmd(
			f"ocean get-app {TEST_FRAPPE_APP} --branch master --overwrite --skip-assets",
			cwd=ocean_path,
		)
		exec_cmd(f"ocean remove-app {TEST_FRAPPE_APP}", cwd=ocean_path)

		with open(os.path.join(ocean_path, "sites", "apps.txt")) as f:
			self.assertFalse(TEST_FRAPPE_APP in f.read())
		self.assertFalse(
			TEST_FRAPPE_APP
			in subprocess.check_output(["ocean", "pip", "freeze"], cwd=ocean_path).decode("utf8")
		)
		self.assertFalse(os.path.exists(os.path.join(ocean_path, "apps", TEST_FRAPPE_APP)))

	def test_switch_to_branch(self):
		self.init_ocean("test-ocean", skip_assets=True)
		ocean_path = os.path.join(self.oceanes_path, "test-ocean")
		app_path = os.path.join(ocean_path, "apps", "frappe")

		# * chore: change to 14 when avalible
		prevoius_branch = "version-13"
		if FRAPPE_BRANCH != "develop":
			# assuming we follow `version-#`
			prevoius_branch = f"version-{int(FRAPPE_BRANCH.split('-')[1]) - 1}"

		successful_switch = not exec_cmd(
			f"ocean switch-to-branch {prevoius_branch} frappe --upgrade",
			cwd=ocean_path,
			_raise=False,
		)
		if successful_switch:
			app_branch_after_switch = str(git.Repo(path=app_path).active_branch)
			self.assertEqual(prevoius_branch, app_branch_after_switch)

		successful_switch = not exec_cmd(
			f"ocean switch-to-branch {FRAPPE_BRANCH} frappe --upgrade",
			cwd=ocean_path,
			_raise=False,
		)
		if successful_switch:
			app_branch_after_second_switch = str(git.Repo(path=app_path).active_branch)
			self.assertEqual(FRAPPE_BRANCH, app_branch_after_second_switch)


if __name__ == "__main__":
	unittest.main()
