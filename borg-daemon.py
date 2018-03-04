#!/usr/bin/python3

from pathlib import Path
import toml
import sys
import os
import typing
import argparse
import subprocess
import getpass


__version__ = (0, 1)


CACHE_TAG_CONTENTS = '''Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created.
# For information about cache directory tags, see:
#	http://www.brynosaurus.com/cachedir/
#
# The directory is marked as cachedir to avoid it being backed up by borg.
'''

CACHE_TAG_STARTLINE = CACHE_TAG_CONTENTS.splitlines()[0]


def update_config(base, new):
    # like dict.update, but recursive
    for key, val in new.items():
        if isinstance(val, dict):
            base[key] = update_config(base.get(key, {}), val)
        else:
            base[key] = val

    return base


def parse_config(path: Path):
    # load the configuration
    with path.open('r') as file:
        contents = toml.load(file)

    # look for any imported configurations
    imports = contents.get('imports', [])
    if isinstance(imports, str):
        imports = [imports]

    # combine all configs

    result = {}
    for importee in imports:
        importee_path = Path(path.parent, importee)
        importee_contents = parse_config(importee_path)
        update_config(result, importee_contents)

    update_config(result, contents)
    return result


def parse_argv():
    parser = argparse.ArgumentParser(description='Easily run borg using short configuration files')
    parser.add_argument('operation',
                        type=str,
                        choices=('create', 'prune', 'list', 'single', 'daemon'),
                        help='the operation to perform')
    parser.add_argument('config',
                        type=str,
                        help='the path to the configuration file')

    return parser.parse_args()


def mark_caches(path_root: Path, caches: typing.List[str]):
    # expand the globs
    cache_dirs = []

    for cache in caches:
        cache_dirs += path_root.glob(cache)

    for dir_path in cache_dirs:
        tag_path = dir_path / 'CACHEDIR.TAG'

        # file exists, ensure it is valid
        if tag_path.exists():
            assert tag_path.is_file()
            contents = tag_path.open().read()
            assert contents.startswith(CACHE_TAG_STARTLINE)

        # directory exist, but the file doesn't - create it
        elif dir_path.exists():
            print('Marking {} as cache directory'.format(tag_path))
            with tag_path.open('w') as tag_file:
                tag_file.write(CACHE_TAG_CONTENTS)


def run_borg(action: str,
             config: dict,
             flags: typing.List[str],
             post_flags: typing.List[str],
             archive_name,
             env):

    full_repo_name = config['borg']['repository']
    if archive_name is not None:
        full_repo_name += '::' + archive_name

    command = [config['borg']['binary']] + \
              [action] + \
              flags + \
              [full_repo_name] + \
              post_flags

    print('Running borg: \'{}\''.format('\' \''.join(command)))

    proc = subprocess.Popen(command, env=env)
    proc.communicate()

    if proc.returncode != 0:
        print('ERROR: borg returned with status code {}'.format(proc.returncode))
        exit(proc.returncode)


def create(config: dict, env):
    backup_directory = config['create']['backup_directory']

    excludes = []
    for exclude in config['create'].get('excludes', []):
        excludes.append('--exclude')
        excludes.append(str(Path(backup_directory, exclude)))

    default_flags = [
        '--progress',
        '--filter', 'AME',
        '--list',
        '--show-rc',
    ]

    flags = \
        default_flags + \
        excludes + \
        config['borg'].get('flags', [])

    post_flags = [config['create']['backup_directory']]

    run_borg('create', config, flags, post_flags, config['create']['name'], env)


def prune(config: dict, env):
    flags = config['prune'].get('flags', [])
    post_flags = []
    run_borg('prune', config, flags, post_flags, None, env)


def list(config: dict, env):
    run_borg('list', config, [], [], None, env)


def run_single(config: dict, env):
    create(config, env)
    prune(config, env)


def run_daemon(config: dict, env):
    while True:
        backup_times = get_backup_times()
        raise NotImplementedError()
        run_single(config)


def main():
    arguments = parse_argv()
    config = parse_config(Path(arguments.config))

    mark_caches(Path(config['create']['backup_directory']),
                config['create'].get('cachedirs', []))

    # set the passphrase environment
    try:
        env = dict(os.environ, BORG_PASSCOMMAND=config['borg']['passphrase_command'])
    except KeyError:
        env = dict(os.environ, BORG_PASSPHRASE=getpass.getpass())

    # dispatch the task
    if arguments.operation == 'create':
        create(config, env)
    elif arguments.operation == 'prune':
        prune(config, env)
    elif arguments.operation == 'list':
        list(config, env)
    elif arguments.operation == 'single':
        run_single(config, env)
    elif arguments.operation == 'daemon':
        run_daemon(config, env)
    else:
        assert False, arguments.operation


if __name__ == '__main__':
    main()
