#!/bin/python

import sys
import typing
from typing import Optional
import argparse
import types
from collections import defaultdict
from pathlib import Path
import tempfile
import appdirs
import json


import_insert_marker="#import insert"

backup_path=Path(tempfile.gettempdir())/".pyimports_backup.py"

user_data_dir=Path(appdirs.user_data_dir("pyimports"))
user_data_dir.mkdir(exist_ok=True)

cache_name_to_paths=user_data_dir/"cache_name_to_paths.json"



## https://stackoverflow.com/questions/8370206/how-to-get-a-list-of-built-in-modules-in-python, first answer, on my version (roughly 3.8)
def generate_name_to_paths()-> dict[str, list[str]]:
	name_to_info: typing.MutableMapping[str, #name
			typing.MutableMapping[int, #id
				str]
			]=defaultdict(dict)  # name → (id → path)

	seen_modules=set()
	pending=[]

	def process(path: str, name: str, item: object)->None:
		if isinstance(item, types.ModuleType):
			if item in seen_modules: return
			seen_modules.add(item)
			pending.append((path, name, item))
		#print(path, "->", name)

		d=name_to_info[name]
		if id(item) not in d:
			d[id(item)]=path

	builtin_modules={*"abc aifc antigravity argparse array ast asynchat asyncio asyncore atexit audioop base64 bdb binascii binhex bisect builtins bz2 calendar cgi cgitb chunk cmath cmd code codecs codeop collections colorsys compileall concurrent configparser contextlib contextvars copy copyreg cProfile crypt csv ctypes curses dataclasses datetime dbm decimal difflib dis distutils doctest email encodings ensurepip enum errno faulthandler fcntl filecmp fileinput fnmatch formatter fractions ftplib functools gc genericpath getopt getpass gettext glob graphlib grp gzip hashlib heapq hmac html http idlelib imaplib imghdr imp importlib inspect io ipaddress itertools json keyword lib2to3 linecache locale logging lzma mailbox mailcap marshal math mimetypes mmap modulefinder multiprocessing netrc nis nntplib ntpath nturl2path numbers opcode operator optparse os ossaudiodev parser pathlib pdb pickle pickletools pip pipes pkg_resources pkgutil platform plistlib poplib posix posixpath pprint profile pstats pty pwd pyclbr py_compile pydoc pydoc_data pyexpat queue quopri random re readline reprlib resource rlcompleter runpy sched secrets select selectors setuptools shelve shlex shutil signal site smtpd smtplib sndhdr socket socketserver spwd sqlite3 sre_compile sre_constants sre_parse ssl stat statistics string stringprep struct subprocess sunau symtable sys sysconfig syslog tabnanny tarfile telnetlib tempfile termios textwrap this threading time timeit tkinter token tokenize trace traceback tracemalloc tty turtle turtledemo types typing unicodedata unittest urllib uu uuid venv warnings wave weakref webbrowser wheel wsgiref xdrlib xml xmlrpc xxlimited xxsubtype zipapp zipfile zipimport zlib zoneinfo".split()} - {*
			"antigravity this binhex formatter imp parser".split()}
	
	for module_name in builtin_modules:
		try: module=__import__(module_name)
		except ImportError: continue

		process("", module_name, module)

	i=0
	while i<len(pending):
		parent, name, o=pending[i]
		i+=1

		assert isinstance(o, types.ModuleType)
		assert o in seen_modules

		path: str=parent+("." if parent else "")+name
		for attribute_name in [*dir(o)]:
			if attribute_name.startswith("_"): continue
			#print(path, "->", attribute_name)
			try: item: object=getattr(o, attribute_name)
			except: raise

			process(path, attribute_name, item)

	return {name: list(cases.values()) for name, cases in name_to_info.items()}


def get_name_to_paths()->dict[str, list[str]]:
	try: return json.loads(cache_name_to_paths.read_text())
	except (FileNotFoundError,
			json.JSONDecodeError  # corrupted file?
			):
		name_to_paths=generate_name_to_paths()
		cache_name_to_paths.write_text(json.dumps(name_to_paths, indent=0, ensure_ascii=False))
		return name_to_paths


def get_undefined_names(code: str)->set[str]:
	"""
	Get the set of undefined names in code. Raise an error if there's some other error in the code.
	"""
	from pyflakes import api, messages  # type: ignore
	class Reporter(object):
		def __init__(self):
			self.undefined_names: set[str]=set()

		def unexpectedError(self, filename, msg):
			raise RuntimeError(msg)

		def syntaxError(self, filename, msg, lineno, offset, text):
			raise RuntimeError("Syntax error {lineno}:{offset} {msg}")

		def flake(self, message):
			if isinstance(message, messages.UndefinedName):
				[undefined_name]=message.message_args
				self.undefined_names.add(undefined_name)

	reporter=Reporter()
	api.check(code, "", reporter)
	return reporter.undefined_names


def main()->None:
	parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument("file", help="Path to Python file to be checked.", type=Path)
	args=parser.parse_args()
	old_code=args.file.read_text()
	backup_path.write_text(old_code)
	lines=old_code.splitlines()

	insert_pos=0
	if import_insert_marker in lines:
		insert_pos=lines.index(import_insert_marker)
	else:
		if lines and lines[0].startswith("#!"):
			insert_pos+=1
			#too lazy to add more heuristics, fix yourself


	undefined_names=get_undefined_names(old_code)

	name_to_paths=get_name_to_paths()

	insertions=[]
	for name in undefined_names:
		if name not in name_to_paths: continue
		paths=name_to_paths[name]
		path=paths[0]  # TODO
		import_statement=f"from {path} import {name}" if path else f"import {name}"
		insertions.append(import_statement)

	lines=lines[:insert_pos]+insertions+lines[insert_pos:]
	new_code='\n'.join(lines)
	args.file.write_text(new_code)


if __name__=="__main__":
	main()
