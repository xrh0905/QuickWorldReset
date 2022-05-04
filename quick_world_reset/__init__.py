import functools
import json
import os
import re
import shutil
import time
from threading import Lock
from typing import Optional, Any, Callable

from mcdreforged.api.all import *

from quick_world_reset.config import Configure
from quick_world_reset.constant import Prefix, RESET_DONE_EVENT, \
	CONFIG_FILE, TRIGGER_RESET_EVENT

config: Configure
server_inst: PluginServerInterface
HelpMessage: RTextBase
armed_reset = False
abort_reset = True
plugin_unloaded = False
operation_lock = Lock()
operation_name = RText('?')


def tr(translation_key: str, *args) -> RTextMCDRTranslation:
	return ServerInterface.get_instance().rtr('quick_world_reset.{}'.format(translation_key), *args)


def print_message(source: CommandSource, msg, tell=True, prefix='[QWR] '):
	msg = RTextList(prefix, msg)
	if source.is_player and not tell:
		source.get_server().say(msg)
	else:
		source.reply(msg)

def copy_worlds(src: str, dst: str):
	for world in config.world_names:
		src_path = os.path.join(src, world)
		dst_path = os.path.join(dst, world)

		while os.path.islink(src_path):
			server_inst.logger.info('copying {} -> {} (symbolic link)'.format(src_path, dst_path))
			dst_dir = os.path.dirname(dst_path)
			if not os.path.isdir(dst_dir):
				os.makedirs(dst_dir)
			link_path = os.readlink(src_path)
			os.symlink(link_path, dst_path)
			src_path = link_path if os.path.isabs(link_path) else os.path.normpath(os.path.join(os.path.dirname(src_path), link_path))
			dst_path = os.path.join(dst, os.path.relpath(src_path, src))

		server_inst.logger.info('copying {} -> {}'.format(src_path, dst_path))
		if os.path.isdir(src_path):
			shutil.copytree(src_path, dst_path, ignore=lambda path, files: set(filter(config.is_file_ignored, files)))
		elif os.path.isfile(src_path):
			dst_dir = os.path.dirname(dst_path)
			if not os.path.isdir(dst_dir):
				os.makedirs(dst_dir)
			shutil.copy(src_path, dst_path)
		else:
			server_inst.logger.warning('{} does not exist while copying ({} -> {})'.format(src_path, src_path, dst_path))

def command_run(message: Any, text: Any, command: str) -> RTextBase:
	fancy_text = message.copy() if isinstance(message, RTextBase) else RText(message)
	return fancy_text.set_hover_text(text).set_click_event(RAction.run_command, command)


def remove_worlds(folder: str):
	for world in config.world_names:
		target_path = os.path.join(folder, world)

		while os.path.islink(target_path):
			link_path = os.readlink(target_path)
			os.unlink(target_path)
			target_path = link_path if os.path.isabs(link_path) else os.path.normpath(os.path.join(os.path.dirname(target_path), link_path))

		if os.path.isdir(target_path):
			shutil.rmtree(target_path)
		elif os.path.isfile(target_path):
			os.remove(target_path)
		else:
			ServerInterface.get_instance().logger.warning('[QWR] {} does not exist while removing'.format(target_path))


def format_time():
	return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


def single_op(name: RTextBase):
	def wrapper(func: Callable):
		@functools.wraps(func)
		def wrap(source: CommandSource, *args, **kwargs):
			acq = operation_lock.acquire(blocking=False)
			if acq:
				try:
					func(source, *args, **kwargs)
				finally:
					operation_lock.release()
			else:
				print_message(source, tr('lock.warning', name))
		return wrap
	return wrapper


def reset_world(source: CommandSource):
	global abort_reset, armed_reset
	abort_reset = False
	armed_reset = True
	print_message(source, tr('reset.echo_action'), tell=False)
	print_message(
		source,
		command_run(tr('reset.confirm_hint', Prefix), tr('reset.confirm_hover'), '{0} confirm'.format(Prefix))
		+ ', '
		+ command_run(tr('reset.abort_hint', Prefix), tr('reset.abort_hover'), '{0} abort'.format(Prefix))
		, tell=False
	)


@new_thread('QWR - reset')
def confirm_reset(source: CommandSource):
	global armed_reset
	if (not armed_reset):
		print_message(source, tr('confirm_reset.nothing_to_confirm'), tell=False)
		return
	armed_reset	= False
	_do_TRIGGRESET_WORLD(source)


