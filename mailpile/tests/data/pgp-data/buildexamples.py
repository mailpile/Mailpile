from __future__ import print_function
import os
import email
import mailbox
from subprocess import Popen, PIPE

def getSourceFiles():
    return os.listdir("sources")
    
def getProcesses():
    return ["--armor --sign", "--armor --clearsign", "--recipient 0x5AB5B329 --armor --encrypt",
            "--sign", "--recipient 0x5AB5B329 --encrypt"]

def runPGP(input, params):
    print("Running PGP")
    params = params.split(" ")
    params.insert(0, "../gpg-keyring/")
    params.insert(0, "--home")
    params.insert(0, "gpg")
    pr = Popen(params, stdin=PIPE, stdout=PIPE)
    pr.stdin.write(input)
    pr.stdin.close()
    pr.wait()
    m = pr.stdout.read()
    return m

def genExamples():
    output = mailbox.mbox("output.mbox")
    for source in getSourceFiles():
	contents = open("sources/" + source, "r").read()
	language, charset = source.split(".")
        for process in getProcesses():
            print("Creating %s mail with %s encoding and %s PGP" % (language,
                  charset, process))
            string = runPGP(contents, process)
            e = email.message_from_string(string)
            e.set_charset(charset)
            e["from"] = "sender@test.mailpile.is"
            e["to"] = "recipient@test.mailpile.is"
            output.add(e)

    output.close()

if __name__ == "__main__":
    genExamples()
