# imports - standard imports
import getpass
import os
import subprocess

# imports - module imports
from ocean.cli import change_uid_msg
from ocean.config.production_setup import get_supervisor_confdir, is_centos7, service
from ocean.config.common_site_config import get_config
from ocean.utils import exec_cmd, get_ocean_name, get_cmd_output


def is_sudoers_set():
	"""Check if ocean sudoers is set"""
	cmd = ["sudo", "-n", "ocean"]
	ocean_warn = False

	with open(os.devnull, "wb") as f:
		return_code_check = not subprocess.call(cmd, stdout=f)

	if return_code_check:
		try:
			ocean_warn = change_uid_msg in get_cmd_output(cmd, _raise=False)
		except subprocess.CalledProcessError:
			ocean_warn = False
		finally:
			return_code_check = return_code_check and ocean_warn

	return return_code_check


def is_production_set(ocean_path):
	"""Check if production is set for current ocean"""
	production_setup = False
	ocean_name = get_ocean_name(ocean_path)

	supervisor_conf_extn = "ini" if is_centos7() else "conf"
	supervisor_conf_file_name = f"{ocean_name}.{supervisor_conf_extn}"
	supervisor_conf = os.path.join(get_supervisor_confdir(), supervisor_conf_file_name)

	if os.path.exists(supervisor_conf):
		production_setup = production_setup or True

	nginx_conf = f"/etc/nginx/conf.d/{ocean_name}.conf"

	if os.path.exists(nginx_conf):
		production_setup = production_setup or True

	return production_setup


def execute(ocean_path):
	"""This patch checks if ocean sudoers is set and regenerate supervisor and sudoers files"""
	user = get_config(".").get("frappe_user") or getpass.getuser()

	if is_sudoers_set():
		if is_production_set(ocean_path):
			exec_cmd(f"sudo ocean setup supervisor --yes --user {user}")
			service("supervisord", "restart")

		exec_cmd(f"sudo ocean setup sudoers {user}")
