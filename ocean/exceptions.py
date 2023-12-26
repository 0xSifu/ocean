class InvalidBranchException(Exception):
	pass


class InvalidRemoteException(Exception):
	pass


class PatchError(Exception):
	pass


class CommandFailedError(Exception):
	pass


class OceanNotFoundError(Exception):
	pass


class ValidationError(Exception):
	pass


class AppNotInstalledError(ValidationError):
	pass


class CannotUpdateReleaseOcean(ValidationError):
	pass


class FeatureDoesNotExistError(CommandFailedError):
	pass


class NotInOceanDirectoryError(Exception):
	pass


class VersionNotFound(Exception):
	pass
