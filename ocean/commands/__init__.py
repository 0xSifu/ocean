# imports - third party imports
import click

# imports - module imports
from ocean.utils.cli import (
	MultiCommandGroup,
	print_ocean_version,
	use_experimental_feature,
	setup_verbosity,
)


@click.group(cls=MultiCommandGroup)
@click.option(
	"--version",
	is_flag=True,
	is_eager=True,
	callback=print_ocean_version,
	expose_value=False,
)
@click.option(
	"--use-feature",
	is_eager=True,
	callback=use_experimental_feature,
	expose_value=False,
)
@click.option(
	"-v",
	"--verbose",
	is_flag=True,
	callback=setup_verbosity,
	expose_value=False,
)
def ocean_command(ocean_path="."):
	import ocean

	ocean.set_frappe_version(ocean_path=ocean_path)


from ocean.commands.make import (
	drop,
	exclude_app_for_update,
	get_app,
	include_app_for_update,
	init,
	new_app,
	pip,
	remove_app,
)

ocean_command.add_command(init)
ocean_command.add_command(drop)
ocean_command.add_command(get_app)
ocean_command.add_command(new_app)
ocean_command.add_command(remove_app)
ocean_command.add_command(exclude_app_for_update)
ocean_command.add_command(include_app_for_update)
ocean_command.add_command(pip)


from ocean.commands.update import (
	retry_upgrade,
	switch_to_branch,
	switch_to_develop,
	update,
)

ocean_command.add_command(update)
ocean_command.add_command(retry_upgrade)
ocean_command.add_command(switch_to_branch)
ocean_command.add_command(switch_to_develop)


from ocean.commands.utils import (
	backup_all_sites,
	ocean_src,
	disable_production,
	download_translations,
	find_oceanes,
	migrate_env,
	renew_lets_encrypt,
	restart,
	set_mariadb_host,
	set_nginx_port,
	set_redis_cache_host,
	set_redis_queue_host,
	set_redis_socketio_host,
	set_ssl_certificate,
	set_ssl_certificate_key,
	set_url_root,
	start,
)

ocean_command.add_command(start)
ocean_command.add_command(restart)
ocean_command.add_command(set_nginx_port)
ocean_command.add_command(set_ssl_certificate)
ocean_command.add_command(set_ssl_certificate_key)
ocean_command.add_command(set_url_root)
ocean_command.add_command(set_mariadb_host)
ocean_command.add_command(set_redis_cache_host)
ocean_command.add_command(set_redis_queue_host)
ocean_command.add_command(set_redis_socketio_host)
ocean_command.add_command(download_translations)
ocean_command.add_command(backup_all_sites)
ocean_command.add_command(renew_lets_encrypt)
ocean_command.add_command(disable_production)
ocean_command.add_command(ocean_src)
ocean_command.add_command(find_oceanes)
ocean_command.add_command(migrate_env)

from ocean.commands.setup import setup

ocean_command.add_command(setup)


from ocean.commands.config import config

ocean_command.add_command(config)

from ocean.commands.git import remote_reset_url, remote_set_url, remote_urls

ocean_command.add_command(remote_set_url)
ocean_command.add_command(remote_reset_url)
ocean_command.add_command(remote_urls)

from ocean.commands.install import install

ocean_command.add_command(install)
