from pathlib import Path
import toml
import sys
import typing
import argparse
import subprocess


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
                        choices=('backup', 'prune', 'single', 'daemon'),
                        help='the operation to perform')
    parser.add_argument('config',
                        type=str,
                        help='the path to the configuration file')

    return parser.parse_args()


def mark_caches(path_root: Path, caches: typing.List[typing.Union[str, Path]]):
    for cache in caches:
        dir_path = Path(path_root, cache)
        tag_path = dir_path / 'CACHEDIR.TAG'

        if tag_path.exists():
            contents = tag_path.open().read()
            assert contents.startswith(CACHE_TAG_STARTLINE)

        else:
            print('Marking {} as cache directory'.format(tag_path))
            with tag_path.open('w') as tag_file:
                tag_file.write(CACHE_TAG_CONTENTS)


def run_borg(action: str, config: dict):
    backup_directory = config['backup']['backup_directory']

    base_command = [
        # borg binary
        config['borg']['binary'],

        # what to do ("create", "prune", ...)
        action,

        # default flags
        '--progress',
        '--filter', 'AME',
        '--list',
        '--show-rc',
    ]

    excludes = []
    for exclude in config['backup'].get('excludes', []):
        excludes.append('--exclude')
        excludes.append(str(Path(backup_directory, exclude)))

    full_repo_name = '{}::{}'.format(config['backup']['repository'],
                                     config['backup']['name'])

    command = base_command + \
              config['borg'].get('flags', []) + \
              excludes + \
              [full_repo_name] + \
              [config['backup']['backup_directory']]

    print('Running borg: \'{}\''.format('\' \''.join(command)))

    proc = subprocess.Popen(command)
    proc.communicate()

    if proc.returncode != 0:
        print('ERROR: borg returned with status code {}'.format(proc.returncode))
        exit(proc.returncode)


def backup(config: dict):
    run_borg('create', config)


def prune(config: dict):
    raise NotImplementedError()


def run_single(config: dict):
    backup(config)
    prune(config)


def run_daemon(config: dict):
    while True:
        lasttime = get_time_of_last_backup()
        raise NotImplementedError()
        run_single()


def main():
    arguments = parse_argv()
    config = parse_config(Path(arguments.config))

    mark_caches(Path(config['backup']['backup_directory']),
                config.get('cachedirs', []))

    if arguments.operation == 'backup':
        backup(config)
    elif arguments.operation == 'prune':
        prune(config)
    elif arguments.operation == 'single':
        run_single(config)
    elif arguments.operation == 'daemon':
        run_daemon(config)
    else:
        assert False, arguments.operation


if __name__ == '__main__':
    main()
