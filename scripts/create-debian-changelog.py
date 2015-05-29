#!/usr/bin/env python2
#This script builds a DCH changelog from the git commit log
from subprocess import check_output, call
from multiprocessing import Pool
import os

def getLogMessage(commitSHA):
    """Get the log message for a given commit hash"""
    output = check_output(["git","log","--format=%B","-n","1",commitSHA])
    return output.strip()

def versionFromCommitNo(commitNo):
    """Generate a version string from a numerical commit no"""
    return "0.0.0-dev%d" % commitNo

#Execute git rev-list $(git rev-parse HEAD) to get list of revisions
head = check_output(["git","rev-parse","HEAD"]).strip()
revisions = check_output(["git","rev-list",head]).strip().split("\n")
#Revisions now contains rev identifiers, newest revisions first.
print "Found %d revisions" % len(revisions)
revisions.reverse() #In-place reverse, to make oldest revision first
#Map the revisions to their log msgs
print "Mapping revisions to log messages"
threadpool = p = Pool(10)
revLogMsgs = threadpool.map(getLogMessage, revisions)
#(Re)create the changelog for the first revision (= the oldest one)
try:
    os.unlink("debian/changelog")
except OSError:
    pass #Don't care if the file does not exist
firstCommitMsg = revLogMsgs[0]
call(["dch","--create","-v",versionFromCommitNo(0),"--package","mailpile",firstCommitMsg])
#Create the changelog entry for all other commits
for i in range(1, len(revisions)):
    print "Generating changelog for revision %d" % i
    commitMsg = revLogMsgs[i]
    call(["dch","-v",versionFromCommitNo(i),"--package","mailpile",commitMsg])