@single_op(tr('operations.reset'))
def _do_TRIGGRESET_WORLD(source: CommandSource):
	try:
		print_message(source, tr('do_reset.countdown.intro'), tell=False)
		for countdown in range(1, 10):
			print_message(source, command_run(
				tr('do_reset.countdown.text', 10 - countdown),
				tr('do_reset.countdown.hover'),
				'{} abort'.format(Prefix)
			), tell=False)
			for i in range(10):
				time.sleep(0.1)
				global abort_reset
				if abort_reset:
					print_message(source, tr('do_reset.abort'), tell=False)
					return

		source.get_server().stop()
		server_inst.logger.info('Wait for server to stop')
		source.get_server().wait_for_start()

		server_inst.logger.info('Backup current world to avoid idiot')
		overwrite_backup_path = os.path.join(config.backup_path, config.overwrite_backup_folder)
		if os.path.exists(overwrite_backup_path):
			shutil.rmtree(overwrite_backup_path)
		copy_worlds(config.server_path, overwrite_backup_path)
		with open(os.path.join(overwrite_backup_path, 'info.txt'), 'w') as f:
			f.write('Overwrite time: {}\n'.format(format_time()))
			f.write('Confirmed by: {}'.format(source))

		server_inst.logger.info('Deleting world')
		remove_worlds(config.server_path)

		source.get_server().start()
	except:
		server_inst.logger.exception('Fail to reset the world')
	else:
		source.get_server().dispatch_event(RESET_DONE_EVENT, (source))  # async dispatch


def trigger_abort(source: CommandSource):
	global abort_reset, armed_reset
	abort_reset = True
	armed_reset = False
	print_message(source, tr('trigger_abort.abort'), tell=False)


@new_thread('QWR - help')
def print_help_message(source: CommandSource):
	if source.is_player:
		source.reply('')
	with source.preferred_language_context():
		for line in HelpMessage.to_plain_text().splitlines():
			prefix = re.search(r'(?<=§7){}[\w ]*(?=§)'.format(Prefix), line)
			if prefix is not None:
				print_message(source, RText(line).set_click_event(RAction.suggest_command, prefix.group()), prefix='')
			else:
				print_message(source, line, prefix='')
		print_message(
			source,
			tr('print_help.hotbar') +
			'\n' +
			RText(tr('print_help.click_to_reset.text'))
				.h(tr('print_help.click_to_reset.hover'))
				.c(RAction.suggest_command, tr('print_help.click_to_reset.command', Prefix).to_plain_text()),
			prefix=''
		)


def print_unknown_argument_message(source: CommandSource, error: UnknownArgument):
	print_message(source, command_run(
		tr('unknown_command.text', Prefix),
		tr('unknown_command.hover'),
		Prefix
	))


def register_command(server: PluginServerInterface):
	def get_literal_node(literal):
		lvl = config.minimum_permission_level.get(literal, 0)
		return Literal(literal).requires(lambda src: src.has_permission(lvl)).on_error(RequirementNotMet, lambda src: src.reply(tr('command.permission_denied')), handled=True)

	def get_slot_node():
		return Integer('slot').requires(lambda src, ctx: 1 <= ctx['slot'] <= get_slot_count()).on_error(RequirementNotMet, lambda src: src.reply(tr('command.wrong_slot')), handled=True)

	server.register_command(
		Literal(Prefix).
		runs(print_help_message).
		on_error(UnknownArgument, print_unknown_argument_message, handled=True).
		then(
			get_literal_node('run').
			runs(lambda src: reset_world(src)).
			then(get_slot_node().runs(lambda src, ctx: reset_world(src)))
		).
		then(get_literal_node('confirm').runs(confirm_reset)).
		then(get_literal_node('abort').runs(trigger_abort)).
		then(get_literal_node('reload').runs(lambda src: load_config(src.get_server(), src)))
	)


def load_config(server: ServerInterface, source: CommandSource or None = None):
	global config
	config = server_inst.load_config_simple(CONFIG_FILE, target_class=Configure, in_data_folder=False, source_to_reply=source)


def register_event_listeners(server: PluginServerInterface):
	server.register_event_listener(TRIGGER_RESET_EVENT, lambda svr, source, slot: _do_TRIGGRESET_WORLD(source, slot))


def on_load(server: PluginServerInterface, old):
	global operation_lock, HelpMessage, server_inst
	server_inst = server
	if hasattr(old, 'operation_lock') and type(old.operation_lock) == type(operation_lock):
		operation_lock = old.operation_lock

	meta = server.get_self_metadata()
	HelpMessage = tr('help_message', Prefix, meta.name, meta.version)
	load_config(server)
	register_command(server)
	register_event_listeners(server)
	server.register_help_message(Prefix, command_run(tr('register.summory_help'), tr('register.show_help'), Prefix))


def on_unload(server):
	global abort_reset, plugin_unloaded
	abort_reset = True
	plugin_unloaded = True
