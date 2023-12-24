# imports - standard imports
import grp
import os
import pwd
import shutil
import sys

# imports - module imports
import ocean
from ocean.utils import (
	exec_cmd,
	get_process_manager,
	log,
	run_frappe_cmd,
	sudoers_file,
	which,
	is_valid_frappe_branch,
)
from ocean.utils.ocean import build_assets, clone_apps_from
from ocean.utils.render import job


@job(title="Initializing Ocean {path}", success="Ocean {path} initialized")
def init(
	path,
	apps_path=None,
	no_procfile=False,
	no_backups=False,
	frappe_path=None,
	frappe_branch=None,
	verbose=False,
	clone_from=None,
	skip_redis_config_generation=False,
	clone_without_update=False,
	skip_assets=False,
	python="python3",
	install_app=None,
	dev=False,
):
	"""Initialize a new ocean directory

	* create a ocean directory in the given path
	* setup logging for the ocean
	* setup env for the ocean
	* setup config (dir/pids/redis/procfile) for the ocean
	* setup patches.txt for ocean
	* clone & install frappe
	        * install python & node dependencies
	        * build assets
	* setup backups crontab
	"""

	# Use print("\033c", end="") to clear entire screen after each step and re-render each list
	# another way => https://stackoverflow.com/a/44591228/10309266

	import ocean.cli
	from ocean.app import get_app, install_apps_from_path
	from ocean.ocean import Ocean

	verbose = ocean.cli.verbose or verbose

	ocean = Ocean(path)

	ocean.setup.dirs()
	ocean.setup.logging()
	ocean.setup.env(python=python)
	config = {}
	if dev:
		config["developer_mode"] = 1
	ocean.setup.config(
		redis=not skip_redis_config_generation,
		procfile=not no_procfile,
		additional_config=config,
	)
	ocean.setup.patches()

	# local apps
	if clone_from:
		clone_apps_from(
			ocean_path=path, clone_from=clone_from, update_app=not clone_without_update
		)

	# remote apps
	else:
		frappe_path = frappe_path or "https://github.com/frappe/frappe.git"
		is_valid_frappe_branch(frappe_path=frappe_path, frappe_branch=frappe_branch)
		get_app(
			frappe_path,
			branch=frappe_branch,
			ocean_path=path,
			skip_assets=True,
			verbose=verbose,
			resolve_deps=False,
		)

		# fetch remote apps using config file - deprecate this!
		if apps_path:
			install_apps_from_path(apps_path, ocean_path=path)

	# getting app on ocean init using --install-app
	if install_app:
		get_app(
			install_app,
			branch=frappe_branch,
			ocean_path=path,
			skip_assets=True,
			verbose=verbose,
			resolve_deps=False,
		)

	if not skip_assets:
		build_assets(ocean_path=path)

	if not no_backups:
		ocean.setup.backups()


def setup_sudoers(user):
	from ocean.config.lets_encrypt import get_certbot_path

	if not os.path.exists("/etc/sudoers.d"):
		os.makedirs("/etc/sudoers.d")

		set_permissions = not os.path.exists("/etc/sudoers")
		with open("/etc/sudoers", "a") as f:
			f.write("\n#includedir /etc/sudoers.d\n")

		if set_permissions:
			os.chmod("/etc/sudoers", 0o440)

	template = ocean.config.env().get_template("frappe_sudoers")
	frappe_sudoers = template.render(
		**{
			"user": user,
			"service": which("service"),
			"systemctl": which("systemctl"),
			"nginx": which("nginx"),
			"certbot": get_certbot_path(),
		}
	)

	with open(sudoers_file, "w") as f:
		f.write(frappe_sudoers)

	os.chmod(sudoers_file, 0o440)
	log(f"Sudoers was set up for user {user}", level=1)


def start(no_dev=False, concurrency=None, procfile=None, no_prefix=False, procman=None):
	program = which(procman) if procman else get_process_manager()
	if not program:
		raise Exception("No process manager found")

	os.environ["PYTHONUNBUFFERED"] = "true"
	if not no_dev:
		os.environ["DEV_SERVER"] = "true"

	command = [program, "start"]
	if concurrency:
		command.extend(["-c", concurrency])

	if procfile:
		command.extend(["-f", procfile])

	if no_prefix:
		command.extend(["--no-prefix"])

	os.execv(program, command)


def migrate_site(site, ocean_path="."):
	run_frappe_cmd("--site", site, "migrate", ocean_path=ocean_path)


def backup_site(site, ocean_path="."):
	run_frappe_cmd("--site", site, "backup", ocean_path=ocean_path)


def backup_all_sites(ocean_path="."):
	from ocean.ocean import Ocean

	for site in Ocean(ocean_path).sites:
		backup_site(site, ocean_path=ocean_path)


def fix_prod_setup_perms(ocean_path=".", frappe_user=None):
	from glob import glob
	from ocean.ocean import Ocean

	frappe_user = frappe_user or Ocean(ocean_path).conf.get("frappe_user")

	if not frappe_user:
		print("frappe user not set")
		sys.exit(1)

	globs = ["logs/*", "config/*"]
	for glob_name in globs:
		for path in glob(glob_name):
			uid = pwd.getpwnam(frappe_user).pw_uid
			gid = grp.getgrnam(frappe_user).gr_gid
			os.chown(path, uid, gid)


def setup_fonts():
	fonts_path = os.path.join("/tmp", "fonts")

	if os.path.exists("/etc/fonts_backup"):
		return

	exec_cmd("git clone https://github.com/frappe/fonts.git", cwd="/tmp")
	os.rename("/etc/fonts", "/etc/fonts_backup")
	os.rename("/usr/share/fonts", "/usr/share/fonts_backup")
	os.rename(os.path.join(fonts_path, "etc_fonts"), "/etc/fonts")
	os.rename(os.path.join(fonts_path, "usr_share_fonts"), "/usr/share/fonts")
	shutil.rmtree(fonts_path)
	exec_cmd("fc-cache -fv")
