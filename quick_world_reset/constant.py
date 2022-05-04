import os

from mcdreforged.api.event import LiteralEvent

PLUGIN_ID = 'quick_world_reset'
Prefix = '!!reset'
CONFIG_FILE = os.path.join('config', 'QuickWorldReset.json')

RESET_DONE_EVENT 		= LiteralEvent('{}.reset_done'.format(PLUGIN_ID))  # -> source
TRIGGER_RESET_EVENT 	= LiteralEvent('{}.trigger_reset'.format(PLUGIN_ID))  # <- source

'''
mcdr_root/
	server/
		world/
	qworld_reset/
		overwrite/
			info.txt
			world/
'''
