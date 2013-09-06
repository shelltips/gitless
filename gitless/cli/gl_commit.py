# Gitless - a version control system built on top of Git.
# Copyright (c) 2013  Santiago Perez De Rosso.
# Licensed under GNU GPL, version 2.

"""gl commit - Record changes in the local repository."""


import os

from gitless.core import file as file_lib
from gitless.core import sync as sync_lib

import commit_dialog
import pprint


def parser(subparsers):
  """Adds the commit parser to the given subparsers object."""
  commit_parser = subparsers.add_parser(
      'commit', help='record changes in the local repository')
  commit_parser.add_argument(
      'only_files', nargs='*',
      help='only the files listed as arguments will be committed (files could '
           'be tracked or untracked files)')
  commit_parser.add_argument(
      '-exc', '--exclude', nargs='+',
      help=('files listed as arguments will be excluded from the commit (files '
            'must be tracked files)'),
      dest='exc_files')
  commit_parser.add_argument(
      '-inc', '--include', nargs='+',
      help=('files listed as arguments will be included to the commit (files '
            'must be untracked files)'),
      dest='inc_files')
  commit_parser.add_argument(
      '-m', '--message', help='Commit message', dest='m')
  commit_parser.set_defaults(func=main)


def main(args):
  # TODO(sperezde): re-think this worflow a bit.

  only_files = frozenset(args.only_files)
  exc_files = frozenset(args.exc_files) if args.exc_files else []
  inc_files = frozenset(args.inc_files) if args.inc_files else []

  if not _valid_input(only_files, exc_files, inc_files):
    return False

  commit_files = _compute_fs(only_files, exc_files, inc_files)

  if not commit_files:
    pprint.err('Commit aborted')
    pprint.err('No files to commit')
    return False

  msg = args.m
  if not msg:
    # Show the commit dialog.
    msg, commit_files = commit_dialog.show(commit_files)
    if not msg.strip() and not sync_lib.rebase_in_progress():
      pprint.err('Commit aborted')
      pprint.err('No commit message provided')
      return False
    if not commit_files:
      pprint.err('Commit aborted')
      pprint.err('No files to commit')
      return False
    if not _valid_input(commit_files, [], []):
      return False

  _auto_track(commit_files)
  ret, out = sync_lib.commit(commit_files, msg)
  if ret is sync_lib.SUCCESS:
    if out:
      pprint.msg(out)
  elif ret is sync_lib.UNRESOLVED_CONFLICTS:
    pprint.err('Commit aborted')
    pprint.err('You have unresolved conflicts:')
    pprint.err_exp(
        'use gl resolve <f> to mark file f as resolved once you fixed the '
        'conflicts')
    for f in out:
      pprint.err_item(f)
    return False
  elif ret is sync_lib.RESOLVED_FILES_NOT_IN_COMMIT:
    pprint.err('Commit aborted')
    pprint.err('You have resolved files that were not included in the commit:')
    pprint.err_exp('these must be part of the commit')
    for f in out:
      pprint.err_item(f)
    return False
  else:
    raise Exception('Unexpected return code %s' % ret)

  return True


def _valid_input(only_files, exc_files, inc_files):
  """Validates user input.

  This function will print to stdout in case user-provided values are invalid
  (and return False).

  Args:
    only_files: user-provided list of filenames to be committed only.
    exc_files: list of filenames to be excluded from commit.
    inc_files: list of filenames to be included to the commit.

  Returns:
    True if the input is valid, False if otherwise.
  """
  if only_files and (exc_files or inc_files):
    pprint.err('Commit aborted')
    pprint.err(
        'You provided a list of filenames to be committed only but also '
        'provided a list of files to be excluded or included.')
    return False

  ret = True
  err = []
  for fp in only_files:
    if not os.path.exists(fp) and not file_lib.is_deleted(fp):
      err.append('File %s doesn\'t exist' % fp)
      ret = False
    elif file_lib.is_tracked(fp) and not file_lib.is_tracked_modified(fp):
      err.append(
          'File %s is a tracked file but has no modifications' % fp)
      ret = False

  for fp in exc_files:
    # We check that the files to be excluded are existing tracked files.
    if not os.path.exists(fp) and not file_lib.is_deleted(fp):
      err.append('File %s doesn\'t exist' % fp)
      ret = False
    elif not file_lib.is_tracked(fp):
      err.append(
          'File %s, listed to be excluded from commit, is not a tracked file' %
          fp)
      ret = False
    elif not file_lib.is_tracked_modified(fp):
      err.append(
          'File %s, listed to be excluded from commit, is a tracked file but '
          'has no modifications' % fp)
      ret = False
    elif file_lib.is_resolved_file(fp):
      err.append('You can\'t exclude a file that has been resolved')
      ret = False

  for fp in inc_files:
    # We check that the files to be included are existing untracked files.
    if not os.path.exists(fp) and not file_lib.is_deleted(fp):
      err.append('File %s doesn\'t exist' % fp)
      ret = False
    elif file_lib.is_tracked(fp):
      err.append(
          'File %s, listed to be included in the commit, is not a untracked '
          'file' % fp)
      ret = False

  if not ret:
    # Some error occured.
    pprint.err('Commit aborted')
    for e in err:
      pprint.err(e)

  return ret


def _compute_fs(only_files, exc_files, inc_files):
  """Compute the final fileset to commit.

  Args:
    only_files: list of filenames to be committed only.
    exc_files: list of filenames to be excluded from commit.
    inc_files: list of filenames to be included to the commit.

  Returns:
    A list of filenames to be committed.
  """
  if only_files:
    ret = only_files
  else:
    tracked_modified, unused_untracked = file_lib.status_all()
    # TODO(sperezde): push the use of frozenset to the library.
    ret = frozenset(tm[0] for tm in tracked_modified)
    # TODO(sperezde): the following is a mega-hack, do it right.
    from gitpylib import common
    ret = ret.difference(common.real_case(exc_f) for exc_f in exc_files)
    ret = ret.union(common.real_case(inc_f) for inc_f in inc_files)

  return ret


def _auto_track(files):
  """Tracks those untracked files in the list."""
  for f in files:
    if not file_lib.is_tracked(f):
      file_lib.track(f)