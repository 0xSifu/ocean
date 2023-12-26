"""Module for setting up system and respective ocean configurations"""


def env():
	from jinja2 import Environment, PackageLoader

	return Environment(loader=PackageLoader("ocean.config"))
