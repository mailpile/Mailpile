#!/bin/bash
#
# This script updates our repositories and syncs to the public site.
#
(
  export LANG=C
  export LC_ALL=C
  set -x
  set -e

  cd ~/incoming
  for repo in *; do
    if [ "$(find $repo -name '*.deb'|wc -l)" != 0 ]; then
      reprepro -b ../deb includedeb $repo $repo/*deb
      rm -f $repo/*deb
    fi
  done

  cd ~/deb
  sha256sum $(find pool -name '*.deb') >.sha256sums.txt.new
  diff .sha256sums.txt.new sha256sums.txt >/dev/null || {
    cp .sha256sums.txt.new sha256sums.txt
    echo '{' > .packages.json.new
    cat sha256sums.txt |while read SUM FN; do
      if [ "$(basename $FN |grep -c dev)" = 1 ]; then
        R=nightly
      else
        R=release
      fi
      echo "  \"$(basename $FN)\": {"               >> .packages.json.new
      echo "    \"repo\": \"$R\","                  >> .packages.json.new
      echo "    \"package\": \"$(basename $FN |cut -f1 -d_)\"," \
	                                            >> .packages.json.new
      echo "    \"path\": \"$FN\","                 >> .packages.json.new
      echo "    \"sha256\": \"$SUM\","              >> .packages.json.new
      echo "    \"mtime\": \"$(stat -c %Y $FN)\","  >> .packages.json.new
      echo "    \"size\": \"$(ls -hs $FN |cut -f1 -d\ )\"}," \
                                                    >> .packages.json.new
    done
    echo '"EOF": 1}' >> .packages.json.new
    mv -f .packages.json.new packages.json
  }
  rm -f .sha256sums.txt.new

  cd
  rsync -prvac --delete deb packages@mailpile.is:www/
)\
  > ~/update-repos.log 2>&1
