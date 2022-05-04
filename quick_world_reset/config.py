from typing import List, Dict

from mcdreforged.api.utils.serializer import Serializable


class Configure(Serializable):
	backup_path: str = './qworld_reset'
	server_path: str = './server'
	overwrite_backup_folder: str = 'overwrite'
	ignored_files: List[str] = [
		'session.lock'
	]
	world_names: List[str] = [
		'world'
	]
	# 0:guest 1:user 2:helper 3:admin 4:owner
	minimum_permission_level: Dict[str, int] = {
		'run': 2,
		'confirm': 2,
		'abort': 2,
		'reload': 2,
	}
	def is_file_ignored(self, file_name: str) -> bool:
		for item in self.ignored_files:
			if len(item) > 0:
				if item[0] == '*' and file_name.endswith(item[1:]):
					return True
				if item[-1] == '*' and file_name.startswith(item[:-1]):
					return True
				if file_name == item:
					return True
		return False


if __name__ == '__main__':
	config = Configure().get_default()
